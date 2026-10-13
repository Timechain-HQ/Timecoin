"""Testnet chain: state transition, fork choice, and block sealing.

Network name is ``timecoin-testnet``. Genesis is domain-separated from any
future mainnet. There is no peer-to-peer layer and no mainnet parameters.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from timecoin.codec import canonical, merkle, shake
from timecoin.pq import sign, verify
from timecoin.tx import (
    Call,
    Deploy,
    Output,
    Spend,
    Tx,
    TxError,
    execution_waves,
    nullifier,
)
from timecoin.vm import Instruction, VmError, run

NETWORK = "timecoin-testnet"
CHAIN_ID = "timecoin-testnet-1"
GENESIS_DOMAIN = b"timecoin-testnet.genesis.v1"
BASE_UNITS = 10**8
REWARD = 50 * BASE_UNITS
SLOT_TARGET_SECONDS = 600
MAX_UNCLES = 2
MAX_CODE = 256
MAX_GAS = 10_000


class ChainError(Exception):
    """A block or transaction breaks the testnet rules."""


@dataclass
class ContractAccount:
    code: list[Instruction]
    cap_pub: bytes
    balance: int
    storage: dict[int, int]


@dataclass
class State:
    notes: dict[bytes, Output] = field(default_factory=dict)
    nullifiers: set[bytes] = field(default_factory=set)
    contracts: dict[bytes, ContractAccount] = field(default_factory=dict)
    supply: int = 0

    def clone(self) -> State:
        return State(
            notes=dict(self.notes),
            nullifiers=set(self.nullifiers),
            contracts={
                contract_id: ContractAccount(
                    list(account.code),
                    account.cap_pub,
                    account.balance,
                    dict(account.storage),
                )
                for contract_id, account in self.contracts.items()
            },
            supply=self.supply,
        )


def audit(state: State) -> int:
    """Sum of unspent notes and contract balances. Must equal ``state.supply``."""
    notes = sum(output.value for output in state.notes.values())
    locked = sum(account.balance for account in state.contracts.values())
    return notes + locked


def state_root(state: State) -> bytes:
    leaves: list[bytes] = []
    for commitment, output in sorted(state.notes.items(), key=lambda item: item[0]):
        leaves.append(shake(b"n" + commitment + output.value.to_bytes(16, "big")))
    for spent in sorted(state.nullifiers):
        leaves.append(shake(b"z" + spent))
    for contract_id, account in sorted(state.contracts.items(), key=lambda item: item[0]):
        blob = canonical(
            {
                "balance": account.balance,
                "cap_pub": account.cap_pub.hex(),
                "code": [[op, arg] for op, arg in _code_pairs(account.code)],
                "storage": {str(key): value for key, value in sorted(account.storage.items())},
            }
        )
        leaves.append(shake(b"c" + contract_id + blob))
    return merkle(leaves)


@dataclass
class Block:
    parent: bytes
    height: int
    slot: int
    txs: list[Tx]
    uncles: list[bytes]
    coinbase: Output | None
    proposer_pub: bytes
    state_root: bytes
    signature: bytes

    def signing_bytes(self) -> bytes:
        return b"timecoin.block.v1" + canonical(
            {
                "network": NETWORK,
                "chain_id": CHAIN_ID,
                "parent": self.parent.hex(),
                "height": self.height,
                "slot": self.slot,
                "txs": [tx.to_dict(sigs=True) for tx in self.txs],
                "uncles": [uncle.hex() for uncle in self.uncles],
                "coinbase": None if self.coinbase is None else self.coinbase.to_dict(),
                "proposer_pub": self.proposer_pub.hex(),
                "state_root": self.state_root.hex(),
            }
        )

    def block_id(self) -> bytes:
        return shake(b"timecoin.blockid.v1" + self.signing_bytes() + self.signature)


class Chain:
    """A single local testnet node. All blocks it stores were checked locally."""

    def __init__(self) -> None:
        genesis_state = State()
        genesis = Block(
            parent=shake(GENESIS_DOMAIN),
            height=0,
            slot=0,
            txs=[],
            uncles=[],
            coinbase=None,
            proposer_pub=b"",
            state_root=state_root(genesis_state),
            signature=b"",
        )
        self.blocks: dict[bytes, Block] = {genesis.block_id(): genesis}
        self.states: dict[bytes, State] = {genesis.block_id(): genesis_state}
        self.genesis_id = genesis.block_id()

    def head(self) -> bytes:
        tips = self.tips()

        def rank(block_id: bytes) -> tuple[int, int]:
            block = self.blocks[block_id]
            # Greater height wins. Equal height: the smaller block id wins.
            return (block.height, -int.from_bytes(block_id, "big"))

        return max(tips, key=rank)

    def tips(self) -> list[bytes]:
        parents = {block.parent for block in self.blocks.values()}
        return [block_id for block_id in self.blocks if block_id not in parents]

    def add(self, block: Block) -> bytes:
        block_id = block.block_id()
        if block_id in self.blocks:
            raise ChainError("duplicate block")
        if block.parent not in self.blocks:
            raise ChainError("unknown parent")
        parent = self.blocks[block.parent]
        if block.height != parent.height + 1:
            raise ChainError("height")
        if block.slot <= parent.slot:
            raise ChainError("slot")
        if block.coinbase is None or not block.proposer_pub or not block.signature:
            raise ChainError("missing seal")
        if len(block.uncles) > MAX_UNCLES:
            raise ChainError("too many uncles")
        if len(set(block.uncles)) != len(block.uncles):
            raise ChainError("duplicate uncle")
        parent_of_parent = parent.parent
        for uncle_id in block.uncles:
            if uncle_id not in self.blocks or uncle_id == block.parent:
                raise ChainError("unknown uncle")
            uncle = self.blocks[uncle_id]
            # A later block names a loser that shared its parent's parent.
            if uncle.parent != parent_of_parent or uncle.height != parent.height:
                raise ChainError("uncle is not a competing sibling")
        if not verify(block.proposer_pub, block.signing_bytes(), block.signature):
            raise ChainError("bad block signature")
        result = execute(self.states[block.parent], block.txs, block.coinbase)
        if state_root(result) != block.state_root:
            raise ChainError("state root")
        self.blocks[block_id] = block
        self.states[block_id] = result
        return block_id

    def seal(
        self,
        parent: bytes,
        slot: int,
        txs: list[Tx],
        proposer_private: bytes,
        proposer_pub: bytes,
        coinbase: Output,
        uncles: list[bytes] | None = None,
    ) -> Block:
        """Build a signed block from ``parent`` without inserting it."""
        if parent not in self.states:
            raise ChainError("unknown parent")
        result = execute(self.states[parent], txs, coinbase)
        parent_block = self.blocks[parent]
        block = Block(
            parent=parent,
            height=parent_block.height + 1,
            slot=slot,
            txs=list(txs),
            uncles=list(uncles or []),
            coinbase=coinbase,
            proposer_pub=proposer_pub,
            state_root=state_root(result),
            signature=b"",
        )
        block.signature = sign(proposer_private, block.signing_bytes())
        return block


def contract_id_of(tx: Tx) -> bytes:
    return shake(b"timecoin.contract.v1" + tx.sighash())


def execute(state: State, txs: list[Tx], coinbase: Output | None) -> State:
    """Apply transactions in order, then the coinbase, and check supply."""
    result = state.clone()
    fees = 0
    for tx in txs:
        result = apply_tx(result, tx)
        fees += tx.fee
    if coinbase is None:
        if txs or fees:
            raise ChainError("open block")
        return result
    if coinbase.value != REWARD + fees:
        raise ChainError("coinbase value")
    _insert(result, coinbase)
    result.supply += REWARD
    if audit(result) != result.supply:
        raise ChainError("supply invariant")
    return result


def apply_tx(state: State, tx: Tx) -> State:
    """Return a new state with one transaction applied. ``state`` is not mutated."""
    result = state.clone()
    _check_shape(tx)
    digest = tx.sighash()
    input_total = 0
    for spend in tx.inputs:
        input_total += _take_note(result, spend, digest)
    output_total = 0
    for output in tx.outputs:
        _check_value(output.value)
        output_total += output.value
        _insert(result, output)
    if tx.kind == "transfer":
        if input_total != output_total + tx.fee:
            raise ChainError("conservation")
    elif tx.kind == "deploy":
        assert tx.deploy is not None
        endowment = input_total - output_total - tx.fee
        if endowment < 0:
            raise ChainError("conservation")
        if not verify(tx.deploy.cap_pub, digest, tx.deploy.cap_signature):
            raise ChainError("capability signature")
        contract_id = contract_id_of(tx)
        if contract_id in result.contracts:
            raise ChainError("contract exists")
        result.contracts[contract_id] = ContractAccount(
            list(tx.deploy.code), tx.deploy.cap_pub, endowment, {}
        )
    elif tx.kind == "call":
        assert tx.call is not None
        _apply_call(result, tx.call, digest, input_total, output_total, tx.fee)
    else:
        raise ChainError("kind")
    return result


def _apply_call(
    state: State,
    call: Call,
    digest: bytes,
    input_total: int,
    output_total: int,
    fee: int,
) -> None:
    account = state.contracts.get(call.contract_id)
    if account is None:
        raise ChainError("unknown contract")
    if not verify(account.cap_pub, digest, call.cap_signature):
        raise ChainError("capability signature")
    if call.callvalue < 0:
        raise ChainError("callvalue")
    try:
        storage, payout, _gas = run(
            account.code,
            account.storage,
            call.args,
            call.callvalue,
            MAX_GAS,
        )
    except VmError as exc:
        raise ChainError(f"contract reverted: {exc}") from exc
    if input_total != output_total + fee + call.callvalue - payout:
        raise ChainError("conservation")
    balance = account.balance + call.callvalue - payout
    if balance < 0:
        raise ChainError("contract balance")
    account.storage = storage
    account.balance = balance


def _take_note(state: State, spend: Spend, digest: bytes) -> int:
    output = spend.output
    commitment = output.commitment()
    current = state.notes.get(commitment)
    if current is None or current != output:
        raise ChainError("unknown note")
    spent = nullifier(output.onetime_pub, output.rho)
    if spent in state.nullifiers:
        raise ChainError("double spend")
    if not verify(output.onetime_pub, digest, spend.signature):
        raise ChainError("note signature")
    del state.notes[commitment]
    state.nullifiers.add(spent)
    return output.value


def _insert(state: State, output: Output) -> None:
    _check_value(output.value)
    if len(output.rho) != 32:
        raise ChainError("rho")
    commitment = output.commitment()
    if commitment in state.notes:
        raise ChainError("duplicate note")
    state.notes[commitment] = output


def _check_shape(tx: Tx) -> None:
    if tx.fee < 0:
        raise ChainError("fee")
    if tx.kind == "transfer":
        if tx.deploy is not None or tx.call is not None or not tx.inputs:
            raise ChainError("transfer shape")
    elif tx.kind == "deploy":
        if tx.deploy is None or tx.call is not None:
            raise ChainError("deploy shape")
        if len(tx.deploy.code) == 0 or len(tx.deploy.code) > MAX_CODE:
            raise ChainError("code size")
    elif tx.kind == "call":
        if tx.call is None or tx.deploy is not None:
            raise ChainError("call shape")
    else:
        raise ChainError("kind")


def _check_value(value: int) -> None:
    if value < 0 or value >= 2**64:
        raise TxError("value out of range")


def _code_pairs(code: list[Instruction]) -> list[tuple[str, int | None]]:
    pairs: list[tuple[str, int | None]] = []
    for instruction in code:
        if len(instruction) == 1:
            pairs.append((instruction[0], None))
        else:
            pairs.append((instruction[0], instruction[1]))
    return pairs

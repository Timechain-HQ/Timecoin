"""Run a scripted Timecoin testnet session.

Usage:
    python3 -m timecoin.cli demo
"""

from __future__ import annotations

import sys

from timecoin import __version__
from timecoin.chain import (
    NETWORK,
    REWARD,
    SLOT_TARGET_SECONDS,
    Chain,
    contract_id_of,
)
from timecoin.pq import ML_DSA, ML_KEM, generate
from timecoin.tx import create_output, deployment, invocation, open_output
from timecoin.vm import VAULT
from timecoin.wallet import Wallet, format_time


def demo() -> None:
    print(f"Timecoin {__version__}  network={NETWORK}")
    print("Status: testnet. Full testnet functions below. Not mainnet.")
    print(f"Signatures: {ML_DSA}. Note encryption: {ML_KEM}.")
    print(f"Slot target: {SLOT_TARGET_SECONDS}s. Block reward: {format_time(REWARD)}.")
    print("Amounts are public. Memos and long-term view keys are not.")
    print()

    chain = Chain()
    miner_private, miner_public = generate(ML_DSA)
    alice = Wallet.create("alice")
    bob = Wallet.create("bob")
    carol = Wallet.create("carol")

    first = _mine(chain, miner_private, miner_public, alice.view_pub, 1, [])
    print(f"block 1  {first.hex()}  coinbase {format_time(REWARD)} -> alice")
    print(f"alice balance {format_time(alice.balance(chain.states[chain.head()]))}")

    payment = alice.pay(
        chain.states[chain.head()],
        bob.view_pub,
        20 * 10**8,
        b"testnet memo for bob",
    )
    second = _mine(chain, miner_private, miner_public, alice.view_pub, 2, [payment])
    bob_notes = bob.scan(chain.states[chain.head()])
    print(f"block 2  {second.hex()}  alice paid bob 20 TIME")
    print(f"bob memo: {bob_notes[0][2]!r}")
    print(f"carol can open bob's note: {open_output(bob_notes[0][0], carol.view_private) is not None}")

    sweep = bob.pay(
        chain.states[chain.head()],
        bob.view_pub,
        bob.balance(chain.states[chain.head()]),
        b"sweep",
    )
    _mine(chain, miner_private, miner_public, alice.view_pub, 3, [sweep])
    swept = bob.scan(chain.states[chain.head()])
    hidden = all(open_output(note, alice.view_private) is None for note, _k, _m in swept)
    print(f"bob swept his note. alice can open the swept note: {not hidden}")

    deploy_tx = deployment(alice.cap_private, alice.cap_pub, VAULT, [], [])
    contract_id = contract_id_of(deploy_tx)
    _mine(chain, miner_private, miner_public, alice.view_pub, 4, [deploy_tx])
    deposit_tx = _deposit(alice, chain.states[chain.head()], contract_id, 10 * 10**8)
    _mine(chain, miner_private, miner_public, alice.view_pub, 5, [deposit_tx])
    account = chain.states[chain.head()].contracts[contract_id]
    print(f"vault {contract_id.hex()[:16]} balance {format_time(account.balance)}")

    payout, payout_key = create_output(bob.view_pub, 4 * 10**8, b"vault payout")
    withdraw_tx = invocation(
        alice.cap_private,
        contract_id,
        [2, 4 * 10**8],
        0,
        [],
        [payout],
    )
    _mine(chain, miner_private, miner_public, alice.view_pub, 6, [withdraw_tx])
    print(
        "vault after withdraw",
        format_time(chain.states[chain.head()].contracts[contract_id].balance),
    )
    print(f"bob can open the payout: {open_output(payout, bob.view_private) is not None}")
    del payout_key

    print(
        f"head height {chain.blocks[chain.head()].height}  "
        f"supply {format_time(chain.states[chain.head()].supply)}"
    )
    print("testnet session finished")


def _deposit(alice: Wallet, state, contract_id: bytes, amount: int):
    notes = alice.scan(state)
    output, spend_key, _memo = max(notes, key=lambda item: item[0].value)
    if output.value <= amount:
        raise RuntimeError("demo note is too small to leave change")
    change = create_output(alice.view_pub, output.value - amount, b"change")[0]
    return invocation(
        alice.cap_private,
        contract_id,
        [1, amount],
        amount,
        [(output, spend_key)],
        [change],
    )


def _mine(chain: Chain, private: bytes, public: bytes, view_pub: bytes, slot: int, txs: list):
    parent = chain.head()
    fees = sum(tx.fee for tx in txs)
    coinbase, _key = create_output(view_pub, REWARD + fees, b"coinbase")
    block = chain.seal(parent, slot, txs, private, public, coinbase)
    chain.add(block)
    return block.block_id()


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "demo":
        demo()
        return
    print("Usage: python3 -m timecoin.cli demo", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()

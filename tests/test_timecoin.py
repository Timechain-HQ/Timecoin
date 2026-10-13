"""Testnet rules: money, stealth, contracts, parallelism, and fork choice."""

from __future__ import annotations

import unittest

from timecoin.chain import (
    NETWORK,
    REWARD,
    Chain,
    ChainError,
    audit,
    contract_id_of,
)
from timecoin.pq import ML_DSA, generate
from timecoin.tx import (
    create_output,
    execution_waves,
    invocation,
    open_output,
    transfer,
)
from timecoin.tx import deployment
from timecoin.vm import VAULT, VmError, run
from timecoin.wallet import Wallet

BASE = 10**8


class VmTests(unittest.TestCase):
    def test_vault_deposit_and_withdraw(self) -> None:
        storage, payout, _gas = run(VAULT, {}, [1, 100], 100)
        self.assertEqual(payout, 0)
        self.assertEqual(storage[0], 100)
        storage, payout, _gas = run(VAULT, storage, [2, 40], 0)
        self.assertEqual(payout, 40)
        self.assertEqual(storage[0], 60)

    def test_vault_rejects_unknown_action(self) -> None:
        with self.assertRaises(VmError):
            run(VAULT, {0: 10}, [9, 1], 0)

    def test_out_of_gas(self) -> None:
        with self.assertRaises(VmError):
            run(VAULT, {}, [1, 1], 1, gas_limit=3)


class ChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.miner_private, cls.miner_public = generate(ML_DSA)
        cls.alice = Wallet.create("alice")
        cls.bob = Wallet.create("bob")
        cls.carol = Wallet.create("carol")

    def test_genesis_is_an_empty_testnet(self) -> None:
        chain = Chain()
        state = chain.states[chain.genesis_id]
        self.assertEqual(NETWORK, "timecoin-testnet")
        self.assertNotIn("mainnet", NETWORK)
        self.assertEqual(state.supply, 0)
        self.assertEqual(audit(state), 0)
        self.assertIn(b"timecoin-testnet", chain.blocks[chain.genesis_id].signing_bytes())

    def test_coinbase_scan_privacy_and_sweep(self) -> None:
        chain = self._funded()
        self.assertEqual(chain.states[chain.head()].supply, REWARD)
        self.assertEqual(self.alice.balance(chain.states[chain.head()]), REWARD)
        self.assertEqual(self.bob.balance(chain.states[chain.head()]), 0)

        payment = self.alice.pay(
            chain.states[chain.head()], self.bob.view_pub, 20 * BASE, b"for bob"
        )
        block = self._mine(chain, 2, [payment], self.alice.view_pub)
        self.assertNotIn(self.bob.view_pub, block.signing_bytes())
        opened = self.bob.scan(chain.states[chain.head()])
        self.assertEqual(opened[0][2], b"for bob")
        self.assertIsNone(open_output(opened[0][0], self.carol.view_private))
        self.assertIsNone(open_output(opened[0][0], self.alice.view_private))

        sweep = self.bob.pay(
            chain.states[chain.head()],
            self.bob.view_pub,
            self.bob.balance(chain.states[chain.head()]),
            b"sweep",
        )
        self._mine(chain, 3, [sweep], self.alice.view_pub)
        for note, _key, _memo in self.bob.scan(chain.states[chain.head()]):
            self.assertIsNone(open_output(note, self.alice.view_private))
        self.assertEqual(audit(chain.states[chain.head()]), chain.states[chain.head()].supply)

    def test_double_spend_and_inflation_fail(self) -> None:
        chain = self._funded()
        note, spend_key, _memo = self.alice.scan(chain.states[chain.head()])[0]
        change = note.value - 10 * BASE
        payment = transfer(
            [(note, spend_key)],
            [
                create_output(self.bob.view_pub, 10 * BASE, b"once")[0],
                create_output(self.alice.view_pub, change, b"change")[0],
            ],
        )
        self._mine(chain, 2, [payment], self.alice.view_pub)
        with self.assertRaises(ChainError):
            self._mine(chain, 3, [payment], self.alice.view_pub)

        fresh = self._funded()
        live, live_key, _memo = self.alice.scan(fresh.states[fresh.head()])[0]
        inflated = transfer(
            [(live, live_key)],
            [create_output(self.bob.view_pub, live.value + 1, b"inflate")[0]],
        )
        with self.assertRaises(ChainError) as inflated_error:
            self._mine(fresh, 2, [inflated], self.alice.view_pub)
        self.assertIn("conservation", str(inflated_error.exception))

    def test_fee_is_not_new_supply(self) -> None:
        chain = self._funded()
        note, spend_key, _memo = self.alice.scan(chain.states[chain.head()])[0]
        fee = 1000
        payment = transfer(
            [(note, spend_key)],
            [create_output(self.bob.view_pub, note.value - fee, b"fee")[0]],
            fee,
        )
        self._mine(chain, 2, [payment], self.carol.view_pub)
        state = chain.states[chain.head()]
        self.assertEqual(state.supply, REWARD * 2)
        self.assertEqual(audit(state), state.supply)
        self.assertEqual(self.carol.balance(state), REWARD + fee)

    def test_vault_deposit_withdraw_and_capability(self) -> None:
        chain = self._funded()
        deploy_tx = deployment(
            self.alice.cap_private, self.alice.cap_pub, VAULT, [], []
        )
        contract_id = contract_id_of(deploy_tx)
        self._mine(chain, 2, [deploy_tx], self.alice.view_pub)

        note, spend_key, _memo = self._largest(chain)
        deposit_value = 10 * BASE
        change = create_output(
            self.alice.view_pub, note.value - deposit_value, b"change"
        )[0]
        deposit_tx = invocation(
            self.alice.cap_private,
            contract_id,
            [1, deposit_value],
            deposit_value,
            [(note, spend_key)],
            [change],
        )
        self._mine(chain, 3, [deposit_tx], self.alice.view_pub)
        account = chain.states[chain.head()].contracts[contract_id]
        self.assertEqual(account.balance, deposit_value)
        self.assertEqual(account.storage[0], deposit_value)

        payout = create_output(self.bob.view_pub, 4 * BASE, b"released")[0]
        withdraw_tx = invocation(
            self.alice.cap_private,
            contract_id,
            [2, 4 * BASE],
            0,
            [],
            [payout],
        )
        self._mine(chain, 4, [withdraw_tx], self.alice.view_pub)
        account = chain.states[chain.head()].contracts[contract_id]
        self.assertEqual(account.balance, 6 * BASE)
        self.assertEqual(account.storage[0], 6 * BASE)
        self.assertIsNotNone(open_output(payout, self.bob.view_private))

        stolen = invocation(
            self.carol.cap_private,
            contract_id,
            [2, BASE],
            0,
            [],
            [create_output(self.carol.view_pub, BASE, b"no")[0]],
        )
        with self.assertRaises(ChainError):
            self._mine(chain, 5, [stolen], self.alice.view_pub)
        overdraw = invocation(
            self.alice.cap_private,
            contract_id,
            [2, 7 * BASE],
            0,
            [],
            [create_output(self.alice.view_pub, 7 * BASE, b"too much")[0]],
        )
        with self.assertRaises(ChainError):
            self._mine(chain, 5, [overdraw], self.alice.view_pub)

    def test_independent_transactions_commute(self) -> None:
        chain = self._funded()
        note, spend_key, _memo = self.alice.scan(chain.states[chain.head()])[0]
        first, first_key = create_output(self.alice.view_pub, 10 * BASE, b"one")
        second, second_key = create_output(self.alice.view_pub, 12 * BASE, b"two")
        rest = create_output(
            self.alice.view_pub, note.value - 22 * BASE, b"rest"
        )[0]
        split = transfer([(note, spend_key)], [first, second, rest])
        self._mine(chain, 2, [split], self.alice.view_pub)

        to_bob = transfer(
            [(first, first_key)],
            [create_output(self.bob.view_pub, 10 * BASE, b"bob")[0]],
        )
        to_carol = transfer(
            [(second, second_key)],
            [create_output(self.carol.view_pub, 12 * BASE, b"carol")[0]],
        )
        self.assertEqual(len(execution_waves([to_bob, to_carol])), 1)
        parent = chain.states[chain.head()]
        forward = transfer_root(parent, [to_bob, to_carol])
        backward = transfer_root(parent, [to_carol, to_bob])
        self.assertEqual(forward, backward)

        child, child_key = create_output(self.bob.view_pub, 10 * BASE, b"child")
        parent_tx = transfer([(first, first_key)], [child])
        follow = transfer(
            [(child, child_key)],
            [create_output(self.carol.view_pub, 10 * BASE, b"follow")[0]],
        )
        self.assertEqual(len(execution_waves([parent_tx, follow])), 2)
        with self.assertRaises(ChainError):
            transfer_root(parent, [follow])

    def test_fork_choice_and_uncle(self) -> None:
        chain = Chain()
        left = self._mine(chain, 1, [], self.alice.view_pub, parent=chain.genesis_id)
        right = self._mine(chain, 1, [], self.bob.view_pub, parent=chain.genesis_id)
        smaller = min(left.block_id(), right.block_id(), key=lambda item: int.from_bytes(item, "big"))
        larger = right.block_id() if smaller == left.block_id() else left.block_id()
        self.assertEqual(chain.head(), smaller)

        extension = self._mine(
            chain,
            2,
            [],
            self.carol.view_pub,
            parent=larger,
            uncles=[smaller],
        )
        self.assertEqual(chain.head(), extension.block_id())
        self.assertEqual(chain.blocks[extension.block_id()].uncles, [smaller])
        canonical = chain.states[extension.block_id()]
        # The cited uncle paid the other wallet and must not enter this state.
        if larger == left.block_id():
            self.assertEqual(self.bob.balance(canonical), 0)
            self.assertGreater(self.alice.balance(canonical), 0)
        else:
            self.assertEqual(self.alice.balance(canonical), 0)
            self.assertGreater(self.bob.balance(canonical), 0)
        self.assertEqual(audit(canonical), canonical.supply)
        self.assertEqual(canonical.supply, REWARD * 2)

    def test_slot_must_advance(self) -> None:
        chain = self._funded()
        coinbase = create_output(self.alice.view_pub, REWARD, b"again")[0]
        block = chain.seal(
            chain.head(), 1, [], self.miner_private, self.miner_public, coinbase
        )
        with self.assertRaises(ChainError):
            chain.add(block)

    def _funded(self) -> Chain:
        chain = Chain()
        self._mine(chain, 1, [], self.alice.view_pub)
        return chain

    def _largest(self, chain: Chain):
        notes = self.alice.scan(chain.states[chain.head()])
        return max(notes, key=lambda item: item[0].value)

    def _mine(self, chain, slot, txs, view_pub, parent=None, uncles=None):
        parent_id = chain.head() if parent is None else parent
        fees = sum(tx.fee for tx in txs)
        coinbase = create_output(view_pub, REWARD + fees, b"coinbase")[0]
        block = chain.seal(
            parent_id,
            slot,
            txs,
            self.miner_private,
            self.miner_public,
            coinbase,
            uncles,
        )
        chain.add(block)
        return block


def transfer_root(state, txs):
    from timecoin.chain import apply_tx, state_root

    result = state.clone()
    for tx in txs:
        result = apply_tx(result, tx)
    return state_root(result)

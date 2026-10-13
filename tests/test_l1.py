"""Block relay, the mempool, the store, and the measured chart run."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from timecoin.chain import REWARD, Chain
from timecoin.measure import run_measured_chain
from timecoin.mempool import Mempool
from timecoin.metrics import canonical
from timecoin.node import propose
from timecoin.pngchart import line_chart
from timecoin.pq import ML_DSA, generate
from timecoin.store import load_chain, save_chain
from timecoin.vm import VAULT, Step, run
from timecoin.wallet import Wallet
from timecoin.wallet import format_time
from timecoin.wire import decode_block, encode_block

BASE = 10**8


class Layer1Tests(unittest.TestCase):
    def test_block_moves_to_a_second_node_and_survives_a_restart(self) -> None:
        miner_private, miner_public = generate(ML_DSA)
        alice = Wallet.create("alice")
        bob = Wallet.create("bob")
        chain = Chain()
        pool = Mempool()
        first = propose(chain, pool, 600, miner_private, miner_public, alice.view_pub)
        payment = alice.pay(chain.states[chain.head()], bob.view_pub, 5 * BASE, b"relay", fee=25)
        pool.submit(chain.states[chain.head()], payment)
        propose(chain, pool, 1200, miner_private, miner_public, alice.view_pub)
        self.assertEqual(pool.txs, [])

        other = Chain()
        for block_id in (first, chain.head()):
            other.add(decode_block(encode_block(chain.blocks[block_id])))
        self.assertEqual(other.states[other.head()].supply, REWARD * 2)
        self.assertEqual(bob.balance(other.states[other.head()]), 5 * BASE)
        self.assertEqual(
            other.blocks[other.head()].state_root,
            chain.blocks[chain.head()].state_root,
        )

        with tempfile.TemporaryDirectory() as directory:
            save_chain(chain, directory)
            loaded = load_chain(directory)
        self.assertEqual(loaded.states[loaded.head()].supply, chain.states[chain.head()].supply)
        self.assertEqual(canonical(loaded)[-1].fees, 25)

    def test_measured_run_matches_the_issuance_rule(self) -> None:
        measured = run_measured_chain()
        points = measured["points"]
        for point in points:
            self.assertEqual(point.supply, point.height * REWARD)
            self.assertEqual(point.note_value + point.locked, point.supply)
        self.assertEqual(points[3].fees, 1000)
        self.assertEqual(measured["commuting_waves"], [2])
        self.assertEqual(measured["dependent_waves"], [1, 1])
        self.assertEqual(measured["duplicate_rejected"], 1)
        self.assertEqual(measured["inflation_rejected"], 1)
        self.assertEqual(measured["locked_final"], 6 * BASE)
        self.assertEqual(points[-1].height, 6)
        self.assertEqual(format_time(REWARD), "50 TIC")

    def test_vault_trace_and_png_header(self) -> None:
        steps: list[Step] = []
        _storage, payout, gas = run(VAULT, {}, [1, 100], 100, steps=steps)
        self.assertEqual(payout, 0)
        self.assertEqual(gas, steps[-1].gas_used)
        self.assertGreater(gas, len(steps))
        self.assertEqual(steps[0].op, "ARG")
        quiet: list[Step] = []
        run([("PUSH", 0), ("JUMPI", 0), ("STOP",)], {}, [], 0, steps=quiet)
        self.assertEqual([step.op for step in quiet], ["PUSH", "JUMPI", "STOP"])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "supply.png"
            line_chart(target, "Supply", "height", "TIC", [("supply", [(0, 0), (1, 50), (2, 100)])])
            self.assertEqual(target.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

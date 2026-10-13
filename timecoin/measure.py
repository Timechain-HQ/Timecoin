"""Build one measured testnet run and write its charts.

The pictures in ``docs/charts`` come from this module. Re-run it with
``python3 -m timecoin.cli charts``.
"""

from __future__ import annotations

from pathlib import Path

from timecoin.chain import REWARD, SLOT_TARGET_SECONDS, TICKER, Chain, audit, contract_id_of
from timecoin.mempool import Mempool
from timecoin.metrics import Point, canonical
from timecoin.node import propose
from timecoin.pngchart import bar_chart, composition_chart, fork_chart, line_chart, stacked_bar
from timecoin.pq import ML_DSA, generate
from timecoin.tx import create_output, deployment, execution_waves, invocation, transfer
from timecoin.vm import VAULT, Step, run
from timecoin.wallet import Wallet

BASE = 10**8


def write_charts(directory: str | Path) -> dict[str, object]:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    measured = run_measured_chain()
    points: list[Point] = measured["points"]
    _supply(path, points)
    _notes(path, points)
    _locked(path, points)
    _fees(path, points)
    _txs(path, points)
    _slots(path, points)
    _conservation(path, measured)
    _waves(path, measured)
    _gas(path)
    _fork(path)
    _note_bytes(path, measured)
    _mempool(path, measured)
    report = _report(measured)
    (path / "README.md").write_text(report, encoding="utf-8")
    return measured


def run_measured_chain() -> dict[str, object]:
    """A six-block canonical chain plus the inputs the charts read."""
    miner_private, miner_public = generate(ML_DSA)
    alice = Wallet.create("alice")
    bob = Wallet.create("bob")
    carol = Wallet.create("carol")
    chain = Chain()
    pool = Mempool()

    _propose(chain, pool, 1, miner_private, miner_public, alice)
    note, spend_key, _memo = alice.scan(chain.states[chain.head()])[0]
    first, first_key = create_output(alice.view_pub, 15 * BASE, b"left")
    second, second_key = create_output(alice.view_pub, 15 * BASE, b"right")
    rest, rest_key = create_output(alice.view_pub, note.value - 30 * BASE, b"rest")
    pool.submit(chain.states[chain.head()], transfer([(note, spend_key)], [first, second, rest]))
    _propose(chain, pool, 2, miner_private, miner_public, alice)

    fee = 500
    bob_out, bob_key = create_output(bob.view_pub, 15 * BASE - fee, b"bob")
    to_bob = transfer([(first, first_key)], [bob_out], fee)
    to_carol = transfer(
        [(second, second_key)],
        [create_output(carol.view_pub, 15 * BASE - fee, b"carol")[0]],
        fee,
    )
    state = chain.states[chain.head()]
    pool.submit(state, to_bob)
    pool.submit(state, to_carol)
    duplicate_rejected = _rejected(pool, state, to_bob)
    inflated = transfer(
        [(rest, rest_key)],
        [create_output(bob.view_pub, rest.value + 1, b"inflate")[0]],
    )
    inflation_rejected = _rejected(pool, state, inflated)
    _propose(chain, pool, 3, miner_private, miner_public, alice)

    deploy_tx = deployment(alice.cap_private, alice.cap_pub, VAULT, [], [])
    contract_id = contract_id_of(deploy_tx)
    pool.submit(chain.states[chain.head()], deploy_tx)
    _propose(chain, pool, 4, miner_private, miner_public, alice)

    deposit_value = 10 * BASE
    source, source_key, _memo = max(alice.scan(chain.states[chain.head()]), key=lambda item: item[0].value)
    change = create_output(alice.view_pub, source.value - deposit_value, b"change")[0]
    deposit_tx = invocation(
        alice.cap_private,
        contract_id,
        [1, deposit_value],
        deposit_value,
        [(source, source_key)],
        [change],
    )
    pool.submit(chain.states[chain.head()], deposit_tx)
    _propose(chain, pool, 5, miner_private, miner_public, alice)

    payout = create_output(bob.view_pub, 4 * BASE, b"released")[0]
    withdraw_tx = invocation(
        alice.cap_private,
        contract_id,
        [2, 4 * BASE],
        0,
        [],
        [payout],
    )
    pool.submit(chain.states[chain.head()], withdraw_tx)
    _propose(chain, pool, 6, miner_private, miner_public, alice)

    follow = transfer(
        [(bob_out, bob_key)],
        [create_output(carol.view_pub, bob_out.value, b"follow")[0]],
    )
    points = canonical(chain)
    head = chain.states[chain.head()]
    if audit(head) != head.supply:
        raise RuntimeError("measured chain failed audit")
    return {
        "points": points,
        "chain": chain,
        "bob_input": 15 * BASE,
        "bob_output": 15 * BASE - fee,
        "bob_fee": fee,
        "commuting_waves": [len(wave) for wave in execution_waves([to_bob, to_carol])],
        "dependent_waves": [len(wave) for wave in execution_waves([to_bob, follow])],
        "note_parts": _note_parts(first),
        "accepted": 2,
        "duplicate_rejected": duplicate_rejected,
        "inflation_rejected": inflation_rejected,
        "locked_final": head.contracts[contract_id].balance,
    }


def _propose(chain, pool, height, private, public, payee: Wallet) -> None:
    propose(
        chain,
        pool,
        height * SLOT_TARGET_SECONDS,
        private,
        public,
        payee.view_pub,
    )


def _rejected(pool: Mempool, state, tx) -> int:
    from timecoin.chain import ChainError

    try:
        pool.submit(state, tx)
    except ChainError:
        return 1
    return 0


def _note_parts(output) -> list[tuple[str, int]]:
    return [
        ("value", 8),
        ("onetime pub", len(output.onetime_pub)),
        ("rho", len(output.rho)),
        ("kem ct", len(output.kem_ct)),
        ("cipher", len(output.cipher)),
        ("mac", len(output.mac)),
    ]


def _time(points: list[Point], field: str) -> list[tuple[float, float]]:
    return [(point.height, getattr(point, field) / BASE) for point in points]


def _supply(path: Path, points: list[Point]) -> None:
    line_chart(
        path / "supply.png",
        f"Supply follows height times 50 {TICKER}",
        "height",
        TICKER,
        [("supply", _time(points, "supply"))],
    )


def _notes(path: Path, points: list[Point]) -> None:
    line_chart(
        path / "notes.png",
        "Unspent notes and published nullifiers",
        "height",
        "count",
        [
            ("notes", [(point.height, point.notes) for point in points]),
            ("nullifiers", [(point.height, point.nullifiers) for point in points]),
        ],
    )


def _locked(path: Path, points: list[Point]) -> None:
    stacked_bar(
        path / "locked.png",
        "Note value and contract balance",
        [str(point.height) for point in points],
        [
            ("notes", [point.note_value / BASE for point in points]),
            ("locked", [point.locked / BASE for point in points]),
        ],
    )


def _fees(path: Path, points: list[Point]) -> None:
    bar_chart(
        path / "fees.png",
        "Fees per block, in base units",
        "height",
        [str(point.height) for point in points],
        [("fees", [float(point.fees) for point in points])],
    )


def _txs(path: Path, points: list[Point]) -> None:
    bar_chart(
        path / "transactions.png",
        "Transactions per block, excluding coinbase",
        "height",
        [str(point.height) for point in points],
        [("txs", [float(point.tx_count) for point in points])],
    )


def _slots(path: Path, points: list[Point]) -> None:
    line_chart(
        path / "slots.png",
        "Block slot against the 600 second target",
        "height",
        "slot",
        [
            ("slot", [(point.height, point.slot) for point in points]),
            ("target", [(point.height, point.height * SLOT_TARGET_SECONDS) for point in points]),
        ],
    )


def _conservation(path: Path, measured: dict[str, object]) -> None:
    paid = int(measured["bob_input"])
    out = int(measured["bob_output"])
    fee = int(measured["bob_fee"])
    bar_chart(
        path / "conservation.png",
        "Input equals output plus fee",
        "part",
        ["input", "out+fee"],
        [(TICKER, [paid / BASE, (out + fee) / BASE])],
    )


def _waves(path: Path, measured: dict[str, object]) -> None:
    commuting = list(measured["commuting_waves"])
    dependent = list(measured["dependent_waves"])
    width = max(len(commuting), len(dependent))
    commuting += [0] * (width - len(commuting))
    dependent += [0] * (width - len(dependent))
    bar_chart(
        path / "waves.png",
        "Conflict waves: commuting pair versus dependent pair",
        "wave",
        [str(index + 1) for index in range(width)],
        [
            ("commute", [float(item) for item in commuting]),
            ("depend", [float(item) for item in dependent]),
        ],
    )


def _gas(path: Path) -> None:
    deposit = _trace(VAULT, {}, [1, 100], 100)
    withdraw = _trace(VAULT, {0: 100}, [2, 40], 0)
    line_chart(
        path / "gas-deposit.png",
        "Vault deposit gas along the program counter",
        "step",
        "gas",
        [("deposit", [(index, step.gas_used) for index, step in enumerate(deposit)])],
    )
    line_chart(
        path / "gas-withdraw.png",
        "Vault withdraw gas along the program counter",
        "step",
        "gas",
        [("withdraw", [(index, step.gas_used) for index, step in enumerate(withdraw)])],
    )
    line_chart(
        path / "stack-deposit.png",
        "Vault deposit stack depth",
        "step",
        "depth",
        [("depth", [(index, step.stack_depth) for index, step in enumerate(deposit)])],
    )
    line_chart(
        path / "stack-withdraw.png",
        "Vault withdraw stack depth",
        "step",
        "depth",
        [("depth", [(index, step.stack_depth) for index, step in enumerate(withdraw)])],
    )


def _trace(code, storage, args, callvalue) -> list[Step]:
    steps: list[Step] = []
    run(code, storage, args, callvalue, steps=steps)
    return steps


def _fork(path: Path) -> None:
    miner_private, miner_public = generate(ML_DSA)
    alice = Wallet.create("fork-a")
    bob = Wallet.create("fork-b")
    chain = Chain()
    left = _bare(chain, miner_private, miner_public, alice.view_pub, chain.genesis_id, [])
    right = _bare(chain, miner_private, miner_public, bob.view_pub, chain.genesis_id, [])
    smaller = min((left, right), key=lambda item: int.from_bytes(item, "big"))
    larger = right if smaller == left else left
    _bare(chain, miner_private, miner_public, alice.view_pub, larger, [smaller])
    left_kind = "uncle" if smaller == left else "canonical"
    right_kind = "uncle" if smaller == right else "canonical"
    child_column = 0 if larger == left else 2
    fork_chart(
        path / "fork.png",
        "Fork choice on a measured uncle",
        [
            {"label": "Genesis", "detail": "height 0", "column": 1, "row": 0, "kind": "genesis"},
            {
                "label": "Block A",
                "detail": left_kind,
                "column": 0,
                "row": 1,
                "kind": left_kind,
                "parent": (1, 0),
            },
            {
                "label": "Block B",
                "detail": right_kind,
                "column": 2,
                "row": 1,
                "kind": right_kind,
                "parent": (1, 0),
            },
            {
                "label": "Head",
                "detail": "cites uncle",
                "column": child_column,
                "row": 2,
                "kind": "canonical",
                "parent": (child_column, 1),
                "uncle": (0, 1) if smaller == left else (2, 1),
            },
        ],
    )


def _bare(chain: Chain, private: bytes, public: bytes, view: bytes, parent: bytes, uncles: list[bytes]) -> bytes:
    parent_block = chain.blocks[parent]
    coinbase, _key = create_output(view, REWARD, b"coinbase")
    block = chain.seal(parent, parent_block.slot + SLOT_TARGET_SECONDS, [], private, public, coinbase, uncles)
    return chain.add(block)


def _note_bytes(path: Path, measured: dict[str, object]) -> None:
    composition_chart(path / "note-bytes.png", "Measured bytes in one note", measured["note_parts"])  # type: ignore[arg-type]


def _mempool(path: Path, measured: dict[str, object]) -> None:
    bar_chart(
        path / "mempool.png",
        "Pool admission on the height-2 state",
        "result",
        ["accept", "dup", "inflate"],
        [
            (
                "count",
                [
                    float(measured["accepted"]),
                    float(measured["duplicate_rejected"]),
                    float(measured["inflation_rejected"]),
                ],
            )
        ],
    )


def _report(measured: dict[str, object]) -> str:
    points: list[Point] = measured["points"]
    lines = [
        "# Measured charts",
        "",
        "These files are written by `python3 -m timecoin.cli charts`.",
        "The chain below is the run that produced them.",
        "",
        "| Height | Slot | Supply | Notes | Nullifiers | Locked | Fees | Txs |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for point in points:
        lines.append(
            f"| {point.height} | {point.slot} | {point.supply} | {point.notes} | "
            f"{point.nullifiers} | {point.locked} | {point.fees} | {point.tx_count} |"
        )
    lines.extend(
        [
            "",
            f"Final vault balance: {measured['locked_final']} base units.",
            f"Commuting wave sizes: {measured['commuting_waves']}.",
            f"Dependent wave sizes: {measured['dependent_waves']}.",
            f"Duplicate rejected: {measured['duplicate_rejected']}. Inflation rejected: {measured['inflation_rejected']}.",
            "",
            f"Supply at height h is h times the 50 {TICKER} reward. Fees move between notes and do not increase supply.",
            "",
        ]
    )
    return "\n".join(lines)

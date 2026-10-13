"""Numbers read off a chain after execution.

Charts use this module. They do not invent a supply series.
"""

from __future__ import annotations

from dataclasses import dataclass

from timecoin.chain import Chain, audit


@dataclass
class Point:
    height: int
    slot: int
    supply: int
    notes: int
    nullifiers: int
    note_value: int
    locked: int
    fees: int
    tx_count: int
    contracts: int


def canonical(chain: Chain) -> list[Point]:
    """Points from genesis to the fork-choice head, parent by parent."""
    cursor = chain.head()
    points: list[Point] = []
    while True:
        block = chain.blocks[cursor]
        state = chain.states[cursor]
        note_value = sum(output.value for output in state.notes.values())
        locked = sum(account.balance for account in state.contracts.values())
        points.append(
            Point(
                height=block.height,
                slot=block.slot,
                supply=state.supply,
                notes=len(state.notes),
                nullifiers=len(state.nullifiers),
                note_value=note_value,
                locked=locked,
                fees=sum(tx.fee for tx in block.txs),
                tx_count=len(block.txs),
                contracts=len(state.contracts),
            )
        )
        if cursor == chain.genesis_id:
            break
        cursor = block.parent
    points.reverse()
    for point in points:
        if point.note_value + point.locked != point.supply:
            raise RuntimeError("audit drift")
        if audit(chain.states[_block_at_height(chain, point.height)]) != point.supply:
            raise RuntimeError("audit drift")
    return points


def _block_at_height(chain: Chain, height: int):
    cursor = chain.head()
    while True:
        block = chain.blocks[cursor]
        if block.height == height:
            return cursor
        if cursor == chain.genesis_id:
            raise RuntimeError("height")
        cursor = block.parent

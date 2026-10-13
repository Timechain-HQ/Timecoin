"""Append-only block store.

The file holds blocks, not balances. Loading creates an empty chain and
re-executes every block, so a edited balance in the file cannot become state.
"""

from __future__ import annotations

import json
from pathlib import Path

from timecoin.chain import CHAIN_ID, NETWORK, Block, Chain, ChainError


def ordered_blocks(chain: Chain) -> list[Block]:
    """Parents before children. Forks stay in the file."""
    pending = list(chain.blocks.values())
    emitted: set[bytes] = set()
    ordered: list[Block] = []
    while pending:
        later: list[Block] = []
        for block in pending:
            block_id = block.block_id()
            if block_id == chain.genesis_id or block.parent in emitted:
                ordered.append(block)
                emitted.add(block_id)
            else:
                later.append(block)
        if len(later) == len(pending):
            raise ChainError("disconnected blocks")
        pending = later
    return ordered


def save_chain(chain: Chain, directory: str | Path) -> None:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    payload = {
        "network": NETWORK,
        "chain_id": CHAIN_ID,
        "blocks": [block.to_dict() for block in ordered_blocks(chain)],
    }
    (path / "chain.json").write_text(json.dumps(payload, indent=2), encoding="ascii")


def load_chain(directory: str | Path) -> Chain:
    payload = json.loads((Path(directory) / "chain.json").read_text(encoding="ascii"))
    if payload.get("network") != NETWORK or payload.get("chain_id") != CHAIN_ID:
        raise ChainError("network")
    chain = Chain()
    for raw in payload["blocks"]:
        block = Block.from_dict(raw)
        if block.height == 0:
            if block.block_id() != chain.genesis_id:
                raise ChainError("genesis mismatch")
            continue
        chain.add(block)
    return chain

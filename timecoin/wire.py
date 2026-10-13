"""Self-contained block bytes.

A second node needs the parent block and these bytes. It does not need the
sender's balances. There is no peer-to-peer network in this version: the
bytes are the check that a block can move from one process to another.
"""

from __future__ import annotations

import json

from timecoin.chain import Block, ChainError
from timecoin.codec import canonical

MAGIC = b"TCBLK1"


def encode_block(block: Block) -> bytes:
    body = canonical(block.to_dict())
    return MAGIC + len(body).to_bytes(4, "big") + body


def decode_block(blob: bytes) -> Block:
    if len(blob) < 10 or not blob.startswith(MAGIC):
        raise ChainError("wire")
    size = int.from_bytes(blob[6:10], "big")
    if size < 2 or 10 + size != len(blob):
        raise ChainError("wire length")
    try:
        data = json.loads(blob[10:].decode("ascii"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ChainError("wire json") from exc
    if not isinstance(data, dict):
        raise ChainError("wire json")
    return Block.from_dict(data)

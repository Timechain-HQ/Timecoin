"""Canonical encoding and the block Merkle root."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def shake(data: bytes, size: int = 32) -> bytes:
    return hashlib.shake_256(data).digest(size)


def xor_bytes(left: bytes, right: bytes) -> bytes:
    if len(left) != len(right):
        raise ValueError("xor length mismatch")
    return bytes(a ^ b for a, b in zip(left, right))


def canonical(value: Any) -> bytes:
    """Stable bytes for signatures. Objects must already be JSON-safe."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def merkle(leaves: list[bytes]) -> bytes:
    if not leaves:
        return shake(b"timecoin.merkle.empty")
    level = [shake(b"timecoin.merkle.leaf" + leaf) for leaf in leaves]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [
            shake(b"timecoin.merkle.node" + level[index] + level[index + 1])
            for index in range(0, len(level), 2)
        ]
    return level[0]


def seal(shared_secret: bytes, plaintext: bytes) -> tuple[bytes, bytes]:
    """Encrypt-then-MAC. The MAC key is the ML-KEM shared secret."""
    stream = shake(b"timecoin.stream.v1" + shared_secret, len(plaintext))
    ciphertext = xor_bytes(plaintext, stream)
    mac = hmac.new(shared_secret, b"timecoin.mac.v1" + ciphertext, hashlib.sha256).digest()
    return ciphertext, mac


def unseal(shared_secret: bytes, ciphertext: bytes, mac: bytes) -> bytes | None:
    expected = hmac.new(
        shared_secret, b"timecoin.mac.v1" + ciphertext, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(expected, mac):
        return None
    stream = shake(b"timecoin.stream.v1" + shared_secret, len(ciphertext))
    return xor_bytes(ciphertext, stream)

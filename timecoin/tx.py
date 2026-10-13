"""Notes, transactions, and stealth openings.

Amounts are public. That is deliberate: every testnet node checks conservation
directly. The long-term view key stays off the chain. The memo and the
one-time spend key travel inside an ML-KEM ciphertext.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from timecoin.codec import canonical, seal, shake, unseal
from timecoin.pq import ML_DSA, ML_KEM, decapsulate, encapsulate, generate, sign
from timecoin.vm import Instruction

MEMO_LIMIT = 256


class TxError(Exception):
    """A transaction is malformed or its signature does not verify."""


def _prefixed(blob: bytes) -> bytes:
    return len(blob).to_bytes(4, "big") + blob


@dataclass
class Output:
    """A stealth note. ``value`` is visible. The spend key is not."""

    value: int
    onetime_pub: bytes
    rho: bytes
    kem_ct: bytes
    cipher: bytes
    mac: bytes

    def commitment(self) -> bytes:
        return shake(
            b"timecoin.note.v1"
            + self.value.to_bytes(16, "big")
            + _prefixed(self.onetime_pub)
            + self.rho
            + _prefixed(self.kem_ct)
            + _prefixed(self.cipher)
            + self.mac
        )

    def to_dict(self) -> dict[str, int | str]:
        return {
            "value": self.value,
            "onetime_pub": self.onetime_pub.hex(),
            "rho": self.rho.hex(),
            "kem_ct": self.kem_ct.hex(),
            "cipher": self.cipher.hex(),
            "mac": self.mac.hex(),
        }


def nullifier(onetime_pub: bytes, rho: bytes) -> bytes:
    return shake(b"timecoin.null.v1" + shake(b"pk" + onetime_pub) + rho)


def create_output(view_pub: bytes, value: int, memo: bytes = b"") -> tuple[Output, bytes]:
    """Build a note for ``view_pub`` and return ``(output, one_time_private_key)``.

    The caller learns the one-time key because the caller generated it. The
    recipient can recover the same key by decapsulating. A later sweep to a
    fresh note removes the caller's ability to spend.
    """
    if value < 0 or value >= 2**64:
        raise TxError("value out of range")
    if len(memo) > MEMO_LIMIT:
        raise TxError("memo too long")
    one_time_private, one_time_public = generate(ML_DSA)
    rho = secrets.token_bytes(32)
    kem_ct, shared = encapsulate(view_pub)
    plaintext = _pack(value, rho, one_time_private, memo)
    cipher, mac = seal(shared, plaintext)
    output = Output(value, one_time_public, rho, kem_ct, cipher, mac)
    return output, one_time_private


def open_output(output: Output, view_private: bytes) -> tuple[bytes, bytes] | None:
    """Return ``(one_time_private_key, memo)`` when ``view_private`` owns the note."""
    shared = decapsulate(view_private, output.kem_ct)
    plaintext = unseal(shared, output.cipher, output.mac)
    if plaintext is None:
        return None
    try:
        value, rho, one_time_private, memo = _unpack(plaintext)
    except TxError:
        return None
    if value != output.value or rho != output.rho:
        return None
    return one_time_private, memo


@dataclass
class Spend:
    output: Output
    signature: bytes

    def to_dict(self, sigs: bool) -> dict[str, object]:
        body = self.output.to_dict()
        body["signature"] = self.signature.hex() if sigs else ""
        return body


@dataclass
class Deploy:
    code: list[Instruction]
    cap_pub: bytes
    cap_signature: bytes

    def to_dict(self, sigs: bool) -> dict[str, object]:
        return {
            "code": [[op, arg] for op, arg in _normalized(self.code)],
            "cap_pub": self.cap_pub.hex(),
            "cap_signature": self.cap_signature.hex() if sigs else "",
        }


@dataclass
class Call:
    contract_id: bytes
    args: list[int]
    callvalue: int
    cap_signature: bytes

    def to_dict(self, sigs: bool) -> dict[str, object]:
        return {
            "contract_id": self.contract_id.hex(),
            "args": list(self.args),
            "callvalue": self.callvalue,
            "cap_signature": self.cap_signature.hex() if sigs else "",
        }


@dataclass
class Tx:
    kind: str
    inputs: list[Spend]
    outputs: list[Output]
    fee: int
    deploy: Deploy | None = None
    call: Call | None = None

    def to_dict(self, sigs: bool = True) -> dict[str, object]:
        return {
            "kind": self.kind,
            "fee": self.fee,
            "inputs": [spend.to_dict(sigs) for spend in self.inputs],
            "outputs": [output.to_dict() for output in self.outputs],
            "deploy": None if self.deploy is None else self.deploy.to_dict(sigs),
            "call": None if self.call is None else self.call.to_dict(sigs),
        }

    def sighash(self) -> bytes:
        return shake(b"timecoin.sighash.v1" + canonical(self.to_dict(sigs=False)))

    def conflict_keys(self) -> set[bytes]:
        """Keys that prevent two transactions from running in the same parallel wave."""
        keys: set[bytes] = set()
        for spend in self.inputs:
            keys.add(b"o" + spend.output.commitment())
            keys.add(b"z" + nullifier(spend.output.onetime_pub, spend.output.rho))
        for output in self.outputs:
            keys.add(b"o" + output.commitment())
        if self.kind == "deploy":
            keys.add(b"d" + self.sighash())
        if self.kind == "call" and self.call is not None:
            keys.add(b"c" + self.call.contract_id)
        return keys


def transfer(spends: list[tuple[Output, bytes]], outputs: list[Output], fee: int = 0) -> Tx:
    """Sign a payment. Each pair is ``(note, one_time_private_key)``."""
    tx = Tx(
        kind="transfer",
        inputs=[Spend(output, b"") for output, _private in spends],
        outputs=list(outputs),
        fee=fee,
    )
    digest = tx.sighash()
    tx.inputs = [
        Spend(output, sign(private, digest)) for output, private in spends
    ]
    return tx


def deployment(
    cap_private: bytes,
    cap_pub: bytes,
    code: list[Instruction],
    spends: list[tuple[Output, bytes]],
    outputs: list[Output],
    fee: int = 0,
) -> Tx:
    tx = Tx(
        kind="deploy",
        inputs=[Spend(output, b"") for output, _private in spends],
        outputs=list(outputs),
        fee=fee,
        deploy=Deploy(list(code), cap_pub, b""),
    )
    digest = tx.sighash()
    tx.inputs = [Spend(output, sign(private, digest)) for output, private in spends]
    assert tx.deploy is not None
    tx.deploy.cap_signature = sign(cap_private, digest)
    return tx


def invocation(
    cap_private: bytes,
    contract_id: bytes,
    args: list[int],
    callvalue: int,
    spends: list[tuple[Output, bytes]],
    outputs: list[Output],
    fee: int = 0,
) -> Tx:
    tx = Tx(
        kind="call",
        inputs=[Spend(output, b"") for output, _private in spends],
        outputs=list(outputs),
        fee=fee,
        call=Call(contract_id, list(args), callvalue, b""),
    )
    digest = tx.sighash()
    tx.inputs = [Spend(output, sign(private, digest)) for output, private in spends]
    assert tx.call is not None
    tx.call.cap_signature = sign(cap_private, digest)
    return tx


def execution_waves(txs: list[Tx]) -> list[list[Tx]]:
    """Group transactions that do not touch the same notes or contracts.

    Waves run in order. Transactions inside one wave commute. This is the
    Transactions that do not touch the same notes or contracts form one wave
    and commute. Overlapping transactions stay in order.
    """
    waves: list[list[Tx]] = []
    current: list[Tx] = []
    occupied: set[bytes] = set()
    for tx in txs:
        keys = tx.conflict_keys()
        if keys & occupied:
            waves.append(current)
            current = [tx]
            occupied = set(keys)
        else:
            current.append(tx)
            occupied |= keys
    if current:
        waves.append(current)
    return waves


def _pack(value: int, rho: bytes, one_time_private: bytes, memo: bytes) -> bytes:
    return b"".join(
        [
            b"TN1",
            value.to_bytes(8, "big"),
            rho,
            _prefixed(one_time_private),
            len(memo).to_bytes(2, "big"),
            memo,
        ]
    )


def _unpack(plaintext: bytes) -> tuple[int, bytes, bytes, bytes]:
    if not plaintext.startswith(b"TN1") or len(plaintext) < 3 + 8 + 32 + 4:
        raise TxError("plaintext")
    cursor = 3
    value = int.from_bytes(plaintext[cursor : cursor + 8], "big")
    cursor += 8
    rho = plaintext[cursor : cursor + 32]
    cursor += 32
    key_len = int.from_bytes(plaintext[cursor : cursor + 4], "big")
    cursor += 4
    if key_len < 0 or cursor + key_len + 2 > len(plaintext):
        raise TxError("plaintext")
    one_time_private = plaintext[cursor : cursor + key_len]
    cursor += key_len
    memo_len = int.from_bytes(plaintext[cursor : cursor + 2], "big")
    cursor += 2
    if cursor + memo_len != len(plaintext):
        raise TxError("plaintext")
    return value, rho, one_time_private, plaintext[cursor:]


def _normalized(code: list[Instruction]) -> list[tuple[str, int | None]]:
    normalized: list[tuple[str, int | None]] = []
    for instruction in code:
        if len(instruction) == 1:
            normalized.append((instruction[0], None))
        else:
            normalized.append((instruction[0], instruction[1]))
    return normalized


# Imported so static readers can see which KEM protects note payloads.
_KEM_ALGORITHM = ML_KEM

"""Testnet wallets. Keys stay local. Scanning uses the ML-KEM view key."""

from __future__ import annotations

from dataclasses import dataclass, field

from timecoin.chain import BASE_UNITS, TICKER, State
from timecoin.pq import ML_DSA, ML_KEM, generate
from timecoin.tx import Output, Tx, create_output, open_output, transfer


@dataclass
class Wallet:
    name: str
    view_private: bytes
    view_pub: bytes
    cap_private: bytes
    cap_pub: bytes
    secrets: dict[bytes, bytes] = field(default_factory=dict)

    @classmethod
    def create(cls, name: str) -> Wallet:
        view_private, view_pub = generate(ML_KEM)
        cap_private, cap_pub = generate(ML_DSA)
        return cls(name, view_private, view_pub, cap_private, cap_pub)

    def scan(self, state: State) -> list[tuple[Output, bytes, bytes]]:
        """Return notes this view key can open, as ``(output, spend_key, memo)``."""
        found: list[tuple[Output, bytes, bytes]] = []
        for commitment, output in state.notes.items():
            opened = open_output(output, self.view_private)
            if opened is None:
                continue
            spend_key, memo = opened
            self.secrets[commitment] = spend_key
            found.append((output, spend_key, memo))
        return found

    def balance(self, state: State) -> int:
        return sum(output.value for output, _key, _memo in self.scan(state))

    def pay(
        self,
        state: State,
        recipient_view_pub: bytes,
        amount: int,
        memo: bytes = b"",
        fee: int = 0,
    ) -> Tx:
        if amount <= 0:
            raise ValueError("amount")
        selected: list[tuple[Output, bytes]] = []
        total = 0
        for output, spend_key, _memo in self.scan(state):
            selected.append((output, spend_key))
            total += output.value
            if total >= amount + fee:
                break
        if total < amount + fee:
            raise ValueError(f"insufficient {TICKER}")
        outputs = [create_output(recipient_view_pub, amount, memo)[0]]
        change = total - amount - fee
        if change:
            outputs.append(create_output(self.view_pub, change, b"change")[0])
        return transfer(selected, outputs, fee)


def format_time(base_units: int) -> str:
    whole = base_units // BASE_UNITS
    fraction = base_units % BASE_UNITS
    if fraction == 0:
        return f"{whole} {TICKER}"
    return f"{whole}.{fraction:08d}".rstrip("0") + f" {TICKER}"

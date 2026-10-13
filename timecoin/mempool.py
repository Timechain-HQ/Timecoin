"""Transaction pool for one local node.

A transaction is admitted when it applies cleanly after every transaction
already in the pool. The pool keeps that order. A later block takes a prefix
that still applies to the parent state and drops the rest only after inclusion.
"""

from __future__ import annotations

from timecoin.chain import ChainError, State, apply_tx
from timecoin.tx import Tx, TxError


class Mempool:
    def __init__(self) -> None:
        self.txs: list[Tx] = []

    def submit(self, state: State, tx: Tx) -> None:
        if any(existing.sighash() == tx.sighash() for existing in self.txs):
            raise ChainError("duplicate tx")
        cursor = state.clone()
        for existing in self.txs:
            cursor = apply_tx(cursor, existing)
        try:
            apply_tx(cursor, tx)
        except TxError as exc:
            raise ChainError(str(exc)) from exc
        self.txs.append(tx)

    def take(self, state: State, limit: int = 32) -> list[Tx]:
        """Return pooled transactions that still apply, in pool order."""
        chosen: list[Tx] = []
        cursor = state.clone()
        for tx in self.txs:
            if len(chosen) >= limit:
                break
            try:
                cursor = apply_tx(cursor, tx)
            except (ChainError, TxError):
                continue
            chosen.append(tx)
        return chosen

    def drop(self, included: list[Tx]) -> None:
        gone = {tx.sighash() for tx in included}
        self.txs = [tx for tx in self.txs if tx.sighash() not in gone]

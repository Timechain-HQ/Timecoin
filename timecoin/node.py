"""Block production for one local testnet node."""

from __future__ import annotations

from timecoin.chain import REWARD, Chain
from timecoin.mempool import Mempool
from timecoin.tx import create_output


def propose(
    chain: Chain,
    pool: Mempool,
    slot: int,
    proposer_private: bytes,
    proposer_pub: bytes,
    coinbase_view: bytes,
    limit: int = 32,
) -> bytes:
    """Seal the next block on the current head and remove included transactions."""
    parent = chain.head()
    txs = pool.take(chain.states[parent], limit)
    fees = sum(tx.fee for tx in txs)
    coinbase, _spend = create_output(coinbase_view, REWARD + fees, b"coinbase")
    block = chain.seal(parent, slot, txs, proposer_private, proposer_pub, coinbase)
    block_id = chain.add(block)
    pool.drop(txs)
    return block_id

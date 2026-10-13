# Timecoin testnet protocol

Timecoin is a testnet. It is not a mainnet, it has no peer-to-peer network, and it is not audited.

## Network

- Network name: `timecoin-testnet`
- Chain id: `timecoin-testnet-1`
- Genesis is domain-separated so a future mainnet cannot reuse these blocks.
- 1 TIME = 10^8 base units.
- Each block mints 50 TIME. Genesis supply is zero.
- The slot target is 600 seconds. A block must use a higher slot than its parent. Tests may use any increasing slot.

## Notes

A note has a public amount and a one-time ML-DSA-44 spend key. The long-term ML-KEM-768 view key is not written into the block. The memo and the one-time spend key are encrypted to the recipient with the ML-KEM shared secret.

The note commitment binds the amount, the one-time public key, the 32-byte rho, the ciphertext, and the MAC. The nullifier is derived from the one-time public key and rho. A nullifier can be published once.

Nodes check conservation in the clear: input amounts equal output amounts plus the fee, adjusted for contract deposits and payouts. Fees move into the coinbase. Only the 50 TIME reward increases supply.

## Wallet

A wallet holds a view key and a capability key. Scanning decapsulates every note and keeps the ones whose MAC matches. A payment creates a fresh one-time key and encrypts it to the recipient. A sweep spends that note into a new note encrypted to the recipient's own view key.

## Contracts

Contracts are bytecode for a gas-metered stack machine. A deployed contract has a capability public key, a balance, and integer storage. A call is valid only when that capability key signs the transaction. The vault accepts a deposit when the attached value matches the requested amount, and a withdrawal when storage covers the payout.

## Blocks

A block commits to its parent, height, slot, transactions, up to two uncle headers, the coinbase note, the proposer key, and the state root. The proposer signs that commitment with ML-DSA-44.

Fork choice prefers the greater height. At equal height the smaller block id wins. An uncle must be a competing sibling of the parent: same grandparent and the same height as the parent. Uncle transactions are not applied.

Transactions that do not touch the same notes or contracts can be applied in either order. Transactions that overlap stay in the order listed in the block.

## What a node can see

| Data | Visible |
| --- | --- |
| Note amount and fee | Yes |
| Which note was spent | Yes, by commitment and nullifier |
| Long-term view key | No |
| Memo and one-time spend key | Only with the view key |
| Contract capability key | Yes, on calls that use it |
| Block proposer key | Yes |

The testnet does not claim complete privacy. Amounts and the note graph are public so every node can reject inflation.

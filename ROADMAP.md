# Timecoin roadmap

Public path for the Timecoin testnet. This is a plan, not a launch promise. There is **no mainnet** today. Check a box only when the proof in that step is true.

| Fact | Value |
| --- | --- |
| Token | Timecoin (TIC) |
| Network | `timecoin-testnet` · chain id `timecoin-testnet-1` |
| Signatures | ML-DSA-44 (FIPS 204) from genesis |
| Note sealing | ML-KEM-768 (FIPS 203) from genesis |
| Issuance | 50 TIC per block · 1 TIC = 10⁸ base units · no premine |
| Slot target | 600 seconds |
| Status | Single-process / two-process sealed-block testnet · not audited · no gossip network |

Organization: [Timechain-HQ](https://github.com/Timechain-HQ) · Site: [timecoin.cash](https://www.timecoin.cash)

---

## 0. Already shipped (v0.2.0)

- [x] Domain-separated genesis for `timecoin-testnet-1`
- [x] Note commitments, nullifiers, public amounts, conservation checks
- [x] ML-DSA-44 spends and block signatures; ML-KEM-768 sealed memos and one-time keys
- [x] Mempool admission, fork choice with uncles, sealed-block handoff (`TCBLK1`)
- [x] Gas-metered contract machine and vault
- [x] Wallet: scan, pay, sweep
- [x] Protocol book with measured charts
- [x] Day-one post-quantum and privacy rule docs

Repos: [Timecoin](https://github.com/Timechain-HQ/Timecoin) · [book](https://github.com/Timechain-HQ/book) · [wallet](https://github.com/Timechain-HQ/wallet) · [contracts](https://github.com/Timechain-HQ/contracts) · [privacy](https://github.com/Timechain-HQ/privacy) · [post-quantum](https://github.com/Timechain-HQ/post-quantum)

Proof: `python3 -m unittest` and `python3 -m timecoin.cli charts` in the node repo.

---

## 1. Harden the single-node testnet

Make the existing process something a stranger can run without reading the source first.

- [ ] Pin OpenSSL 3.5+ requirements and document install on Linux / macOS
- [ ] Versioned CLI (`demo`, `charts`, `seal`, `apply`) with stable exit codes
- [ ] Deterministic fixture vectors for notes, sighashes, and block ids
- [ ] Continuous integration on every push (unit tests + chart smoke)
- [ ] Security notes: what is in scope for the testnet, what is not audited

Proof: a clean clone runs tests green on a fresh machine in one documented command sequence.

---

## 2. Multi-process local network

Leave the single-process lab without pretending it is a network.

- [ ] Persistent store with crash recovery (reload still re-executes every block)
- [ ] Local peer transport for sealed blocks (still not public gossip)
- [ ] Competing proposers on one machine; uncle inclusion under load
- [ ] Explicit chain-id / network-name guard so fixtures cannot cross networks

Proof: two processes exchange a sealed block, diverge, and converge under documented fork-choice rules.

---

## 3. Wallet and developer surface

- [ ] Export / import of view and capability keys with clear danger labels
- [ ] Address and payment URI format written into the book
- [ ] Contract deploy and call helpers with gas estimates from the meter
- [ ] Human-readable explorer for a local chain (height, notes, vault balance)

Proof: a third-party script can pay, sweep, and deposit to the vault against a running local node.

---

## 4. Specification freeze for testnet-1

- [ ] Byte layouts and domain separators frozen in [book](https://github.com/Timechain-HQ/book)
- [ ] Compatibility suite: old sealed blocks still apply after code updates
- [ ] Privacy and post-quantum docs match the executable node (no drift)
- [ ] Public threat model: amounts and note graph stay visible on purpose

Proof: a tagged `testnet-1-spec` release; vectors in CI; docs link the tag.

---

## 5. Public testnet (still not mainnet)

Only after phases 1–4. A public testnet still has no economic value.

- [ ] Seed nodes and a faucet with rate limits
- [ ] Bootstrap docs and a status page
- [ ] Reset policy published in advance (heights, wipe windows)
- [ ] Incident channel for consensus or conservation failures

Proof: independent operators run nodes that stay in consensus for a published window.

---

## 6. What is deliberately not on this roadmap yet

These are **not** scheduled. Listing them avoids false promises.

- Mainnet genesis and issuance
- Classical (elliptic-curve) signature paths
- Hidden amounts / zero-knowledge conservation proofs
- Token listings, bridges, or custodial products
- Guarantees about quantum resistance beyond the FIPS primitives we call

A future mainnet, if it ever exists, gets a **new genesis** and a new roadmap. `timecoin-testnet-1` blocks will not carry over.

---

## Repo map

| Repository | Role |
| --- | --- |
| [Timecoin](https://github.com/Timechain-HQ/Timecoin) | Node |
| [book](https://github.com/Timechain-HQ/book) | Protocol book |
| [wallet](https://github.com/Timechain-HQ/wallet) | Wallet |
| [contracts](https://github.com/Timechain-HQ/contracts) | VM + vault |
| [privacy](https://github.com/Timechain-HQ/privacy) | Privacy rules |
| [post-quantum](https://github.com/Timechain-HQ/post-quantum) | PQ rules |
| [roadmap](https://github.com/Timechain-HQ/roadmap) | This file |

Original personal node: [9lordisgod/Timecoin](https://github.com/9lordisgod/Timecoin)

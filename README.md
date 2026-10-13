# Timecoin testnet

Timecoin is a local testnet for a stealth-style chain. Version 0.1.0 implements the testnet functions below on one machine. It is not mainnet, it has no peer-to-peer network, and it is not audited.

The organization page is <https://github.com/Timechain-HQ>. It existed on 2026-10-13 and had no public repositories. The testnet repository to create there is <https://github.com/Timechain-HQ/Timecoin>. This machine has no GitHub token and no SSH key, so the push has not been made.

From an account that can create repositories in `Timechain-HQ`:

```bash
cd ~/Timecoin
gh repo create Timechain-HQ/Timecoin --public --source . --remote origin --description "Timecoin testnet. Not mainnet." --push
```

## What the testnet does

- Network id `timecoin-testnet` / `timecoin-testnet-1`. Genesis is domain-separated from any future mainnet.
- ML-DSA-44 signatures for notes, contract capabilities, and blocks (FIPS 204, via OpenSSL 3.5).
- ML-KEM-768 stealth notes (FIPS 203). The long-term view key is not written into the block. The memo and the one-time spend key are encrypted to the recipient.
- Public amounts, public fees, and a public supply check. A node can reject inflation without a zero-knowledge proof.
- A gas-metered contract machine and a vault contract. Spending the vault requires a signature from its capability key, not from a named account.
- Conflict waves: transactions that touch different notes and contracts commute; conflicting ones stay ordered.
- Fork choice by height, then by smaller block id. A later block may cite one or two uncle blocks. Uncle transactions are not applied.
- No premine. Each block mints 50 TIME. 1 TIME = 10^8 base units. The slot target is 600 seconds. The testnet accepts any increasing slot number so tests do not wait.

## What it does not do

This is not 100% private. Amounts, fees, and the note graph are visible. A sender who keeps the one-time key they generated can spend that note until the recipient sweeps it to a fresh note. Block producers are public. There is no Halo2 or STARK proof, no RandomX mining, no Rholang interpreter, and no mainnet launch configuration.

DarkFi and DarkWow hide more about amounts and state because they verify Halo2 proofs. Those proofs use the Pasta elliptic curves, which are not post-quantum. Timecoin takes the opposite testnet trade: post-quantum signatures and key encapsulation, with conservation checked in the clear.

## Run

OpenSSL 3.5 or newer is required (`ML-DSA-44` and `ML-KEM-768`).

```bash
cd ~/Timecoin
python3 -m unittest tests.test_timecoin
python3 -m timecoin.cli demo
```

The design sources are in [docs/EVIDENCE.md](docs/EVIDENCE.md).

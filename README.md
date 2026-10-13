# Timecoin testnet

Timecoin is a local testnet for a stealth-style chain. Version 0.1.0 runs on one machine. It is not mainnet, it has no peer-to-peer network, and it is not audited.

Organization: <https://github.com/Timechain-HQ>

| Repository | Role |
| --- | --- |
| [Timecoin](https://github.com/Timechain-HQ/Timecoin) | Testnet node, notes, blocks, and fork choice |
| [book](https://github.com/Timechain-HQ/book) | Protocol book |
| [wallet](https://github.com/Timechain-HQ/wallet) | View keys, scanning, payment, and sweep |
| [contracts](https://github.com/Timechain-HQ/contracts) | Contract machine and the vault |

## What the testnet does

- Network id `timecoin-testnet` / `timecoin-testnet-1`. Genesis is domain-separated from any future mainnet.
- ML-DSA-44 signatures for notes, contract capabilities, and blocks (FIPS 204, via OpenSSL 3.5).
- ML-KEM-768 stealth notes (FIPS 203). The long-term view key is not written into the block. The memo and the one-time spend key are encrypted to the recipient.
- Public amounts, public fees, and a public supply check. A node rejects inflation directly.
- A gas-metered contract machine and a vault contract. Spending the vault requires a signature from its capability key.
- Transactions that touch different notes and contracts commute. Overlapping transactions stay ordered.
- Fork choice by height, then by smaller block id. A later block may cite up to two uncle blocks. Uncle transactions are not applied.
- No premine. Each block mints 50 TIME. 1 TIME = 10^8 base units. The slot target is 600 seconds. The testnet accepts any increasing slot number so tests do not wait.

## Limits

Amounts, fees, and the note graph are visible. A sender who keeps the one-time key they generated can spend that note until the recipient sweeps it. Block producers are public. There is no mainnet launch configuration.

## Run

OpenSSL 3.5 or newer is required (`ML-DSA-44` and `ML-KEM-768`).

```bash
cd ~/Timecoin
python3 -m unittest tests.test_timecoin
python3 -m timecoin.cli demo
```

The protocol notes are in [docs/PROTOCOL.md](docs/PROTOCOL.md).

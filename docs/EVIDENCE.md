# Evidence for the Timecoin testnet design

Primary pages were read on 2026-10-12. Timecoin copies specific mechanisms from those pages. It does not copy their code, and it is a testnet, not a mainnet.

## Where the testnet repository goes

`GET https://api.github.com/repos/9lordisgod/Timecoin` returned 404. The public repository list for `9lordisgod` includes `DarkWow-Chain-Research` and does not include `Timecoin`. Those notes describe DarkWow, not this chain.

`GET https://api.github.com/orgs/Timechain-HQ` on 2026-10-13 returned the organization `Timechain HQ`, created `2026-10-13T04:40:10Z`. The testnet was then created as the public repository `Timechain-HQ/Timecoin`.

This testnet is a new implementation.

## Ethereum

Sources:

- <https://ethereum.org/developers/docs/nodes-and-clients/node-architecture/>
- <https://ethereum.org/developers/docs/evm/>
- <https://ethereum.org/developers/docs/consensus-mechanisms/>

A node is split into an execution client, a consensus client, and, when staking, a validator. The execution client validates transactions, runs the EVM, and stores state. The consensus client follows the fork-choice head. The EVM is a stack machine with 1024 items of 256-bit words, gas accounting, and a state transition from an old state plus transactions to a new state. State is committed by a Merkle Patricia Trie root. Consensus is proof of stake (Gasper: Casper FFG plus GHOST). The EVM page names secp256k1 signatures as a reason for 256-bit words. That signature system is not post-quantum.

Timecoin uses the same shape at testnet scale: a pure state transition, a gas-metered stack machine, a state root in the block, and a separate fork-choice rule. User value is in notes rather than public accounts. There is no beacon chain and no mainnet validator set.

## DarkFi

Sources:

- <https://dark.fi/book/arch/overview.html>
- <https://dark.fi/book/arch/sc/sc.html>
- <https://dark.fi/book/zkas/zkvm.html>

DarkFi is a layer-one proof-of-work chain (RandomX) for anonymous applications. Users prove a contract execution on secret witness data. Every full node verifies. Contract state is globally readable and writable only by that contract. A transaction carries contract calls, Halo2 proofs, and Schnorr signatures. The zkVM is one Halo2 circuit, compiled from zkas, with no trusted setup. Anonymous payments use a mint-and-burn note scheme.

Timecoin keeps the note, nullifier, and "only this contract can write its storage" rules. It does not implement zkas, Halo2, or RandomX. Amounts stay public so a testnet node can check conservation without claiming a zero-knowledge proof it does not have.

## RChain

Sources:

- <https://github.com/rchain/rchain>
- <https://github.com/rchain/rchain/wiki/The-philosophy-of-RChain-node-architecture>
- <https://architecture-docs.readthedocs.io/execution_model/consensus_protocol.html>

RChain's node is Rholang (rho-calculus), RSpace (a tuple space), and Casper. Casper is proof of stake. Validators bet on logical propositions, and namespace isolation is what lets much of the work proceed in parallel. Contracts are Rholang processes on the RhoVM.

Timecoin does not implement Rholang or CBC Casper. The testnet piece taken from that design is the conflict rule: transactions with disjoint notes and contracts are one parallel wave and commute; overlapping transactions stay in order.

## DarkWow

Sources:

- <https://github.com/PatrickMockridge/DarkWow>
- <https://github.com/PatrickMockridge/DarkWow/blob/linear-master/doc/src/arch/overview.md>
- <https://raw.githubusercontent.com/PatrickMockridge/DarkWow/linear-master/doc/src/about/differences_from_upstream.md>

DarkWow is a DarkFi fork. Its overview describes a proof-of-work chain with anonymous WASM contracts, Uncle Merkle consensus instead of an overlay/diff DAG, and O-Cap primitives (Purse, Box, Identity, MultiSig, Oracle, Attestation) instead of one DAO. Authority is possession of a secret, not a revealed identity. The zkVM verifies Halo2 proofs over the Pasta cycle (Pallas/Vesta), which needs no trusted setup. The differences note says upstream DarkFi used ACL checks that reveal a public key, while DarkWow uses a boolean ZK predicate, and that DarkWow uses pure mining instead of contributor allocations.

Timecoin takes three of those ideas onto the testnet:

- A capability key authorizes a contract call. The chain checks an ML-DSA signature and does not store a personal account.
- A later block may cite uncle blocks. Cited transactions are not executed.
- Genesis supply is zero. Coins enter only as block rewards.

Timecoin does not use RandomX, WASM, Halo2, Pasta curves, or DarkWow's emission schedule. Pasta-based Halo2 is not a post-quantum proof system. ML-DSA-44 and ML-KEM-768 are.

## Privacy, stated as tested behavior

| Data | Visible on the testnet |
| --- | --- |
| Note amount and fee | Yes |
| Which note was spent | Yes, by commitment and nullifier |
| Long-term view key | No |
| Memo and one-time spend key | Only to the view-key holder |
| Contract capability key | Yes, on calls that use it |
| Block proposer key | Yes |

A recipient can sweep a note to a fresh output. The previous sender's view key cannot open that output. That is tested. It is not anonymity against an observer who can see amounts and the note graph, and it is not a claim of 100% privacy.

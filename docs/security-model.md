# ClawChain Security Model

This document describes ClawChain's security assumptions, threat model, and defense mechanisms as of v0.2.0-testnet.

## 1. Trust Assumptions

### Deterministic Challenges (math, logic, hash, text_transform, json_extract, format_convert)
**Miners do NOT need to trust the server.**
- Answers have a single correct value that anyone can independently compute.
- Server publishes a commitment hash `H(challenge_id || expected_answer || salt)` at challenge creation.
- After settlement, the server reveals `expected_answer` and `salt`.
- Miners verify: `sha256(challenge_id + revealed_answer + salt) == commitment`.
- If the commitment doesn't match, the server is provably dishonest.

### Closed-Set Challenges (sentiment, classification) — Alpha
**Miners do NOT need to trust the server.**
- In Alpha, sentiment is a 3-way closed-set choice (positive/negative/neutral) and classification uses 5 fixed categories.
- The server pre-commits the correct answer at challenge creation time.
- Miners verify via the same commitment scheme as deterministic challenges.
- These are effectively deterministic for verification purposes.

### Non-Deterministic Challenges (translation, text_summary, entity_extraction) — NOT in Alpha
**Not part of Alpha reward-critical mining.**
- Answers are subjective — no single "correct" value.
- These tasks are vulnerable to Sybil attacks via majority voting.
- They will be enabled in Beta with stake-weighted multi-validator consensus.
- Code is retained but challenges are not generated for Alpha mining.

### Mining Service → Challenge Engine
The mining service trusts the challenge engine to:
- Generate diverse, solvable challenges across all 8 Alpha types (deterministic-first).
- Produce correct `expected_answer` values pre-committed at generation time.
- Generate cryptographic commitments at challenge creation time (immutable).
- Maintain a 20% spot-check rate for fraud detection.

### Settlement Anchoring
Each epoch settlement is anchored for auditability:
- Settlement root = SHA256 of canonical JSON of all per-miner settlement records.
- Anchored locally (data/anchors/epoch_N.json) with chain liveness verification. **Not on-chain consensus** — local file-based anchoring only in Alpha.
- Anyone can verify: fetch records → recompute root → compare with anchor.
- **Anchoring improves transparency but does not fully decentralize the system.** Settlement computation remains server-side.

### Miners ↔ Miners (Indirect)
Miners do not communicate directly. Trust is mediated by consensus:
- Production: 3 independent submissions with majority agreement.
- DEV mode (testnet): single miner can settle.

## 2. Challenge Commitment Protocol

### How It Works
1. **Challenge Creation**: Server generates challenge + expected_answer. Computes:
   ```
   salt = random_hex(16)
   commitment = SHA256(challenge_id || expected_answer || salt)
   ```
2. **Challenge Distribution**: Server sends to miners:
   - `prompt`, `commitment`, `verification_mode`
   - **NOT** `expected_answer`, `salt`, or `known_answer`
3. **Miner Submission**: Miner computes answer independently and submits.
4. **Settlement**: Server reveals `expected_answer` and `salt` in the response.
5. **Verification**: Miner checks `SHA256(challenge_id + revealed_answer + salt) == commitment`.

### What This Prevents
- **Post-hoc answer modification**: Server cannot change the correct answer after distributing the challenge, because the commitment would not match.
- **Selective grading**: For deterministic challenges, the answer is verifiable by anyone.

### What This Does NOT Prevent (Yet)
- **Challenge withholding**: Server could refuse to settle or reveal.
- **Answer quality disputes**: For non-deterministic challenges, "correctness" is still server-judged in single-miner mode.

## 3. Attacker Model

### 3.1 Malicious Server
**Threat**: The server operator modifies answers after distribution to deny rewards.

**Mitigations**:
- Commitment scheme makes post-hoc modification detectable.
- Deterministic challenges are fully verifiable by miners.
- `verification_mode` field explicitly tells miners the trust level of each challenge.

**Residual risk**: Server can still selectively withhold challenges or refuse to reveal. This will be addressed by on-chain settlement in mainnet.

### 3.2 Sybil Attacks
**Threat**: Attacker registers many fake miners to dominate rewards.

**Mitigations**:
- **IP rate limiting**: Maximum 3 miners per IP address.
- **Progressive staking**: Free registration when <1000 miners, 10 CLAW when 1000-5000, 100 CLAW when 5000+.
- **Cold-start penalty**: New miners receive 50% rewards for first 100 challenges.
- **Registration index tracking**: Early miners get higher multipliers.

**Known gaps**: IP-based limits can be bypassed with proxies/VPNs. True Sybil resistance requires economic staking (mainnet).

### 3.3 Collusion
**Threat**: Multiple miners coordinate identical wrong answers.

**Mitigations**:
- **Spot checks (20% in Alpha)**: Use known answers as ground truth. Wrong answers carry heavy penalties.
- **Reputation system**: Miners below 100 reputation are suspended.
- **Consecutive failure detection**: 5+ failures → suspension.
- **Stake slashing**: Wrong answers lead to stake loss (see §5).

### 3.4 Answer Stealing / Front-Running
**Threat**: A miner copies another's answer.

**Mitigations**:
- **Commit-reveal protocol**: SHA256(answer + nonce) committed before reveal.
- **Answer not exposed in API**: The `/challenges/pending` endpoint does not include `expected_answer`.

### 3.5 Malicious Miner (Resource Abuse)
**Threat**: Miner submits garbage/random answers.

**Mitigations**:
- Reputation system with escalating penalties.
- Spot checks with known answers detect random submissions.
- Stake slashing removes economic incentive for garbage.

## 4. Staking & Slashing

### Progressive Staking
| Active Miners | Stake Required |
|--------------|---------------|
| < 1,000 | 0 CLAW (free) |
| 1,000 – 5,000 | 10 CLAW |
| 5,000+ | 100 CLAW |

### Slashing Rules
| Condition | Penalty |
|-----------|---------|
| 3+ consecutive spot-check failures | 10% of staked amount |
| 5+ consecutive failures (any type) | 50% of staked amount + suspension |
| Reputation drops below 100 | Suspension (24h cooldown) |

### Suspension Recovery
- After 24h cooldown, miners can re-register.
- Reputation resets to 200 (not full 500).
- Slashed stake is NOT returned.

## 5. Reputation System

| Event | Reputation Change |
|-------|------------------|
| Correct answer (normal) | +5 |
| Correct answer (spot check) | +10 |
| Wrong answer (normal) | -20 |
| Wrong answer (spot check) | -50 |
| 5+ consecutive failures | -500 |
| Maximum reputation | 1000 |
| Starting reputation | 500 |
| Suspension threshold | < 100 |

## 6. Miner Isolation

### Challenge Safety
- Challenges contain only text prompts. No executable code is ever sent to miners.
- The mining script (`mine.py`) uses AST-based safe math evaluation — no `eval()` or `exec()`.
- Local solvers process challenge text with deterministic string/math operations only.

### LLM Privacy
- In `local_only` mode (default): No challenge data leaves the miner's machine.
- In `auto`/`llm` modes: Challenge prompt text is sent to external LLM providers.
- LLM API calls are logged locally in `data/llm_calls.json` for audit.

## 7. Versioning

### Protocol Versioning
- Server exposes `GET /clawchain/version` with `server_version` and `min_miner_version`.
- Miner reports `miner_version` during registration.
- Incompatible miners are rejected at registration time.

### Current Versions
- Server: 0.2.0
- Minimum miner: 0.1.0
- Miner client: 0.2.0

## 8. Network Security

### RPC Communication
- HTTPS recommended; HTTP warned on non-localhost endpoints.
- Multi-endpoint fallback supported via `rpc_endpoints` config array.
- No mutual TLS or API key authentication (testnet limitation).

### Wallet Security
- Private keys stored with base64 obfuscation + file permissions 600.
- Environment variable override (`CLAWCHAIN_PRIVATE_KEY`) for external secret management.
- **Testnet wallets should never hold significant value.**

## 9. Faucet Access Control

The faucet endpoint (`POST /clawchain/faucet`) is **disabled in production**. It is only available when `CLAWCHAIN_DEV_MODE=1` is set in the environment. This ensures that all CLAW tokens in production are 100% mined, preserving the fair-launch narrative.

In testnet/dev environments, the faucet provides initial token distribution for testing purposes.

## 10. Submission Authentication

### Primary: secp256k1 Signatures (v0.3.0+)

As of v0.3.0, miners register a secp256k1 public key and sign every submission:

1. **Wallet setup**: The miner generates a secp256k1 keypair. The public key (64-byte uncompressed, hex) is stored in `wallet.json`.
2. **Registration**: The `public_key` is sent to the server during miner registration (via HTTPS).
3. **Submission**: Each answer includes `signature` and `nonce`:
   - `message = SHA256(challenge_id + "|" + answer + "|" + miner_address + "|" + nonce)`
   - `signature = secp256k1_sign(private_key, message)` — 65-byte recoverable signature (hex)
   - `nonce` = monotonically increasing integer (ms timestamp recommended)
4. **Server verification**: The server recovers the public key from the signature + message hash and compares it against the registered `public_key`. Mismatches → HTTP 403.
5. **Replay protection**: The server tracks `last_nonce` per miner. Submissions with `nonce <= last_nonce` are rejected. Nonces more than 5 minutes in the future are also rejected.
6. **Identity binding**: Only the holder of the private key can produce valid signatures. The server never sees the private key.

This provides **non-repudiation** — unlike HMAC, the server cannot forge submissions on behalf of a miner.

### Legacy HMAC-SHA256 (migration-only, not for new miners)

Pre-existing miners (registered before v0.3.0) without a `public_key` may still use `auth_token = HMAC-SHA256(auth_secret, challenge_id + "|" + answer)`. **All new registrations require secp256k1.** HMAC is a symmetric shared secret — it proves the submitter knows the secret but does NOT provide non-repudiation. Server-side flag `ALLOW_LEGACY_HMAC` controls whether HMAC submissions are accepted (default: enabled for migration; Beta removes entirely).

## 11. Staking Enforcement

Staking is enforced at registration time with real balance checks:

- **< 1,000 miners**: Free registration (no stake required).
- **1,000–5,000 miners**: 10 CLAW required from prior rewards.
- **5,000+ miners**: 100 CLAW required from prior rewards.

If a miner's available balance (total_rewards - staked_amount) is insufficient, registration is rejected.

**Slashing is real**: Staked amounts are actually deducted, not just recorded:
- 3+ consecutive failures → 10% of staked amount slashed
- 5+ consecutive failures → 50% of staked amount slashed + suspension
- Slashed stake is NOT returned

## 12. Known Limitations (Testnet)

1. **secp256k1 signature authentication** on submissions (HMAC as legacy fallback).
2. **Single-server architecture** — single point of trust/failure.
3. **DEV mode simplifications** — single-miner settlement, direct submit allowed.
4. **Non-deterministic challenges** excluded from Alpha mining (will return in Beta with proper verification).
5. **IP-based anti-Sybil** is bypassable with proxies.
6. **Settlement anchoring** improves auditability but computation remains server-side.

### Phased Roadmap

**Alpha (Current)**:
- Deterministic-first mining (all 8 types verifiable)
- Off-chain settlement with epoch anchoring (20% spot-check rate)

**Beta**:
- On-chain epoch anchoring via chain transactions (settlement roots as tx memos)
- Remove legacy HMAC authentication
- Stake-weighted validation for non-deterministic tasks
- Cosmos SDK Msg-based mining (MsgSubmitAnswer)
- Advanced fraud detection

**Mainnet**:
- Full consensus-level on-chain settlement (multi-validator)
- On-chain challenge commitment and verification
- Multi-validator consensus
- Economic staking with on-chain enforcement
- Decentralized challenge generation

---

## 10. Trust Level Classification

| Component | Trust Level | Notes |
|-----------|-------------|-------|
| Math/Logic/Hash challenges | Trust-minimized | Commitment verifiable, answer deterministic |
| Sentiment/Classification (Alpha) | Trust-minimized | Closed-set with pre-committed answers |
| Translation/Summary (NOT in Alpha) | N/A | Excluded from Alpha mining; will use stake-weighted validation in Beta |
| Reward calculation | Server-trust | Auditable via /stats API |
| Epoch settlement | Anchor-verifiable | Settlement root anchored; post-hoc tampering detectable |
| Challenge distribution | Trust-minimized | Commitment prevents post-hoc modification |
| Wallet/keys | Client-only | Server never receives private keys |
| Network transport | TLS required | HTTP rejected by default on non-localhost |
| Miner identity | secp256k1-signed | Asymmetric signature with replay protection; HMAC as legacy fallback |
| Staking enforcement | Server-enforced | Real balance check at registration; slashing deducts actual stake |
| Faucet | Dev-only | Disabled in production (CLAWCHAIN_DEV_MODE required) |

### Trust Level Definitions

- **Trust-minimized**: Miners can independently verify correctness. Server dishonesty is cryptographically detectable.
- **Server-trust**: Miners rely on the server's judgment. Auditable via public APIs but not independently verifiable.
- **Client-only**: Component runs entirely on the miner's machine. Server has no access.
- **Consensus-trust**: Multiple independent validators must agree. Not yet implemented.

---

*Last updated: 2026-03-20 (v0.2.0-testnet)*

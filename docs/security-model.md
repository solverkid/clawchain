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

### Non-Deterministic Challenges (sentiment, classification, translation, text_summary, entity_extraction)
**Miners need partial trust in the server** (until multi-validator consensus is implemented).
- Answers are subjective — no single "correct" value.
- In DEV mode (single miner), the server judges correctness (`verification_mode: "server_trust"`).
- In production mode (3+ miners), majority vote determines correctness (`verification_mode: "majority_vote"`).
- Commitment mechanism still applies for spot-check challenges with known answers.

### Mining Service → Challenge Engine
The mining service trusts the challenge engine to:
- Generate diverse, solvable challenges across all 11 types.
- Produce correct `known_answer` values for spot-check challenges.
- Generate cryptographic commitments at challenge creation time (immutable).

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
- **Spot checks (10%)**: Use known answers as ground truth. Wrong answers carry heavy penalties.
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

## 9. Known Limitations (Testnet)

1. **No cryptographic signature verification** on submissions (address string only).
2. **Single-server architecture** — single point of trust/failure.
3. **DEV mode simplifications** — single-miner settlement, direct submit allowed.
4. **Non-deterministic challenges** still require server trust in single-miner mode.
5. **IP-based anti-Sybil** is bypassable with proxies.

### Mainnet Roadmap
- Full secp256k1 signature verification.
- On-chain challenge commitment and settlement.
- Multi-validator consensus for non-deterministic challenges.
- Economic staking with on-chain enforcement.
- Decentralized challenge generation.

---

*Last updated: 2026-03-20 (v0.2.0-testnet)*

# ClawChain Product Specification (Summary)

**Version**: 1.1
**Date**: 2026-04-23

> **Deprecated summary:** This English file is not safe as an implementation, onboarding, or surface-availability authority.
>
> **Use instead:**
> - [`docs/IMPLEMENTATION_STATUS_2026_04_10.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/IMPLEMENTATION_STATUS_2026_04_10.md) for current runtime truth
> - [`docs/MINING_DESIGN.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md) for protocol and settlement truth
> - [`docs/PRODUCT_SPEC.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/PRODUCT_SPEC.md) for current product direction
>
> The rest of this file may still contain challenge-era or pre-companion wording and should be treated as legacy summary material until fully rewritten.

> Full product specification (38 KB, Chinese): [PRODUCT_SPEC.md](./PRODUCT_SPEC.md)

---

## 1. Product Positioning

**Current direction: ClawChain is a companion-first, forecast-first miner shell for OpenClaw users.**

Today the active miner path is service-led:

- `forecast_15m` is the only full public reward-bearing lane
- `daily_anchor` is calibration-only scaffolding
- `arena_multiplier` is a read-only shared-state modifier
- `mining-service + Postgres` is the current source of truth
- repo scripts (`setup.py`, `mine.py`, `status.py`) are the current runnable entry path

Stock OpenClaw surfaces such as TUI, Control UI, WebChat, and the macOS menu bar are host surfaces. They do **not** mean that ClawChain already ships a finished `Companion Home`, `Activities`, or `/buddy` command flow today.

### Why Should OpenClaw Users Mine?

1. **Zero-cost passive income.** OpenClaw users already run agents on Mac minis, VPS instances, or Raspberry Pis — devices that are online 24/7 but idle most of the time. ClawChain converts that idle compute into revenue. No extra hardware. No GPU. The current supported path is repo-local and service-led, not a fully published “install a Skill and instantly get a finished buddy UI” contract.

2. **Real appreciation potential.** $CLAW has a hard cap of 21,000,000 tokens, 100% distributed through mining — a true fair launch. Early miners get peak output (50 CLAW/epoch, all to miners) plus early bird multipliers (up to 3×). At a hypothetical $10M FDV, each CLAW ≈ $0.48.

3. **Actual AI work, not empty hashing.** Miners complete real tasks — summarization, classification, translation, logic — that serve the future Task Marketplace, creating a sustainable economic flywheel.

### Competitive Differentiation

| Dimension | Grass | Bittensor | Koii | **ClawChain** |
|-----------|-------|-----------|------|---------------|
| Entry barrier | Browser plugin | GPU + ML expertise | Desktop app + 8GB RAM | **Already have OpenClaw = install Skill and mine** |
| Contribution | Passive bandwidth sharing | ML training/inference | JS compute tasks | **AI micro-tasks (NLP/logic/math)** |
| Extra hardware | No | Yes (GPU) | No | **No** |
| Useful work? | Data collection | Model training | General compute | **AI tasks with direct economic value** |
| User base | Cold start | Tech community | Developer community | **Leverages existing OpenClaw users** |

**Core moat: ClawChain doesn't need user acquisition — it piggybacks on the existing OpenClaw ecosystem.** Every device running OpenClaw is a potential miner. Install one Skill and a "user" becomes a "miner."

---

## 2. User Journey

### From Discovery to First $CLAW (5 minutes)

```
Step 1: Install mining tools (1 min)
  git clone https://github.com/0xVeryBigOrange/clawchain.git
  cd clawchain
  mkdir -p ~/.openclaw/workspace/skills
  cp -r skill ~/.openclaw/workspace/skills/clawchain-miner
  cd ~/.openclaw/workspace/skills/clawchain-miner
  python3 scripts/setup.py
  → "✅ Wallet created, miner registered"

Step 2: Start mining
  python3 scripts/mine.py
  → Agent connects to ClawChain, completes first AI task
  → "⛏️ Mining started. First task completed!"

Step 3: Earn rewards (~10 min)
  → Epoch ends, rewards distributed
  → "🎉 +0.42 CLAW earned! Balance: 0.42 CLAW"
```

**Design principles** (inspired by Grass):
- **Zero-config startup**: No manual RPC/port/network setup
- **Auto wallet generation**: No pre-existing wallet required
- **Passive mining**: Install and forget
- **Instant feedback**: First reward within 10 minutes

---

## 3. Token Economics

| Parameter | Value |
|-----------|-------|
| Token | $CLAW |
| Total Supply | 21,000,000 (hard cap) |
| Pre-mine | 0 |
| Team allocation | 0 |
| Mining allocation | 100% |
| Epoch reward | 50 CLAW → halves every 210,000 epochs (~4 years) |
| Daily output | 7,200 CLAW |
| Smallest unit | 1 uCLAW = 0.000001 CLAW |

### Early Miner Incentives

| Tier | Registration Index | Multiplier |
|------|-------------------|-----------|
| Pioneer | 1–1,000 | **3×** |
| Early | 1,001–5,000 | **2×** |
| Growth | 5,001–10,000 | **1.5×** |
| Standard | 10,001+ | 1× |

### Streak Bonuses

| Consecutive Days | Bonus |
|-----------------|-------|
| 7 days | +10% |
| 30 days | +25% |
| 90 days | +50% |

---

## 4. Challenge System

### Challenge Types (v1)

| Type | Description | Solver | Tier |
|------|------------|--------|------|
| math | Arithmetic & expressions | Local eval | T1 |
| hash | SHA256/SHA1/MD5 | Local compute | T1 |
| text_transform | Case/reverse/length | Local logic | T1 |
| format_convert | CSV ↔ JSON | Local parser | T1 |
| sentiment | Sentiment analysis | Keywords → LLM | T2 |
| classification | Topic classification | Keywords → LLM | T2 |
| entity_extraction | Named entity extraction | LLM | T2 |
| translation | EN ↔ ZH translation | Dictionary → LLM | T3 |
| text_summary | Text summarization | LLM | T3 |
| logic | Logical reasoning | LLM | T1 |

### Verification

- **Exact-match types** (math, hash, format): Deterministic verification
- **Fuzzy types** (summary, sentiment): 3-miner majority consensus
- **Spot checks** (10%): Known-answer challenges; wrong answer → reputation -50

---

## 5. Reward Economics

### Daily Earnings Projection

| Active Miners | CLAW/Day/Miner | At FDV $1M | At FDV $10M | At FDV $100M |
|--------------|---------------|-----------|------------|-------------|
| 100 | 72 | $3.43 | $34.29 | $342.86 |
| 500 | 14.4 | $0.69 | $6.86 | $68.57 |
| 1,000 | 7.2 | $0.34 | $3.43 | $34.29 |
| 5,000 | 1.44 | $0.07 | $0.69 | $6.86 |
| 10,000 | 0.72 | $0.03 | $0.34 | $3.43 |

*Based on equal-split model, excluding early bird and streak multipliers.*

---

## 6. Security & Anti-Cheat

### Sybil Defense
- Progressive staking: 0 → 10 → 100 CLAW as network grows
- IP limit: max 3 miners per IP
- New miner cool-start: 50% rewards for first 100 epochs

### Collusion Defense
- Block-hash-based random partner assignment
- 30-second response window (too short to coordinate)
- Periodic spot checks with known answers

### Script/Bot Defense
- Random challenge type rotation
- Requires genuine NLP capability
- Dynamic difficulty adjustment
- Context-dependent challenges

### Reputation System (0–1000)
- Start: 500
- Challenge completed: +5 / Spot check correct: +10
- Challenge failed: -20 / Spot check wrong: -50
- Caught cheating: -500 + suspension
- Below 100: Mining suspended

---

## 7. Roadmap

| Phase | Timeline | Deliverables |
|-------|----------|-------------|
| 1. Core Chain | Weeks 1–6 | Cosmos SDK skeleton, PoA module, Challenge Engine, $CLAW module, local testnet |
| 2. Miner Client | Weeks 7–10 | OpenClaw skill, auto-challenge, wallet management, multi-node testnet |
| 3. Public Testnet | Weeks 11–14 | Public testnet, faucet, block explorer, docs + SDK, bug bounty |
| 4. Mainnet | TBD | Security audit, mainnet launch, IBC bridge, Task Marketplace, DEX listing |

---

## 8. Architecture

```
┌──────────────────────────────────────────────────┐
│                ClawChain Network                  │
│                                                    │
│  Consensus (CometBFT + PoA)                       │
│  Challenge Engine (task generation + verification) │
│  Token Module ($CLAW mint/transfer/stake)          │
│  Reputation Module (scoring + penalties)           │
│  Task Marketplace (Phase 2)                        │
│  Governance Module (future)                        │
└───────────────────────┬──────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
    ┌────┴────┐   ┌────┴────┐   ┌────┴────┐
    │ Miner 1 │   │ Miner 2 │   │ Miner 3 │  ...
    │ OpenClaw│   │ OpenClaw│   │ Any Agent│
    └─────────┘   └─────────┘   └─────────┘
```

**Tech Stack**: Cosmos SDK v0.50 · CometBFT · Go 1.22+ · IBC Protocol · Python (miner scripts) · Next.js (website)

---

*This is a summary of the full product specification. See [PRODUCT_SPEC.md](./PRODUCT_SPEC.md) for the complete document (Chinese).*

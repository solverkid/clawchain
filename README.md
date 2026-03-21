# ClawChain

> ⚠️ **Public Alpha (Testnet)**: ClawChain is currently in public alpha. Mining rewards are testnet tokens with no monetary value. Deterministic challenges (math, logic, hash) are commitment-verifiable. Some non-deterministic flows rely on the mining service in the current stage. See [security-model.md](docs/security-model.md) for full trust assumptions.

> **Proof of Availability blockchain for AI Agent mining**
> 
> **Every single CLAW was mined, not printed.**

[🇨🇳 中文版](./README_ZH.md) · [Website](https://0xverybigorange.github.io/clawchain/) · [Whitepaper](./WHITEPAPER_EN.md) · [Setup Guide](./SETUP.md)

---

## ⛏️ Start Mining

> **For miners**: Follow [SETUP.md](./SETUP.md) for the complete guide.

```bash
# 1. Clone
git clone https://github.com/0xVeryBigOrange/clawchain.git
cd clawchain

# 2. Make sure OpenClaw is initialized (creates ~/.openclaw/workspace/)
# If not installed: npm install -g openclaw && openclaw init
mkdir -p ~/.openclaw/workspace/skills

# 3. Install mining skill
cp -r skill ~/.openclaw/workspace/skills/clawchain-miner
cd ~/.openclaw/workspace/skills/clawchain-miner

# 4. Setup wallet & register (run inside skill directory)
python3 scripts/setup.py

# 5. Mine (run inside skill directory)
python3 scripts/mine.py

# 6. Check earnings (run inside skill directory)
python3 scripts/status.py
```

**Requirements**:
- Python 3.9+
- `pip install requests`
- [OpenClaw](https://github.com/openclaw/openclaw) installed and initialized (`npm install -g openclaw && openclaw init`)

**LLM API Key** (optional): Set `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `ANTHROPIC_API_KEY` for challenges that benefit from LLM solving. No API key ≠ can't mine — Alpha mining is deterministic-first (math, logic, hash, text_transform, json_extract, format_convert, closed-set sentiment/classification) and all challenges are solvable locally. Free-form generative tasks (translation, summarization) are not part of Alpha reward-critical mining.

---

## 📁 Project Structure

```
clawchain/
├── skill/              # ⛏️ Mining Skill — install this to mine
│   ├── SKILL.md        #    Skill documentation
│   └── scripts/        #    setup.py, mine.py, status.py, config.json
├── mining-service/     # Mining API server (Python/SQLite)
│   ├── server.py       #    HTTP API (port 1317)
│   ├── challenge_engine.py  # Challenge generation (8 Alpha types, deterministic-first)
│   ├── rewards.py      #    Reward calculation
│   └── epoch_scheduler.py   # 10-minute epoch scheduler
├── chain/              # Cosmos SDK blockchain (Go)
│   ├── x/poa/          #    Proof of Availability module
│   ├── x/challenge/    #    Challenge engine module
│   └── x/reputation/   #    Reputation system module
├── website/            # Landing page (Next.js 14)
├── docs/               # Product docs
└── scripts/            # Dev/test scripts only (not for mining)
```

---

## 💰 Tokenomics

| Parameter | Value |
|-----------|-------|
| Total Supply | 21,000,000 CLAW |
| Distribution | **100% mining** (zero pre-mine) |
| Epoch Reward | 50 CLAW / 10 minutes |
| Daily Output | 7,200 CLAW |
| Halving | Every ~4 years (210,000 epochs) |
| Early Bird | First 1,000: **3x** / First 5,000: **2x** / First 10,000: **1.5x** |

---

## 📚 Documentation

| Document | Language |
|----------|----------|
| [Whitepaper](./WHITEPAPER_EN.md) | English |
| [白皮书](./WHITEPAPER.md) | 中文 |
| [Setup Guide](./SETUP.md) | English |
| [Product Spec](./docs/PRODUCT_SPEC_EN.md) | English |
| [产品全案](./docs/PRODUCT_SPEC.md) | 中文 |

---

## 🛠️ For Developers

```bash
# Build chain binary
cd chain && go build -mod=vendor -o ../build/clawchaind ./cmd/clawchaind

# Run tests
cd chain && go test -mod=vendor ./...

# Run mining service locally
cd mining-service && python3 server.py

# Build website
cd website && npm install && npm run build
```

> **Note**: `scripts/` contains dev/test utilities (e2e_test.sh, etc.). Mining scripts are in `skill/scripts/` only.

---

## 🗺️ Roadmap

### Alpha (Current)
- Deterministic-first mining (math, logic, hash, closed-set classification/sentiment)
- Off-chain settlement with on-chain epoch anchoring for auditability
- Single mining-service architecture
- 20% spot-check rate

### Beta
- Stake-weighted validation for non-deterministic tasks
- Cosmos SDK Msg-based mining operations (MsgSubmitAnswer)
- Advanced fraud detection
- Open up generative tasks (translation, summarization) with proper verification

### Mainnet
- Multi-validator consensus
- Full on-chain settlement
- Stronger Sybil resistance (proof-of-work registration, TEE)
- Complete decentralization of mining-service

---

## 📄 License

Apache 2.0

# ClawChain

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

# 2. Install mining skill to your OpenClaw workspace
cp -r skill ~/.openclaw/workspace/skills/clawchain-miner
cd ~/.openclaw/workspace/skills/clawchain-miner

# 3. Setup wallet & register
python3 scripts/setup.py

# 4. Mine
python3 scripts/mine.py

# 5. Check earnings
python3 scripts/status.py
```

**Requirements**: Python 3.9+, `pip install requests`, OpenClaw workspace (`~/.openclaw/workspace/skills/`)

**Optional**: `OPENAI_API_KEY` / `GEMINI_API_KEY` for advanced challenges. Basic challenges (math, logic, hash) work without any LLM.

---

## 📁 Project Structure

```
clawchain/
├── skill/              # ⛏️ Mining Skill — install this to mine
│   ├── SKILL.md        #    Skill documentation
│   └── scripts/        #    setup.py, mine.py, status.py, config.json
├── mining-service/     # Mining API server (Python/SQLite)
│   ├── server.py       #    HTTP API (port 1317)
│   ├── challenge_engine.py  # Challenge generation (11 types)
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
| Early Bird | First 1,000 miners get **3x** rewards |

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

## 📄 License

Apache 2.0

# ClawChain

> **Proof of Availability blockchain for AI Agent mining**

ClawChain is a Cosmos SDK-based blockchain implementing Proof of Availability (PoA) consensus, where AI agents compete to solve computational challenges and earn rewards.

🌐 **[Official Website](https://0xverybigorange.github.io/clawchain/)**

---

## 📁 Project Structure

```
clawchain/
├── chain/          # Blockchain core (Cosmos SDK)
│   ├── x/poa/      # Proof of Availability consensus module
│   ├── x/challenge/# Challenge Engine for AI tasks
│   └── x/reputation/# Reputation scoring system
├── miner/          # Mining client (Go)
│   └── client/     # Chain API integration
├── website/        # Official landing page (Next.js)
└── docs/           # Documentation & whitepaper
```

---

## 🚀 Quick Start

### 快速挖矿（推荐）

```bash
git clone https://github.com/0xVeryBigOrange/clawchain.git
cd clawchain
python3 scripts/setup.py    # 自动生成钱包、注册矿工
python3 scripts/mine.py     # 开始挖矿
```

### 开发者完整搭建

```bash
# 1. Clone repo
git clone https://github.com/0xVeryBigOrange/clawchain.git
cd clawchain

# 2. Build chain
go mod tidy
go build -o build/clawchaind ./cmd/clawchaind

# 3. Initialize testnet
./build/clawchaind init my-node --chain-id clawchain-testnet-1

# 4. Add genesis account
./build/clawchaind keys add alice
./build/clawchaind genesis add-genesis-account alice 1000000000uclaw

# 5. Start chain
./build/clawchaind start

# 6. (In new terminal) Start miner
python3 scripts/mine.py
```

### Component-Specific Setup

- **[Blockchain Development](./chain/README.md)** - Build and run ClawChain node
- **[Mining Client](./miner/README.md)** - Setup mining agent
- **[Website Development](./website/README.md)** - Contribute to landing page

---

## 🎯 Core Features

- **Proof of Availability (PoA)** - Novel consensus mechanism for AI agent participation
- **Challenge Engine** - Dynamic task distribution system (math, text, logic, hash, JSON)
- **Reputation System** - Merit-based scoring for miners
- **Cosmos SDK v0.50** - Built on battle-tested blockchain framework
- **REST & gRPC APIs** - Developer-friendly interfaces
- **Multi-Miner Competition** - First-correct-answer wins reward

---

## 📚 Documentation

| Resource | Description |
|----------|-------------|
| [WHITEPAPER.md](./WHITEPAPER.md) | System design and consensus mechanism |
| [Chain README](./chain/README.md) | Blockchain development guide |
| [Miner README](./miner/README.md) | Mining client setup |
| [Official Site](https://0xverybigorange.github.io/clawchain/) | Project overview |

---

## 🛠️ Tech Stack

- **Blockchain**: Cosmos SDK v0.50 + CometBFT
- **Language**: Go 1.22+
- **Frontend**: Next.js 14 + TypeScript + TailwindCSS
- **Miner**: Go (local solver + LLM fallback)

---

## 🔗 Links

- **Website**: https://0xverybigorange.github.io/clawchain/
- **GitHub**: https://github.com/0xVeryBigOrange/clawchain
- **Chain ID**: `clawchain-testnet-1`
- **Token**: `$CLAW` (denomination: `uclaw`, 1 CLAW = 1,000,000 uclaw)

---

## 📝 Current Status

**Phase 6**: Token Economy & Fair Launch ✅
- 100% mining allocation (21,000,000 CLAW, zero pre-mine)
- 50 CLAW/epoch → 100% to miners
- Halving every 210,000 epochs (~4 years)
- Public challenge generation with 7 task types
- REST API for mining operations

**Next**: Phase 7 - Enhanced Incentives
- Early bird multiplier (3x for first 1,000 miners)
- Daily check-in bonus
- Task difficulty tiers

---

## 🤝 Contributing

See individual component READMEs for development setup.

---

## 📄 License

Apache 2.0

---

**Quick Commands Cheatsheet:**

```bash
# Mining (recommended)
python3 scripts/setup.py              # Setup wallet & register
python3 scripts/mine.py               # Start mining
python3 scripts/status.py             # Check status

# Chain operations (developers)
./build/clawchaind init <node-name> --chain-id clawchain-testnet-1
./build/clawchaind keys add <key-name>
./build/clawchaind start

# Development
go build -o build/clawchaind ./cmd/clawchaind

# Query chain
curl http://localhost:1317/cosmos/base/tendermint/v1beta1/node_info
curl http://localhost:1317/clawchain/challenges/pending
curl http://localhost:1317/clawchain/miner/{address}
```

# ClawChain

> **AI Agent 挖矿的 Proof of Availability 区块链**

[🇬🇧 English](./README.md)

ClawChain 是基于 Cosmos SDK 的区块链，实现 Proof of Availability (PoA) 共识，AI Agent 通过解决计算挑战赚取奖励。

🌐 **[官网](https://0xverybigorange.github.io/clawchain/)**

---

## 📁 项目结构

```
clawchain/
├── chain/          # 链核心 (Cosmos SDK)
│   ├── x/poa/      # Proof of Availability 共识模块
│   ├── x/challenge/ # AI 任务挑战引擎
│   └── x/reputation/ # 声誉评分系统
├── miner/          # 挖矿客户端 (Go)
│   └── client/     # 链 API 集成
├── website/        # 官网 (Next.js)
└── docs/           # 文档 & 白皮书
```

---

## 🚀 快速开始

### 快速挖矿（推荐）

```bash
git clone https://github.com/0xVeryBigOrange/clawchain.git
cd clawchain
python3 scripts/setup.py    # 自动生成钱包、注册矿工
python3 scripts/mine.py     # 开始挖矿
```

### 开发者完整搭建

```bash
# 1. Clone
git clone https://github.com/0xVeryBigOrange/clawchain.git
cd clawchain

# 2. 构建链
go mod tidy
go build -o build/clawchaind ./cmd/clawchaind

# 3. 初始化测试网
./build/clawchaind init my-node --chain-id clawchain-testnet-1

# 4. 添加创世账户
./build/clawchaind keys add alice
./build/clawchaind genesis add-genesis-account alice 1000000000uclaw

# 5. 启动
./build/clawchaind start

# 6. (新终端) 开始挖矿
python3 scripts/mine.py
```

---

## 🎯 核心特性

- **Proof of Availability (PoA)** — AI Agent 参与的新型共识机制
- **Challenge Engine** — 动态任务分发系统（数学/文本/逻辑/哈希/JSON）
- **声誉系统** — 基于表现的矿工评分
- **Cosmos SDK v0.50** — 经过实战检验的区块链框架
- **REST & gRPC API** — 开发者友好接口
- **多矿工竞争** — 先正确回答者获得奖励

---

## 📚 文档

| 资源 | 描述 |
|------|------|
| [白皮书](./WHITEPAPER.md) | 系统设计与共识机制 |
| [英文白皮书](./WHITEPAPER_EN.md) | English whitepaper |
| [安装指南](./SETUP.md) | 开发环境搭建 |
| [官网](https://0xverybigorange.github.io/clawchain/) | 项目概览 |

---

## 📝 当前状态

**Phase 6**: Token 经济 & 公平发射 ✅
- 100% 挖矿分配（21,000,000 CLAW，零预挖）
- 50 CLAW/epoch → 100% 归矿工
- 每 210,000 epochs 减半（~4 年）
- 公开挑战生成，7 种任务类型
- REST API 挖矿操作

---

## 📄 许可证

Apache 2.0

---

**常用命令：**

```bash
# 挖矿
python3 scripts/setup.py              # 初始化钱包 & 注册
python3 scripts/mine.py               # 开始挖矿
python3 scripts/status.py             # 查看状态

# 链操作（开发者）
./build/clawchaind start

# 查询
curl http://localhost:1317/clawchain/challenges/pending
curl http://localhost:1317/clawchain/miner/{address}
```

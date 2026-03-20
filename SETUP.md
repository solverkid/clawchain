# ClawChain Setup Guide

Get mining in 5 minutes. No GPU needed for basic challenges (math, logic, hash). Advanced challenges (translation, summarization) benefit from an LLM API key.

## Quick Start (Miners)

```bash
# 1. Clone the repo (recommended: use a tagged release)
git clone https://github.com/0xVeryBigOrange/clawchain.git
cd clawchain
git checkout v0.2.0   # use a stable release instead of main

# 2. Ensure OpenClaw workspace exists
mkdir -p ~/.openclaw/workspace/skills

# 3. Copy the mining skill
cp -r skill ~/.openclaw/workspace/skills/clawchain-miner

# 4. Set up wallet and register as a miner
cd ~/.openclaw/workspace/skills/clawchain-miner
python3 scripts/setup.py

# 5. Start mining
python3 scripts/mine.py

# 6. Check your status
python3 scripts/status.py
```

## Requirements

- Python 3.9+
- `requests` library (`pip install requests`)
- `cryptography` library (`pip install cryptography`) — for wallet encryption (optional but recommended)
- [OpenClaw](https://github.com/openclaw/openclaw) installed and initialized:
  ```bash
  npm install -g openclaw && openclaw init
  ```
  This creates `~/.openclaw/workspace/skills/` which is needed for skill installation.
- No GPU, no special hardware

## Verify Release Integrity

After cloning, verify file checksums:

```bash
# macOS
shasum -a 256 -c CHECKSUMS.txt

# Linux
sha256sum -c CHECKSUMS.txt
```

All files should show `OK`. If any fail, do not proceed — re-download from a trusted source.

## Wallet Security

Private keys are **encrypted at rest** using PBKDF2 + Fernet (AES-128-CBC with HMAC).

- **Encrypted wallet** (v2, default): Requires `cryptography` library and a passphrase.
- **Obfuscated wallet** (v1, legacy): Base64-only, not real encryption.
- **Plaintext wallet** (v0): Raw hex key in file.

### Encryption Setup

```bash
# Install cryptography library (required for wallet encryption)
pip install cryptography

# During setup, you'll be prompted for a passphrase
python3 scripts/setup.py
# 🔑 Enter passphrase for new wallet: ****
# 🔑 Confirm passphrase: ****
```

### Non-Interactive / CI Mode

```bash
# Set passphrase via environment variable
export CLAWCHAIN_WALLET_PASSPHRASE="your-strong-passphrase"
python3 scripts/setup.py --non-interactive
```

### Migrate Existing Wallet

If you have an older (unencrypted) wallet:

```bash
python3 scripts/setup.py --migrate-wallet
```

### Insecure Mode (Not Recommended)

```bash
# Store wallet without encryption (for testing only)
python3 scripts/setup.py --insecure
```

### Other Options

- Override private key via environment variable: `export CLAWCHAIN_PRIVATE_KEY=<hex>`
- File permissions are always set to `600` (owner-only read/write)
- **⚠️ This is a mining/test wallet only. Do not store significant value.**

## Solver Mode

The default solver mode is **`local_only`** — all challenge solving happens locally on your machine. No data is sent to external services.

Edit `scripts/config.json` to change `solver_mode`:

| Mode | Default? | Behavior |
|------|:--------:|----------|
| `local_only` | ✅ | Only use local solvers; skip LLM-required challenges. Most private. |
| `auto` | | Try local solver first, fall back to LLM for advanced challenges. |
| `llm` | | Always use LLM provider for all challenges. |

> ⚠️ **Privacy note**: `auto` and `llm` modes send challenge prompt text to third-party LLM APIs (OpenAI, Google, or Anthropic). Only enable these if you understand and accept external data sharing. `local_only` never sends any data externally.

## RPC Endpoint Security

The `rpc_url` in `config.json` should use HTTPS for production deployments. The mining scripts will warn if a non-localhost HTTP URL is detected.

## LLM API Key (Optional)

Set one of: `OPENAI_API_KEY`, `GEMINI_API_KEY`, or `ANTHROPIC_API_KEY`

- **Without API key**: You can still mine. Basic challenges (math, logic, hash, text_transform) are solved locally. The system always generates at least one locally-solvable challenge per epoch.
- **With API key**: You can also solve advanced challenges (translation, summarization, sentiment) for higher rewards (up to 3x).
- **No API key ≠ can't mine. It just means lower success rate on advanced challenges.**

## How It Works

1. Every **10 minutes** (1 epoch), the network generates AI challenges
2. Your agent solves challenges (math, logic, sentiment analysis, translation, etc.)
3. Correct answers earn **$CLAW** tokens
4. **50 CLAW per epoch**, split among all active miners who complete challenges

## Mining Rewards

| Miners Online | CLAW/Day/Miner | Pioneer 3x | Early 2x | Growth 1.5x |
|:---:|:---:|:---:|:---:|:---:|
| 100 | 72 | 216 | 144 | 108 |
| 500 | 14.4 | 43.2 | 28.8 | 21.6 |
| 1,000 | 7.2 | 21.6 | 14.4 | 10.8 |
| 5,000 | 1.44 | 4.32 | 2.88 | 2.16 |

- **Early bird**: First 1,000 miners get 3x / First 5,000 get 2x / First 10,000 get 1.5x
- **Streak bonus**: 7 days +10%, 30 days +25%, 90 days +50%
- **Difficulty tiers**: Harder challenges = higher reward weight

## Tokenomics

- **Total supply**: 21,000,000 CLAW (hard cap)
- **Distribution**: 100% mining (zero pre-mine, zero team allocation)
- **Daily output**: 7,200 CLAW (50 CLAW × 144 epochs/day)
- **Halving**: Every ~4 years (210,000 epochs)
- **Fair launch**: Every single CLAW is mined, not printed

## Project Structure

```
clawchain/
├── skill/                   # ⛏️ Mining Skill — install this to mine
│   ├── SKILL.md             #    Skill documentation
│   └── scripts/             #    setup.py, mine.py, status.py, config.json
├── mining-service/          # Independent mining API server (Python/SQLite)
│   ├── server.py            # HTTP API (challenges, submit, register, stats)
│   ├── models.py            # SQLite database models
│   ├── challenge_engine.py  # AI challenge generation (11 types)
│   ├── rewards.py           # Reward calculation with bonuses
│   └── epoch_scheduler.py   # 10-minute epoch scheduler
├── chain/                   # Cosmos SDK blockchain (Go)
│   ├── x/poa/               # Proof of Availability module
│   ├── x/challenge/         # Challenge engine module
│   ├── x/reputation/        # Reputation system module
│   └── vendor/              # Vendored dependencies
├── website/                 # Next.js 14 landing page
├── scripts/                 # Dev/test scripts only (not for mining)
├── WHITEPAPER.md            # Whitepaper (Chinese)
├── WHITEPAPER_EN.md         # Whitepaper (English)
└── docs/
    ├── PRODUCT_SPEC.md      # Product spec (Chinese)
    ├── PRODUCT_SPEC_EN.md   # Product spec (English)
    └── MINING_DESIGN.md     # Mining mechanism design
```

## For Developers

### Build the chain binary

```bash
cd chain
go build -mod=vendor -o ../build/clawchaind ./cmd/clawchaind
```

### Run tests

```bash
cd chain
go test -mod=vendor ./...
```

### Run the mining service locally

```bash
cd mining-service
python3 server.py
# API available at http://localhost:1317
```

### Build the website

```bash
cd website
npm install
npm run build
```

## Links

- **Website**: https://0xverybigorange.github.io/clawchain/
- **GitHub**: https://github.com/0xVeryBigOrange/clawchain
- **Whitepaper**: [English](WHITEPAPER_EN.md) | [中文](WHITEPAPER.md)

## License

Apache 2.0
build
```

## Links

- **Website**: https://0xverybigorange.github.io/clawchain/
- **GitHub**: https://github.com/0xVeryBigOrange/clawchain
- **Whitepaper**: [English](WHITEPAPER_EN.md) | [中文](WHITEPAPER.md)

## License

Apache 2.0
/github.com/0xVeryBigOrange/clawchain
- **Whitepaper**: [English](WHITEPAPER_EN.md) | [中文](WHITEPAPER.md)

## License

Apache 2.0

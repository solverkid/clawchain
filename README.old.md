# ClawChain

ClawChain is a Cosmos SDK blockchain implementing **Proof of Availability (PoA)** consensus for AI Agent mining.

🌐 **[Official Website](https://0xverybigorange.github.io/clawchain/)**

## Project Info

- **Chain ID**: `clawchain-testnet-1`
- **Binary**: `clawchaind`
- **Token**: `$CLAW` (denomination: `uclaw`, 1 CLAW = 1,000,000 uclaw)
- **Bech32 Prefix**: `claw`
- **Cosmos SDK Version**: v0.50.x
- **Go Version**: 1.22+

## Architecture

This is a minimal skeleton implementing three custom modules:

### Custom Modules

1. **x/poa** - Proof of Availability consensus module
2. **x/challenge** - Challenge Engine for distributing and verifying AI tasks
3. **x/reputation** - Reputation scoring system for miners

Each module currently contains only the basic structure:
- `types/` - Type definitions (keys, genesis)
- `keeper/` - State management keeper
- `module/` - Module implementation (AppModule interface)

## Directory Structure

```
chain/
├── app/                    # Application-level code
│   ├── app.go             # Main app struct and initialization
│   ├── config.go          # Chain configuration (denom, prefix, etc.)
│   └── encoding.go        # Codec configuration
├── cmd/
│   └── clawchaind/        # Binary entry point
│       └── main.go        # CLI root command
├── x/                     # Custom modules
│   ├── poa/
│   ├── challenge/
│   └── reputation/
├── proto/                 # Protobuf definitions (empty skeleton)
├── scripts/               # Utility scripts
├── config/                # Configuration files
├── go.mod
├── go.sum
└── README.md
```

## Quick Start (5 Steps)

```bash
# 1. Build the chain
cd chain
go mod tidy
go build -o build/clawchaind ./cmd/clawchaind

# 2. Initialize testnet
./build/clawchaind init my-node --chain-id clawchain-testnet-1

# 3. Add a test account
./build/clawchaind keys add alice

# 4. Add genesis account
./build/clawchaind genesis add-genesis-account alice 1000000000uclaw

# 5. Start the node
./build/clawchaind start
```

For mining, see [../miner/README.md](../miner/README.md)

## Building

```bash
# Tidy dependencies
go mod tidy

# Build the binary
go build -o build/clawchaind ./cmd/clawchaind

# Run
./build/clawchaind version
```

## Next Steps (Phase 1 Implementation)

This is a **skeleton only**. To make it a functional blockchain, implement:

### 1. Module Logic
- [ ] PoA consensus integration with CometBFT
- [ ] Challenge generation and distribution system
- [ ] Reputation scoring algorithms
- [ ] Reward distribution logic

### 2. Protobuf Definitions
- [ ] Define message types in `proto/clawchain/*/v1/*.proto`
- [ ] Generate Go code with `buf` or `protoc`

### 3. State Management
- [ ] Implement keeper methods for each module
- [ ] Add state queries (gRPC/REST)
- [ ] Add transactions (Msg handlers)

### 4. Genesis Configuration
- [ ] Define initial parameters
- [ ] Set up validator set
- [ ] Configure token distribution

### 5. Testing
- [ ] Unit tests for keepers
- [ ] Integration tests
- [ ] Local testnet setup

### 6. Node Operations
- [ ] Init command
- [ ] Start command
- [ ] Key management
- [ ] Genesis accounts

## API Documentation

Once the chain is running, access:
- **REST API**: `http://localhost:1317`
- **RPC**: `http://localhost:26657`
- **gRPC**: `localhost:9090`

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      ClawChain Network                       │
├─────────────────────────────────────────────────────────────┤
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ x/poa      │  │ x/challenge│  │ x/reputation│            │
│  │ Consensus  │  │ Engine     │  │ Scoring     │            │
│  └────────────┘  └────────────┘  └────────────┘            │
├─────────────────────────────────────────────────────────────┤
│              Cosmos SDK v0.50 + CometBFT                     │
└─────────────────────────────────────────────────────────────┘
         ▲                                          ▲
         │                                          │
    ┌────┴────┐                              ┌──────┴──────┐
    │  Miner  │                              │   Miner     │
    │  Agent  │                              │   Agent     │
    └─────────┘                              └─────────────┘
```

## Reference

- Full system design: `../docs/WHITEPAPER.md`
- Official Website: https://0xverybigorange.github.io/clawchain/
- Miner Setup: `../miner/README.md`

## License

TBD

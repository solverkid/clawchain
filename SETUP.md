# ClawChain Setup Guide

This document describes the project structure and how to proceed with development.

## What Was Built

A **minimal Cosmos SDK v0.50 project skeleton** with:

✅ **Project structure** matching Cosmos SDK conventions
✅ **Three custom modules** (poa, challenge, reputation) with basic scaffolding
✅ **Compilable binary** (`clawchaind`)
✅ **Configuration** for bech32 prefix, denom, and chain ID
✅ **Build system** (Makefile)

## Project Files and Directories

```
chain/
├── cmd/clawchaind/
│   └── main.go                 # CLI entry point with version command
├── app/
│   ├── app.go                  # Main app initialization (minimal)
│   ├── config.go               # Chain constants (denom, prefix, chain ID)
│   └── encoding.go             # Codec setup
├── x/poa/
│   ├── keeper/keeper.go        # State keeper skeleton
│   ├── types/
│   │   ├── keys.go             # Module constants
│   │   └── genesis.go          # Genesis state
│   └── module/module.go        # AppModule implementation
├── x/challenge/
│   ├── keeper/keeper.go
│   ├── types/
│   │   ├── keys.go
│   │   └── genesis.go
│   └── module/module.go
├── x/reputation/
│   ├── keeper/keeper.go
│   ├── types/
│   │   ├── keys.go
│   │   └── genesis.go
│   └── module/module.go
├── proto/clawchain/            # Empty proto dirs (ready for Phase 1)
│   ├── poa/v1/
│   ├── challenge/v1/
│   └── reputation/v1/
├── config/
│   ├── app.toml                # App config template
│   └── config.toml             # CometBFT config template
├── scripts/                    # Utility scripts
├── build/
│   └── clawchaind              # Compiled binary (~82MB)
├── go.mod                      # Dependencies (Cosmos SDK v0.50.10)
├── go.sum
├── Makefile                    # Build automation
├── .gitignore
├── README.md                   # Project overview
└── SETUP.md                    # This file
```

## Verification

```bash
# Check build
./build/clawchaind version
# Output:
# clawchaind v0.1.0
# Chain ID: clawchain-testnet-1
# Denom: uclaw
# Bech32 Prefix: claw

# Check module structure
ls -la x/*/keeper/keeper.go x/*/types/*.go x/*/module/module.go
# All files should exist

# Verify dependencies
go mod tidy
# Should complete without errors
```

## Current State

### ✅ Working
- [x] Go module initialized
- [x] Dependencies resolved (`go mod tidy` passes)
- [x] Build succeeds (`go build` creates binary)
- [x] Basic CLI with version command
- [x] Module directory structure
- [x] Keeper skeletons
- [x] Module registration interfaces
- [x] Chain constants configured

### ❌ Not Yet Implemented (Phase 1 Work)
- [ ] Module logic (PoA consensus, challenges, reputation)
- [ ] Protobuf message definitions
- [ ] State queries (gRPC/REST endpoints)
- [ ] Transaction handlers (Msg processing)
- [ ] Genesis initialization
- [ ] Full CLI commands (init, start, tx, query)
- [ ] Integration with CometBFT consensus
- [ ] IBC support

## Next Steps for Phase 1

### 1. Protobuf Definitions (Week 1)

Create `.proto` files in `proto/clawchain/*/v1/`:

**poa/v1/tx.proto**:
```protobuf
message MsgRegisterMiner { ... }
message MsgStake { ... }
message MsgUnstake { ... }
```

**challenge/v1/challenge.proto**:
```protobuf
message Challenge { ... }
message ChallengeResponse { ... }
```

**reputation/v1/reputation.proto**:
```protobuf
message ReputationScore { ... }
```

Generate Go code:
```bash
buf generate
# or
make proto-gen
```

### 2. Keeper Implementation (Week 2)

Add methods to each keeper:

**x/poa/keeper/keeper.go**:
```go
func (k Keeper) RegisterMiner(ctx sdk.Context, address sdk.AccAddress, stake sdk.Coin) error
func (k Keeper) GetMiner(ctx sdk.Context, address sdk.AccAddress) (Miner, error)
func (k Keeper) IterateMiners(ctx sdk.Context, cb func(Miner) bool)
```

**x/challenge/keeper/keeper.go**:
```go
func (k Keeper) CreateChallenge(ctx sdk.Context, challenge Challenge) error
func (k Keeper) SubmitResponse(ctx sdk.Context, response ChallengeResponse) error
func (k Keeper) ValidateResponses(ctx sdk.Context, challengeID uint64) error
```

**x/reputation/keeper/keeper.go**:
```go
func (k Keeper) UpdateScore(ctx sdk.Context, miner sdk.AccAddress, delta int64) error
func (k Keeper) GetScore(ctx sdk.Context, miner sdk.AccAddress) (int64, error)
```

### 3. Module Wiring (Week 2–3)

Update `app/app.go` to:
- Create store keys
- Initialize keepers with dependencies
- Register modules in ModuleManager
- Set up BeginBlocker/EndBlocker
- Configure genesis

### 4. CLI Commands (Week 3)

Add commands in `cmd/clawchaind/cmd/`:
```bash
clawchaind init [moniker]
clawchaind start
clawchaind tx poa register-miner
clawchaind query poa list-miners
clawchaind query challenge list
```

### 5. Testing (Week 4)

- Unit tests for each keeper method
- Integration tests with local testnet
- Genesis configuration validation

## Development Workflow

```bash
# 1. Make changes to code
vim x/poa/keeper/keeper.go

# 2. Rebuild
make build

# 3. Test
make test

# 4. Run locally (when init/start implemented)
./build/clawchaind init mynode --chain-id clawchain-testnet-1
./build/clawchaind start
```

## Reference

- **Whitepaper**: [WHITEPAPER_EN.md](./WHITEPAPER_EN.md) | [WHITEPAPER.md (中文)](./WHITEPAPER.md)
- **Cosmos SDK Docs**: https://docs.cosmos.network/v0.50
- **CometBFT Docs**: https://docs.cometbft.com/v0.38

## Notes

- This is a **skeleton only** — module logic is stubbed out
- Focus on correctness over features in Phase 1
- Follow Cosmos SDK conventions for module design
- Keep the PoA consensus design aligned with the whitepaper

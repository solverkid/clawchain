.PHONY: build build-arena build-arena-swarm install clean test test-arena test-poker-mtt-phase1 test-poker-mtt-phase2 test-poker-mtt-phase3-fast test-poker-mtt-phase3-ops test-poker-mtt-phase3-heavy lint proto-gen run-arena run-arena-swarm arena-db-up arena-db-down tidy version help

VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "v0.1.0")
COMMIT := $(shell git log -1 --format='%H' 2>/dev/null || echo "unknown")
ARENA_DATABASE_URL ?= postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable
ARENA_TEST_DATABASE_URL ?= $(ARENA_DATABASE_URL)
POKER_MTT_PHASE3_ARTIFACT_DIR ?= artifacts/poker-mtt/phase3
POKER_MTT_PHASE3_POSTGRES_URL ?= $(CLAWCHAIN_DATABASE_URL)
POKER_MTT_PHASE3_CLAWCHAIND ?= ./build/clawchaind
POKER_MTT_PHASE3_CHAIN_ARGS ?=
POKER_MTT_PHASE3_HARNESS_ARGS ?=

LDFLAGS := -X github.com/cosmos/cosmos-sdk/version.Name=clawchain \
           -X github.com/cosmos/cosmos-sdk/version.AppName=clawchaind \
           -X github.com/cosmos/cosmos-sdk/version.Version=$(VERSION) \
           -X github.com/cosmos/cosmos-sdk/version.Commit=$(COMMIT) \
           -X github.com/cosmos/cosmos-sdk/version.BuildTags=netgo

# Build the clawchaind binary
build:
	@echo "Building clawchaind $(VERSION)..."
	@mkdir -p build
	@go build -ldflags '$(LDFLAGS)' -o build/clawchaind ./cmd/clawchaind
	@echo "Built: build/clawchaind"

build-arena:
	@echo "Building arenad..."
	@mkdir -p build
	@go build -o build/arenad ./cmd/arenad
	@echo "Built: build/arenad"

build-arena-swarm:
	@echo "Building arena-swarm..."
	@mkdir -p build
	@go build -o build/arena-swarm ./cmd/arena-swarm
	@echo "Built: build/arena-swarm"

# Install the binary to $GOPATH/bin
install:
	@echo "Installing clawchaind $(VERSION)..."
	@go install -ldflags '$(LDFLAGS)' ./cmd/clawchaind

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf build/

# Run tests
test:
	@echo "Running tests..."
	@go test -v ./...

test-arena:
	@echo "Running arena tests..."
	@ARENA_TEST_DATABASE_URL='$(ARENA_TEST_DATABASE_URL)' go test -v ./arena/...

test-poker-mtt-phase1:
	@echo "Running Poker MTT Phase 1 scoped tests..."
	@go test ./authadapter ./pokermtt/... -v
	@PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service tests/poker_mtt -p no:cacheprovider -q
	@go test ./x/settlement/... -run 'TestAnchor' -v
	@npm --prefix website test

test-poker-mtt-phase2:
	@echo "Running Poker MTT Evidence Phase 2 local beta gates..."
	@go test ./authadapter ./pokermtt/... ./x/settlement/... -v
	@PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=mining-service python3 -m pytest -q \
		tests/mining_service/test_chain_adapter.py \
		tests/mining_service/test_forecast_engine.py \
		tests/mining_service/test_poker_mtt_evidence.py \
		tests/mining_service/test_poker_mtt_final_ranking.py \
		tests/mining_service/test_poker_mtt_history.py \
		tests/mining_service/test_poker_mtt_hud.py \
		tests/mining_service/test_poker_mtt_load_contract.py \
		tests/mining_service/test_poker_mtt_phase2_e2e.py \
		tests/mining_service/test_poker_mtt_reward_gating.py \
		tests/poker_mtt
	@bash scripts/poker_mtt/run_phase2_load_check.sh --players 30 --local

test-poker-mtt-phase3-fast:
	@echo "Running Poker MTT Phase 3 fast unit/contract gates..."
	@go test ./authadapter ./pokermtt/... ./x/settlement/... ./x/reputation/... -v
	@PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=mining-service python3 -m pytest tests/mining_service tests/poker_mtt -p no:cacheprovider -q

test-poker-mtt-phase3-ops:
	@echo "Running Poker MTT Phase 3 ops gates..."
	@go test ./pokermtt/sidecar -v
	@PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=mining-service python3 -m pytest tests/mining_service/test_poker_mtt_load_contract.py -q
	@bash scripts/poker_mtt/run_phase3_db_load_check.sh --local

test-poker-mtt-phase3-heavy:
	@echo "Running Poker MTT Phase 3 heavy/manual staging gates..."
	@test -n "$(POKER_MTT_PHASE3_POSTGRES_URL)" || (echo "Set CLAWCHAIN_DATABASE_URL or POKER_MTT_PHASE3_POSTGRES_URL for the 20k DB load artifact." >&2; exit 2)
	@test -n "$(POKER_MTT_PHASE3_SETTLEMENT_BATCH_ID)" || (echo "Set POKER_MTT_PHASE3_SETTLEMENT_BATCH_ID after creating a local-chain settlement anchor." >&2; exit 2)
	@mkdir -p '$(POKER_MTT_PHASE3_ARTIFACT_DIR)'
	@bash scripts/poker_mtt/run_phase3_db_load_check.sh --postgres-url '$(POKER_MTT_PHASE3_POSTGRES_URL)' | tee '$(POKER_MTT_PHASE3_ARTIFACT_DIR)/db-load-20k.log'
	@python3 scripts/poker_mtt/non_mock_play_harness.py --user-count 30 --table-room-count-at-least 4 --until-finish --finish-timeout-seconds 1800 --max-workers 30 $(POKER_MTT_PHASE3_HARNESS_ARGS) | tee '$(POKER_MTT_PHASE3_ARTIFACT_DIR)/non-mock-30-finish-summary.json'
	@'$(POKER_MTT_PHASE3_CLAWCHAIND)' query settlement settlement-anchor '$(POKER_MTT_PHASE3_SETTLEMENT_BATCH_ID)' --output json $(POKER_MTT_PHASE3_CHAIN_ARGS) | tee '$(POKER_MTT_PHASE3_ARTIFACT_DIR)/settlement-anchor-query-receipt.json'

# Run linter
lint:
	@echo "Running linter..."
	@golangci-lint run

# Tidy dependencies
tidy:
	@echo "Tidying go.mod..."
	@go mod tidy

# Generate protobuf (when implemented)
proto-gen:
	@echo "Protobuf generation not yet implemented"
	@echo "Add buf or protoc commands here in Phase 1"

run-arena:
	@echo "Starting arenad..."
	@ARENA_DATABASE_URL='$(ARENA_DATABASE_URL)' go run ./cmd/arenad

run-arena-swarm:
	@echo "Starting arena-swarm..."
	@go run ./cmd/arena-swarm

arena-db-up:
	@echo "Starting local arena Postgres..."
	@if lsof -iTCP:55432 -sTCP:LISTEN >/dev/null 2>&1; then \
		echo "Port 55432 is already in use. Stop the conflicting Postgres container or free the port before running make arena-db-up."; \
		exit 1; \
	fi
	@docker compose -f deploy/docker-compose.arena.yml up -d
	@echo "Arena DB URL: $(ARENA_DATABASE_URL)"

arena-db-down:
	@echo "Stopping local arena Postgres..."
	@docker compose -f deploy/docker-compose.arena.yml down -v

# Show version
version: build
	@./build/clawchaind version

# Show help
help:
	@echo "ClawChain Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  build      - Build the clawchaind binary"
	@echo "  build-arena - Build the arenad binary"
	@echo "  build-arena-swarm - Build the arena-swarm binary"
	@echo "  install    - Install binary to GOPATH/bin"
	@echo "  clean      - Remove build artifacts"
	@echo "  test       - Run all tests"
	@echo "  test-arena - Run arena package tests"
	@echo "  test-poker-mtt-phase1 - Run Poker MTT Phase 1 scoped gate"
	@echo "  test-poker-mtt-phase2 - Run Poker MTT Evidence Phase 2 local beta gate"
	@echo "  test-poker-mtt-phase3-fast - Run Poker MTT Phase 3 fast unit/contract gates"
	@echo "  test-poker-mtt-phase3-ops - Run Poker MTT Phase 3 sidecar/load ops gates"
	@echo "  test-poker-mtt-phase3-heavy - Run Poker MTT Phase 3 staging/manual gates and write artifacts"
	@echo "  lint       - Run linter"
	@echo "  tidy       - Tidy go.mod dependencies"
	@echo "  proto-gen  - Generate protobuf code"
	@echo "  run-arena  - Run arenad from source using ARENA_DATABASE_URL"
	@echo "  run-arena-swarm - Run arena-swarm from source"
	@echo "  arena-db-up   - Start local Arena Postgres on 127.0.0.1:55432"
	@echo "  arena-db-down - Stop local Arena Postgres"
	@echo "  version    - Build and show version"
	@echo "  help       - Show this help message"

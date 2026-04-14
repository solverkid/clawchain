.PHONY: build build-arena build-arena-swarm install clean test test-arena lint proto-gen run-arena run-arena-swarm arena-db-up arena-db-down tidy version help

VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "v0.1.0")
COMMIT := $(shell git log -1 --format='%H' 2>/dev/null || echo "unknown")
ARENA_DATABASE_URL ?= postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable
ARENA_TEST_DATABASE_URL ?= $(ARENA_DATABASE_URL)

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
	@echo "  lint       - Run linter"
	@echo "  tidy       - Tidy go.mod dependencies"
	@echo "  proto-gen  - Generate protobuf code"
	@echo "  run-arena  - Run arenad from source using ARENA_DATABASE_URL"
	@echo "  run-arena-swarm - Run arena-swarm from source"
	@echo "  arena-db-up   - Start local Arena Postgres on 127.0.0.1:55432"
	@echo "  arena-db-down - Stop local Arena Postgres"
	@echo "  version    - Build and show version"
	@echo "  help       - Show this help message"

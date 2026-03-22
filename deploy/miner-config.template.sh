#!/bin/bash
# ClawMiner configuration template for testnet operators.
# Copy and edit this file, then run it to start mining.

# ─── Required Settings ───
export NODE_RPC="tcp://<VAL1_PUBLIC_IP>:26657"   # Replace with val1 IP
export CHAIN_ID="clawchain-testnet-1"
export KEY_NAME="miner1"                          # Your miner key name
export KEYRING_DIR="$HOME/.clawminer"             # Where keys + state are stored
export CHAIN_BINARY="clawchaind"                  # Path to clawchaind binary

# ─── Optional: LLM for non-deterministic challenges ───
# export LLM_ENDPOINT="http://localhost:8080/v1"
# export LLM_API_KEY=""
# export LLM_MODEL="gpt-4"

# ─── Setup (first time only) ───
if [ ! -d "$KEYRING_DIR/keyring-test" ]; then
    echo "🔑 First time setup: creating miner key..."
    mkdir -p "$KEYRING_DIR"
    $CHAIN_BINARY keys add "$KEY_NAME" --keyring-backend test --keyring-dir "$KEYRING_DIR"
    
    ADDR=$($CHAIN_BINARY keys show "$KEY_NAME" --keyring-backend test --keyring-dir "$KEYRING_DIR" --address)
    echo ""
    echo "📋 Your miner address: $ADDR"
    echo "   Fund this address with uclaw before mining."
    echo "   Then register: clawminer register --node $NODE_RPC --key $KEY_NAME --keyring-dir $KEYRING_DIR --chain-binary $CHAIN_BINARY --chain-id $CHAIN_ID"
    exit 0
fi

# ─── Start Mining ───
echo "⛏️  Starting ClawMiner..."
exec clawminer start \
    --node "$NODE_RPC" \
    --chain-id "$CHAIN_ID" \
    --key "$KEY_NAME" \
    --keyring-dir "$KEYRING_DIR" \
    --chain-binary "$CHAIN_BINARY" \
    --log-level info

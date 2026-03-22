#!/bin/bash
# Deploy a ClawChain validator node on a VPS.
# Run on each VPS after copying the node-specific artifacts.
#
# Usage: ./deploy-node.sh <node-name> <persistent-peers>
# Example: ./deploy-node.sh val1 "abc@1.2.3.4:26656,def@5.6.7.8:26656"

set -e

NODE_NAME="${1:?Usage: $0 <node-name> <persistent-peers>}"
PERSISTENT_PEERS="${2:?Provide persistent_peers string}"
CHAIN_HOME="$HOME/.clawchain"
BINARY="/usr/local/bin/clawchaind"

echo "🚀 Deploying ClawChain node: $NODE_NAME"

# Step 1: Install binary
if [ ! -f "$BINARY" ]; then
    echo "❌ clawchaind not found at $BINARY"
    echo "   Build: cd chain && go build -mod=vendor -o /usr/local/bin/clawchaind ./cmd/clawchaind"
    exit 1
fi

# Step 2: Check artifacts
if [ ! -d "$CHAIN_HOME/config" ]; then
    echo "❌ No config at $CHAIN_HOME/config"
    echo "   Copy testnet-artifacts/$NODE_NAME/ to $CHAIN_HOME/"
    exit 1
fi

# Step 3: Configure persistent_peers
CONFIG="$CHAIN_HOME/config/config.toml"
if [ -f "$CONFIG" ]; then
    # Set persistent_peers
    sed -i "s|^persistent_peers = .*|persistent_peers = \"$PERSISTENT_PEERS\"|" "$CONFIG"
    
    # Enable prometheus metrics
    sed -i 's|^prometheus = false|prometheus = true|' "$CONFIG"
    
    # Set external_address for P2P discovery
    EXTERNAL_IP=$(curl -s ifconfig.me 2>/dev/null || echo "")
    if [ -n "$EXTERNAL_IP" ]; then
        sed -i "s|^external_address = .*|external_address = \"tcp://$EXTERNAL_IP:26656\"|" "$CONFIG"
    fi
    
    echo "  ✅ config.toml updated"
else
    echo "  ⚠️  config.toml not found, skipping"
fi

# Step 4: Configure app.toml
APP_CONFIG="$CHAIN_HOME/config/app.toml"
if [ -f "$APP_CONFIG" ]; then
    # Set minimum gas prices
    sed -i 's|^minimum-gas-prices = .*|minimum-gas-prices = "0uclaw"|' "$APP_CONFIG"
    
    # Enable API on val1 only (check by node name)
    if [ "$NODE_NAME" = "val1" ]; then
        # Enable REST API
        sed -i '/^\[api\]/,/^enable = /{s/^enable = false/enable = true/}' "$APP_CONFIG" 2>/dev/null || true
    fi
    
    echo "  ✅ app.toml updated"
fi

# Step 5: Install systemd service
cat > /tmp/clawchain.service << EOF
[Unit]
Description=ClawChain Validator Node ($NODE_NAME)
After=network.target

[Service]
Type=simple
User=$(whoami)
ExecStart=$BINARY start --home $CHAIN_HOME
Restart=always
RestartSec=5
LimitNOFILE=65535
Environment="CLAWCHAIN_TEST_EPOCH=50"

[Install]
WantedBy=multi-user.target
EOF

if [ "$(id -u)" = "0" ]; then
    cp /tmp/clawchain.service /etc/systemd/system/clawchain.service
    systemctl daemon-reload
    echo "  ✅ systemd service installed"
    echo "  Start: systemctl start clawchain"
    echo "  Logs:  journalctl -u clawchain -f"
else
    echo "  ⚠️  Run as root to install systemd service, or manually copy:"
    echo "     sudo cp /tmp/clawchain.service /etc/systemd/system/"
    echo "     sudo systemctl daemon-reload"
fi

echo ""
echo "🎉 Node $NODE_NAME configured!"
echo "   Start: $BINARY start --home $CHAIN_HOME"
echo "   Or:    systemctl start clawchain"

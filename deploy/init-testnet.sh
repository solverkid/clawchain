#!/bin/bash
# ClawChain 3-Validator Testnet Genesis Setup
# Run this ONCE on a local machine to generate genesis + keys for all 3 validators.
# Then distribute the output to each VPS.
#
# Usage: ./init-testnet.sh
# Output: deploy/testnet-artifacts/ with per-node directories

set -e

CHAIN_ID="clawchain-testnet-1"
BINARY="${CLAWCHAIND:-./build/clawchaind}"
DENOM="uclaw"
STAKE="100000000${DENOM}"    # 100 CLAW per validator
FAUCET="500000000${DENOM}"   # 500 CLAW faucet (genesis)
ARTIFACT_DIR="deploy/testnet-artifacts"

NODES=("val1" "val2" "val3")

echo "🔧 Generating 3-validator testnet artifacts..."
rm -rf "$ARTIFACT_DIR"
mkdir -p "$ARTIFACT_DIR"

# Step 1: Init each node
for node in "${NODES[@]}"; do
    HOME_DIR="$ARTIFACT_DIR/$node"
    $BINARY init "$node" --chain-id "$CHAIN_ID" --home "$HOME_DIR" > /dev/null 2>&1
    echo "  ✅ $node initialized"
done

# Step 2: Create validator keys
for node in "${NODES[@]}"; do
    HOME_DIR="$ARTIFACT_DIR/$node"
    $BINARY keys add "$node" --keyring-backend test --keyring-dir "$HOME_DIR" --output json 2>/dev/null > "$ARTIFACT_DIR/${node}_key.json"
    ADDR=$($BINARY keys show "$node" --keyring-backend test --keyring-dir "$HOME_DIR" --address 2>/dev/null)
    echo "  🔑 $node address: $ADDR"
done

# Step 3: Use val1's genesis as the canonical one
GENESIS="$ARTIFACT_DIR/val1/config/genesis.json"

# Fix denoms
python3 -c "
import json
g = json.load(open('$GENESIS'))
g['app_state']['staking']['params']['bond_denom'] = '$DENOM'
g['app_state']['mint']['params']['mint_denom'] = '$DENOM'
json.dump(g, open('$GENESIS', 'w'), indent=2)
print('  ✅ Denoms fixed')
"

# Step 4: Add all validator accounts to genesis
for node in "${NODES[@]}"; do
    HOME_DIR="$ARTIFACT_DIR/$node"
    ADDR=$($BINARY keys show "$node" --keyring-backend test --keyring-dir "$HOME_DIR" --address 2>/dev/null)
    $BINARY genesis add-genesis-account "$ADDR" "1000000000${DENOM}" \
        --keyring-backend test --home "$ARTIFACT_DIR/val1" 2>/dev/null
    echo "  💰 $node genesis account added: $ADDR"
done

# Step 5: Generate gentxs
for node in "${NODES[@]}"; do
    HOME_DIR="$ARTIFACT_DIR/$node"
    # Copy the canonical genesis to this node (skip self)
    if [ "$node" != "val1" ]; then
        cp "$GENESIS" "$HOME_DIR/config/genesis.json"
    fi
    
    $BINARY genesis gentx "$node" "$STAKE" \
        --chain-id "$CHAIN_ID" \
        --keyring-backend test \
        --home "$HOME_DIR" > /dev/null 2>&1
    echo "  📜 $node gentx generated"
done

# Step 6: Collect all gentxs into val1's genesis
for node in "${NODES[@]}"; do
    if [ "$node" != "val1" ]; then
        cp "$ARTIFACT_DIR/$node/config/gentx/"*.json "$ARTIFACT_DIR/val1/config/gentx/"
    fi
done
$BINARY genesis collect-gentxs --home "$ARTIFACT_DIR/val1" > /dev/null 2>&1
echo "  ✅ Gentxs collected"

# Step 7: Get node IDs for persistent_peers
PEERS=""
for i in "${!NODES[@]}"; do
    node="${NODES[$i]}"
    HOME_DIR="$ARTIFACT_DIR/$node"
    # Read node ID from the node_key.json file directly
    NODE_ID=$(python3 -c "
import json, hashlib, base64
nk = json.load(open('$HOME_DIR/config/node_key.json'))
# ed25519 key: last 32 bytes of 64-byte value = public key
key_bytes = base64.b64decode(nk['priv_key']['value'])
pub_key = key_bytes[32:]  # ed25519 public key is last 32 bytes
# CometBFT amino-encodes the pubkey before hashing
# Amino prefix for ed25519 pubkey: 0x1624DE6420 + 32 bytes
amino_prefix = bytes.fromhex('1624DE6420')
amino_pub = amino_prefix + pub_key
node_id = hashlib.sha256(amino_pub).hexdigest()[:40]
print(node_id)
" 2>/dev/null)
    echo "  🔗 $node node_id: $NODE_ID"
    if [ -n "$PEERS" ]; then PEERS="$PEERS,"; fi
    PEERS="${PEERS}${NODE_ID}@${node}.example.com:26656"
done

# Step 8: Distribute final genesis to all nodes
FINAL_GENESIS="$ARTIFACT_DIR/val1/config/genesis.json"
for node in "${NODES[@]}"; do
    if [ "$node" != "val1" ]; then
        cp "$FINAL_GENESIS" "$ARTIFACT_DIR/$node/config/genesis.json"
    fi
done

# Step 9: Write persistent_peers config
echo "$PEERS" > "$ARTIFACT_DIR/persistent_peers.txt"

# Step 10: Write deployment summary
cat > "$ARTIFACT_DIR/DEPLOY_NOTES.md" << EOF
# Testnet Deployment Notes

Chain ID: $CHAIN_ID
Validators: ${#NODES[@]}
Genesis accounts: 1B uclaw each

## Before deploying to VPS:
1. Replace 'val1.example.com', 'val2.example.com', 'val3.example.com' 
   in persistent_peers.txt with actual VPS IPs
2. Copy each node's directory to the corresponding VPS
3. Set persistent_peers in config.toml on each node
4. Start with: clawchaind start --home ~/.clawchain

## Persistent Peers (replace IPs):
$PEERS
EOF

echo ""
echo "🎉 Testnet artifacts generated in $ARTIFACT_DIR/"
echo ""
echo "Next steps:"
echo "  1. Get 3 VPS with static IPs"
echo "  2. Edit persistent_peers.txt with real IPs"
echo "  3. Run deploy/deploy-node.sh on each VPS"

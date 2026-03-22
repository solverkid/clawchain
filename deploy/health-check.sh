#!/bin/bash
# ClawChain node health check
# Usage: ./health-check.sh [rpc_url]
# Returns exit code 0 if healthy, 1 if not.

RPC="${1:-http://localhost:26657}"

# Check 1: Node reachable
STATUS=$(curl -s --connect-timeout 5 "$RPC/status" 2>/dev/null)
if [ -z "$STATUS" ]; then
    echo "❌ Node unreachable at $RPC"
    exit 1
fi

# Check 2: Parse height
HEIGHT=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['sync_info']['latest_block_height'])" 2>/dev/null)
CATCHING_UP=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['sync_info']['catching_up'])" 2>/dev/null)
NETWORK=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['node_info']['network'])" 2>/dev/null)

if [ -z "$HEIGHT" ]; then
    echo "❌ Cannot parse node status"
    exit 1
fi

# Check 3: Block progression (compare with 10s ago)
sleep 10
HEIGHT2=$(curl -s --connect-timeout 5 "$RPC/status" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['sync_info']['latest_block_height'])" 2>/dev/null)

if [ "$HEIGHT2" -le "$HEIGHT" ] 2>/dev/null; then
    echo "❌ Block height not advancing: $HEIGHT → $HEIGHT2"
    exit 1
fi

# Check 4: Validator count
VALIDATORS=$(curl -s "$RPC/validators" 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)['result']['validators']))" 2>/dev/null || echo "?")

echo "✅ Node healthy"
echo "   Network:    $NETWORK"
echo "   Height:     $HEIGHT → $HEIGHT2 (+$((HEIGHT2 - HEIGHT)) in 10s)"
echo "   Catching up: $CATCHING_UP"
echo "   Validators: $VALIDATORS"
exit 0

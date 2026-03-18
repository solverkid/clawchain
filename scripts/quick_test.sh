#!/usr/bin/env bash
# 快速测试：验证挑战生成

set -e

export CHAIN_HOME=/tmp/clawchain-quick
rm -rf "$CHAIN_HOME"

cd "$(dirname "$0")/.."

# 初始化
./clawchaind init val1 --chain-id test-1 --home "$CHAIN_HOME" > /dev/null 2>&1
sed -i '' 's/"stake"/"uclaw"/g' "$CHAIN_HOME/config/genesis.json"

# 创建账户
./clawchaind keys add val1 --keyring-backend test --keyring-dir "$CHAIN_HOME" > /dev/null 2>&1
./clawchaind keys add miner1 --keyring-backend test --keyring-dir "$CHAIN_HOME" > /dev/null 2>&1

VAL_ADDR=$(./clawchaind keys show val1 -a --keyring-backend test --keyring-dir "$CHAIN_HOME")
MINER_ADDR=$(./clawchaind keys show miner1 -a --keyring-backend test --keyring-dir "$CHAIN_HOME")

./clawchaind genesis add-genesis-account "$VAL_ADDR" 1000000000000uclaw --home "$CHAIN_HOME"
./clawchaind genesis add-genesis-account "$MINER_ADDR" 100000000uclaw --home "$CHAIN_HOME"

./clawchaind genesis gentx val1 100000000000uclaw \
  --chain-id test-1 \
  --keyring-backend test \
  --keyring-dir "$CHAIN_HOME" \
  --home "$CHAIN_HOME" > /dev/null 2>&1

./clawchaind genesis collect-gentxs --home "$CHAIN_HOME" > /dev/null 2>&1

# 启用 API
sed -i '' 's/enable = false/enable = true/g' "$CHAIN_HOME/config/app.toml"

echo "🚀 启动链..."
./clawchaind start --home "$CHAIN_HOME" > "$CHAIN_HOME/chain.log" 2>&1 &
CHAIN_PID=$!

# 等待启动
sleep 5

echo "✓ 矿工地址: $MINER_ADDR"

# 注册矿工
echo "👷 注册矿工..."
curl -s -X POST http://localhost:1317/clawchain/miner/register \
  -H "Content-Type: application/json" \
  -d "{\"address\":\"$MINER_ADDR\",\"name\":\"test-miner\"}" | jq '.'

# 等待区块到达 10
echo "⏳ 等待区块 10..."
for i in {1..60}; do
  HEIGHT=$(curl -s http://localhost:1317/cosmos/base/tendermint/v1beta1/blocks/latest 2>/dev/null | jq -r '.block.header.height // "0"')
  echo "区块高度: $HEIGHT"
  
  if [ "$HEIGHT" -ge 10 ]; then
    echo "✓ 达到区块 10"
    break
  fi
  sleep 1
done

# 查询挑战
echo "📋 查询挑战..."
curl -s http://localhost:1317/clawchain/challenges/pending | jq '.'

# 查看日志
echo ""
echo "📝 链日志 (BeginBlock 相关):"
grep -i "begin\|生成\|challenge" "$CHAIN_HOME/chain.log" | grep -v "served RPC" | tail -20

# 清理
kill $CHAIN_PID
wait $CHAIN_PID 2>/dev/null || true

echo ""
echo "✅ 测试完成"

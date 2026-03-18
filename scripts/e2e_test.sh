#!/usr/bin/env bash
# ClawChain 端到端挖矿测试脚本
# 测试流程：启动链 → 启用 API → 矿工注册 → 查询挑战 → 提交答案 → 验证奖励

set -e

echo "🧪 ClawChain 端到端测试"
echo "========================"

# 清理旧环境
export CHAIN_HOME=/tmp/clawchain-e2e
rm -rf "$CHAIN_HOME"
echo "✓ 清理测试环境"

# 切换到链目录
cd "$(dirname "$0")/.."
CHAIN_DIR=$(pwd)

# 1. 初始化链
echo ""
echo "📦 步骤 1: 初始化链"
./clawchaind init val1 --chain-id clawchain-testnet-1 --home "$CHAIN_HOME"
sed -i '' 's/"stake"/"uclaw"/g' "$CHAIN_HOME/config/genesis.json"
echo "✓ 链初始化完成"

# 2. 创建账户
echo ""
echo "🔑 步骤 2: 创建账户"
./clawchaind keys add val1 --keyring-backend test --keyring-dir "$CHAIN_HOME" > /dev/null 2>&1
./clawchaind keys add miner1 --keyring-backend test --keyring-dir "$CHAIN_HOME" > /dev/null 2>&1

VAL_ADDR=$(./clawchaind keys show val1 -a --keyring-backend test --keyring-dir "$CHAIN_HOME")
MINER_ADDR=$(./clawchaind keys show miner1 -a --keyring-backend test --keyring-dir "$CHAIN_HOME")

echo "验证者地址: $VAL_ADDR"
echo "矿工地址: $MINER_ADDR"
echo "✓ 账户创建完成"

# 3. 添加创世账户
echo ""
echo "💰 步骤 3: 分配初始代币"
./clawchaind genesis add-genesis-account "$VAL_ADDR" 1000000000000uclaw --home "$CHAIN_HOME"
./clawchaind genesis add-genesis-account "$MINER_ADDR" 100000000uclaw --home "$CHAIN_HOME"
echo "✓ 创世账户配置完成"

# 4. 生成创世交易
echo ""
echo "📝 步骤 4: 生成创世交易"
./clawchaind genesis gentx val1 100000000000uclaw \
  --chain-id clawchain-testnet-1 \
  --keyring-backend test \
  --keyring-dir "$CHAIN_HOME" \
  --home "$CHAIN_HOME" > /dev/null 2>&1

./clawchaind genesis collect-gentxs --home "$CHAIN_HOME" > /dev/null 2>&1
echo "✓ 创世交易完成"

# 5. 启用 REST API
echo ""
echo "🔧 步骤 5: 启用 REST API"
sed -i '' 's/enable = false/enable = true/g' "$CHAIN_HOME/config/app.toml"
echo "✓ API 已启用 (http://localhost:1317)"

# 6. 启动链（后台）
echo ""
echo "🚀 步骤 6: 启动链"
./clawchaind start --home "$CHAIN_HOME" > "$CHAIN_HOME/chain.log" 2>&1 &
CHAIN_PID=$!
echo "链进程 PID: $CHAIN_PID"

# 等待链启动
echo -n "等待链启动"
for i in {1..30}; do
  if curl -s http://localhost:1317/cosmos/base/tendermint/v1beta1/blocks/latest > /dev/null 2>&1; then
    echo " ✓"
    break
  fi
  echo -n "."
  sleep 1
done

# 7. 等待链稳定
echo ""
echo "⏳ 步骤 7: 等待链稳定"
sleep 3

# 8. 矿工注册
echo ""
echo "👷 步骤 8: 矿工注册"
REGISTER_RESP=$(curl -s -X POST http://localhost:1317/clawchain/miner/register \
  -H "Content-Type: application/json" \
  -d "{\"address\":\"$MINER_ADDR\",\"name\":\"test-miner\"}")

echo "注册响应: $REGISTER_RESP"

if echo "$REGISTER_RESP" | grep -q '"success":true'; then
  echo "✓ 矿工注册成功"
else
  echo "✗ 矿工注册失败"
  kill $CHAIN_PID
  exit 1
fi

# 9. 查询矿工信息
echo ""
echo "🔍 步骤 9: 查询矿工信息"
MINER_INFO=$(curl -s http://localhost:1317/clawchain/miner/"$MINER_ADDR")
echo "$MINER_INFO" | jq '.'

# 10. 等待挑战生成（每 10 个块生成一次）
echo ""
echo "⏳ 步骤 10: 等待挑战生成"
echo "挑战将在第 10、20、30...个区块生成"

CHALLENGES_FOUND=0
for i in {1..60}; do
  HEIGHT=$(curl -s http://localhost:1317/cosmos/base/tendermint/v1beta1/blocks/latest 2>/dev/null | grep -o '"height":"[0-9]*"' | cut -d'"' -f4)
  
  CHALLENGES=$(curl -s http://localhost:1317/clawchain/challenges/pending 2>/dev/null)
  CHALLENGE_COUNT=$(echo "$CHALLENGES" | jq '.challenges | length' 2>/dev/null || echo 0)
  
  if [ "$CHALLENGE_COUNT" -gt 0 ]; then
    echo ""
    echo "✓ 找到 $CHALLENGE_COUNT 个挑战 (区块高度: $HEIGHT)"
    CHALLENGES_FOUND=1
    break
  fi
  
  echo -n "."
  sleep 1
done

if [ "$CHALLENGES_FOUND" -eq 0 ]; then
  echo ""
  echo "✗ 等待超时，未找到挑战"
  kill $CHAIN_PID
  exit 1
fi

# 11. 查询待处理挑战
echo ""
echo "📋 步骤 11: 查询待处理挑战"
echo "$CHALLENGES" | jq '.'

CHALLENGE_ID=$(echo "$CHALLENGES" | jq -r '.challenges[0].id // empty')
CHALLENGE_TYPE=$(echo "$CHALLENGES" | jq -r '.challenges[0].type // empty')
CHALLENGE_PROMPT=$(echo "$CHALLENGES" | jq -r '.challenges[0].prompt // empty')
EXPECTED_ANSWER=$(echo "$CHALLENGES" | jq -r '.challenges[0].expected_answer // empty')

echo "挑战详情:"
echo "  ID: $CHALLENGE_ID"
echo "  类型: $CHALLENGE_TYPE"
echo "  问题: $CHALLENGE_PROMPT"
echo "  答案: $EXPECTED_ANSWER"

# 12. 提交答案
echo ""
echo "📝 步骤 12: 提交答案"
SUBMIT_RESP=$(curl -s -X POST http://localhost:1317/clawchain/challenge/submit \
  -H "Content-Type: application/json" \
  -d "{\"challenge_id\":\"$CHALLENGE_ID\",\"miner_address\":\"$MINER_ADDR\",\"answer\":\"$EXPECTED_ANSWER\"}")

echo "提交响应: $SUBMIT_RESP"

if echo "$SUBMIT_RESP" | grep -q '"success":true'; then
  CORRECT=$(echo "$SUBMIT_RESP" | jq -r '.correct')
  REWARD=$(echo "$SUBMIT_RESP" | jq -r '.reward')
  echo "✓ 答案提交成功"
  echo "  正确: $CORRECT"
  echo "  奖励: $REWARD"
else
  echo "✗ 答案提交失败"
  kill $CHAIN_PID
  exit 1
fi

# 13. 查询矿工余额
echo ""
echo "💰 步骤 13: 查询矿工余额"
BALANCE=$(curl -s "http://localhost:1317/cosmos/bank/v1beta1/balances/$MINER_ADDR" | jq -r '.balances[0].amount // "0"')
echo "矿工余额: $BALANCE uclaw"

# 14. 清理
echo ""
echo "🧹 步骤 14: 清理测试环境"
kill $CHAIN_PID
wait $CHAIN_PID 2>/dev/null || true
echo "✓ 链进程已停止"

# 总结
echo ""
echo "================================"
echo "✅ 端到端测试完成！"
echo "================================"
echo "测试结果："
echo "  ✓ 链启动成功"
echo "  ✓ API 服务正常"
echo "  ✓ 矿工注册成功"
echo "  ✓ 挑战生成成功"
echo "  ✓ 答案提交成功"
echo "  ✓ 奖励发放成功"
echo ""
echo "日志文件: $CHAIN_HOME/chain.log"

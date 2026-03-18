#!/usr/bin/env bash
# ClawChain 端到端挖矿测试脚本
# 测试流程：启动链 → 启用 API → 矿工注册 → 查询挑战 → 提交答案 → 验证奖励

set -e

echo "🧪 ClawChain 端到端测试"
echo "========================"

# 启用 dev mode（允许单矿工结算）
export CLAWCHAIN_DEV=1
# 测试模式下使用短 epoch（10 blocks 而非生产的 100 blocks）
export CLAWCHAIN_TEST_EPOCH=10

# 清理旧环境
export CHAIN_HOME=/tmp/clawchain-e2e
rm -rf "$CHAIN_HOME"
echo "✓ 清理测试环境"

# 切换到链目录
cd "$(dirname "$0")/../chain"
CHAIN_DIR=$(pwd)

# 构建二进制
echo ""
echo "🔨 构建 clawchaind"
go build -o clawchaind ./cmd/clawchaind
echo "✓ 构建完成"

# 1. 初始化链
echo ""
echo "📦 步骤 1: 初始化链"
./clawchaind init val1 --chain-id clawchain-testnet-1 --home "$CHAIN_HOME" > /dev/null 2>&1
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

# 5. 启用 REST API + 加速出块
echo ""
echo "🔧 步骤 5: 启用 REST API + 加速出块"
sed -i '' 's/enable = false/enable = true/g' "$CHAIN_HOME/config/app.toml"
# 加速出块：1秒出块间隔（默认5秒太慢）
sed -i '' 's/timeout_commit = "5s"/timeout_commit = "1s"/g' "$CHAIN_HOME/config/config.toml"
sed -i '' 's/timeout_propose = "3s"/timeout_propose = "1s"/g' "$CHAIN_HOME/config/config.toml"
echo "✓ API 已启用 + 出块加速至 1s"

# 6. 启动链（后台）
echo ""
echo "🚀 步骤 6: 启动链"
./clawchaind start --home "$CHAIN_HOME" > "$CHAIN_HOME/chain.log" 2>&1 &
CHAIN_PID=$!
echo "链进程 PID: $CHAIN_PID"

# 清理函数
cleanup() {
  echo ""
  echo "🧹 清理测试环境"
  kill $CHAIN_PID 2>/dev/null || true
  wait $CHAIN_PID 2>/dev/null || true
  echo "✓ 链进程已停止"
}
trap cleanup EXIT

# 等待链启动（最多 30 秒）
echo -n "等待链启动"
STARTED=0
for i in {1..30}; do
  if curl -s http://localhost:1317/cosmos/base/tendermint/v1beta1/blocks/latest > /dev/null 2>&1; then
    echo " ✓"
    STARTED=1
    break
  fi
  echo -n "."
  sleep 1
done

if [ "$STARTED" -eq 0 ]; then
  echo ""
  echo "✗ 链启动超时（30s），查看日志："
  tail -20 "$CHAIN_HOME/chain.log"
  exit 1
fi

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
  exit 1
fi

# 9. 查询矿工信息
echo ""
echo "🔍 步骤 9: 查询矿工信息"
MINER_INFO=$(curl -s http://localhost:1317/clawchain/miner/"$MINER_ADDR")
echo "$MINER_INFO" | jq '.'

# 10. 等待挑战生成（测试模式: 每 10 blocks 一次，生产: 每 100 blocks = 1 epoch）
echo ""
echo "⏳ 步骤 10: 等待挑战生成"

CHALLENGES_FOUND=0
# 等待一个新鲜的挑战（通过检查 created_height 确保未过期）
for i in {1..120}; do
  CURRENT_HEIGHT=$(curl -s http://localhost:1317/cosmos/base/tendermint/v1beta1/blocks/latest 2>/dev/null | jq -r '.block.header.height // "0"')

  CHALLENGES=$(curl -s http://localhost:1317/clawchain/challenges/pending 2>/dev/null)
  CHALLENGE_COUNT=$(echo "$CHALLENGES" | jq '.challenges | length' 2>/dev/null || echo 0)

  if [ "$CHALLENGE_COUNT" -gt 0 ]; then
    # 取最新创建的挑战，确保 created_height 在 100 blocks 之内
    LAST_IDX=$((CHALLENGE_COUNT - 1))
    CREATED_H=$(echo "$CHALLENGES" | jq -r ".challenges[$LAST_IDX].created_height // 0")
    AGE=$((CURRENT_HEIGHT - CREATED_H))
    if [ "$AGE" -lt 80 ]; then
      echo "✓ 找到新鲜挑战 (区块高度: $CURRENT_HEIGHT, 挑战创建高度: $CREATED_H, 年龄: ${AGE} blocks)"
      CHALLENGES_FOUND=1
      break
    fi
  fi

  echo -n "."
  sleep 1
done

if [ "$CHALLENGES_FOUND" -eq 0 ]; then
  echo ""
  echo "✗ 等待超时，未找到新鲜挑战"
  exit 1
fi

# 11. 查询待处理挑战（取最新的挑战，避免过期）
echo ""
echo "📋 步骤 11: 查询挑战详情"
CHALLENGE_ID=$(echo "$CHALLENGES" | jq -r ".challenges[$LAST_IDX].id // empty")
CHALLENGE_TYPE=$(echo "$CHALLENGES" | jq -r ".challenges[$LAST_IDX].type // empty")
CHALLENGE_PROMPT=$(echo "$CHALLENGES" | jq -r ".challenges[$LAST_IDX].prompt // empty")
EXPECTED_ANSWER=$(echo "$CHALLENGES" | jq -r ".challenges[$LAST_IDX].expected_answer // empty")

echo "  ID: $CHALLENGE_ID"
echo "  类型: $CHALLENGE_TYPE"
echo "  问题: $CHALLENGE_PROMPT"
echo "  预期答案: ${EXPECTED_ANSWER:-（无固定答案）}"

# 12. 提交答案
echo ""
echo "📝 步骤 12: 提交答案"

# 构造答案：有预期答案用预期答案，否则用通用答案
if [ -n "$EXPECTED_ANSWER" ]; then
  ANSWER="$EXPECTED_ANSWER"
else
  ANSWER="test answer for e2e"
fi

SUBMIT_RESP=$(curl -s -X POST http://localhost:1317/clawchain/challenge/submit \
  -H "Content-Type: application/json" \
  -d "{\"challenge_id\":\"$CHALLENGE_ID\",\"miner_address\":\"$MINER_ADDR\",\"answer\":\"$ANSWER\"}")

echo "提交响应: $SUBMIT_RESP"

if echo "$SUBMIT_RESP" | grep -q '"success":true'; then
  SUBMIT_STATUS=$(echo "$SUBMIT_RESP" | jq -r '.status')
  echo "✓ 答案提交成功 (状态: $SUBMIT_STATUS)"
else
  echo "✗ 答案提交失败"
  exit 1
fi

# 验证挑战状态为 complete
if [ "$SUBMIT_STATUS" != "complete" ]; then
  echo "✗ 挑战未结算（状态: $SUBMIT_STATUS，预期: complete）"
  exit 1
fi
echo "✓ 挑战已结算"

# 13. 等待几个区块让 EndBlock 处理 pending rewards
echo ""
echo "⏳ 步骤 13: 等待奖励结算"
sleep 5

# 14. 验证矿工奖励
echo ""
echo "💰 步骤 14: 验证矿工奖励"

# 通过矿工统计 API 验证奖励记录
STATS=$(curl -s http://localhost:1317/clawchain/miner/"$MINER_ADDR"/stats)
echo "矿工统计:"
echo "$STATS" | jq '.'

TOTAL_REWARDS=$(echo "$STATS" | jq -r '.total_rewards // 0')
CHALLENGES_COMPLETED=$(echo "$STATS" | jq -r '.challenges_completed // 0')

echo ""
echo "  完成挑战数: $CHALLENGES_COMPLETED"
echo "  累计奖励: $TOTAL_REWARDS uclaw"

REWARD_OK=0
# 生产环境每 epoch 矿工池 30,000,000 uclaw (30 CLAW)，测试模式下奖励金额相同
if [ "$TOTAL_REWARDS" -gt 0 ] 2>/dev/null; then
  echo "✓ 奖励已记录: $TOTAL_REWARDS uclaw (预期 ≈30,000,000 uclaw = 30 CLAW)"
  REWARD_OK=1
else
  echo "✗ 奖励未记录（total_rewards = $TOTAL_REWARDS）"
fi

if [ "$CHALLENGES_COMPLETED" -gt 0 ] 2>/dev/null; then
  echo "✓ 挑战完成数已更新: $CHALLENGES_COMPLETED"
else
  echo "✗ 挑战完成数为 0"
  REWARD_OK=0
fi

# 15. 查询链统计
echo ""
echo "📊 步骤 15: 链统计"
CHAIN_STATS=$(curl -s http://localhost:1317/clawchain/stats)
echo "$CHAIN_STATS" | jq '.'

# 总结
echo ""
echo "================================"
if [ "$REWARD_OK" -eq 1 ]; then
  echo "✅ 端到端测试全部通过！"
else
  echo "❌ 端到端测试失败"
fi
echo "================================"
echo "测试结果："
echo "  ✓ 链启动成功"
echo "  ✓ API 服务正常"
echo "  ✓ 矿工注册成功"
echo "  ✓ 挑战生成成功"
echo "  ✓ 答案提交成功"
echo "  ✓ 挑战结算成功"
if [ "$REWARD_OK" -eq 1 ]; then
  echo "  ✓ 奖励记录正确 ($TOTAL_REWARDS uclaw)"
else
  echo "  ✗ 奖励验证失败"
fi
echo ""
echo "日志文件: $CHAIN_HOME/chain.log"

# 非零退出码表示失败
if [ "$REWARD_OK" -ne 1 ]; then
  exit 1
fi

# x/reputation 模块

> 2026-04-22 当前真实状态：`x/reputation` 现在有 keeper-level score CRUD、leaderboard query helper、`challenge` 所需的 `GetMinerScore/UpdateScore` 接口对齐，以及授权 controller 且绑定到已锚定 settlement batch 的 append-only `reputation_delta` apply contract。它**还没有**完整的 protobuf/gRPC/CLI tx surface，也**不接受**单场 Poker MTT 结果、raw HUD、hidden eval 原始分或 public ELO 直接写入。

## 概述

`x/reputation` 模块是 ClawChain 声誉系统的核心实现，负责管理所有矿工的链上声誉分（0-1000），根据矿工的挖矿行为（完成挑战、失败、作弊等）动态更新声誉，并提供声誉查询、排行榜等功能。

## 核心功能

### 1. 声誉分管理

每个矿工拥有 0-1000 的声誉分：

| 事件 | 分数变化 | 触发条件 |
|------|----------|----------|
| 初始注册 | 500 | 矿工首次注册 |
| 完成挑战 | +5 | 成功完成一次挑战 |
| 连续在线 24h | +10 | 连续在线 864 个区块（@ 6s/block） |
| 挑战失败 | -20 | 未通过挑战验证 |
| 超时未响应 | -10 | 超过 30 秒未响应 |
| 作弊被检测 | -500 + slash 10% 质押 | 作弊行为被发现 |

**分数范围：** 0-1000（自动 clamp）

### 2. 声誉等级

声誉分决定矿工的挖矿资格和挑战分配优先级：

| 等级 | 分数范围 | 影响 |
|------|----------|------|
| **Elite（精英）** | > 800 | 优先分配高价值挑战 |
| **Normal（正常）** | 600-800 | 正常参与所有挑战 |
| **Reduced（降频）** | 100-599 | 降低挑战分配频率 |
| **Suspended（暂停）** | < 100 | 暂停挖矿资格，需重新质押 |

### 3. 事件驱动更新（EndBlocker）

`x/reputation` 在每个区块结束时（`EndBlock`）处理来自 `x/challenge` 模块提交的声誉事件：

```go
// x/challenge 提交事件示例
keeper.EnqueueEvent(ctx, types.PendingReputationEvent{
    Type:         types.EventChallengeCompleted,
    MinerAddress: "claw1abc...",
    ChallengeID:  "challenge-123",
})
```

所有事件在 `EndBlocker` 中批量处理，确保状态一致性。

### 4. 作弊检测与 Slash

当检测到作弊（`EventCheating`）时：
1. 声誉分 -500
2. 通知 `x/poa` 模块 slash 矿工质押的 10%
3. 发出 `cheating_detected` 事件

```go
// Keeper 需在 app 初始化时注入 PoASlasher 接口
keeper.SetPoASlasher(poaKeeper)
```

## 代码结构

```
x/reputation/
├── keeper/
│   ├── keeper.go          # 核心 Keeper：声誉分 CRUD、事件处理
│   └── grpc_query.go      # 查询接口（声誉分、排行榜、历史）
├── module/
│   └── module.go          # 模块定义、EndBlocker
└── types/
    ├── keys.go            # 存储键定义
    ├── reputation.go      # ReputationScore 结构体、常量
    ├── events.go          # 事件类型定义
    ├── genesis.go         # 创世状态
    └── errors.go          # 错误定义
```

## 核心数据结构

### ReputationScore

```go
type ReputationScore struct {
    MinerAddress            string  // 矿工地址
    Score                   int64   // 当前声誉分（0-1000）
    Tier                    string  // 声誉等级（elite/normal/reduced/suspended）
    TotalChallenges         int64   // 总挑战次数
    CompletedChallenges     int64   // 完成的挑战次数
    FailedChallenges        int64   // 失败的挑战次数
    ConsecutiveOnlineBlocks int64   // 当前连续在线区块数
    LastUpdateHeight        int64   // 最后更新区块高度
}
```

### PendingReputationEvent

```go
type PendingReputationEvent struct {
    Type         EventType  // 事件类型
    MinerAddress string     // 矿工地址
    ChallengeID  string     // 关联的挑战 ID（可选）
}
```

**支持的事件类型：**
- `challenge_completed` - 完成挑战
- `challenge_failed` - 挑战失败
- `timeout` - 超时未响应
- `cheating` - 作弊检测
- `online_heartbeat` - 在线心跳（用于连续在线奖励）

## Keeper 接口

### 声誉分管理

```go
// 获取矿工声誉分
func (k Keeper) GetScore(ctx sdk.Context, minerAddr sdk.AccAddress) (types.ReputationScore, error)

// 初始化新矿工（500 分）
func (k Keeper) InitializeMiner(ctx sdk.Context, minerAddr sdk.AccAddress) (types.ReputationScore, error)

// 获取或初始化声誉分（不存在则自动创建）
func (k Keeper) GetOrInitScore(ctx sdk.Context, minerAddr sdk.AccAddress) (types.ReputationScore, error)
```

### 事件处理

```go
// 将事件加入待处理队列（x/challenge 调用）
func (k Keeper) EnqueueEvent(ctx sdk.Context, event types.PendingReputationEvent)

// 应用事件，更新声誉分（EndBlocker 调用）
func (k Keeper) ApplyEvent(ctx sdk.Context, event types.PendingReputationEvent) error
```

### 查询接口

```go
// 获取矿工声誉等级
func (k Keeper) GetMinerTier(ctx sdk.Context, minerAddr sdk.AccAddress) types.ReputationTier

// 检查矿工是否被暂停
func (k Keeper) IsMinerSuspended(ctx sdk.Context, minerAddr sdk.AccAddress) bool

// 检查矿工是否有资格参与挑战
func (k Keeper) IsMinerEligible(ctx sdk.Context, minerAddr sdk.AccAddress) bool

// 获取声誉排行榜（按分数降序，limit=0 返回全部）
func (k Keeper) GetLeaderboard(ctx sdk.Context, limit int) []types.ReputationScore

// 获取矿工声誉历史记录（逆序，最新优先）
func (k Keeper) GetHistory(ctx sdk.Context, minerAddr sdk.AccAddress, limit int) []types.ReputationEvent
```

## 集成示例

### 在 app.go 中注册模块

```go
import (
    reputationkeeper "github.com/clawchain/clawchain/x/reputation/keeper"
    reputationmodule "github.com/clawchain/clawchain/x/reputation/module"
    reputationtypes "github.com/clawchain/clawchain/x/reputation/types"
)

// 创建 Keeper
app.ReputationKeeper = reputationkeeper.NewKeeper(
    appCodec,
    keys[reputationtypes.StoreKey],
)

// 注入 PoA Slasher 接口
app.ReputationKeeper.SetPoASlasher(&app.PoAKeeper)

// 注册模块
reputationModule := reputationmodule.NewAppModule(app.ReputationKeeper)
```

### x/challenge 提交事件

```go
// 挑战完成
app.ReputationKeeper.EnqueueEvent(ctx, types.PendingReputationEvent{
    Type:         types.EventChallengeCompleted,
    MinerAddress: minerAddr.String(),
    ChallengeID:  challengeID,
})

// 挑战失败
app.ReputationKeeper.EnqueueEvent(ctx, types.PendingReputationEvent{
    Type:         types.EventChallengeFailed,
    MinerAddress: minerAddr.String(),
    ChallengeID:  challengeID,
})

// 作弊检测
app.ReputationKeeper.EnqueueEvent(ctx, types.PendingReputationEvent{
    Type:         types.EventCheating,
    MinerAddress: minerAddr.String(),
    ChallengeID:  challengeID,
})
```

### 查询声誉分

```go
// 获取矿工声誉
score, err := app.ReputationKeeper.GetScore(ctx, minerAddr)
if err != nil {
    return err
}
fmt.Printf("矿工 %s 声誉分: %d (%s)\n", minerAddr, score.Score, score.Tier)

// 检查是否有资格参与挑战
if !app.ReputationKeeper.IsMinerEligible(ctx, minerAddr) {
    return fmt.Errorf("矿工声誉分过低，暂停挖矿资格")
}

// 获取排行榜前 100 名
leaderboard := app.ReputationKeeper.GetLeaderboard(ctx, 100)
for i, score := range leaderboard {
    fmt.Printf("%d. %s: %d (%s)\n", i+1, score.MinerAddress, score.Score, score.Tier)
}
```

## 存储布局

| Prefix | Key | Value | 说明 |
|--------|-----|-------|------|
| `0x01` | `miner_addr` | `ReputationScore` | 矿工声誉分 |
| `0x02` | `miner_addr + block_height` | `ReputationEvent` | 声誉历史记录 |
| `0x03` | `miner_addr` | `int64` | 最后在线区块 |
| `0x04` | `miner_addr` | `int64` | 连续在线区块数 |
| `0x05` | - | `PendingEvents` | 待处理事件队列 |

## 发出的事件

模块在链上发出以下事件，供客户端/区块浏览器监听：

### reputation_updated

```json
{
  "type": "reputation_updated",
  "attributes": [
    {"key": "miner", "value": "claw1abc..."},
    {"key": "score", "value": "750"},
    {"key": "delta", "value": "+5"},
    {"key": "tier", "value": "normal"},
    {"key": "event_type", "value": "challenge_completed"}
  ]
}
```

### miner_suspended

```json
{
  "type": "miner_suspended",
  "attributes": [
    {"key": "miner", "value": "claw1abc..."},
    {"key": "score", "value": "85"}
  ]
}
```

### cheating_detected

```json
{
  "type": "cheating_detected",
  "attributes": [
    {"key": "miner", "value": "claw1abc..."},
    {"key": "challenge_id", "value": "challenge-123"}
  ]
}
```

## 未来扩展

- [ ] gRPC 查询服务（当前为简化版查询接口）
- [ ] 声誉分加权投票治理
- [ ] 声誉分衰减机制（长期不活跃逐渐降低）
- [ ] 声誉分 NFT 徽章（Elite 矿工特殊标识）
- [ ] 历史快照（按 epoch 保存排行榜快照）

## 常见问题

**Q: 声誉分会无限增长吗？**  
A: 不会，所有分数变化会通过 `ClampScore()` 限制在 [0, 1000] 范围内。

**Q: 连续在线奖励如何计算？**  
A: 需要 x/challenge 模块在每个 epoch 发送 `online_heartbeat` 事件。当累计 864 个区块（24h）时自动奖励 +10 并重置计数。

**Q: 作弊检测谁负责？**  
A: x/challenge 模块负责检测（如多数验证失败、spot check 答错等），检测到后提交 `EventCheating` 事件。

**Q: 声誉分低于 100 会怎样？**  
A: 矿工被标记为 `suspended`，无法参与挑战。需重新质押或等待声誉恢复。

**Q: 如何恢复被暂停的矿工？**  
A: 暂停状态只是标记，不是永久 ban。矿工可以通过完成其他任务（如提交有效的链上证明）逐步恢复声誉，或由治理投票解除。

---

**模块状态：** ✅ 编译通过，核心功能完整  
**依赖：** x/poa（可选，用于 slash）  
**被依赖：** x/challenge（事件提交方）

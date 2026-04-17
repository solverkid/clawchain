# Poker MTT Sidecar 接入对齐文档

**版本**: 0.1  
**日期**: 2026-04-10  
**状态**: 现状对齐，不改 donor 代码  
**上游 donor**: `lepoker-gameserver` `dev` 分支  
**配套计划**: `docs/superpowers/plans/2026-04-10-poker-mtt-sidecar.md`

---

## 1. 文档目的

这份文档只做一件事：

**把 `lepoker-gameserver` 作为现成 `poker mtt` sidecar 接入 ClawChain 时，当前真实存在的接口、状态机、依赖、缺口和边缘情况一次性写清楚。**

本文档明确按下面的约束编写：

- 参考 `lepoker-gameserver` 当前代码和 GitNexus code graph
- 不假设 donor 会为了 ClawChain 重构接口
- 不把 `poker mtt` 和现有 `arena / bluff arena` 混在一起
- 当前阶段不做 donor 代码修改

这不是一个“理想 API 设计”文档。  
这是一个“**按 donor 现状接，哪些能接、哪些不能接、哪里必须绕开**”的文档。

## 2. 边界约束

### 2.1 产品边界

- `arena/*` 继续只代表当前 Bluff Arena 线
- 新线统一叫 `poker mtt`
- 不把 `poker mtt` 叫成 `arena poker`
- 不把 donor runtime 当成 Arena runtime 的一个 mode

### 2.2 仓库和图谱边界

- `lepoker-gameserver` 是独立 git repo
- `lepoker-gameserver` 继续独立 GitNexus 索引
- 对 donor 的图谱查询必须用 repo `lepoker-gameserver`
- 不允许把 donor 包直接挂到 `arena/*`

### 2.3 当前集成原则

当前冻结的集成原则只有两个：

1. **控制面按 donor 现有 HTTP 路由走**
2. **实时打牌面按 donor 现有 WebSocket 走**

也就是说，当前阶段不去把 donor 改成“HTTP-only poker runtime”。

### 2.4 ClawChain Phase 1 状态机冻结

ClawChain 侧 Phase 1 只把 donor 当成 sidecar runtime，不把 donor 内部状态串直接升级为 ClawChain domain state。

运行时状态机:

```text
scheduled -> start_requested -> sidecar_starting -> seating_ready -> running -> finalizing -> standings_ready -> completed
```

异常状态:

```text
failed_to_start
cancelled
void
degraded
manual_review
```

奖励和证据状态机:

```text
raw_ingested -> final_ranking_ready -> evidence_ready -> result_ready -> locked -> anchorable -> anchored
```

Poker MTT Evidence Phase 2 统一把 evidence 子状态展开为:

```text
raw_ingested -> replay_ready -> hud_ready -> hidden_eval_ready -> final_ranking_ready -> result_ready -> locked -> anchorable -> anchored
```

这不是说 final ranking 必须等待所有 hand evidence 才能被保存；它只表示 **reward-ready / anchorable** 必须等 final ranking 与 evidence component roots 都满足 policy。执行计划见 `docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2.md`。

Phase 1 的硬约束:

- `live_ranking` 只用于赛中观察和恢复，不进入 reward window
- `final_ranking_ready` 必须来自 canonical standings，不直接等于 donor `FINISHED`
- `result_ready` 不能只看 `evaluation_state=final`，还要有证据状态
- `locked` 后才能进入日榜 / 周榜 reward window
- `anchorable` 后才能进入 settlement batch anchor payload
- post-anchor correction 只能 append / supersede，不能改旧 root

### 2.5 Phase 1 实现硬化点（2026-04-17）

当前 ClawChain Phase 1 代码已经把以下边界固化为测试约束：

- donor `roomID` 只作为路由信息，不进入 final ranking canonical root
- donor HTTP base URL 会转换成正确的 `ws://` / `wss://` 连接 URL
- `EntryNumber = 1` 走首次 join；只有显式 `Reentry` 或 `EntryNumber > 1` 才走 reentry
- reward-bearing 结果必须先落入 `poker_mtt_final_rankings`，再投影 `poker_mtt_result_entries`
- legacy/admin `apply_poker_mtt_results` 不能伪造 `final_ranking_id` 绕过 canonical final ranking
- reward window 会再次校验 `poker_mtt_result_entries.final_ranking_id` 是否存在并与 rank/miner/tournament/evidence 对齐
- `rank_state = ranked`、完整 evidence、`locked_at`、`anchorable_at`、policy bundle 都是进入 reward window 的前置条件
- `x/settlement` 的 `MsgAnchorSettlementBatch` 不再 permissionless；submitter 必须在 settlement genesis `authorized_submitters` 白名单中

## 3. 证据基础

本文档基于以下事实源：

### 3.1 GitNexus 索引结果

`lepoker-gameserver` 当前 GitNexus 索引结果：

- 3,436 nodes
- 12,415 edges
- 107 clusters
- 300 processes

### 3.2 关键代码图谱节点

本次对齐重点追过的核心符号：

- `service/http_client.go:StartMTT`
- `server/hub.go:NewMTTOrSNG`
- `server/hub.go:PreSplitTable`
- `server/mtt.go:MTTController`
- `server/mtt.go:GetHub`
- `server/ranking.go:calculateMTTRanking`
- `server/ranking.go:listeningRanking`
- `service/http_client.go:GetMTTRoomByID`
- `service/http_client.go:ReentryMTTGame`
- `service/http_client.go:checkfirstCall`
- `service/http_client.go:sendToMTTAddUserChan`
- `service/http_client.go:mttValidAndSendToChannelIfMttNotStarted`
- `server/websocket.go:HandleWebSocket`
- `server/client.go:ClientAsyncRun`
- `server/client.go:RunWriteAndRead`
- `server/client.go:notifyForendToReconnect`
- `server/client.go:closeConn`

### 3.3 补充源码和文档

还结合了 donor 的这些文件：

- `run_server/main.go`
- `run_server/middleware.go`
- `service/model/game.go`
- `service/model/command.go`
- `config/const.go`
- `config/viper_config.go`
- `README.md`
- `doc/mtt.md`
- `doc/mtt ranking.md`
- `doc/mtt和private差异.md`

## 4. donor 当前运行拓扑

## 4.1 两套 HTTP surface，不是一个单口模型

donor 当前不是一个“单 HTTP server + 单 ws 路由”的极简模型，而是两套面：

### A. 外部/玩家面

默认走 `server.port`，典型职责：

- `GET /v1/ws`
- `POST /v1/join_game`
- `POST /v1/spectators`
- `POST /v1/new_game`
- `GET /v1/hello`

这一面是玩家会话、ws 连接、旁观、普通房间加入。

### B. 内部/控制面

默认走 `server.inner_port`，典型职责：

- `POST /v1/mtt/start`
- `GET /v1/mtt/getMTTRoomByID`
- `POST /v1/mtt/reentryMTTGame`
- `POST /v1/mtt/validRoomConfig`
- `GET /v1/mtt/RestartValid`
- `GET /v1/mtt/Stop`
- `POST /v1/mtt/cancel`
- `GET /v1/snapshot`

这一面是 MTT 创建、房间查询、reentry、运维和内部调试。

**结论**：

- ClawChain adapter 不能假设 donor 只有一个 base URL
- 至少要区分“控制面端口”和“玩家/ws 端口”

## 4.2 外部依赖不是可选信息

按 donor 现状，以下依赖需要明确写入接入条件：

### 必需依赖

- Redis
  - 启动锁
  - ranking snapshot
  - 活跃玩家 zset
  - died list
- RocketMQ producer 初始化
  - 当前启动阶段会直接执行 `mq.Init(ctx)`
  - producer 初始化失败会 panic

### 条件性 auth 依赖

是否真正依赖 auth service，取决于 donor 是否跑在 `config.Mock=true`：

#### donor mock 模式

如果 `config.Mock=true`：

- `StartMTT` 走 `mockMTT`
- `RequestUserInfo` 不走 `TokenValid`
- `ws/join` 主要依赖 `Mock-Userid`

也就是说：

- **本地跑通不需要真实 token 校验链路**
- **关键是 `Mock-Userid`，不是 token 本身**

#### auth-stub 模式

如果 `config.Mock=false`：

- `StartMTT` 需要 `GetMTTInfoUrl`
- `join/ws` 需要 `TokenValid`
- 生命周期通知会打 `NotifyTournamentUrl`

这时就不是“有 token 就行”，而是：

- token 要能通过 `TokenValid`
- `TokenValid` 要返回 `code=0`
- `TokenValid` 返回体里要有 `data.userID` 和 `data.playerName`
- `GetMTTInfoUrl` 也必须返回 donor 能消费的 MTT 详情

### 配置和基础设施依赖

- Apollo / config 装载链路
- RocketMQ 配置

### 可降级依赖

- chat group / 腾讯群相关能力，可通过本地 mock 配置关闭

### donor 自带本地 mock 建议

`README.md` 里明确给了本地启动建议：

- `mock: true`
- `mock_autoCall: true`
- `mock_mtt_valid: true`
- `chat_group_available: false`
- `GAME_ENV=local`

**结论**：

如果当前目标只是“先对齐现有并跑通 `poker mtt` sidecar”，最现实的入口是：

- 本地或开发环境优先走 donor mock 模式
- 生产前再讨论 auth/notify 真实对接

### 4.3 MQ 的当前结论

MQ 不能简单归类为“完全可忽略”。

当前 donor 的真实情况是：

#### 启动阶段

- `run_server/Init/Init.go` 里会执行：
  - `InitRedis`
  - `mq.Init`
  - `cache.Init`
- `mq.Init` 如果 producer 初始化失败，会直接 panic

所以：

- **MQ 对当前 donor 进程启动是硬依赖**

#### 比赛运行阶段

大量 MQ 发送是这样使用的：

- `SendToMQAsync`
- `Send2SocketProjectMQ`
- `SendRoundPlayersMQ`
- `SendRankMQ`
- `SendRoomCloseMQ`

它们在很多地方都是：

- 异步调用
- 返回错误只记录日志
- 大量调用点是 `_ = ...` 或 `sendErr` 后仅 `Log.Errorf`

所以：

- **MQ 对很多比赛内 side effect 是软依赖**
- **但在“不改 donor 代码”的前提下，不能先假设它对启动可忽略**

当前 phase 1 的现实策略应当是：

- 先把 MQ 视为 donor 启动前置条件
- 再单独研究哪些 topic 只是外部同步/通知，哪些会影响真实产品联动

## 5. donor 当前的核心状态模型

当前 donor 里，MTT 相关不是只有一个表或一个 hub，而是几层并存的状态：

### 5.1 Tournament 级

- `MTTCompetes`
  - key: `MTTID`
  - value: `*MTTCompete`

### 5.2 User -> current hub 映射

- `MTTParticipants`
  - 逻辑结构: `map[userID]map[mttID]*Hub`

这层非常关键。  
它说明 donor 默认就认为：

**一个用户在同一个 MTT 里的当前 `roomID` 是会变化的。**

也就是分桌、并桌、迁移以后，用户所在桌并不是固定不变的。

### 5.3 未入桌/待处理参赛者缓冲

- `AuthMTTParticipantsByMTTID`
- `GlobalAuthMTTParticipantsChan`

这意味着：

- late join / reentry 不一定立刻对应到某一桌
- 有一段“已属于比赛，但尚未真正映射到最终 hub”的缓冲态

### 5.4 Ranking 级

`MTTController` 内还有：

- `RankingSnapshotChan`
- `RankingDiedChan`
- `RankingNoticeDiedChan`
- `DieUserByUserID`

而 ranking 持久化结果最终写入 Redis，不是先天有一个 HTTP read model。

## 6. 接入时必须接受的身份语义

在 donor 里，至少有四类不同语义的标识：

| 标识 | 稳定性 | 作用 | 集成要求 |
| --- | --- | --- | --- |
| `MTTID` | 稳定 | 一场比赛 | ClawChain 外部比赛 ID 要映射到这里 |
| `userID` | 稳定 | 玩家身份 | bot / miner 的主身份锚点 |
| `roomID` | 不稳定 | 当前所在桌 | 不能缓存成永久值 |
| `sessionID` | 会变 | 当前会话/连接关联 | 不能当作玩家永久身份 |

**冻结原则**：

- ClawChain 的 canonical identity 只能是 `poker_mtt_tournament_id + user_id`
- donor 的 `roomID` 只代表“当前桌”
- donor 的 `sessionID` 只代表“当前会话”

## 7. 当前 donor 的完整接入主链路

## 7.1 比赛启动链路

`StartMTT` 当前真实行为不是“直接本地开赛”，而是：

1. 校验 `type` 必须是 `mtt/sng`
2. 校验 `ID` 非空
3. 如果 `MTTCompetes` 已经存在该 `ID`，直接返回成功响应，但不会重复启动
4. 从 auth service 获取 `AuthMTTDetail`
   - mock 模式下走 `mockMTT`
5. 用 `GameModeHandler.InitMTTRoomConfig` 生成房间配置
6. 以 `MTTStartLocker:<ID>` 为 key 做 Redis 分布式锁
7. 在后台进入 `NewMTTOrSNG`

### `NewMTTOrSNG` 当前实际做的事

它一次性做了很多关键初始化：

- 去重参赛者
- 初始化 `EntryNumber = 1`
- shuffle participants
- `PreSplitTable`
- 创建 `MTTController`
- 启动 ranking listener
- 为每桌创建 `Hub`
- 为每个参赛者创建离线 session 和 client
- 先 `Sit`
- 把 `userID -> MTTID -> Hub` 写进 `MTTParticipants`
- 初始化 ranking snapshot
- 构造 `MTTCompete`
- 调 `NotifyTournamentUrl` 通知外部
- 启动 `calculateRanking`
- 启动 `noticeDiedRank`
- 推送 `MTTPreparedCommand`
- 启动 `MTTController.Handler`

### 当前对 ClawChain 的含义

ClawChain 在 donor 启动后，不需要自己再为每个参赛者建空会话。  
donor 已经在启动阶段为所有初始参赛者创建了离线 session。

ClawChain 真正要做的是：

- 发起启动
- 后续让具体玩家或 bot 通过 join + ws 连进去

## 7.2 玩家进入比赛的当前链路

这里有一个很容易误判的点：

**MTT 玩家不是只靠 `/v1/mtt/start` 就能自动“在线”。**

当前 donor 下，一个玩家真正开始收发牌桌消息，需要至少这几步：

1. 先知道自己当前在哪个 `roomID`
2. 调 `POST /v1/join_game`
3. 拿到 `sessionID`
4. 再连 `GET /v1/ws`

### 为什么必须先知道 `roomID`

因为 `JoinGame` 内部调用的 `createSessionWithJoinReq`，会先从上下文取 `roomID`，再执行：

- `GetHubByRoomID`
- `JoinGameCheck`
- session 继承 / session 复用 / 重连修正

`JoinGameReq` 自身非常薄，主要只是 `BaseGameReq`，并不把 `MTTID` 直接作为 join 唯一输入。

### 当前 donor 提供的 room 查询能力

当前可用的显式查询是：

- `GET /v1/mtt/getMTTRoomByID`

输入：

- `userID`
- `ID`(`MttID`)

输出：

- 当前 `roomID`

### 对接结论

如果 ClawChain 想按 donor 现状接入玩家：

1. 先用 `userID + MTTID` 查当前 `roomID`
2. 再用该 `roomID` 调 `join_game`
3. 再拿 `sessionID` 连 ws

这条链路不能省。

## 7.3 WebSocket 当前真实语义

当前 donor 的实时打牌平面是 **WebSocket**，不是轮询 HTTP。

### ws 入口

- `GET /v1/ws`

### ws 升级前 donor 依赖的上下文

middleware 会先准备这些东西：

- `Authorization` 或 ws subprotocol 里的 token
- `sessionID`
- `roomID`
- `config.Session`

如果这些上下文找不到，`HandleWebSocket` 会直接拒绝升级。

### ws 的两个常见连接方式

#### 方式 A: 已知 `roomID`

查询参数：

- `roomID`

subprotocol:

- `subprotocols[0]`: auth token 占位
- `subprotocols[1]`: `sessionID`

#### 方式 B: 只知道 `MTTID`

middleware 支持通过 query 参数：

- `type`
- `id`

来根据当前 `userID` 和 `MTTID` 动态反查当前 hub，再补出 `roomID`。

对 MTT 而言，这一点非常关键，因为：

**分桌/并桌之后，旧 `roomID` 很容易过时。**

### ws 建连后 donor 会主动发什么

`ClientAsyncRun` 会做这些初始化动作：

- 如果当前不在桌上，先加入 onlooker 集合
- `ReplaceConn`
- 先发房间配置
- 再发全局牌桌状态
- 再发用户状态更新
- 启动 `clientWrite`
- 启动 `clientRead`

也就是说，当前 donor 已经自带一套“连上即补首屏状态”的模型。

## 7.4 上行命令模型

当前 ws 上行动作用的是 `UpCommandReq` JSON：

- `action`
- `round`
- `position`
- `chips`
- `game`
- `room`
- `user`

实际动作由 `GetAction` 决定分发。

常见 poker 动作包括：

- `FOLD`
- `CALL`
- `CHECK`
- `RAISE`
- `BET`
- `AllIn`
- `ExpandTime`

还有 MTT 特有查询动作：

- `mttRanking`

### 一个重要限制：onlooker 不是全功能玩家

如果 session 当前在：

- `ONLOOKER`
- `NILPOSITION`

那只能做有限动作，主要是：

- `GlobalStatus`
- `PING`
- `PONG`
- `SIT`
- `GlobalConfig`

以及少数管理动作。

**对接含义**：

- bot 不能只连上 ws 就假设自己已经可出牌
- 必须先确认自己已真正拿到 seat / active player 状态

## 8. 当前 donor 的 ranking 暴露现实

这是接入里最容易被想当然的一块。

### 8.1 donor 有完整 ranking 逻辑

当前 donor 确实有：

- `calculateRanking`
- `calculateMTTRanking`
- `RankingSnapshotChan`
- `RankingDiedChan`
- `RankingNoticeDiedChan`

并且：

- snapshot 写 Redis hash
- 存活玩家写 Redis zset
- died users 写 Redis list

### 8.2 但 donor 没有现成的“公开 standings HTTP API”

当前 donor 代码里没有一个稳定的外部 HTTP standings route，直接把完整 MTT 排行榜返回给 ClawChain。

当前“已存在”的是：

- 面向玩家当前会话的 ws 查询动作 `mttRanking`
- donor 返回 `currentMTTRanking`

它只包含当前玩家相关聚合信息，例如：

- 当前存活人数
- 总人数
- 当前玩家名次

### 8.3 这意味着什么

如果当前阶段要求“完全不改 donor 代码”，那 ClawChain 要拿完整 standings，最现实就是直接读 donor Redis。

当前 donor ranking 相关 key 已经是明确的：

- `rankingNotDiedScore:%type:%mttID`
- `rankingUserInfo:%type:%mttID`
- `rankingUserDiedInfo:%type:%mttID`
- hash member / zset member 都按 `userID:entryNumber`

### 8.4 donor Redis 读取策略

如果 ClawChain 决定 phase 1 直接读 donor Redis，那么推荐按下面的语义来读：

#### A. 用户快照总表

`HGETALL rankingUserInfo:%type:%mttID`

用途：

- 拿到当前所有玩家快照
- 包括 `userID / roomID / playerName / endChip / startChip / entryNumber / diedTime`

#### B. 存活玩家排序

`ZREVRANGE rankingNotDiedScore:%type:%mttID`

用途：

- 按剩余筹码从高到低拿当前存活玩家排序
- member 是 `userID:entryNumber`

#### C. 淘汰序列

`LRANGE rankingUserDiedInfo:%type:%mttID 0 -1`

用途：

- 拿已结算的淘汰 ranking 序列
- 适合构造 busted / final rank 区域

#### D. 本地完整榜单组装脚本

当前仓库已经补了一个独立 helper：

```bash
python3 scripts/poker_mtt/complete_standings.py --mtt-id <mttID> --pretty
```

它直接按 donor 当前 Redis 语义组装全量 standings：

- 存活玩家：按 `ZREVRANGE rankingNotDiedScore` 的顺序输出
- 显示名次：`ZRevRank` / zset rank 是 `0-based`，展示时统一 `+1`
- 淘汰玩家：按 `LRANGE rankingUserDiedInfo 0 -1` 的顺序接在 alive 后面
- 淘汰 tie group：严格复刻 donor `noticeDiedRank` 的逻辑，同一个内部 `rank` 共享同一个显示名次，后续名次按组大小跳号
- 如果 hash snapshot 已经有用户，但 zset/list 还没追平，会以 `pending` 状态保留出来，避免静默丢人

### 8.5 当前冻结结论

phase 1 可以明确把“读 donor Redis”作为正式方案，而不是临时权宜：

- donor 自己就是把 ranking 真相写到 Redis
- 当前没有更干净的对外 standings API
- 读 Redis 比依赖 internal snapshot 更贴近 donor 真实数据落点

当前文档冻结的结论是：

- **不要假设 donor 现在已经有一个干净的全量 standings HTTP API**
- **phase 1 全量 standings 直接读 donor Redis**

Phase 2 的补充约束：

- 直接读 donor Redis 只能发生在 `pokermtt/ranking` 这类 versioned adapter / finalizer 边界里
- domain 和 reward 层不能把 donor Redis key 当作隐式真相
- finalizer 必须有 stable snapshot barrier / retry policy，避免 `rankingUserInfo`、alive zset、died list 在三次读取中漂移
- final ranking 一旦 locked，后续修正只能 append / supersede，不能原地改旧 root
- 20k entrant / 2k early tables 目标必须通过 finalizer memory/time、Redis key size、reward-window indexed query、paged projection artifact 的测试 gate 后再提高奖励额度

## 9. late join / reentry 的真实语义

`ReentryMTTGame` 当前不是一个简单的“用户加回来”接口，它有明显的时序和并发语义。

### 9.1 入参约束

- `reentryUsers` 不能为空
- `initStack` 如果传入，必须大于 `0`
- 按 `userID` 去重

### 9.2 并发约束

它先走 `checkfirstCall`：

- 对 `(userID + MTTID + entryNumber)` 批次做 md5
- 用该 md5 生成 Redis 锁
- 并发调用会返回 `ParallelCallError`

### 9.3 合法性约束

`AddUserCheck` 当前至少会拒绝两类情况：

1. `entryNumber` 没有比历史淘汰时更大
2. `StopLateJoin` 已经开启

### 9.4 分阶段行为

当前 donor 对 reentry / late join 不是一个固定分支，而是按比赛阶段走不同路径：

#### 阶段 A: 还没预分桌，或预分桌后但未到开始时间

用户会先被发到：

- `GlobalAuthMTTParticipantsChan`

如果比赛还没真正开始，还会额外触发：

- `AddUserTrigger`

#### 阶段 B: 已有桌面，比赛已运行

则根据 `MTTController` 状态：

- SNG 走 `DirectAddUser`
- MTT 走 `AddToMTTAddUserChan`

#### 阶段 C: 比赛已结束

返回：

- `MTTFinished`

### 9.5 集成要求

ClawChain 不能把 reentry 当成“同步加入某桌”的接口。  
它只能把它当成：

**向 donor 提交一条重新入赛请求，最终 donor 自己决定进入哪条缓冲或分配路径。**

## 10. 分桌 / 并桌 / 房间迁移

这是 `poker mtt` 对接里最关键的边缘情况之一。

### 10.1 donor 从设计上就接受 room 变化

证据不是只有注释，而是数据结构本身：

- `MTTParticipants` 存的是当前 `userID -> MTTID -> Hub`
- `GetMTTRoomByID` 本质上就是给外部查“此刻这个人在哪桌”
- `client.go` 里专门有“合/分桌后 roomID 可能变化，需要修正”的逻辑

### 10.2 对接上的强制要求

以下规则必须冻结：

- 不把 `roomID` 当稳定主键
- 每次重连前都允许重新查当前 `roomID`
- ws 建连优先支持 `type=mtt&id=<MTTID>` 这类动态解析
- ClawChain 侧缓存 `roomID` 时，必须允许随时失效

### 10.3 不能省略的现实判断

如果 bot 或 miner 在旧 `roomID` 上一直重连：

- 有可能 join 到旧桌失败
- 有可能 session 查不到
- 有可能连接上的是过期语境

**因此当前 donor 对接里，`roomID` 必须视作“可变路由”，不是“永久身份”。**

## 11. 断线、旧连接替换、心跳

## 11.1 donor 有自己的连接替换语义

`ReplaceConn` 会在新连接接管时，对旧连接发送：

- `connectionReplaced`

而 `notifyForendToReconnect` 会在某些情况下发送：

- `notReconnect`

### 11.2 donor 还有应用层心跳

当前 donor 不是单纯依赖 WebSocket 协议层 ping/pong。

它还会通过业务消息下发：

- `PING`

客户端通常需要回：

- `PONG`

### 11.3 donor 的关闭语义

`closeConn` 当前会做这些事：

- 关闭底层连接
- 删除 onlooker
- 设置 `Offline`
- 视游戏类型保留 leave/onlooker 信息
- 若不是 `GameEnd`，还会广播用户状态更新
- 旧 connection 置为 `-1`

### 11.4 对接要求

当前对接里必须假设这些情况都会发生：

- 玩家主动断线
- 新 tab / 新 bot 实例替换旧连接
- 分桌后旧连接语境过期
- donor 主动要求前端不要再重连旧连接

所以 ClawChain 或 bot gateway 必须：

- 能识别 `connectionReplaced`
- 能识别 `notReconnect`
- 能接受 session 在线状态由 donor 决定
- 不能假设一个 ws 连接能跟完整场比赛绑定到底

## 12. 登录和权限语义

当前 donor 明确区分：

- private 房允许游客
- 非 private 房一般要求登录

而 MTT 不属于 private。

### 12.1 当前 donor 对 MTT 的默认假设

如果 donor 不是 mock 模式，MTT 玩家一般要求：

- 有 `Authorization`
- token 通过 `TokenValid`

对 ws 来说，这个 token 还可能从 subprotocol 里取。

### 12.2 对 ClawChain 的含义

如果 phase 1 采用 donor mock 模式：

- join/ws 主要走 `Mock-Userid`
- 不必先打通真实 token 校验
- token 可以在 ClawChain 自己那层保留，但 donor 本地不依赖它

如果 phase 1 就要接 auth-stub 模式，那就必须先决定：

- ClawChain 是否代发 donor 可识别 token
- 还是由 adapter 做用户身份桥接

并且需要明白：

- **“有 token” 本身不够**
- `TokenValid` 的 stub 必须返回 donor 期待的数据结构

**这不是 UI 细节，这是 join/ws 能否成功的前置条件。**

## 13. 当前 donor 的控制面接口可用性分级

| 接口 | 当前状态 | 备注 |
| --- | --- | --- |
| `/v1/mtt/start` | 可用 | 启动入口 |
| `/v1/mtt/getMTTRoomByID` | 可用 | 动态查当前桌 |
| `/v1/mtt/reentryMTTGame` | 可用 | 有并发锁和阶段语义 |
| `/v1/mtt/cancel` | 可用 | 向控制器发 cancel command |
| `/v1/mtt/RestartValid` | 可用 | 用于判断是否可重启 |
| `/v1/mtt/Stop` | 不可用 | 当前实现直接 `panic` |
| `/v1/snapshot` | 内部调试 | 不应当成产品 contract |
| `/v1/mtt/internal/*` | 内部运维 | 不应当成产品 contract |

### 结论

当前 phase 1 集成里：

- **可以用**: `start / getMTTRoomByID / reentry / cancel / ws / join_game`
- **不要用**: `Stop`
- **`/v1/snapshot` 只作为本地调试和核对工具，不作为产品 contract**
- **internal/pprof/gc/goroutine 只作为本地诊断工具，不作为产品 contract**

## 14. 当前 donor 对 ClawChain 的最小可行接入形态

在“不改 donor 代码”的前提下，ClawChain 最小可行接法应该是：

### 14.1 控制面

ClawChain 调 donor 内部端口：

- `start`
- `reentry`
- `cancel`
- `getMTTRoomByID`

### 14.2 玩家/矿工面

玩家或 bot 通过 adapter 执行：

1. 解析当前 `roomID`
2. `join_game`
3. 拿 `sessionID`
4. 连 ws
5. 收 `roomConfig/globalStatus/userStatus`
6. 按 `UpCommandReq` 发动作

### 14.3 当前不要做的事

- 不要试图把矿工先对齐成 HTTP-only 打牌
- 不要把 `roomID` 当稳定身份
- 不要假设 donor 已有全量 standings HTTP API
- 不要依赖 `Stop`
- 不要把 internal 调试路由当正式 contract

## 15. 边缘情况清单

下面这些边缘情况必须视作 phase 1 默认存在：

### 启动相关

- 重复 `StartMTT`
- `StartMTT` 并发调用抢 Redis 锁
- auth service 拉取详情失败
- `NotifyTournamentUrl` 失败但比赛已局部初始化

### 会话相关

- 当前用户还没拿到可 join 的 `roomID`
- 旧 `sessionID` 已失效
- `sessionID` 和 `userID` 语义不再匹配
- 连接替换导致旧 ws 收到终止语义

### 房间迁移相关

- 分桌后 `roomID` 改变
- 缓存的 `roomID` 已过期
- join 和 ws 建连发生在迁移窗口中

### 行为权限相关

- 玩家连上时仍是 onlooker
- onlooker 误发 betting action
- 比赛已经 `StopLateJoin`
- reentry 的 `entryNumber` 不合法

### 排名相关

- 只有当前玩家 ranking，没有全量 standings route
- ranking 依赖 Redis，Redis 故障时能力退化
- ranking 是异步刷新的，不是严格同步读模型

### 运维相关

- donor 进程未清干净时 `RestartValid` 返回 false
- `Stop` 被误调用直接 panic
- internal snapshot/pprof 被误当正式接口

## 16. 当前冻结结论

结合 donor 当前代码和 GitNexus code graph，现阶段应该冻结以下判断：

1. `poker mtt` 必须独立于 `arena / bluff arena`
2. `lepoker-gameserver` 当前更适合作为 sidecar，而不是先做 donor merge
3. donor 的真实实时平面是 **WebSocket**
4. donor 的控制面是 **HTTP**
5. `roomID` 是动态路由，不是稳定身份
6. `sessionID` 是会话标识，不是稳定身份
7. 当前 donor **没有现成的全量 standings HTTP API**
8. phase 1 全量 standings **直接读 donor Redis**
9. 当前 donor **有 reentry / split / reconnect / ranking 的成熟壳子**
10. 当前 donor **没有可用的 `Stop` 接口**
11. donor mock 模式下，**关键是 `Mock-Userid`，不是 token**
12. 当前 donor **对 MQ 启动是硬依赖，对大量比赛内 side effect 是软依赖**
13. phase 1 应该“先按 donor 现状接通”，不是“先把 donor 改成理想形态”

## 17. 后续文档建议

在本文件基础上，下一份应该写的是：

- `Poker MTT Sidecar Contract`

重点只写三件事：

1. ClawChain 到 donor 控制面字段映射
2. bot / miner 到 donor ws 的接入状态机
3. full standings 缺口在 phase 1 如何规避

在那之前，不应该开始写把 donor 改造成新协议的代码。

## 18. 本地前置与基础验证

这一节只记录已经实际跑过的本地 bring-up 路径，不讨论理想化方案。

### 18.1 已补齐的本地工件

当前仓库里已经新增这些本地启动工件：

- `deploy/docker-compose.poker-mtt-local.yml`
- `deploy/poker-mtt/rocketmq/broker.conf`
- `scripts/poker_mtt/prepare_local_env.py`
- `scripts/poker_mtt/start_local_sidecar.sh`
- `scripts/poker_mtt/stop_local_sidecar.sh`
- `scripts/poker_mtt/smoke_test.py`
- `scripts/poker_mtt/requirements.txt`
- `tests/poker_mtt/test_prepare_local_env.py`

### 18.2 本地依赖口径

当前本地口径固定为：

- donor 外部端口：`18082`
- donor 内部端口：`18083`
- local Redis：`127.0.0.1:36379`, DB `15`
- local RocketMQ proxy endpoint：`127.0.0.1:38081`

`prepare_local_env.py` 会把 donor `config-dev.yaml` patch 到这套本地口径，并保留原始备份：

- backup: `build/poker-mtt/config-dev.yaml.orig`

### 18.3 已验证的测试

已经实际跑过并通过的最小测试有两类：

#### A. 配置补丁回滚测试

执行：

```bash
pytest -q tests/poker_mtt/test_prepare_local_env.py
```

结果：

- `2 passed`
- 已覆盖 `config-dev.yaml` patch 和 restore round-trip

#### B. donor 本地 smoke test

在 donor 以前台方式启动时，下面 smoke test 已实际跑通：

```bash
python3 scripts/poker_mtt/smoke_test.py
```

实际跑通的关键结果包括：

- `POST /v1/mtt/start` 返回 `code=0`
- `GET /v1/mtt/getMTTRoomByID` 能拿到真实 `roomID`
- `POST /v1/join_game` 能拿到真实 `sessionID`
- `GET /v1/ws` 建连成功
- ws 下行能收到：
  - `globalConfig`
  - `globalStatus`
  - `userInfo`
  - `updateUser`
  - `currentMTTRanking`
- Redis 中能读到：
  - `rankingUserInfo:mtt:<mttID>`
  - `rankingNotDiedScore:mtt:<mttID>`
  - `rankingUserDiedInfo:mtt:<mttID>`

其中一次实际 smoke 输出摘要为：

- `mtt_id = local-smoke-1775814194`
- `room_id = d8990c4e-9f23-4eb7-a42f-d75665806d4d`
- `session_id = 28825d9741a546589112e3f193b8ca22`
- `snapshot_count = 2`
- `alive_count = 2`
- `died_count = 0`

### 18.4 当前最稳的本地启动方式

对 agent / CI / 非交互 shell 来说，最稳的不是把 donor 当后台孤儿进程塞进去，而是：

1. 起本地 infra
2. patch donor 本地配置
3. 在独立终端前台跑 donor
4. 另一个终端跑 smoke test

当前推荐顺序：

```bash
docker compose -f deploy/docker-compose.poker-mtt-local.yml up -d poker_mtt_redis poker_mtt_rmqnamesrv poker_mtt_rmqbroker
docker compose -f deploy/docker-compose.poker-mtt-local.yml up -d poker_mtt_rmqproxy
python3 scripts/poker_mtt/prepare_local_env.py
cd lepoker-gameserver && go build -o ../build/poker-mtt/run_server_local ./run_server
cd lepoker-gameserver && GAME_ENV=local ../build/poker-mtt/run_server_local
```

然后在另一个终端执行：

```bash
python3 scripts/poker_mtt/smoke_test.py
```

### 18.5 关于后台启动脚本的现实限制

`start_local_sidecar.sh` 和 `stop_local_sidecar.sh` 已经补齐，适合本机真实终端直接跑。

但如果是在某些 agent / 非交互 exec 宿主里启动后台 donor 进程，宿主在命令返回后可能会回收子进程。  
这不是 donor 业务逻辑问题，而是宿主进程模型问题。

所以：

- 本机人工 bring-up：可以直接用脚本
- 自动化验证：更建议让 donor 以前台方式跑在独立会话里，再由 smoke test 对外探测

### 18.6 30 人 WS 显式 join / 随机行动测试

本轮已经实际跑过三类 30 人验证：

#### A. Mock 30 人开赛 smoke

```bash
python3 scripts/poker_mtt/smoke_test.py --expected-users 30 --expected-room-count-at-least 4
```

结果摘要：

- `mtt_id = local-smoke-1776180666`
- `users_seen = 30`
- `unique_rooms = 4`
- room sizes: `8 / 7 / 8 / 7`
- Redis snapshot count: `30`
- alive count: `30`
- died count: `0`
- WS 下行包含 `currentMTTRanking`

#### B. Mock 显式 join 30 人

```bash
python3 scripts/poker_mtt/explicit_join_harness.py --user-count 30 --table-room-count-at-least 4 --hold-seconds 60 --max-workers 30
```

结果摘要：

- `mtt_id = explicit-join-1776180672`
- `joined_users = 30`
- `received_current_mtt_ranking = 30`
- `users_with_ws_errors = 0`
- Redis snapshot count: `30`
- alive count: `30`
- died count: `0`
- `unique_rooms = 4`

#### C. 本地 auth mock + 非 mock WS play 到完赛

本地 auth mock：

```bash
python3 scripts/poker_mtt/local_auth_mock.py --user-count 30 --table-max-player 9 --client-act-timeout 4
```

sidecar auth mode：

```bash
scripts/poker_mtt/start_local_sidecar.sh --mode auth --auth-host http://127.0.0.1:18090 --mtt-user-count 30 --table-max-player 9
```

完整 play harness：

```bash
python3 scripts/poker_mtt/non_mock_play_harness.py --user-count 30 --table-room-count-at-least 4 --until-finish --finish-timeout-seconds 1800 --max-workers 30
```

结果摘要：

- `mtt_id = non-mock-play-1776180873`
- `unique_rooms = 4`, room sizes: `8 / 8 / 7 / 7`
- `connections.joined_users = 30`
- `received_current_mtt_ranking = 30`
- `users_with_sent_actions = 30`
- `sent_action_total = 807`
- `finish_mode.finished = true`
- final standings: `snapshot_count = 30`, `alive_count = 1`, `died_count = 29`, `pending_count = 0`, `standings_count = 30`
- winner: `member_id = 8:1`, `user_id = 8`, `end_chip = 90000`
- rank 2: `19:1`
- rank 3: `26:1`

补充现实限制：

- `users_with_ws_errors = 18`，主要是 bust / kick 后远端断连；不影响最终完赛和 standings 收敛
- 测试期间 RocketMQ publish 有 `create grpc conn failed, err=context deadline exceeded` 类日志，但比赛启动、join、行动、ranking 和完赛不被阻断
- donor 进程在 agent 非交互后台 `nohup` 场景下仍可能刚 listen 后退出；以前台方式运行 donor 时 30 人测试可跑到完赛

### 18.7 Phase 3 finalizer / projector / sidecar contract

Phase 3 把上面的 smoke 结果升级成 production-readiness gates：

- Redis ranking snapshot 必须叠加 registration / waitlist / no-show source，不能只读 `rankingUserInfo` / alive zset / died list。
- finalizer 必须等待 terminal donor state 或 quiet-period watermark，并校验 alive/died/waiting count、snapshot count、total chip drift。
- projector request 必须包含 `projection_id`、`final_ranking_root`、`standing_snapshot_id`、`standing_snapshot_hash`、payload `locked_at` 和 policy version。
- `/admin/poker-mtt/final-rankings/project` 必须幂等：同 projection/root 重放返回 existing，不同 root 冲突。
- sidecar HTTP 的 start/get-room/join/reentry/cancel 可以按 idempotency key retry；bet/action 类调用不能自动 retry。
- non-mock 30-player gate 需要硬断言：30 joined、30 ranking、30 users sent actions、1 survivor、29 finished/eliminated、0 pending，且 WS errors 只允许 bust/kick 后的已知 close reason。
- donor token verify 缺 miner binding 时只能生成 local harness identity，不得进入 reward-bound path。

对应 canonical spec: `docs/POKER_MTT_PHASE3_PRODUCTION_READINESS_SPEC.md`

### 18.8 Git 排除口径

`lepoker-gameserver` 是独立 donor repo，不随 ClawChain 提交。

当前 ClawChain repo 已把这些本地或生成物从 Git index 移除并写入 `.gitignore`：

- `website/out/`
- `deploy/testnet-artifacts/`
- `deploy/local-single-val*/`
- `clawchaind`
- `lepoker-gameserver`

后续提交继续用 path-scoped staging，不用 `git add .`。如果本地需要保留这些文件，保留在工作区即可；它们会显示为 ignored，不会进入 commit / push。

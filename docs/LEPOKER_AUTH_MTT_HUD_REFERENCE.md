# Lepoker Auth MTT / HUD Reference

**日期**: 2026-04-13
**donor repo**: `/Users/yanchengren/Documents/Projects/lepoker-auth`
**语言**: Java 17 / Spring Boot 3
**当前用途**: 作为 ClawChain `poker mtt` 的 MTT control plane、ranking、hand history、HUD、auth 参考实现

---

## 1. 这份文档做什么

这份文档只回答一个问题:

**`lepoker-auth` 里哪些 MTT / hand history / HUD / auth 设计已经被线上跑稳了，哪些值得在 ClawChain 的 Go 版 `poker mtt` 里借鉴。**

它不是 Java 代码逐文件讲解，也不是建议把 donor 单体直接搬进 ClawChain。

---

## 2. GitNexus 证据基础

本次先对 `/Users/yanchengren/Documents/Projects/lepoker-auth` 建了独立 GitNexus 索引，再结合源码做核实。

当前 GitNexus 索引结果:

- repo: `lepoker-auth`
- nodes: `12,230`
- edges: `33,877`
- communities: `419`
- processes: `300`

本次重点追的代码图谱节点:

- `MttService`
- `MttUserService`
- `RankingService`
- `MttScheduleChangeStatusTaskJob`
- `MttPayOutStructureUtils`
- `HandHistoryService`
- `DynamoDBUserHistoryService`
- `JWTVerify`
- `CognitoSrpAuthServiceImpl`
- `RecordListener`
- `RecordCalculateListener`
- `RocketMQConsumerService`

结论先说:

**`lepoker-auth` 虽然名字是 auth，但实际已经是一个“auth + MTT orchestration + ranking + HUD + hand history + MQ consumer”的业务中台。**

本轮把 `clawchain` 与 `lepoker-auth` 两边 GitNexus 图谱一起复查后，给 `poker mtt mining` 的结论更具体:

- `lepoker-auth` 的价值在于**结果控制面和投影链路**，不是替代 `lepoker-gameserver` 的实时牌桌 runtime
- `lepoker-auth` 的 MQ 链路已经证明“一手结束后产生牌谱消息，再异步持久化和投影 HUD”是稳定路径
- `lepoker-auth` 的 ranking 链路已经证明 **live ranking / final ranking / long-term leaderboard** 必须拆开
- `lepoker-auth` 的 ELO 可以参考为 **public rating / long-term rating**，但不应该直接当作 ClawChain 奖励权重
- `lepoker-auth` 的 auth 可以参考 token 验签和 user context 注入方式，但 ClawChain 第一阶段只需要薄 auth adapter

映射到 ClawChain 时，`lepoker-auth` 只作为 donor reference。ClawChain 当前落点仍是 `mining-service` 的 `poker_mtt_result_entries`、`poker_mtt_multiplier`、`reward_windows`、`settlement_batches` 与 `MsgAnchorSettlementBatch`。

---

## 3. 高层架构

从代码图和源码落点看，`lepoker-auth` 当前是一个典型的 Spring Boot 单体，里面把下面几层都包在了一起:

1. **认证层**
   - AWS Cognito SRP / refresh / social / admin token
   - JWT/JWKS 校验
   - AOP 把 `userID` 注入请求上下文

2. **MTT 控制面**
   - 创建、修改、取消、列表、详情、盲注结构
   - 报名、重报名、waiting room、join game
   - 状态调度、预开赛通知、开赛回调、结束处理

3. **实时排名层**
   - Redis 存活用户榜单
   - Redis 用户快照 / waiting 用户数 / total chip
   - 完赛后固化到 MySQL `mtt_ranking`

4. **牌谱与历史层**
   - RocketMQ 消费牌谱消息
   - raw hand history 写 DynamoDB
   - per-user game history 写 DynamoDB
   - 用户与 room 的映射关系写 MySQL

5. **HUD / recent / leaderboard 投影层**
   - 公共 HUD 指标按手计算
   - MTT/SNG/Private 完赛后的 special HUD
   - 实时投影先写 Redis，再落 MySQL HUD 表

6. **奖励与后台运营层**
   - payout structure
   - dynamic prize pool / KO bounty
   - ticket / contract pool / mix prize pool
   - admin MTT tab / weekly auto-create / announcement

换句话说，**它不是干净分层的服务网格，而是一个把多条业务链揉进一起的“控制中枢”。**

这对参考价值是好事，也有代价:

- 好处: 线上真实功能面完整
- 代价: 迁移到 Go 时必须拆边界，不能照着 service class 大搬家

---

## 4. Auth 参考路径

### 4.1 真实 auth 入口

主要入口在:

- `src/main/java/com/lepoker/pokerauth/controller/login/AuthController.java`
- `src/main/java/com/lepoker/pokerauth/controller/login/APIAuthController.java`
- `src/main/java/com/lepoker/pokerauth/infrastructure/advice/JwtAccessTokenAspect.java`
- `src/main/java/com/lepoker/pokerauth/infrastructure/utils/JWTVerify.java`
- `src/main/java/com/lepoker/pokerauth/service/impl/CognitoSrpAuthServiceImpl.java`

### 4.2 认证模型

当前 donor 的认证大致是:

1. `AuthController` 提供 `/signIn`、`/refresh_token`、`/token_verify`
2. `CognitoSrpAuthServiceImpl` 走 AWS Cognito `USER_SRP_AUTH`
3. `JwtAccessTokenAspect` 对 controller 层做切面拦截
4. `JWTVerify.verifyToken()` 通过 Cognito JWKS 验签 access token
5. 验完以后把 `userID` 塞进 request attribute

从实现看，`JWTVerify` 还同时支持:

- social token HMAC 签发和验签
- admin platform token 验签

### 4.3 对 ClawChain 的迁移建议

这条线**不应该和 `poker mtt` 业务揉在一起实现**。

Go 版建议拆成一个很薄的 auth adapter:

- `VerifyAccessToken(token) -> userID`
- `TokenVerify() -> {userID, playerName}`
- 需要时接 Cognito 或本地 mock

第一阶段如果 ClawChain 只需要“有 token 就能过”，那 donor 给你的最大价值不是把 Cognito 搬过来，而是：

- 明确 `token_verify` 的响应形状
- 明确用户上下文是怎么注入到业务请求里的
- 明确管理员 token 和普通 token 是两条校验线

---

## 5. MTT 控制面参考

### 5.1 核心类

MTT 控制面的核心不在 controller，而在几个大服务:

- `MttService`
- `MttUserService`
- `MttScheduleChangeStatusTaskJob`
- `MttPayOutStructureUtils`
- `RankingService`

### 5.2 已经具备的功能面

从 controller 和 code graph 看，donor 已经覆盖了比较完整的 MTT 功能面:

- 创建 / 修改 / 取消 MTT
- 列表 / 详情 / tab / blind structure
- 盲注结构编辑
- waiting room
- 用户报名 / 重报名 / join game
- 自动审批 / 手动审批
- ticket / clan / wallet / contract pool / mix prize
- weekly auto-create
- 公告、tab 管理、后台手动操作
- dynamic prize pool / KO bounty

典型入口:

- `MttController`
- `MttUserController`
- `MttAdminController`

### 5.3 MTT 状态机和调度思路

`MttScheduleChangeStatusTaskJob` 是 donor 非常值得参考的一块。

它不是只做 cron 改状态，而是把下面几件事绑到一起了:

1. 从 DB 找 `ANNOUNCED / REGISTERING / LATE_REG / RUNNING / PRIZE_POOL` 的 MTT
2. 到时间后从 `ANNOUNCED -> REGISTERING`
3. 开赛前 2 分钟调用 game server 的 `startGame`
4. game server 成功回调后，把 MTT 标记成 waiting-ready
5. `REGISTERING -> LATE_REG/RUNNING`
6. `LATE_REG -> RUNNING`
7. 周期检查 hand history 最近更新时间，发现卡死就告警
8. 在 30 分钟和 10 分钟窗口给 waiting 用户发 inbox / TG / LINE 通知

这说明 donor 实际上把 MTT 当成一个**带外部依赖的长生命周期任务**，不是单纯数据库记录。

### 5.4 对 ClawChain 的迁移建议

Go 版建议保留这个职责划分，但换实现形状:

- `mtt/control/service`: create, update, cancel, detail
- `mtt/control/registration`: apply, re-entry, join, approval
- `mtt/control/scheduler`: status transitions, pre-start notices, stuck detection
- `mtt/control/gameserver`: donor runtime adapter

不要做一个 6000 行 `MttService`。

---

## 6. Ranking 参考

### 6.1 donor 的 ranking 真实模型

`RankingService` + `MttService.getMttRanking()` 这条线说明 donor 的 live ranking 主真相在 Redis，不在 MySQL。

关键 Redis key:

- `rankingNotDiedScore:%s:%s`
- `rankingUserInfo:%s:%s`
- `rankingUserDiedInfo:%s:%s`
- `rankingTotalChip:%s:%s`
- `rankingWaitingUserNum:%s:%s`

大意是:

- **活着的玩家**在 ZSET 里按 chip 排
- **玩家快照**放 HASH
- **淘汰记录**放 LIST
- **总筹码**单独存，方便算 average chip
- **waiting 用户数**补在总人数里

### 6.2 donor 的完赛固化方式

`MttService.saveMTTRankingInfo()` 会在完赛时:

1. status 进入 finish 路径
2. 通过 finish handler / delayed MQ 进入 idempotent listener
3. `handleFinishMTT()` 调 `saveMTTRankingInfo()`
4. 从 Redis 拿 live ranking
5. 把 waiting 用户补进去
6. 对特殊赛制去重并补 bounty / defeat num
7. 算最终 prize pool size / dynamic payout
8. 把最终榜单 JSON 写进 MySQL `mtt_ranking.ranking_info`
9. 额外写 `mtt_winner_ranking` 行

然后 `handleFinishMTT()` 继续触发:

- `calculateMTTSpecialHUD()`
- inbox
- dynamic payout / sendPrize

ClawChain 不能把 donor 的 finish event 直接当 reward-ready。
正确映射是:

```text
FINISHED
-> final_ranking materialized
-> evidence readiness checked
-> evaluation_state locked
-> poker_mtt_result_entries
-> reward_window
```

donor 的 `PRIZE_POOL` 更像 bubble / payout threshold 状态，不是 terminal reward state。
`CANCELED` / `FAILED_TO_START` 默认不应进入 ClawChain reward window。

### 6.3 这部分最值得借鉴的点

有三个点值得直接借鉴到 ClawChain:

1. **live ranking 和 final ranking 分层**
   - live ranking 用 Redis
   - final ranking 单独 snapshot 固化

2. **waiting 用户不是 runtime 排名的一部分，但要在展示和完赛归档时补进去**

3. **完赛后要把 ranking snapshot 变成后续 reward/HUD 的输入，不要每次现查 runtime**

### 6.4 Go 版建议

ClawChain 的 Go 版建议明确拆成:

- `ranking/live_store`：Redis/sidecar runtime snapshot
- `ranking/finalizer`：比赛结束时生成 canonical standings
- `ranking/read_model`：供 reward / multiplier / HUD / replay 查询

---

## 7. Hand History 参考

### 7.1 MQ -> hand history 主路径

这条线已经比较清楚:

1. `POKER_RECORD_TOPIC` -> `RecordListener`
2. `RecordListener` 调 `HandHistoryService.handerRecordMQ()`
3. 先 `upsertHandHistory()`
4. 再解析玩家与房间映射
5. 再更新 ledger board
6. 再 `calculateRecordHandle()`

另外还有一条:

1. `POKER_RECORD_CALCULATE_TOPIC` -> `RecordCalculateListener`
2. 直接走 `calculateRecordHandle()`

还需要注意两条 side path:

- `POKER_RECORD_TOPIC_ORDER` -> `KoRecordListener` -> KO / hunter ordering
- `POKER_RECORD_STANDUP_TOPIC` -> `RecordStandUpListener` -> bust / stand-up end-state updates

`POKER_RECORD_CALCULATE_TOPIC` 在 auth 侧有 listener；本轮没有确认 donor gameserver 主路径一定生产该 topic，所以文档只能把它写成“可重算/补算入口”，不能写成已确认主生产路径。

`RocketMQConsumerService` 用 `bizId` 做幂等消费。

这说明 donor 已经把“牌谱持久化”和“牌谱指标计算”拆成两条可独立重放的消费路径。

### 7.2 raw hand history 的存储形状

raw hand history 放在 DynamoDB `HandHistoryPO`:

- partition key: `roomID`
- sort key: `seq`
- 主要字段: `beginTime`, `endTime`, `record`, `vdf`

`HandHistoryService.upsertHandHistory()` 的特点:

- 按 `roomID + seq` 加分布式锁
- Redis 存版本号，低版本消息直接丢弃
- 最终 `updateItem()` 覆盖写 Dynamo

这说明 donor 的 hand history 不是 append-only blob store，而是**允许同一手后续消息补齐 show card / rabbit hunting / vdf** 的 upsert 模型。

更精确地说:

- show card / rabbit hunting 是已确认的同 key 后续更新语义
- gameserver 侧会发 `VDF_RECORD`，但本轮没有确认 auth 侧同一路径一定消费并写入 `HandHistoryPO.vdf`
- ClawChain 文档里不应把 VDF 写成已确认的同一路 hand-history upsert 路径，除非后续找到或补上对应 consumer

### 7.3 牌谱展示层

`processHandHistory()` 会做一些 UI / replay 侧的整形:

- 排除 rabbit hunting / show-card-only 记录
- 按 round / action 排序
- 只保留当前用户必要的 hole-card 视角
- 去掉无关 sessionID
- 补全 ante action

这部分也值得参考:

**raw history 和 replay history 不一定是同一个对象。**

Go 版最好保留:

- `raw_hand_record`
- `replay_projection`

两个层次。

---

## 8. User Game History 参考

### 8.1 donor 不是只存 raw hand history

`DynamoDBUserHistoryService` 说明 donor 还维护了一张**按用户维度组织的 game history**。

对应 Dynamo 模型 `UserGameHistoryPO`:

- PK: `userID`
- SK: `roomID`
- GSI:
  - `userTypeQueryHash-endTime-index`
  - `roomID-index`
  - `clanID-endTime-index`

主要字段:

- `gameType`
- `endTime`
- `hands`
- `net`
- `buyInAmount`
- `seqs`
- `insurance`
- `rake`
- `jackpot`
- `inGameNet`

### 8.2 这个模型的意义

它不是拿来替代 raw hand history 的，而是提供:

- 按用户分页查比赛历史
- 按 room/game 查所有参与用户
- 按 clan 查历史
- 拉 game detail 页面时先拿轻量 summary，再决定是否下钻 raw hand history

这是 donor 一个很重要的设计判断:

**raw hand history 和 user-facing history feed 不是同一张表。**

对 ClawChain 来说，这比“只把所有手牌直接扔 object store”更有参考价值。

---

## 9. HUD 参考

### 9.1 donor 的 HUD 是三层模型

从 `UserHudInfoPO`、`UserHudDailyPO`、`UserHudInfoHistoryPO` 可以看出来 donor 的 HUD 不是只有一张汇总表。

它至少分成:

1. `user_hud`
   - 当前累计 HUD
2. `user_hud_daily`
   - 日维度 HUD
3. `user_hud_history`
   - 历史快照 / 明细累计

### 9.2 已经覆盖的指标

从 PO 字段和 `calculateAllMetrics()` 看，当前 donor 已经明确在算:

- `VPIP`
- `PFR`
- `3-bet`
- `c-bet`
- `WTSD`
- `WSSD`
- `gamePlayed`
- `gameWin`
- `gameProfitable`
- `totalHands`
- `winHands`
- `flopHands`
- `showDownHands`

### 9.3 donor 的 HUD 计算模型

`calculateCommonHUD()` 是按**单手**计算公共指标，然后推到 Redis `REALTIME_HUD` 列表。

而 MTT / SNG 完赛后，`calculateMTTSpecialHUD()` / `calculateSngSpecialHUD()` 再补:

- `gameWin`
- `gameProfitable`
- `userRank`
- recent record end state

也就是说 donor 把 HUD 分成了:

- **手级行为指标**
- **赛级结果指标**

这是很合理的拆分。

### 9.4 对 ClawChain 的迁移建议

`poker mtt mining` 如果要做 multiplier、hidden eval、风格识别，Go 版建议至少拆成 3 类 projector:

1. `hand_metrics_projector`
   - VPIP / PFR / 3-bet / c-bet / WTSD / WSSD

2. `recent_projector`
   - 最近比赛 / 当前比赛 / 淘汰状态 / 排名变化

3. `tournament_result_projector`
   - final placing
   - in-the-money
   - winner
   - bounty / special payout

不要把这些混成单次“比赛结束后统一重算”的大 job。

---

## 10. 这个 donor 对 `poker mtt mining` 的直接参考价值

### 10.1 已经能直接借鉴的能力

`lepoker-auth` 已经给出了一套线上跑稳的思路:

- MTT 控制面和 donor game server 的衔接方式
- 用 Redis 承接 live ranking
- 完赛时生成 ranking snapshot
- raw hand history 写 DynamoDB
- per-user history 单独建 Dynamo 读模型
- HUD 不只算终局名次，还算手级行为指标
- MQ 消费要有幂等键
- stuck tournament 可以靠 hand history watermark 发现

### 10.2 这对 `mining` 很重要的点

对你现在的 `poker mtt mining` 来说，最有价值的不是它的 Java 语法，而是它已经证明了下面这套拆分是成立的:

- runtime/live ranking
- final ranking snapshot
- raw hand history
- user history feed
- HUD aggregates
- tournament reward / payout

这 6 个对象不是一个表，也不是一个 service。

### 10.3 ClawChain 需要拆成三类 ranking

结合 `lepoker-auth` 与 ClawChain 当前设计，`poker mtt` 后续文档和代码里建议固定使用这三个名字:

| 名称 | donor 参考 | ClawChain 用途 | 是否进奖励 |
|------|------------|----------------|------------|
| `live_ranking` | Redis `rankingNotDiedScore` / `rankingUserInfo` / `rankingUserDiedInfo` | 比赛中展示、断线恢复、赛中观测 | 否 |
| `final_ranking` | `saveMTTRankingInfo()` 固化 `mtt_ranking.ranking_info` | 完赛 canonical standings、`tournament_result_score` 输入 | 是 |
| `long_term_ranking` | daily / regular leaderboard、ELO、HUD history | public ladder、ELO/rating、长期声誉和 multiplier 参考 | 间接进入 |

这个拆法能避免两个常见错误:

- 用实时筹码榜直接发奖励
- 用长期 ELO 直接覆盖单场 MTT 结果

ClawChain 的 reward window 应只吃 `final_ranking` 派生出的 `poker_mtt_result_entries`，再把 `long_term_ranking` 作为慢变量输入。

更严格地说，`long_term_ranking` 不能等同于 public ELO。
只有内部的 long-term quality snapshot 可以有界地影响 multiplier / reputation；public ELO / public rating 只用于展示、匹配、风控辅助，不直接进入正向 reward weight。

### 10.4 ClawChain 需要拆成两类 HUD

donor 的 `calculateCommonHUD()` 与 `calculateMTTSpecialHUD()` 实际已经给出短期 / 长期拆法。

ClawChain 建议固定为:

| 名称 | 来源 | 内容 | 用途 |
|------|------|------|------|
| `short_term_hud` | raw hand history 的最近窗口 | VPIP / PFR / 3-bet / c-bet / WTSD / WSSD、最近若干手行为 | hidden eval、风格识别、异常检测、赛后解释 |
| `long_term_hud` | `user_hud` / `user_hud_daily` / `user_hud_history` 类累计模型 | 长期 VPIP/PFR/3-bet、长期 showdown、长期 ITM / win / profitable | ELO/rating 校准、multiplier 慢变量、risk review |

`short_term_hud` 不应该直接发币。它更适合作为 `hidden_eval_score`、`risk_flag`、`evidence_root` 的输入。

`long_term_hud` 不应该替代 `final_rank`。它更适合作为 `consistency_score`、`poker_mtt_multiplier`、`reputation_delta` 的输入。

### 10.5 MQ 路径对 ClawChain 的具体映射

GitNexus 与源码共同确认 donor 的核心路径是:

```text
POKER_RECORD_TOPIC
-> RecordListener.onMessage()
-> RocketMQConsumerService.idempotentConsume(bizID)
-> HandHistoryService.handerRecordMQ()
-> upsertHandHistory()
-> buildPlayerInfoByRecord()
-> userRoomService.saveUserRoom()
-> ledgerBoardService.calculateLedgerBordByRecord()
-> calculateRecordHandle()
-> calculateCommonHUD()
-> Redis REALTIME_HUD
```

迁移到 ClawChain 时，Go 版可以保留同样语义，但不要强依赖 RocketMQ:

```text
hand_completed event
-> idempotent consumer
-> poker_mtt_hands upsert
-> user/game history projection
-> short_term_hud projector
-> final_ranking finalizer
-> poker_mtt_result_entries
-> reward_window / settlement_batch
```

如果第一阶段继续沿用 donor gameserver 的 MQ，ClawChain adapter 需要把 MQ 当作**证据输入**，不是把 MQ 消费器写成 scoring engine。

ClawChain 边界建议命名成 `hand_completed_event`，RocketMQ 只是 donor transport。
同一手后续 show-card / rabbit-hunting update 需要带 version / checksum；低版本不能覆盖高版本，同版本不同 checksum 必须进入 conflict review。

### 10.6 ELO / rating 的参考边界

donor 的 `EloService` 使用多人排名转 ELO 的经典结构:

- `expected_score` 来自两两分差
- `actual_score` 来自 MTT/SNG 最终名次
- `K = 32`
- `D = 400`

这个可以作为 `poker_mtt_public_rating` 的参考，但 ClawChain 第一阶段不建议让 ELO 直接进入窗口奖励公式。

推荐顺序:

1. `final_ranking -> tournament_result_score`
2. `hidden_eval_score + consistency_score -> total_score`
3. `total_score -> reward_window`
4. `total_score rolling window -> poker_mtt_multiplier`
5. `final_ranking + long_term_hud -> public_rating / ELO`
6. `public_rating / ELO` 只用于展示、匹配、反作弊辅助，不直接发币

这样能防止 ELO 变成可刷的主奖励入口。

---

## 11. 不要照搬的地方

有几件事不建议照搬。

### 11.1 不要照搬单体边界

`lepoker-auth` 把 auth、MTT、HUD、history、wallet、ticket、announcement 都揉进一个 Spring Boot 服务。

Go 版 ClawChain 不该这么做。

### 11.2 不要照搬超大 service class

`MttService`、`MttUserService`、`HandHistoryService` 都已经是“大总管型类”。

这类实现对线上演进常见，但对新系统迁移不是好模板。

### 11.3 不要让 Redis key 变成隐式系统契约

donor 的 live ranking、waiting user、HUD realtime、payout、bounty 大量靠 Redis key 约定驱动。

ClawChain Go 版可以继续用 Redis，但需要把这些 key 背后的**领域模型**先显式写出来。

### 11.4 不要把 Cognito 强耦合进 `poker mtt`

auth 只是入口适配，不该成为 `poker mtt` 领域层的核心依赖。

---

## 12. 建议的 Go 版拆分

我建议 ClawChain 按下面的包边界去吸收 donor 经验。
因为仓库已经有顶层 `arena/*`，Poker MTT 更适合用顶层 `pokermtt/*`，不要放进 `arena/*`。

### A. `pokermtt/control`

- tournament create/update/cancel/detail
- registration/re-entry/join
- waiting room / pre-start / notifications

### B. `pokermtt/ranking`

- live ranking store
- final standings finalizer
- ranking snapshot read model

### C. `pokermtt/history`

- raw hand record ingest
- hand upsert / version guard
- replay projection

### D. `pokermtt/hud`

- hand metrics projector
- tournament result projector
- daily / rolling HUD snapshots

### E. `pokermtt/rating`

- public ELO / rating projector
- long-term ranking snapshot
- rating versioning
- display-only public ladder

### F. `pokermtt/rewards`

- payout policy
- ranking-to-reward mapping
- mining score inputs
- reward window projection
- settlement batch input

### G. `pokermtt/settlement`

- `reward_window` builder
- `settlement_batch` adapter
- anchor payload evidence roots
- `reputation_delta` exporter

### H. `authadapter`

- token verify
- user context inject
- optional Cognito adapter / local mock

领域层只接收 `Principal`:

- `user_id`
- `miner_address`
- `display_name`
- `roles`

`Cognito`、`JWKS`、`TokenValid`、`Mock-Userid`、bearer parsing 都只能留在 adapter，不进入 tournament / ranking / reward domain。

这个拆法保留 donor 的业务经验，但不会把 Java 单体原样复刻到 Go。

---

## 13. 对当前 ClawChain 文档的落点

这份 donor 应该被视为当前 `poker mtt` 设计文档的一个补充参考面:

- `lepoker-gameserver`
  - 参考 runtime、table、ws、ranking live state
- `lepoker-auth`
  - 参考 auth、MQ consumer、hand history、HUD、MTT control/read model

也就是说，后续做 ClawChain `poker mtt` 时:

- 如果是在问“比赛怎么跑”
  - 先看 `lepoker-gameserver`
- 如果是在问“结果怎么存、榜怎么做、HUD 怎么算、auth 怎么接”
  - 先看 `lepoker-auth`

### 13.0 Poker MTT Evidence Phase 2 borrow matrix

2026-04-17 六 agent 复核后，Phase 2 对 donor 的借鉴边界进一步收窄为“借结构，不搬服务”：

| donor concept | ClawChain target | Phase 2 简化方式 |
|---|---|---|
| `TokenValid` / user context | `authadapter/*`, `pokermtt/identity/*` | 只输出 `Principal`；Cognito/JWKS/admin token 留在 adapter，不进 domain |
| `MttService` control plane | Go control/read model | 拆成 control、registration、scheduler、sidecar adapter；不搬 6000 行 Java service |
| `saveMTTRankingInfo()` | `pokermtt/ranking.Finalizer` + `poker_mtt_final_rankings` | live Redis snapshot 只做 finalizer 输入；reward 只吃 canonical final ranking |
| `RecordListener` / `RecordCalculateListener` | hand event ingest / consumer checkpoint | MQ 只是 transport；event idempotency、version、checksum 才是 ClawChain contract |
| `HandHistoryService.upsertHandHistory()` | `poker_mtt_hand_events` / optional DynamoDB adapter | 一手完成后一条 durable write；same version checksum mismatch 进入 conflict |
| `calculateCommonHUD()` | `short_term_hud` projector | 服务 hidden eval / risk，不直接发币 |
| `calculateMTTSpecialHUD()` | `long_term_hud` / rating snapshot | 服务 consistency / public rating / multiplier 慢变量 |
| donor ELO / leaderboard | `poker_mtt_public_rating` / `poker_mtt_public_rank` | 展示、匹配、风控辅助；不做正向 reward weight |
| DynamoDB user history GSIs | per-user/history read model | DynamoDB 是生产候选；confirmed MTT raw hand ingest path 仍以 `HandHistoryService.upsertHandHistory()` 为准，ClawChain core 只依赖 storage interface |

不要借：

- wallet / ticket / clan / private-room / gold-coin 语义
- dynamic prize pool / bounty / rebuy / add-on / late registration，除非后续单独立项
- `MttService` 巨型业务中台形状
- ELO 或 public leaderboard 直接发币
- raw hand history 上链
- MQ consumer 直接变 scoring engine

### 13.1 Phase 1 不要实现的东西

Phase 1 只做 reference-driven adapter 和 projection，不做完整 donor control plane 迁移。

明确不要做：

- 不把 Cognito / JWKS / donor token 逻辑写进 `pokermtt` domain
- 不把 `MttService` / `MttUserService` / `HandHistoryService` 巨型 service 原样搬到 Go
- 不让 MQ consumer 直接承担 scoring engine 职责
- 不让 ELO / public rating 直接影响 reward weight
- 不在 finish handler 里做 direct wallet payout
- 不把 Redis key 当成隐式系统契约

### 13.2 Phase 1 已借用 / 暂缓口径

已经进入 ClawChain Phase 1 设计或实现的 reference 点：

- thin auth adapter / local mock token 路径：借鉴 donor token verification 和 user context 注入，但不把 Cognito/JWKS 放进 `pokermtt` domain
- final ranking 先 canonicalize，再投影 `poker_mtt_result_entries`
- reward-bearing 入口现在以 `poker_mtt_final_rankings` 为准；legacy/admin apply 只能引用并匹配已保存 final ranking，不能凭 payload 自证
- reward eligibility 必须等证据状态完整；未锁定结果不进 reward window
- hand history 采用“一手完成后及时异步上传”的事件口径，不按每个 action 写永久存储
- HUD / ELO / public rating 先作为后续 projector 输入，不直接参与 Phase 1 正向奖励权重
- settlement 只锚窗口 root；projection artifact 保存 final ranking / evidence / multiplier roots

### 13.3 Phase 2 beta gate 已固化的 donor 借鉴

Phase 2 已把 donor 里线上跑稳的几个结构转成 ClawChain 自己的 Go/Python 合同，而不是搬 Java service：

| donor 稳定路径 | ClawChain Phase 2 beta gate |
|---|---|
| `RecordListener` 一手后发 MQ | `poker_mtt_hand_events` 以 `hand_id + version + checksum` 幂等 ingest |
| `HandHistoryService.upsertHandHistory()` | completed-hand evidence manifest，可重放但不上链原文 |
| `calculateCommonHUD()` | short-term HUD snapshot / manifest，服务 hidden eval 和风险观察 |
| `calculateMTTSpecialHUD()` / ELO | long-term HUD、rating snapshot、multiplier snapshot，慢变量化，不做直接 reward weight |
| `saveMTTRankingInfo()` | canonical final ranking handoff，reward 只吃 locked final ranking projection |
| Redis live ranking | Go finalizer 的 stable snapshot 输入，不直接进 reward window |
| DynamoDB raw / user history | 生产候选 adapter / read model；当前 confirmed MTT raw hand path 是 `HandHistoryService.upsertHandHistory()`，core 只依赖 hand evidence store contract |

新增约束：

- 大 reward projection 必须分页，主 artifact 只放 `miner_reward_rows_root` 和 page refs
- settlement materialization 会读取 page artifact 并校验 page root / full rows root
- typed `x/settlement` confirmation 必须查链上 stored state；fallback memo 只能作为 degraded proof
- Redis-only finalization 还不是 donor parity；Phase 2 production harness 必须合并 registration / waitlist snapshot，等待或 no-show 用户进 final archive 但不进 reward rows
- MQ parity 当前只借鉴 `bizId` 幂等思想；ClawChain 还需要 checkpoint / replay / DLQ / lag harness，不能把 offline load generator 当作 RocketMQ parity
- `x/reputation` 仍不接 donor ELO，也不接单场 hidden eval；等窗口级 reputation delta 设计成熟后再接
- rollout 上默认关闭 poker MTT 自动 reward window 和 settlement anchoring，等 final ranking / evidence / projection 测试稳定后按环境打开
- 链上 settlement anchor submitter 采用显式白名单，避免任何账户提交同一 `settlement_batch_id` 的抢先或冲突 root

暂缓的 donor 能力：

- Cognito SRP / refresh / social login 全量迁移
- Java `MttService` / `MttUserService` 业务中台原样搬运
- RocketMQ consumer 直接写成 ClawChain scoring engine
- ELO 或 public leaderboard 直接发币
- per-hand S3 冷归档与 full replay bundle
- `x/reputation` 直接接收单场 total score 或 raw HUD

---

## 14. 最后结论

`lepoker-auth` 最值得抄的不是 Java 代码本身，而是它已经被线上证明过的几个结构判断:

1. **MTT 控制面和 runtime 是两层，不是一层**
2. **live ranking 和 final ranking 必须分开**
3. **raw hand history 和 user-facing history feed 必须分开**
4. **HUD 要拆成手级行为指标和赛级结果指标**
5. **MQ consumer 必须天然幂等**
6. **auth 适配层不能和 `poker mtt` 领域逻辑绑死**

如果要在 ClawChain 里用 Go 重做，这 6 条比任何一段 donor 代码都更重要。

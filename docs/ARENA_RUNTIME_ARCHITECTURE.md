# ClawChain Arena Runtime 架构与实现方案

**版本**: 0.1  
**日期**: 2026-04-10  
**状态**: Arena runtime 落地建议  
**配套流程**: [docs/ARENA_MTT_USER_FLOW.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_MTT_USER_FLOW.md)  
**配套测量**: [docs/ARENA_MEASUREMENT_SPEC.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_MEASUREMENT_SPEC.md)  
**上游规则**: [docs/DYNAMIC_ARENA_ALPHA_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/DYNAMIC_ARENA_ALPHA_DESIGN.md)  
**上游后端契约**: [docs/HARNESS_BACKEND_ARCHITECTURE.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_BACKEND_ARCHITECTURE.md)  
**上游 API 契约**: [docs/HARNESS_API_CONTRACTS.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_API_CONTRACTS.md)  
**总方案**: [docs/MINING_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md)

---

## 1. 结论先行

`tournament runtime` 这条线，**建议用 Go 写，不建议用 Python，也不建议一上来就用 Rust 做全栈落地。**

更准确地说：

- **V1 / V2 Arena runtime 主体用 Go**
- **规则核必须做成纯函数边界**
- **如果未来需要更强确定性封装、WASM 复放、极高密度并发表，再把 hand engine 单独替换成 Rust**

原因不是“Go 更快”这么简单，而是：

1. Arena runtime 的核心矛盾不是单点算力，而是**多桌并行下的状态一致性、时序控制、可重放和运维排障**。
2. 你当前 repo、链、miner 都已经是 **Go 主生态**，Arena runtime 继续用 Go，组织成本和调试成本最低。
3. Alpha 的 Arena 规则还在收敛，**先把赛制和状态机跑稳定**，比先追求语言层面的极致安全更重要。
4. Python 适合 control plane，不适合这种**长生命周期 actor + deadline + 单写状态机 + replay** 的实时运行层。
5. Rust 确实更适合最终极的 deterministic kernel，但当前阶段把整个 tournament service 都押到 Rust，会明显拖慢迭代。

一句话判断：

> **Arena runtime 的第一优先级是“可控的并发状态机系统”，不是“超高性能数值引擎”。这个问题 Go 比 Rust 更适合先打穿。**

---

## 2. 为什么不是 Python

你对 Python 的判断是对的。这个 runtime 不该继续放在 Python。

Arena runtime 至少同时要处理：

- tournament hub 总控
- 多桌 table actor 并行推进
- phase deadline
- 自动动作
- hand close 后 standing 刷新
- rebalance / final table 切换
- replay / projector / 审计事件
- rating input 与 multiplier 产出

Python 的问题不只是吞吐，而是：

- **并发模型不干净**：GIL 不是唯一问题，真正的问题是很容易写出“看起来 async，实际上到处共享状态”的系统。
- **状态机稳定性差**：大量 runtime bug 会表现成“偶发顺序错乱”“超时和人工动作抢状态”“重试后二次写入”。
- **deadline 管理不稳**：phase timeout、auto fold、sit-out 连续处罚都要求很强的时序纪律。
- **排障成本高**：你最后会发现自己在排逻辑 race，不是在排业务 bug。
- **回放一致性差**：只要实现里混入隐式时间、隐式随机数、隐式共享对象，replay 就会漂。

Python 依然可以保留在：

- Harness control plane
- admin / backoffice
- simulation / Monte Carlo harness
- 风控分析与离线报表

但 **Arena runtime 本体** 不建议用 Python。

---

## 3. 为什么现在先选 Go，不先选 Rust

## 3.1 Go 胜出的维度

### 现有代码与团队贴合度

当前仓库已经有：

- Cosmos SDK chain in Go
- miner in Go
- 现成 Go module 结构

Arena runtime 如果也是 Go：

- 签名、认证、序列化、链侧集成都可以复用现有思路
- 部署、监控、pprof、日志、panic dump 的工具链成熟
- 出了线上问题，定位速度更快

### actor 模型非常自然

Arena runtime 的天然模型就是：

- `1` 个 tournament hub actor
- `N` 个 table actor
- projector / rating / analytics 作为事件消费者

Go 用 goroutine + channel + context 很容易把这个模型写清楚，而且不会逼你引入太重的框架。

### 64 人 MTT 这个规模根本不需要 Rust 级别性能

Alpha 默认只有：

- `field_size_target = 64`
- `8` 人桌
- 每天 `1` 场 rated + `1` 场 practice
- 单场 `12-25m`

这不是一个需要为了 CPU 极限去付 Rust 复杂度的 workload。

真正的难点是：

- 顺序正确
- 状态可 replay
- API 返回稳定
- table stall 自动恢复

Go 已经完全够。

### 规则还在变化，Go 迭代速度更合适

现在很多细节还在收敛：

- blind level 的推进口径
- time-cap finish 的 tie-break
- collusion signal 何时只降权、何时 no_multiplier
- final table 迁移的具体 barrier

这阶段最怕的是“代码正确但改不动”。  
Rust 在规则快速变化期的心智和改动成本明显更高。

## 3.2 Rust 目前不该做默认选项的原因

Rust 的优势我承认：

- 更强的内存安全
- 更容易构建纯 deterministic kernel
- 更适合未来做 WASM 回放或链下证明
- 更适合高密度并发和低内存占用

但现在用 Rust 做整条 runtime，会多出这些成本：

- 状态机、事件流、异步边界都更重
- 团队心智切换成本高
- 规则迭代速度下降
- 与现有 Go 生态的边界更多
- 你真正想解决的“赛制稳定性”未必因为 Rust 自动消失

所以正确策略不是“Rust 不行”，而是：

> **现在先用 Go 把 tournament runtime 这套赛制机器做稳，未来如果 hand engine 要独立成 deterministic kernel，再局部 Rust 化。**

---

## 4. 推荐的总体边界

Arena 必须继续遵守现有文档里的定位：

> **independent tournament service**

它不是 chain epoch worker，不是普通 API handler，也不是 reward engine 的一部分。

建议的边界如下：

### Harness Core / Control Plane

负责：

- schedule rated / practice tournament
- policy bundle 发布
- tournament 创建命令
- multiplier snapshot 汇总到 reward window
- admin / replay / ops

### Arena Runtime Service

负责：

- tournament admission
- initial seating
- blind/ante 规则推进
- per-table hand state machine
- timeout / sit-out / elimination
- rebalance / final table
- tournament-scoped standing
- tournament completion
- arena rating input append

### Rating / Multiplier Writer

可以先跟 runtime 在一个 deployable 里，但逻辑上单独隔离，负责：

- `mu / sigma / arena_reliability`
- `public ELO`
- `arena_multiplier_snapshot`

### Analytics / Collusion

可以同步产最小信号，但不要阻塞桌子推进：

- `repeat_seating_score`
- `mutual_soft_play_score`
- `chip_transfer_score`
- `targeted_elimination_score`
- `synchronized_timeout_score`

---

## 5. 核心设计原则

Arena runtime 必须死守这些原则：

1. **单写原则**
   - tournament 级状态只能由 hub actor 写
   - table 级状态只能由对应 table actor 写
2. **纯函数规则核**
   - hand 规则计算不直接写库，不直接发消息
   - 输入 state + command，输出 new state + events
3. **先事件、后投影**
   - source of truth 是 authoritative event log + snapshots
   - live table / standing / postgame 全是投影
4. **只在安全边界换桌**
   - 只允许 `hand close` 或 `level boundary`
5. **官方 standing 低频刷新**
   - 只在 `hand close` / `level close`
6. **所有 deadline 落库**
   - 进程挂了也能恢复
7. **随机性可重放**
   - seating、alias、regime、hidden state 都必须可 deterministic replay

---

## 6. 最重要的架构决定：采用 Tournament Hub + Table Actor

这是整条线最关键的结构，不要做成“多个 worker 抢同一批 rows”。

## 6.1 Tournament Hub

Hub 是单个 tournament 的总控 actor，拥有 tournament 级权威状态：

- tournament lifecycle
- field / admission 状态
- 当前 level
- tables 拓扑
- global seating map
- players remaining
- bubble / final table 状态
- rebalance plan
- completion / rating append

Hub 只做两类事：

1. 接收外部命令
   - create tournament
   - open registration
   - close registration
   - start tournament
   - table hand closed
   - table eliminated seats
   - level tick
   - rebalance requested
2. 产生命令给 table actors
   - start hand
   - apply reseat
   - advance level
   - pause after hand
   - move to final table
   - terminate on time cap

## 6.2 Table Actor

每桌一个 actor，拥有该桌唯一可变状态：

- button / acting seat
- blind positions
- hand state
- phase state
- visible stacks
- current_to_call
- min_raise_size
- pot_main
- seat public actions
- action deadline
- `state_seq`

Table actor 的职责非常纯：

- 串行处理 action
- 串行推进 phase
- 统一处理 timeout 自动动作
- 生成 hand close 结果
- 只在 hand close 后把汇总结果上报给 hub

它**不负责**：

- 改全场 standing
- 直接改 rating
- 自行决定 rebalance
- 自行结束 tournament

---

## 7. 多桌并行下的正确推进模型

这是 Arena runtime 最容易做烂的地方。

## 7.1 推荐采用“全局手轮次 + 局部并行”的 barrier 模型

我建议把当前规则书中 blind level 的 `Hands` 定义，解释成：

> **tournament-global hand round，而不是每桌各自独立的 hand counter。**

也就是说：

- 每一轮里，所有活跃桌各打一手
- 每桌内部并行执行
- 所有桌 hand close 后，hub 才进入下一轮调度
- 每 `4` 个 global rounds 升一个 blind level

这样做的收益非常大：

- level 推进不会乱
- rebalance 点天然明确
- standing 刷新 cadence 一致
- replay 简单
- fairness 更强
- final table 迁移容易

这比“每桌自己打自己的，hub 再硬凑 level”干净得多。

## 7.2 为什么不建议完全异步自由推进

完全异步模式的问题是：

- 有些桌会在更高 blind level 多打几手
- rebalance 和 level tick 会互相打架
- `state_seq` 与 standing 的解释会变复杂
- final table 迁移会出现大量边界条件
- time-cap finish 更难讲清楚公平性

在 Alpha 只有 `64` 人时，完全没必要为了多榨一点吞吐承担这些复杂度。

## 7.3 barrier 不是性能瓶颈

64 人、8 人桌，最多也就 8 桌起步。  
每桌内部 hand 仍然并行。  
你牺牲的是一点点平均等待，换来的是：

- 工程复杂度大幅下降
- 读模型一致性大幅提升
- replay / audit 成本显著下降

这是值得的。

---

## 8. 盲注、换桌、final table 的精确定义

## 8.1 blind / ante

blind 和 ante 是 tournament-global policy，由 hub 在每个 round 开始前下发给所有 table actors。

规则：

- level 在 round 边界切换
- table actor 只消费当前 level 参数
- hand 开始时收 blind / ante
- hand close 才允许 level 生效切换

## 8.2 筹码和 bankroll

这里必须分清两套“钱”：

### tournament stack

这是 Arena runtime 内部的唯一筹码真相：

- starting stack = 200
- rebuy = false
- add_on = false
- late_reg = false

玩家跨桌时，**只带 stack，不存在额外 bankroll 注入或带出**。

### chain / reward bankroll

这个不在 tournament runtime 里结算。  
Arena runtime 只产出：

- tournament result
- rating input
- multiplier snapshot

不要把 tournament stack 和链上奖励钱包混在一起。

## 8.3 rebalance

Rebalance 只能由 hub 发起，流程固定：

1. 某桌 hand close，上报剩余人数
2. hub 计算是否失衡
3. 若需要换桌，先在 round boundary 形成 `reseat plan`
4. hub 向相关 table 发 `pause_after_hand`
5. affected tables 都进入 safe point 后执行 reseat
6. 重新分配 button 约束，避免同玩家连续两手拿 button
7. 广播新 seating，进入下一 round

## 8.4 final table

当 `players_remaining <= 8`：

- hub 停止新 round 发放
- 所有存活玩家迁移到 final table
- final table actor 接管
- 旧 tables 关闭
- 从下一个 round 起只跑 final table

这个迁移必须是**一次性原子事件**，不要让两个 table 自己商量。

## 8.5 time-cap finish

当 wall clock 达到 `24m`：

- hub 设置 `terminate_after_current_round = true`
- 当前 round 完成后不再发新 hand
- 按规则书执行 `stack rank + percentile + blind-adjusted chip EV` 结算

这里 time cap 是 **tournament-global**，不是某桌单独计时。

---

## 9. 单手规则核应该怎么拆

Arena runtime 里最该做纯的部分不是“整个服务”，而是 **hand engine**。

建议把 hand engine 做成纯函数包：

```text
next_state, events = ResolveHandCommand(state, command, ruleset)
```

command 至少包括：

- start_hand
- submit_signal
- submit_probe
- submit_wager
- timeout_phase
- close_hand

events 至少包括：

- hand_started
- phase_closed
- action_accepted
- action_rejected
- auto_action_applied
- hand_closed
- seat_eliminated

这样做有三个好处：

1. table actor 很薄，只负责串行化和持久化
2. 单手逻辑可以做 property test / replay test
3. 未来如果要 Rust 化，替换的是这层，不是整个 runtime

---

## 10. `state_seq` 应该怎么用

`state_seq` 不是装饰字段，它是 Arena 写路径的硬保护。

建议规则：

- table actor 每次 authoritative state transition 都 `state_seq + 1`
- client action 必须携带 `expected_state_seq`
- 不匹配直接拒绝
- timeout 自动动作也会推进 `state_seq`
- reseat / level apply / hand close 也推进 `state_seq`

这样可以明确处理：

- 迟到 action
- 重放 action
- 双发 action
- UI 看到旧状态后误发 action

这也是为什么 table state 必须单写。

---

## 11. standing、排名和 leaderboard 应该拆成三层

用户直觉里“排名”是一件事，但工程上必须拆开。

## 11.1 Live standing

这是 tournament-scoped：

- players remaining
- exact self rank
- non-table rank band
- average stack
- bubble distance
- current level

刷新 cadence：

- `hand close`
- `level close`

## 11.2 Postgame result

这是赛后静态结果：

- finishing percentile
- stack timeline
- key hands
- probe efficiency
- tournament score decomposition
- multiplier delta

## 11.3 Long-term ladder

这是全局展示层：

- `public ELO`
- public rank
- leaderboard snapshot

刷新 cadence：

- tournament 进入 `RATED` 后更新 Arena `public ELO`
- 公共 ladder 每 `60m` 做 snapshot

**不要**把 long-term ladder 的任何信息带回 live table。

---

## 12. 反共谋链路应该怎么接

我建议把 collusion analytics 分成两层：

## 12.1 在线最小信号

runtime 同步产出的只有轻量信号：

- repeat seating
- suspicious chip transfer
- synchronized timeout
- mutual no-contest pattern

这些信号可以：

- 写 `arena_collusion_metric`
- 给 tournament 打 `review_needed`
- 决定 `no_multiplier`

但**不要**让复杂分析阻塞 hand progression。

## 12.2 赛后增强分析

赛后异步跑更重的分析：

- soft-play graph
- targeted elimination graph
- cluster-level repeat interaction
- bot-adjusted review

输出到：

- rating weight reduction
- anti_abuse_discount
- freeze / review

---

## 13. 持久化策略：事件账本 + 快照，不做纯内存黑盒

Arena runtime 不能只靠内存 actor，不然重启恢复和 replay 都会很痛苦。

建议 authoritative persistence：

### 追加式事件表

- `tournament_event`
- `table_event`
- `hand_event`

每条事件至少带：

- `event_id`
- `tournament_id`
- `table_id`
- `hand_id`
- `round_no`
- `state_seq`
- `occurred_at`
- `payload`
- `payload_hash`

### 周期性快照

快照点建议放在：

- hand close
- reseat complete
- level advance
- tournament completed

快照至少包括：

- tournament snapshot
- table snapshot
- seat snapshot
- standing snapshot

### deadline 持久化

`arena_action_deadline` 必须是持久化真相。  
重启后 actor 重新装载 snapshot，再重建 timer wheel / scheduler。

---

## 14. 随机性和 replay 要一开始就设计对

Arena 有大量随机面：

- seating
- alias
- regime family
- hidden state
- clue 分配
- public event bias

如果这些随机数不做 deterministic seed 管理，赛后几乎没法审计。

建议：

- 每场 tournament 固定 `rng_root_seed`
- 每个 table / hand / seat 从 root seed 派生子流
- 派生规则版本化并入 `policy_bundle_version`

例如：

```text
seed(table, hand, seat, stream_name)
  = HMAC_SHA256(rng_root_seed, tournament_id | table_id | hand_no | seat_no | stream_name)
```

这样：

- replay 可还原
- 不同子流互不污染
- 规则升级可版本化

---

## 15. 对外接口建议

Arena runtime 不需要暴露一大堆花哨 API，先把写路径和读路径分清楚。

## 15.1 写路径

- `POST /internal/tournaments`
- `POST /internal/tournaments/{id}/start`
- `POST /v1/tournaments/{tournament_id}/actions`
- `POST /internal/tournaments/{id}/recover`

其中 public action 入口继续沿用已有契约：

- `request_id`
- `tournament_id`
- `table_id`
- `hand_id`
- `phase_id`
- `seat_alias`
- `action_type`
- `action_amount_bucket`
- `expected_state_seq`
- `signature`

## 15.2 读路径

- `GET /v1/tournaments/{tournament_id}/standing`
- `GET /v1/tournaments/{tournament_id}/live-table/{table_id}`
- `GET /v1/tournaments/{tournament_id}/postgame`

## 15.3 内部事件输出

至少继续对齐已有 outbox 语义：

- `tournament.created`
- `tournament.seating.completed`
- `tournament.level.started`
- `table.hand.started`
- `table.phase.closed`
- `table.action.accepted`
- `table.hand.closed`
- `tournament.rebalanced`
- `tournament.completed`
- `arena.rating.input.appended`

---

## 16. 建议的仓库落位

建议在当前 monorepo 新增独立 Go 模块：

```text
arena-runtime/
  go.mod
  cmd/arena-runtime/main.go
  internal/app/
  internal/api/
  internal/runtime/
    tournament/
    table/
    scheduler/
  internal/engine/
    hand/
    ranking/
    scoring/
  internal/store/
    postgres/
  internal/projector/
    live_table/
    standing/
    postgame/
  internal/rating/
  internal/collusion/
  internal/replay/
  internal/policy/
```

这样做的理由：

- 不把 Arena runtime 和 chain module 搅在一起
- 不让 Python harness 绑死 runtime 实现
- 独立 deploy / 独立压测 / 独立故障域

---

## 17. 分阶段实现方案

## Phase 0: 先补齐规范，不写 runtime 业务

先把以下问题钉死进文档：

1. blind level 采用 **global round barrier** 口径
2. time-cap finish 的 exact tie-break
3. `state_seq` 增长规则
4. final table 迁移协议
5. `no_multiplier` 的自动触发条件
6. rating input 的最小字段

没有这一步，后面写代码一定返工。

## Phase 1: 纯函数 hand engine

先只做：

- state schema
- legal action matrix
- phase transitions
- timeout auto actions
- showdown / award
- elimination

要求：

- 无 IO
- 无 goroutine
- 无 DB
- 只做输入输出

测试：

- golden tests
- property tests
- deterministic replay tests

## Phase 2: table actor runtime

实现：

- table command inbox
- per-table state snapshot
- deadline manager
- `state_seq`
- hand close emit

测试：

- duplicate action
- stale action
- timeout race
- restart recovery

## Phase 3: tournament hub

实现：

- admission
- initial seating
- round barrier
- level progression
- rebalance
- final table
- completion / time-cap finish

测试：

- 64 -> 56 -> 48 entrant 边界
- bubble -> final table 迁移
- reseat fairness
- all tables recovered after restart

## Phase 4: persistence + read model + replay

实现：

- authoritative event log
- snapshots
- live table projector
- standing projector
- postgame projector
- replay endpoint

测试：

- rebuild projector from zero
- replay parity
- crash mid-round recovery

## Phase 5: rating / multiplier / anti-collusion

实现：

- `arena_rating_input`
- `mu / sigma`
- `arena_reliability`
- `public ELO`
- `arena_multiplier_snapshot`
- minimal collusion metrics

测试：

- practice 不更新 multiplier
- non-human-only rated 不更新 multiplier
- first 15 eligible tournaments force `1.00`
- bot final table -> `no_multiplier`

## Phase 6: shadow simulation 与压测

实现：

- random / tight / timeout / soft-play bots
- tournament Monte Carlo
- recovery drills
- projector rebuild drills

验收口径对齐现有仿真文档：

- rated tournament 大部分可在 `24m` 前自然结束
- multiplier 噪声不压过 fast lane
- time-cap finish 不系统性奖励被动生存

---

## 18. 什么时候再考虑把一部分换成 Rust

只有出现以下场景，再认真考虑 Rust：

1. 需要把 hand engine 编译成 WASM，给 replay / proof / sandbox 共用
2. 需要单机承载远高于 Alpha 数量级的并发 tournament
3. 需要极强的 deterministic binary reproducibility
4. Go 的 GC 或内存占用已经成为明确瓶颈
5. 团队已经愿意长期维护 Rust 运行层

到那时，优先 Rust 化的是：

- `internal/engine/hand`
- `internal/engine/scoring`

**不是**先把 hub、API、projector、ops tooling 全部 Rust 化。

---

## 19. 最终建议

最终建议很明确：

> **Arena runtime 用 Go 写。**

并且不是普通 Go CRUD，而是：

> **Go + tournament hub actor + per-table actor + pure hand engine + event log + replayable snapshots。**

具体落地策略：

- 先用 Go 把赛制、状态机、deadline、recovery、standing 跑稳
- 先把 blind/rebalance/final-table/time-cap 这四个 hardest parts 钉死
- rating / multiplier / anti-collusion 作为 tournament completion 之后的明确后处理链路
- hand engine 从第一天开始按“未来可 Rust 替换”来设计

如果只让我给一句工程判断：

> **这条线现在最值钱的是“Go 写一个足够硬的可回放 actor runtime”，而不是“Rust 写一个理论上更优但会拖慢整个产品收敛的系统”。**

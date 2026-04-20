# Arena MTT Edge Cases And Hardening

**日期**: 2026-04-10  
**状态**: donor 对照 + 当前 runtime 加固清单  
**donor**: `lepoker-gameserver`  
**关联文档**: `docs/ARENA_MTT_USER_FLOW.md`, `docs/ARENA_RUNTIME_ARCHITECTURE.md`, `docs/ARENA_RUNTIME_STATE_MACHINE_SPEC.md`

---

## 1. 目的

这份文档只做三件事：

- 把 `lepoker-gameserver` 的 MTT 关键职责拆分和边缘情况收敛成可执行清单。
- 把这些职责映射到当前 `clawchain` 的 `hub / runtime / table / gateway / store / projector / rating`。
- 明确当前 arena runtime 还缺什么，哪些已经在本轮补上，哪些必须继续硬化。

这里不重复完整用户流程；完整流程以 `docs/ARENA_MTT_USER_FLOW.md` 为准。这里关注的是“真实可上线的 MTT service 会在哪里出事”。

---

## 2. donor 结论

综合 `lepoker-gameserver` 代码和 code graph，可以把 donor 的经验压缩成下面几条：

- MTT 不是单一线性状态机。`bubble / prize pool / final table / heads-up` 可能重叠，不能假设只有一条幸福路径。
- tournament 级 orchestration 必须串行。`add-user / split / cancel / end / ranking` 不能分散在多个 goroutine 各写各的。
- table 级状态机必须只负责一桌内的合法性和结算，不能承担跨桌 barrier 或排名。
- 断线、重连、重复提交、late join、split、final table transition 都不是边缘点，而是常态点。
- ranking 不是“最后剩 1 人就写 winner”这么简单；同轮、同手、同时间淘汰的 deterministic 排名必须冻结。

---

## 3. 当前模块边界

### 3.1 Hub / Runtime

Arena hub/runtime 应负责：

- wave / tournament 生命周期
- 报名、锁场、座位发布
- 每轮 barrier
- rebalance / final table transition
- blind / ante level 推进
- time cap / void / cancel / operator intervention
- tournament completion
- standings / rating 输入的最终产出

它不应该负责：

- 单桌行动合法性
- 单手 pot / winner / refund 计算
- seat 级 timeout 自动动作判定

### 3.2 Table Actor / Engine

Table actor/engine 应负责：

- 单桌单写串行化
- `expected_state_seq` 校验
- 当前 acting seat、phase、legal action 校验
- timeout 自动 `check/fold/pass`
- hand close
- pot / winner / chip redistribution
- timeout streak、sit-out、eliminate 的桌内语义
- table snapshot / hand snapshot / deadline 持久化

它不应该负责：

- 跨桌 barrier
- reseat / rebalance
- tournament ranking
- operator 审批语义

### 3.3 Gateway

Gateway 应负责：

- auth / signature / session ownership
- `request_id` 幂等
- miner 到 tournament/table/seat 的授权
- HTTP status code 和错误分类
- admin 接口鉴权与操作幂等

它不应该负责：

- 改 table state
- 改 standings
- 改 rating 结果

### 3.4 Store / Replay / Projector / Rating

Store 应负责 durable truth：

- action / event / deadline / snapshot / elimination / reseat / barrier

Projector 应负责 read model：

- live table
- standing
- postgame

Rating 应只消费 tournament completion 事实，不反向控制 runtime。

---

## 4. 边缘情况清单

### 4.1 报名与开赛前

- 重复报名
- 锁场后继续报名
- publish 后继续报名
- force-remove 后 republish
- 最小开赛人数不足
- hard cap 超限
- 开赛前桌 actor 创建失败
- publish 重试
- runtime 重启后恢复已发布赛事

### 4.2 单桌行动与 timeout

- 手动动作和 timeout 抢同一 state
- stale `expected_state_seq`
- 一次 timeout 后没有开下一条 deadline
- timeout 导致 hand close 但没有推进 round barrier
- sit-out 后仍然被当作可行动 seat
- sit-out 是否继续付盲 / ante
- 自动 fold / check / pass 的合法性
- all-in 后 side pot / refund / odd chip
- raise / min-raise / reopen action 规则

### 4.3 多桌 barrier / rebalance / final table

- 某桌先结束，别的桌还在打
- close signal 重复到达
- 某桌在 barrier 时已经空桌
- split 与 add-user / reconnect 并发
- 搬桌后 seat 重复、miner 重复、桌超员
- final table 提前出现
- heads-up 长局 button / blind 轮转漂移

### 4.4 Completion / Ranking / Postgame

- 单 survivor 正常结束
- time cap 多 survivor 结束
- 同轮多桌同时淘汰
- 同手多名玩家同时出局
- `FinishRank` 缺失但 rating 已经写出
- winner 有了但完整 standings 没有
- no-multiplier / void / cancel 语义混淆

### 4.5 网络 / 重连 / 管理员干预

- 重复提交相同 `request_id`
- 相同 `request_id` 不同 payload
- 多客户端共享 miner 身份
- 断网后 reconnect assignment 不一致
- admin 强制 sit-out / eliminate / ban / void
- void 后仍可继续 action

### 4.6 存储 / 恢复 / 审计

- action 写成功但 snapshot 没写成功
- deadline close 写了但新 deadline 没写
- actor crash 后从 snapshot 恢复不到 phase identity
- hand close 发生了但没有 hand snapshot
- projector 依赖的事件与实际 durable truth 不一致

---

## 5. 当前 clawchain 的主要缺口

### P0: 继续补的

- 报名状态机仍要收紧。`open / locked / published / live / completed / voided` 下允许什么操作，需要 API 级硬拒绝。
- reconnect / session ownership 已经补到 tournament-scoped owner / handoff / stale reject，但 expiry / explicit disconnect / forced replace policy 还没完全冻结。
- operator intervention 已经补到 live `disqualify`，但 `force sitout / ban ladder / richer sanctions` 还没补完。
- `sit_out` 语义还需要显式冻结。现在字段存在，但“是否继续付盲、是否可 act、是否可争 pot”还没有彻底锁死。
- completion 已经能冻结 `FinishRank / StageReached / time-cap survivors` 并写出 `arena_rating_input`；`per-hand measurement / tie-break source / richer final_standings payload` 也已经接到 completion safe point。

### P1: 已知但不阻塞这轮

- `all_in / min_raise / reopen action` 仍是简化规则，不是完整 NLHE 语义。
- runtime completion 的 postgame standing 已经包含冻结后的 `final_standings`；后续还需要补前端展示、批量报告和更细的质量门槛。
- replay 更像 snapshot 校验，不是完整 event-sourced rebuild。

---

## 6. 本轮已落地的加固

### 6.1 timeout 链路补平

之前 `ProcessExpiredDeadlines` 只会把 timeout 交给 actor，然后更新 table snapshot：

- 不会像正常 submit 一样打开下一条 deadline
- 如果 timeout 让手牌关闭，也不会推进 round barrier

这会导致“全靠 timeout 推进的桌子”卡死在第一步。

本轮修复后：

- manual submit 和 timeout sweep 复用同一条 post-mutation 路径
- timeout 后如果还有 acting seat，会自动打开下一条 deadline
- timeout 后如果 `hand_closed=true`，会进入和正常提交同一条 barrier / next-round / completion 逻辑

### 6.2 自动收手也会持久化 hand snapshot

之前只有显式 `CloseHand` 命令才保存 `arena_hand_snapshot`。  
但现实里大部分 hand close 都是：

- 普通 action 触发自动 close
- timeout 触发自动 close

这会直接打断审计和 replay 证据链。

本轮修复后：

- 只要 reducer 的结果状态已经 `HandClosed`，无论是 `SubmitArenaAction`、`ApplyPhaseTimeout` 还是显式 `CloseHand`，都会保存 hand snapshot

### 6.3 跑批分析工具入库

新增脚本：

- `scripts/poker_mtt/analyze_runtime_batch.go`

它能做两种模式：

- 有数据库快照时：查 tournament/deadline/snapshot/reseat/elimination 的完整摘要
- 数据库已被清理时：退化成 log-only 分析，至少保留 phases / actions / status / tables_seen 的批量摘要

这让 `43 / 56 / 64 / 87 / 111` 这种多批次回归不再只能靠手工肉眼扫日志。

### 6.4 RoundBarrier 持久化与重启恢复补平

之前 `arena_round_barrier` 虽然已经建表，但 runtime 的 live barrier 仍主要活在内存里：

- 某桌 hand close 后只在内存里记录 `closed_tables`
- 进程重启后 barrier 进度会丢
- round 已经接近完成时 crash，重启后会把 barrier 当成全新状态

本轮修复后：

- 每次 `hand_closed` 到达都会把当前 round 的 `closed_table_ids` 和 `received_hand_close_count` 落到 `arena_round_barrier`
- seats publish / next round transition 也会刷新 barrier truth
- runtime bootstrap 会从 `arena_round_barrier` 恢复当前 round 的 close 进度，再重建 live hub

这意味着：

- round 中途 crash 后，不会再把已 close 的桌子忘掉
- `round barrier -> rebalance -> next round` 的推进开始具备真正的 restart safety

### 6.5 submission_ledger durable idempotency 补平

之前 `gateway` 的重复请求语义只靠进程内 map：

- 重启后重复 `request_id` 会失忆
- `observer` 失败但 `arena_action` 已落库时，retry 拿不回第一次 authoritative result
- `submission_ledger` 的 upsert 会允许同一 `request_id` 覆盖成不同 payload

本轮修复后：

- `gateway` 新增 durable ledger 依赖，retry 会先查 `submission_ledger` / `arena_action`
- 相同 `request_id` + 相同 payload：返回第一次 authoritative result
- 相同 `request_id` + 不同 payload：立即冲突返回
- 单进程内增加 request single-flight，避免同一 `request_id` 并发双写
- Postgres 层也拒绝 `request_id` payload 覆盖，不再只靠 gateway 保护

这意味着：

- `actor commit succeeded, client ack lost` 的真实重试场景开始可恢复
- 网关层和数据库层的幂等语义终于一致

### 6.6 reconnect / seat authority / eliminated read-only hydrate 补平

之前 reconnect 更像薄薄一层 session 壳：

- `reconnect` 只是在内存里改 `session_id`
- `/actions` 不校验当前 session ownership
- 旧 session、错 table、错 seat 仍可能继续写
- 玩家被淘汰后，read-only hydrate 在 transition / restart 后会丢失

本轮修复后：

- session ownership 改成 `(tournament_id, miner_id) -> active session`
- `/actions` 必须携带 `session_id`，并校验 active session / current table / current seat / read-only gate
- bot/client 会先 `reconnect`，再带当前 `session_id` 写动作
- eliminated entrant 会保留只读 assignment
- restart 后会从 immutable `arena_elimination_event` 恢复 busted 玩家的 read-only hydrate，而不是依赖会被 seat reuse 覆盖的 `arena_seat`

这意味着：

- stale session / stale table assignment 不再能继续写 authoritative action
- 玩家 busted 后仍能 reconnect 看最后桌面上下文
- final table transition / restart 不会再把淘汰者客户端视角直接抹掉

### 6.7 live disqualification safe-point 补平

之前 runtime 虽然有 `arena_operator_intervention` 表，但 live tournament 里没有真正可执行的 DQ 语义：

- admin API 没有 live `disqualify`
- 写入 intervention 后不会立刻阻断人工 action
- round barrier 不会把被 DQ 的 seat 从 remaining field 移出
- restart 后 pending DQ 也不会恢复成 read-only

本轮修复后：

- 新增 `POST /v1/admin/arena/tournaments/{id}/disqualify`
- DQ 一旦写入：
  - entrant 当前 assignment 立即变成 `read_only`
  - `/actions` 立刻拒绝该矿工后续手动提交
  - tournament 立即标记 `no_multiplier = true`
  - standing 补 `no_multiplier_reason = "live_disqualification"`
- round barrier 计算 remaining field 时会跳过 pending DQ entrant
- safe point 到达后：
  - entrant 转成 `registration_state = disqualified`
  - 记录 immutable field-exit event，保留 read-only hydrate 所需的最后 table/seat truth
  - operator intervention 状态转成 `applied`
- runtime bootstrap 会从 `arena_operator_intervention` 恢复 pending DQ，并继续把该 seat 维持成 read-only

这意味着：

- live DQ 终于不是“写个表记一下”，而是能真的阻断动作、跨重启持续生效，并在 barrier 安全点移出 field
- `restart between request and barrier` 这种真实线上边缘情况，不会再把已 DQ 的矿工放回可写路径

### 6.8 sit_out 恢复语义补平

之前 `sit_out` 只补到了一半：

- timeout 两手后 seat 会进入 `sit_out`
- `sit_out` seat 仍会继续付 blind / ante，也仍会继续进入 auto action 流程
- 但如果矿工后来恢复并提交了有效手动 action，`timeout_streak` 虽然会清零，`seat_state` 却不会回到 `active`

这会造成一个很别扭的半坏状态：

- 玩家实际上已经恢复手动参与
- 但 authoritative seat state 仍然永远停在 `sit_out`

本轮修复后：

- `sit_out` seat 继续正常参与发牌、继续支付 ante / blind
- 一旦该 seat 提交有效手动 action：
  - 当前 hand 内立即去掉 `sit_out`
  - hand close 时 `timeout_streak` 清零
  - 下一手 authoritative `seat_state` 回到 `active`

这意味着：

- `sit_out` 终于成为真正的 `inactive_auto overlay`，而不是一次性不可逆的半淘汰状态
- reconnect 后恢复手动参与的矿工，不会再被 runtime 永久标成 `sit_out`

### 6.9 completion -> standings -> rating pipeline 补齐

之前 runtime 的 completion 只做到了一半：

- standing 里会出现 `completed`
- winner 可能会有
- 但非冠军 entrant 常常没有 `finish_rank`
- `arena_rating_input / arena_result_entries` 并不会由真实 runtime completion 写出

这轮补齐后：

- tournament completion 会稳定计算全体 entrant 的 `FinishRank`
- `arena_elimination_event.finish_rank` 会在 completion safe point 回填冻结
- `StageReached` 会统一冻结成 `completed / final_table / time_cap_finish / disqualified / eliminated`
- runtime completion 会直接调用 rating writer 写出 `arena_rating_input / arena_result_entries`
- rating writer 启动时会从 durable state bootstrap，恢复 `mu / sigma / public_elo / arena_multiplier / eligible_tournament_count`

这意味着：

- natural finish 不会再出现 winner 有了、runner-up `finish_rank=0`、rating 没写出的残缺状态
- restart 后 multiplier warmup 不会被当成全新 miner 重新开始
- time-cap 多 survivor 至少已经有 deterministic 的 stack-based completion ranking

当前剩下的不是“有没有 completion”，而是“measurement 是否足够接近最终评分模型”：

- `arena_rating_input` 已经从 `arena_action / submission_ledger / arena_seat` 聚合 `hands_played / meaningful_decisions / auto_actions / timeout_actions / invalid_actions`
- completed `/standing` 已经暴露冻结后的 `final_standings`，包括 `finish_rank / stage_reached / final_stack / rank_source / rank_tiebreaker / measurement`
- `time_cap_adjustment / confidence_weight` 目前还是 conservative 默认值，不是最终测量模型
- `hands_played` 当前按已归属 action 的 distinct hand 统计，不是完整“被发到牌/在场 hand”统计；后续如果要严肃做 median hand quality gate，需要从 hand snapshot 或 seat occupancy 再补一层

### 6.10 recovery / replay parity 第一层补齐

completion pipeline 接上之后，replay 还有两个硬缺口：

- runtime completion 没有保存 `tournament completed` snapshot，repository replay 只能看到旧的 tournament snapshot
- repository final hash 没覆盖 `arena_elimination_event`，所以 `finish_rank` 被篡改时 replay parity 不一定失败

这轮补齐后：

- natural finish 会写入 `snap:{tournament_id}:completed`
- completed snapshot 的 `stream_seq` 放到高位，避免和未来 seating snapshots 打平导致 latest 查询不稳定
- `replay.ComputeFinalHash` 会纳入 elimination events 的 `entrant_id / seat_id / finish_rank / stage_reached / state_hash / payload_hash`
- app 级回归验证了 completed tournament 在 `App.Close -> App.New` 后 repository final hash 完全一致

这意味着：

- placement truth 被改，final hash 会变
- completed tournament restart 后 replay parity 有真实 DB 路径覆盖，不再只是 synthetic fixture
- recovery / replay 已经能覆盖 completion snapshot、table snapshots、elimination truth、rating input 这四类核心 truth

### 6.11 time-cap 多 survivor stage 语义修正

这轮还补了一条 time-cap 专项：

- 16 人两桌同时 time-cap，最终 8 个 survivor
- survivor 的 `arena_rating_input.stage_reached` 必须是 `time_cap_finish`
- 非 survivor 必须保持 `eliminated`
- 不能因为 finish rank 进入 top 9 就被误标成 `final_table`

之前的问题是 `stageReachedForPlacement` 的顺序过于泛化：

- 先按 rank band 推断 `final_table`
- 再考虑已有 stage
- 导致 rank 9 这种“final table bubble”在 time-cap 场景下被误标

修复后：

- time-cap 分支先独立处理
- 只有 survivor 会拿到 `time_cap_finish`
- 非 survivor 优先保留 authoritative elimination stage

---

## 7. 本轮 10 场回归的可确认事实

基于现有 `jsonl` 批日志：

- 两批共 `10/10` 场全部 `natural_finish`
- `43 / 56 / 64 / 87 / 111` 五种规模都能收尾
- 所有规模都出现了 `signal / probe / wager`
- 所有规模都出现了 `all_in / call / fold / raise`
- 多桌并发确实发生，`tables_seen` 与人数规模基本匹配

从这 10 场日志能直接看出的风险点：

- 真实存在少量 `stale_state`，说明多 miner 并发提交下 state race 是现实问题，不是理论问题
- `111` 人随机策略会打到很深，第二批走到 `1473` steps，heads-up 长局必须持续关注

注意：

- 因为本轮修 bug 过程里重置过测试库，这 10 场历史 run 的数据库快照已经不在，所以这次只能保留 log-only 摘要
- 之后再跑批，可以直接用 `scripts/poker_mtt/analyze_runtime_batch.go` 在 run 结束后立即做 DB+log 联合分析

---

## 8. 下一步执行顺序

建议严格按下面顺序继续：

1. 把 replay 从 snapshot hash 推进到完整 event-tail rebuild。
2. 把 measurement quality gate 做成批量报告，至少输出 median/p75 hands 和 decisions。
3. 跑真实随机策略批回归，覆盖 `43 / 56 / 64 / 87 / 111` 每种至少 5 场，并保留 DB+log 联合分析。

如果只做一个下一步，优先做第 `1` 项。  
原因很简单：completion、measurement、standings 输出现在都已经能落库和回读；下一处真正影响上线可信度的是“DB 最终状态能否由 event tail 完整重放证明”，而不是再加一个摘要字段。

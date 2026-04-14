# ClawChain Arena Runtime State Machine Spec

**版本**: 0.1  
**日期**: 2026-04-10  
**状态**: Draft  
**流程基线**: [docs/ARENA_MTT_USER_FLOW.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_MTT_USER_FLOW.md)  
**运行架构**: [docs/ARENA_RUNTIME_ARCHITECTURE.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_RUNTIME_ARCHITECTURE.md)  
**测量规范**: [docs/ARENA_MEASUREMENT_SPEC.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_MEASUREMENT_SPEC.md)  
**规则基线**: [docs/DYNAMIC_ARENA_ALPHA_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/DYNAMIC_ARENA_ALPHA_DESIGN.md)  
**后端契约**: [docs/HARNESS_BACKEND_ARCHITECTURE.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_BACKEND_ARCHITECTURE.md)  
**API 契约**: [docs/HARNESS_API_CONTRACTS.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_API_CONTRACTS.md)

---

## 1. Scope

这份文档的目标不是讨论产品方向，而是把 Arena runtime 冻结成一份**可实现、可验证、可恢复**的运行时规格。

覆盖范围：

- `rated / practice wave` 下的 `arena_tournament` 运行时
- pre-start 到 postgame 的 authoritative state machine
- command / event / projector 的职责边界
- table actor、tournament hub、gateway、rating writer、ops 的模块边界
- `state_seq`、deadline、reconnect、rebalance、final table、time-cap finish
- authoritative DB schema、event flow、snapshot、replay、void/recovery

不覆盖：

- UI 视觉稿
- solver / AI 策略本身
- chain settlement 细节
- daily / forecast lane 业务

核心设计目标：

1. **顺序正确**
2. **幂等正确**
3. **重启可恢复**
4. **赛后可 replay**
5. **边缘情况可穷举验证**

## 2. Non-Goals

Arena V1 明确不是一个完整扑克平台。

以下能力不在本 spec 范围内：

- late registration
- early bird bonus
- re-entry
- rebuy / add-on
- satellite
- bounty / PKO
- final table manual seat selection
- ICM deal / chop
- blind rollback
- player time bank / chess clock
- scheduled tournament breaks
- chat / social layer

Arena V1 固定为：

> **fixed-start freezeout MTT-like tournament service**

## 3. Runtime Boundaries

## 3.1 Harness Control Plane

负责：

- 创建 `arena_wave`
- 生成 `arena_tournament`
- 发布 `policy_bundle_version`
- 驱动 rated / practice 时间窗
- 接收 tournament completion 结果
- 把 `arena_multiplier_snapshot` 汇入 reward window

不负责：

- 桌内 hand state
- timeout 自动动作
- rebalance 细节
- final table seat assignment

## 3.2 Submission Gateway

负责：

- 验签
- 幂等键 `request_id` 检查
- 基础 payload 验证
- `expected_state_seq` 预检查
- 写 `submission_ledger`
- 把 arena action 投递到目标 table actor

不负责：

- 直接修改 table state
- 延迟执行 stale action
- 改写排名

## 3.3 Tournament Hub

Hub 是单个 `arena_tournament` 的唯一 tournament-level writer。

负责：

- tournament lifecycle
- registration -> field lock -> seating -> live -> final table -> completed
- global round barrier
- level advancement
- table-count calculation
- rebalance / break-table 计划
- final table transition
- completion / cancellation / void / time-cap finish
- standing authoritative refresh
- 产出 tournament-level events

不负责：

- 单桌 phase 内动作接受
- 本地 hand 规则计算
- 重计算 projector

## 3.4 Table Actor

每桌一个 actor，是唯一 table-level writer。

负责：

- hand / phase state
- blind / ante 扣除
- action acceptance / rejection
- timeout 自动动作
- `state_seq`
- hand close
- table-local elimination result
- 上报 hand result 给 hub

不负责：

- 全场排名
- 自行 rebalance
- 自行结束 tournament
- 直接写 multiplier

## 3.5 Rating / Multiplier Writer

负责：

- 消费 `tournament.completed`
- 生成 `arena_rating_input`
- 更新 `mu / sigma / arena_reliability`
- 更新 `public ELO`
- 生成 `arena_multiplier_snapshot`

不负责：

- 修改已完赛 tournament state
- 修改 table / hand records

## 3.6 Projectors

负责：

- `live_table`
- `tournament_standing`
- `postgame_forensics`
- `miner_status` 中的 Arena 片段

所有 projector 都是 derived state，不是 source of truth。

## 3.7 Ops / Replay

负责：

- replay parity
- projector rebuild
- dead letter 消费
- tournament recover / void / override

不负责：

- 正常比赛中的同步决策

## 3.8 Measurement / Risk

负责：

- confidence weight
- no-multiplier gating
- collusion metrics
- low-quality tournament downgrade

不应阻塞正常 hand progression。

## 4. Aggregate Model

## 4.1 Core Aggregates

建议 Arena runtime 的核心聚合根为：

- `arena_wave`
- `arena_tournament`
- `arena_table`
- `arena_hand`
- `arena_phase`
- `arena_seat`

其中真正有写入 authority 的只有两层：

- `arena_tournament`
- `arena_table`

`arena_hand` / `arena_phase` / `arena_seat` 更多是子实体或快照对象。

## 4.2 `arena_wave`

作用：

- 承载一次 rated 或 practice 时间窗
- 收集 entrants
- 进行 shard packing
- 发布 wave-level policy 和开赛裁决

建议字段：

- `wave_id`
- `rated_or_practice`
- `registration_open_at`
- `registration_close_at`
- `scheduled_start_at`
- `policy_bundle_version`
- `wave_state`
- `target_shard_size`
- `soft_min_entrants`
- `soft_max_entrants`
- `hard_max_entrants`

## 4.3 `arena_tournament`

作用：

- 一场独立的 MTT shard
- hub authority 的主对象

建议字段：

- `tournament_id`
- `wave_id`
- `rated_or_practice`
- `tournament_state`
- `exhibition`
- `no_multiplier`
- `cancelled`
- `voided`
- `human_only`
- `policy_bundle_version`
- `rng_root_seed`
- `integrity_hold`
- `seating_republish_count`
- `current_round_no`
- `current_level_no`
- `players_registered`
- `players_confirmed`
- `players_remaining`
- `active_table_count`
- `final_table_table_id`
- `time_cap_at`
- `completed_at`

## 4.4 `arena_table`

作用：

- 单桌 authoritative state holder

建议字段：

- `table_id`
- `tournament_id`
- `table_state`
- `table_no`
- `round_no`
- `current_hand_id`
- `button_seat_no`
- `acting_seat_no`
- `current_to_call`
- `min_raise_size`
- `pot_main`
- `state_seq`
- `level_no`
- `is_final_table`
- `paused_for_rebalance`

## 4.5 `arena_seat`

建议字段：

- `seat_id`
- `table_id`
- `seat_no`
- `seat_alias`
- `miner_id`
- `seat_state`
- `stack`
- `timeout_streak`
- `sit_out_warning_count`
- `last_forced_blind_round`
- `last_manual_action_at`
- `tournament_seat_draw_token`
- `admin_status_overlay`
- `removed_reason`

## 4.6 `arena_hand`

建议字段：

- `hand_id`
- `table_id`
- `tournament_id`
- `round_no`
- `level_no`
- `hand_state`
- `hand_started_at`
- `hand_closed_at`
- `button_seat_no`
- `active_seat_count`
- `pot_main`
- `winner_count`
- `time_cap_forced_last_hand`

## 4.7 `arena_phase`

建议字段：

- `phase_id`
- `hand_id`
- `phase_type`
- `phase_state`
- `opened_at`
- `deadline_at`
- `closed_at`

## 4.8 Auxiliary Arena Entities

需要明确纳入 runtime spec 的 Arena 专用表：

- `arena_alias_map`
- `arena_reseat_event`
- `arena_elimination_event`
- `arena_action_deadline`
- `arena_public_snapshot`
- `arena_collusion_metric`
- `arena_regime_family`
- `arena_operator_intervention`

## 4.9 Aggregate Ownership Summary

- Hub owns:
  - `arena_wave` decisions after registration close
  - `arena_tournament`
  - `arena_reseat_event`
  - `arena_public_snapshot` for standing
- Table owns:
  - `arena_table`
  - `arena_hand`
  - `arena_phase`
  - table-local `arena_seat` mutations
  - `arena_action_deadline`
  - table-local `arena_elimination_event`
- Other modules own:
  - `arena_rating_input`
  - `arena_multiplier_snapshot`
  - `arena_collusion_metric`
  - replay artifacts

## 5. State Machines

## 5.1 `arena_wave_state`

建议：

```text
scheduled
-> registration_open
-> registration_frozen
-> field_locked
-> eligibility_resolving
-> field_finalized
-> packing
-> tournaments_created
-> seating_generated
-> seats_published
-> start_armed
-> in_progress
-> completed
-> finalized
```

异常出口：

- `cancelled`
- `voided`

规则：

- `registration_frozen` 后拒绝 public register / unregister
- `field_locked` snapshot immutable；之后只能移除 entrant，不能新增 entrant
- `seats_published` 后禁止 cross-shard 迁移；只允许 shard-local pre-start reseat
- `seats_published` 后若出现 pre-start 强制移除，只允许 `1` 次 deterministic shard-local reseat republish，且必须发生在 `start_armed` 前
- 高流量扩容靠新增 shard，不靠放大单 shard field

## 5.2 `arena_tournament_state`

建议：

```text
scheduled
-> registration_confirmed
-> seating
-> ready
-> live_multi_table
-> rebalancing
-> final_table_transition
-> live_final_table
-> completed
-> rated
-> settled
```

异常出口：

- `cancelled`
- `voided`

overlay flags：

- `bubble_active = players_remaining <= 10`
- `terminate_after_current_round = true|false`
- `no_multiplier = true|false`
- `integrity_hold = true|false`

## 5.3 `arena_table_state`

建议：

```text
open
-> hand_starting
-> hand_live
-> hand_closing
-> awaiting_barrier
-> paused_for_rebalance
-> closed
```

规则：

- `hand_starting`：blind/ante 扣除、hidden state 生成、deadline 打开
- `hand_live`：只覆盖 signal/probe/wager 三阶段
- `awaiting_barrier`：table 已 hand close，但不得自行进入下一手

## 5.4 `arena_hand_state`

建议：

```text
created
-> blinds_posted
-> signal_open
-> signal_closed
-> probe_open
-> probe_closed
-> wager_open
-> wager_closed
-> showdown_resolved
-> awards_applied
-> elimination_resolved
-> closed
```

辅助标志：

- `forced_last_hand_by_time_cap`
- `aborted_by_void`

## 5.5 `arena_phase_state`

建议：

```text
pending
-> open
-> closing
-> closed
```

## 5.6 `arena_seat_state`

后端现有粗粒度是：

```text
active -> sit_out -> eliminated
```

为了运行时清晰，V1 规范化解释为：

- `active`
- `sit_out`
  - 语义等同于“`inactive_auto` overlay 生效”
  - seat 仍继续付 blind/ante，仍收 hidden state，仍走 auto action
- `eliminated`

注意：

- `temporarily_disconnected` 不进入 authoritative seat_state，只作为 session/gateway 层状态
- `sit_out` 不是冻结，不是离桌，不是取消报名

## 5.7 `player_registration_state`

建议：

```text
not_registered
-> registered
-> waitlisted
-> confirmed
-> seated
-> playing
-> eliminated | champion
```

例外：

- `removed_before_start`
- `disqualified`

## 5.8 Critical State-Gap Decisions

以下 gap 在实现前必须冻结：

1. `inactive` 与 `sit_out` 统一为同一 authoritative 语义
2. timeout streak 是“按手计数”，不是按 phase 计数
3. `action_rejected` 不推进 `state_seq`
4. `seats_published` 后禁止 cross-shard mutation
5. rated shard 启动范围冻结为 `56..64`
6. 高流量扩容使用多 shard，不做单 shard `>64` 扩容
7. `seats_published` 后的 pre-start 强制移除只允许一次 deterministic shard-local reseat republish
8. live disqualification 只在 round barrier safe point 生效，并自动触发 `no_multiplier`

## 6. Event Flow

## 6.1 Authoritative Event Families

Arena runtime 必须至少产出：

- `wave.registration.opened`
- `wave.registration.frozen`
- `wave.field.locked`
- `wave.eligibility.resolved`
- `wave.packing.completed`
- `tournament.created`
- `tournament.registration.confirmed`
- `tournament.seating.completed`
- `tournament.seating.published`
- `tournament.ready`
- `tournament.round.started`
- `tournament.level.started`
- `table.hand.started`
- `table.phase.opened`
- `table.phase.closed`
- `table.action.accepted`
- `table.action.rejected`
- `table.auto_action.applied`
- `table.hand.closed`
- `seat.eliminated`
- `tournament.rebalanced`
- `tournament.final_table.transition_started`
- `tournament.final_table.transition_completed`
- `tournament.time_cap.armed`
- `tournament.completed`
- `tournament.cancelled`
- `tournament.voided`
- `arena.rating.input.appended`

## 6.2 Pre-start Event Flow

```text
wave.registration.opened
-> entrant.registered / entrant.waitlisted
-> wave.registration.frozen
-> wave.field.locked
-> wave.eligibility.resolved
-> wave.packing.completed
-> tournament.created
-> tournament.seating.completed
-> tournament.seating.published
-> tournament.ready
```

## 6.3 Live Round Event Flow

```text
tournament.round.started
-> table.hand.started
-> table.phase.opened(signal)
-> table.phase.closed(signal)
-> table.phase.opened(probe)
-> table.phase.closed(probe)
-> table.phase.opened(wager)
-> table.action.accepted / table.auto_action.applied ...
-> table.phase.closed(wager)
-> table.hand.closed
-> tournament.round.barrier_reached
-> hub applies eliminations and ranks
-> standing refreshed
-> optional rebalance
-> optional level advance
-> next round started
```

## 6.4 Final Table Event Flow

```text
tournament.final_table.transition_started
-> source tables paused
-> reseat events emitted
-> final table seating applied
-> tournament.final_table.transition_completed
-> tournament.round.started
```

## 6.5 Completion Event Flow

```text
tournament.completed
-> integrity / measurement gates
-> arena.rating.input.appended
-> rating updated
-> public ELO updated
-> arena_multiplier_snapshot updated
-> postgame projector published
```

## 6.6 Error / Recovery Event Flow

必须显式记录：

- `table.recovery.started`
- `table.recovery.completed`
- `tournament.recovery.started`
- `tournament.recovery.completed`
- `tournament.voided`

## 7. Command Handling

## 7.1 Command Sources

只允许三类源：

1. control plane
2. gateway / clients
3. internal runtime scheduler

## 7.2 Control-plane Commands

- `OpenWaveRegistration`
- `FreezeWaveRegistration`
- `LockWaveField`
- `RunEligibilitySweep`
- `AssignShards`
- `GenerateSeating`
- `PublishSeating`
- `StartTournament`
- `RecoverTournament`
- `VoidTournament`
- `ForceRemoveEntrantPrestart`

## 7.3 Hub Commands

- `StartRound`
- `AdvanceLevel`
- `PauseTableForRebalance`
- `ApplyRebalancePlan`
- `StartFinalTableTransition`
- `ArmTimeCap`
- `CompleteTournament`
- `FinishTournamentByTimeCap`

## 7.4 Table Commands

- `StartHand`
- `OpenPhase`
- `SubmitArenaAction`
- `ApplyPhaseTimeout`
- `ClosePhase`
- `ResolveShowdown`
- `CloseHand`
- `PauseForRebalance`
- `ApplySeatMove`

## 7.5 Gateway Validation Pipeline

arena action 写入前必须依次经过：

1. schema validation
2. signature validation
3. `request_id` idempotency lookup
4. tournament/table/seat existence check
5. tentative cached `expected_state_seq` check
6. write `submission_ledger` / `arena_action`
7. enqueue to owning table actor

最终 acceptance 只由 table actor authoritatively 决定。

## 7.6 Rejection Semantics

Arena 必备 rejection：

- `validation_error`
- `signature_invalid`
- `duplicate_request`
- `state_seq_mismatch`
- `seat_not_acting`
- `phase_closed`
- `action_illegal`
- `late_submission`
- `table_paused`
- `tournament_voided`

## 7.7 No Delayed Execution Rule

任何 stale action 都只能 rejected，绝不允许“延迟排队等待正确时机再执行”。

## 8. Module Ownership

## 8.1 Hub Owns

- tournament lifecycle
- effective mode
- round number
- level number
- table topology
- global seating map
- players remaining
- bubble / final-table flags
- rebalance / break-table plans
- completion reason
- official elimination order

## 8.2 Table Owns

- current hand
- current phase
- acting seat
- visible stacks
- pot / to-call / min-raise
- deadlines
- `state_seq`
- hand close results

## 8.3 Gateway / Session Layer Owns

- connection session id
- signature verification
- request idempotency
- duplicate retry handling
- reconnect hydration

Gateway 不拥有 tournament truth。

## 8.4 Projectors Own

- live table read model
- tournament standing read model
- postgame forensics

这些都可 rebuild。

## 8.5 Rating / Measurement Owns

- `arena_rating_input`
- `confidence_weight`
- `no_multiplier` gating
- `mu / sigma / arena_reliability`
- `public ELO`

## 8.6 Ops Owns

- recover / rebuild / void workflows
- dead letter handling
- replay parity checks

## 8.7 Forbidden Ownership Patterns

以下必须禁止：

- gateway 直接改 table state
- projector 写回 authoritative ranking
- table actor 直接写 multiplier
- rating writer 反写 hand history
- ops 临时 SQL 改 `state_seq`

## 8.8 Edge-case Ownership Matrix

- pre-start register/unregister race:
  - owner: hub
  - authoritative safe point: `registration_frozen`
  - outcome: freeze 后一律拒绝变更
- duplicate submit / partial ack loss:
  - owner: gateway + table
  - authoritative safe point: table actor command intake
  - outcome: 同 `request_id` 返回原结果；新 `request_id` 走正常 stale 检查
- disconnect / reconnect:
  - owner: gateway/session + table
  - authoritative safe point: phase deadline / hydrate response
  - outcome: deadline 前可继续；deadline 后只认已落地 auto action
- consecutive timeouts:
  - owner: table
  - authoritative safe point: hand close
  - outcome: warning / `sit_out` / elimination
- pre-start forced removal:
  - owner: hub
  - authoritative safe point: `seats_published` 前后但 `start_armed` 前
  - outcome: deterministic shard-local reseat republish，或 downgrade / cancel
- live disqualification:
  - owner: hub
  - execution assist: gateway blocks manual submit，table执行 forced-auto until barrier
  - authoritative safe point: round barrier
  - outcome: seat 移出 field，tournament `no_multiplier = true`
- rebalance / break-table failure:
  - owner: hub + ops
  - authoritative safe point: barrier / recovery procedure
  - outcome: tournament 进入 recoverable pause，不得局部继续
- crash / restart:
  - owner: owning actor + ops
  - authoritative safe point: latest snapshot + event tail
  - outcome: recover or void，绝不 silent skip

## 9. Timeout / Disconnect / Reconnect

## 9.1 Timeout Policy

冻结为：

- `signal` timeout -> `signal_none`
- `probe` timeout -> `pass_probe`
- `wager`
  - `to_call = 0` -> `auto check`
  - `to_call > 0` -> `auto fold`

## 9.2 Timeout Streak Policy

按“手”计数，而不是按 phase 计数：

- 连续 `1` 手 timeout -> `sit_out_warning`
- 连续 `2` 手 timeout -> `sit_out`
- 连续 `4` 手 timeout -> `eliminated`

同一手内多个 phase timeout 只记作一次 missed hand。

## 9.3 Disconnect Semantics

disconnect 本身不改变 seat 生存资格：

- tournament 不暂停
- 玩家仍继续付 blind/ante
- deadline 到点即应用 timeout policy

## 9.4 Reconnect Semantics

玩家 reconnect 后：

- 若 phase 仍 open 且 auto action 未落地，可继续手动动作
- 若 auto action 已落地，不可回滚
- 若 seat 已 moved，则必须先 hydrate 最新 table assignment
- 若 seat 已 eliminated，则只允许 read-only

## 9.5 Partial ACK / Duplicate Submit

- 同 `request_id` retry：返回第一次 authoritative 结果
- 新 `request_id` 但旧 UI/stale state：`state_seq_mismatch`
- stale action 永不 delayed execution

## 9.6 Session Handoff Rule

同一 miner 若开新连接：

- 不创建第二个 seat authority
- 新 session 只替换消息投递通道
- authoritative identity 仍是 `seat_alias -> miner_id`

## 9.7 Forced Removal / Disqualification

需要区分：

1. `removed_before_start`
2. timeout / blind attrition 的自然淘汰
3. operator `disqualified`

规则：

- pre-start disqualification 可直接移出 confirmed field
- `seats_published` 后但 `start_armed` 前若被强制移除：
  - hub 可执行一次 deterministic shard-local reseat republish
  - republish 后不得改变 shard 边界
  - 若 republish 后 shard 无法满足 rated 启动条件，则该 shard downgrade 为 practice/exhibition；再不足则 cancel
- live disqualification 不允许回滚既往 hand；只能在下一 safe point 生效
- live disqualification 一旦写入：
  - gateway 立刻拒绝该 entrant 后续手动动作
  - table 在当前 hand / round 剩余阶段仅允许对该 seat 执行 forced-auto policy
  - hub 在 round barrier 将其移出 remaining field，并按该 round 末位行政淘汰处理
  - rated tournament 自动标记 `no_multiplier = true`
- live disqualification 的 rank 规则冻结为：
  - 先结算该 round 内所有自然淘汰
  - 再写入 administrative elimination
  - 被 DQ 的 seat rank 低于该 round 幸存者，高于下一 round 才会淘汰的玩家

## 9.8 Reconnect Boundary Cases

必须覆盖：

- reconnect during signal
- reconnect during probe
- reconnect during wager while acting
- reconnect after wager auto-fold
- reconnect during round barrier
- reconnect after move-table
- reconnect after final-table transition
- reconnect after elimination

## 10. Rebalance / Break Table / Final Table

## 10.1 Safe Points

只允许在：

- hand close
- round barrier

绝不允许：

- phase 中途换桌
- hand 中途换桌
- acting seat 未完成动作时换桌

## 10.2 Table Count Rule

为解决 `P=9..13` 与 bubble 文档的不一致，冻结为：

```text
if P <= 8: N = 1
else if 9 <= P <= 13: N = 2
else: N = min n>=2 such that 7n <= P <= 9n
```

说明：

- `9..13` 是 late-stage exception
- 近 bubble 阶段允许 `4..7` 人桌，仅为最终过渡到固定 `8` 人 final table

额外冻结：

- 不允许“每轮随机全量重分桌”
- reseat 只允许发生在：
  - 初始 seating
  - rebalance / break-table
  - final table transition

## 10.3 Rebalance Rule

table 数不变但人数差超过 `1` 时 rebalance。

优先级：

1. 最长桌出人
2. 最短桌进人
3. mover 选择以 blind fairness 优先
4. destination seat 选择以 blind obligation 接近优先

## 10.4 Break Table Rule

当 `P` 下降到可减少一桌时：

- 优先 break 最短桌
- 若并列，`table_id ASC`
- break 后人数分布尽量均衡，seat-count delta `<=1`

## 10.5 Final Table Transition

当 `players_remaining <= 8`：

1. 当前 round 正常结束
2. 不再发下一 round
3. 所有 source tables 进入 paused state
4. 生成 final table seating plan
5. 一次性迁移全部 survivor
6. 目标 table 标记 `is_final_table = true`
7. tournament state -> `live_final_table`

## 10.6 Transition Precedence Rules

- FT 优先于普通 rebalance
- natural champion 优先于 time-cap settlement
- level-up 与 rebalance 可同 barrier 一起提交
- level-up 与 FT 可同 barrier 一起提交；FT 下一轮使用新 level

## 10.7 Deterministic Tie-break Rules

同桌同手淘汰：

1. `stack_at_hand_start DESC`
2. button-relative order
3. `tournament_seat_draw_token`

跨桌同轮淘汰：

1. `stack_at_hand_start DESC`
2. `tournament_seat_draw_token`

绝不按 wall-clock 完手先后排序。

## 10.8 Time-Cap Finish

达到 `time_cap_at`：

- 仅设置 `terminate_after_current_round = true`
- 当前 round 打完
- 不再发新 hand
- 按 time-cap formula 结算

若恢复时已超过 time cap：

- 只允许完成已挂起 round
- 不允许补发新 hand

## 10.9 Rebalance Failure Handling

若源桌已暂停但迁移失败：

- topology 仍以 hub 计划为准
- tournament 进入 recoverable pause
- 不得局部放行继续打

## 11. Elimination / Ranking / Completion

## 11.1 Table-local Elimination

hand close 后若 `stack <= 0`：

- seat state -> `eliminated`
- 生成 `arena_elimination_event`
- 上报 hub

## 11.2 Tournament Ranking

Hub 在 round barrier 统一应用 elimination events 并计算：

- exact ranks for busted seats
- current standing for survivors

## 11.3 Completion Conditions

满足任一条件即完成：

- `players_remaining == 1`
- 当前 round 后执行 time-cap finish
- operator voids tournament

## 11.4 Completion Outputs

completion 必须产出：

- final standings
- elimination order
- stage reached per entrant
- hand / stack summaries
- `no_multiplier` final flag
- measurement quality summary

## 11.5 Rating Gate

`completed` 不等于必然 `rated`。

必须先过：

- integrity checks
- no-multiplier checks
- replay parity
- measurement confidence gate

然后才进入 `rated`。

## 12. Persistence Model

## 12.1 Truth Layers

Arena 的 source-of-truth 必须分层：

- ingress truth:
  - `submission_ledger`
  - `arena_action`
- domain truth:
  - append-only Arena event streams
- recovery truth:
  - latest durable snapshots
  - open `arena_action_deadline`
- replay truth:
  - `rng_root_seed`
  - deterministic seed derivation
  - `policy_bundle_version`
- visibility truth:
  - standing / live-table / postgame / public ladder 都是 projector

## 12.2 Event Log Wins

若 snapshot、read model 与 event log 冲突：

- event log 为最终真相
- snapshot / projector 视为可重建缓存

## 12.3 Timer Truth Must Be Durable

`arena_action_deadline` 必须与以下内容在同一事务边界保持一致：

- phase open event
- table snapshot
- current `state_seq`

## 12.4 Event Stream Model

建议物理上使用单一 `arena_event_log` 表，逻辑上切分为：

- tournament stream
- table stream
- hand stream

## 12.5 Snapshot Strategy

必须在以下安全点做 snapshot：

- field locked
- seating published
- hand close
- round barrier after standing refresh
- rebalance applied
- final table transition completed
- tournament completed

## 12.6 Recovery Model

恢复顺序：

1. load latest snapshot
2. replay event tail
3. rebuild open deadlines
4. schedule synthetic timeout commands for expired deadlines
5. actor ready 后才重新接入写流

## 12.7 Projector Model

projector：

- 幂等键是 `event_id`
- rebuild 只从 event log 出发
- 绝不反写 authoritative state

## 12.8 Replay Model

replay 必须能重建：

- final tournament state
- per-seat measurement
- `arena_rating_input`
- `no_multiplier` reason
- replay proof hash

replay parity 失败即 hard integrity failure。

## 13. DB Schema

## 13.1 Core Runtime Tables

- `arena_wave`
- `arena_entrant`
- `arena_waitlist`
- `arena_prestart_check`
- `arena_shard_assignment`
- `arena_tournament`
- `arena_level`
- `arena_table`
- `arena_hand`
- `arena_phase`
- `arena_seat`
- `arena_alias_map`
- `submission_ledger`
- `arena_action`
- `arena_action_deadline`
- `arena_operator_intervention`
- `arena_reseat_event`
- `arena_elimination_event`
- `arena_round_barrier`

## 13.2 Event / Snapshot Tables

- `arena_event_log`
- `arena_tournament_snapshot`
- `arena_table_snapshot`
- `arena_hand_snapshot`
- `arena_standing_snapshot`
- `outbox_event`
- `outbox_dispatch`
- `projector_cursor`
- `dead_letter_event`

## 13.3 Measurement / Rating Tables

- `arena_rating_input`
- `arena_collusion_metric`
- `rating_state_current`
- `rating_snapshot`
- `public_ladder_snapshot`
- `arena_multiplier_snapshot`

## 13.4 `arena_event_log` Required Columns

- `event_id`
- `aggregate_type`
- `aggregate_id`
- `stream_key`
- `stream_seq`
- `tournament_id`
- `table_id`
- `hand_id`
- `phase_id`
- `round_no`
- `barrier_id`
- `event_type`
- `event_version`
- `policy_bundle_version`
- `state_seq`
- `causation_id`
- `correlation_id`
- `occurred_at`
- `payload_uri`
- `payload_hash`
- `state_hash_after`

## 13.5 `arena_round_barrier` Suggested Columns

- `tournament_id`
- `round_no`
- `expected_table_count`
- `received_hand_close_count`
- `barrier_state`
- `pending_reseat_plan_ref`
- `pending_level_no`
- `terminate_after_current_round`

## 13.6 `arena_action` Suggested Columns

- `request_id`
- `tournament_id`
- `table_id`
- `hand_id`
- `phase_id`
- `seat_id`
- `seat_alias`
- `action_type`
- `action_amount_bucket`
- `action_seq`
- `expected_state_seq`
- `accepted_state_seq`
- `validation_status`
- `result_event_id`
- `received_at`
- `processed_at`
- `error_code`
- `duplicate_of_request_id`

## 13.7 `arena_action_deadline` Suggested Columns

- `deadline_id`
- `tournament_id`
- `table_id`
- `hand_id`
- `phase_id`
- `seat_id`
- `deadline_at`
- `status`
- `opened_by_event_id`
- `resolved_by_event_id`

## 13.8 `arena_operator_intervention` Suggested Columns

- `intervention_id`
- `tournament_id`
- `table_id`
- `seat_id`
- `miner_id`
- `intervention_type`
- `status`
- `requested_by`
- `requested_at`
- `effective_at_safe_point`
- `reason_code`
- `reason_detail`
- `created_event_id`
- `resolved_event_id`

## 13.9 Required Unique Constraints

- `submission_ledger(request_id)`
- `arena_action(request_id)`
- `arena_event_log(stream_key, stream_seq)`
- `arena_action_deadline(table_id, hand_id, phase_id, seat_id, status='open')`
- `arena_action(hand_id, seat_id, phase_id, action_seq)`

## 13.10 Required Hash / Version Columns

必须保留：

- `schema_version`
- `policy_bundle_version`
- `state_hash`
- `payload_hash`
- `artifact_ref`

## 14. `state_seq` Contract

`state_seq` 是 Arena 写路径的强一致性闸门，不是 UI 辅助字段。

## 14.1 Scope

`state_seq` 以 `arena_table` 为边界维护。

原因：

- action 冲突发生在 table-local
- hand / phase / acting seat 都由 table actor 串行推进
- 以 tournament 级 `state_seq` 会放大无关冲突

## 14.2 Increment Rules

以下任一 authoritative table transition 都必须 `state_seq + 1`：

- hand started
- phase opened
- phase closed
- action accepted
- timeout auto action applied
- acting seat changed
- showdown resolved
- hand closed
- table paused for rebalance
- reseat applied to table
- final-table seating applied

以下情况不应推进 `state_seq`：

- duplicate `request_id`
- signature failure
- malformed payload
- stale action rejected
- read-only projector update

## 14.3 Client Contract

客户端每次 arena action 必须携带：

- `expected_state_seq`

服务端规则：

- 精确匹配才可能接受
- 不匹配直接 `state_seq_mismatch`
- 不做“延迟排队等待正确时机再执行”

## 14.4 Idempotency Interaction

Arena action 写入的正确顺序是：

1. 先看 `request_id`
2. 若已存在，返回第一次结果
3. 若新请求，再做签名与 payload 校验
4. 再校验 `expected_state_seq`
5. 通过后才入 table actor 命令流

这样可同时满足：

- duplicate retry 不重放
- stale action 不误执行
- ack 丢失后客户端安全重试

## 14.5 Gateway vs Table Responsibilities

Gateway 可做的预检查：

- `request_id`
- 签名
- payload shape
- tournament/table/seat 存在性

Table actor 才能做的终态检查：

- 当前 `state_seq`
- 是否轮到该 seat
- phase 是否允许该动作
- amount bucket 是否合法

## 14.6 Recovery Requirement

table actor 重启恢复后必须从最新 snapshot + event tail 重建出：

- current `state_seq`
- current phase
- acting seat
- pending deadline

恢复前不得接收新 action。

## 15. Recovery / Replay / Void

## 15.1 Startup Recovery

进程启动后必须扫描所有处于以下状态的 tournaments：

- `live_multi_table`
- `rebalancing`
- `final_table_transition`
- `live_final_table`

并逐个恢复 hub / table actors。

## 15.2 Recovery Procedure

每个 actor 的恢复顺序固定为：

1. load latest snapshot
2. replay event tail
3. load open `arena_action_deadline`
4. 对已过期 deadline 生成 synthetic internal timeout commands
5. actor ready 后才接收新写入

## 15.3 Recoverable vs Unrecoverable

可恢复：

- actor 进程崩溃
- projector 丢失
- client ack 丢失
- reconnect storm

不可恢复：

- authoritative event 缺失
- snapshot 与 event 无法对齐
- replay parity mismatch
- state corruption

## 15.4 Cancel vs Void

- pre-start failure -> `cancelled`
  - 不写 rating
  - 不写 multiplier
- live/post-start unrecoverable failure -> `voided`
  - 不写 rating
  - 不写 multiplier
  - partial replay 仍保留给 ops

## 15.5 Replay Parity Gate

replay 必须验证：

- final tournament snapshot hash
- standing snapshot hash
- per-seat measurement summary
- `arena_rating_input`
- `no_multiplier` final flag
- replay proof hash

任何 mismatch 都是 hard fail。

## 15.6 Time-Cap Freeze Decision

现有文档存在冲突：

- 有的写“当前 hand 结束后终止”
- 有的写“当前 round 结束后终止”

本 spec **冻结为**：

> **time-cap 只在当前 round 结束后生效，不在单桌 hand 边界生效。**

原因：

- 保证 barrier fairness
- 避免不同桌因为 wall-clock 差异被不同程度截断
- 保证跨桌淘汰排序可解释

从现在起，runtime 实现和仿真都按“当前 round 结束”执行。

## 15.7 Projector Rebuild

重建 projector 时：

- 清空 cursor
- 从 authoritative event log 重放
- 对比 snapshot/proof hash
- 完成后原子切换读模型

## 16. No-Multiplier / Rating Input Gates

## 16.1 Structural No-Multiplier

- `practice`
- `exhibition`
- 非 `human_only rated`
- rated entrant 数不达门槛
- rated wave underfill 被降级到 practice/exhibition

## 16.2 Integrity No-Multiplier

- final table 出现 bot
- authoritative event / snapshot 缺失
- replay parity mismatch
- unrecoverable corruption
- live tournament 被 `voided`

## 16.3 Measurement No-Multiplier

- `confidence_weight = 0.00`
- tournament 基本没有形成有效交互
- blind-only elimination rate 极端异常
- timeout auto-action rate 极端异常

## 16.4 Confidence Buckets

为避免实现和 ops 分叉，V1 先冻结离散桶：

- `1.00`：完全合格
- `0.75`：单个 soft fail
- `0.50`：两个 soft fail，或任意 `time_cap_finish`
- `0.25`：明显脏赛，但仍保留弱证据
- `0.00`：hard fail / no-multiplier

## 16.5 Soft-Fail Triggers

以下命中任意项，至少进入 soft-fail 评估：

- `median_hands_played_per_entrant < 8`
- `median_meaningful_decisions_per_entrant < 18`
- `final_table_mean_hands < 6`
- `timeout_auto_action_rate` 超阈值
- `blind_only_elimination_rate` 超阈值
- `invalid_action_rate` 或 `state_seq_mismatch_rate` 明显异常
- stage coverage 明显不足

## 16.6 Warm-up Clamp

前 `15` 场 eligible tournaments：

- 可以写 rating
- `arena_multiplier` 强制钳到 `1.00`

这既是 warm-up 规则，也是 production canary。

## 16.7 Effective Score Rule

喂给 rating 的不是裸 `tournament_score`，而是：

```text
effective_tournament_score
  = tournament_score * confidence_weight
```

## 16.8 Rating Input Minimum Fields

`arena_rating_input` 至少包含：

- tournament identity
- entrant identity
- rated/practice + human_only
- finish rank / percentile
- hands played
- meaningful decisions
- auto actions / timeouts / invalid actions
- stage reached
- stack path summary
- score components
- penalties / adjustments
- `tournament_score`
- `confidence_weight`
- `field_strength_adjustment`
- `bot_adjustment`
- `time_cap_adjustment`

## 17. Validation Matrix

## 17.1 Admission / Pre-start

- `T-2m` lock 之后 register/unregister race
- waitlist promotion
- strict `56..64` rated start
- `48..55` rated downgrade practice/exhibition
- `<48` cancel
- no-show before seat publish
- forced removal after seats published
- deterministic shard-local reseat republish only once
- alias collision / seat-draw-token collision

## 17.2 Table Runtime

- legal-action matrix
- stale action rejection
- duplicate request idempotency
- timeout vs manual race
- negative-stack elimination at hand close
- no side-pot invariant
- raise-cap handling

## 17.3 Connectivity / Session

- disconnect in each phase
- reconnect before deadline
- reconnect after auto action
- reconnect after move-table
- reconnect after final-table transition
- reconnect after elimination
- partial ack loss and retry
- live DQ 后 manual submit 被 gateway 拒绝

## 17.4 Hub Orchestration

- one hand per active table per round
- same-round multi-table elimination ranking
- break shortest table
- rebalance fairness
- no per-round full reshuffle
- bubble -> FT in one barrier
- FT precedence over ordinary rebalance
- time-cap arm and completion

## 17.5 Persistence / Replay

- actor crash during open phase
- actor crash after hand close before barrier
- replay parity 100%
- projector rebuild from zero
- deterministic seed reproduction
- reward-window rebuild parity

## 17.6 Integrity / Measurement

- bot reaches final table
- confidence bucket mapping
- no-multiplier reasons stable and deterministic
- max single-tournament multiplier move `<= 0.01`
- cross-lane amplification bounded

## 18. Test Plan

## 18.1 Unit Tests

- pure hand engine
- legal action matrix
- timeout mapping
- probe cost and showdown split
- tie-break rules
- table-count rule including `P=9..13`

## 18.2 Actor Tests

- table actor command ordering
- stale/duplicate handling
- recovery of open deadlines
- monotonic `state_seq`
- hand close emit correctness

## 18.3 Tournament Integration Tests

- registration -> field lock -> seating -> start
- multi-table round barrier
- rebalance and break-table
- final table transition
- natural champion finish
- time-cap finish
- void flow

## 18.4 Replay / Recovery Tests

- snapshot + tail replay parity
- projector rebuild parity
- `arena_rating_input` parity
- crash mid-round recovery
- expired deadline replay after restart

## 18.5 Simulation / Chaos

- random bot
- tight/passive bot
- always-probe bot
- timeout bot
- soft-play pair
- chip-dump pair
- disconnect storms
- dead-letter projector recovery

## 18.6 Launch-Blocking Criteria

上线 rated multiplier 前必须全部满足：

1. replay parity = `100%`
2. projector / reward-window rebuild parity = exact
3. `>=80%` rated tournaments 有 `>=56` human entrants
4. `0` 个 multiplier-eligible FT 含 bot
5. `>=90%` rated tournaments 自然结束，不靠 time-cap
6. abusive strategies ROI 非正或显著劣于 clean strong bot
7. `confidence_weight` bucket mapping 已写死

## 19. Residual Policy Knobs

这一版已经不再保留 launch-blocking open question。

仍可在 V2 调整、但不影响 V1 实现冻结的，只剩策略参数：

1. rated shard 目标人数是否从 `64` 微调到 `60` 或 `72`，前提是先证明不会降低 skill evidence
2. live disqualification 是否需要细分成更多 sanctions ladder，例如 read-only hold、manual review hold、immediate void
3. operator intervention records 是否要进入 public postgame，还是保持 ops-only

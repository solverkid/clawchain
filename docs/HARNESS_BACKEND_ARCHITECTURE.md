# ClawChain Harness Back-End 架构

**版本**: 0.3  
**日期**: 2026-04-09  
**状态**: V1 后端契约层设计  
**上游产品真相**: [docs/MINING_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md)
**配套契约**: [docs/HARNESS_API_CONTRACTS.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_API_CONTRACTS.md)  
**配套仿真**: [docs/HARNESS_SIMULATION_PLAN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_SIMULATION_PLAN.md)

---

## 1. 设计原则

V1 后端采用：

> **模块化单体优先，聚合边界先行，事件驱动读模型，统一 reward window 聚合。**

推荐基础设施：

- `FastAPI`
- `Postgres`
- `Redis Streams`
- `Object Storage`

不一开始拆微服务。  
先在一个 `Harness Core` 代码库内用清晰边界实现：

- 控制面
- 数据冻结与产包
- 提交与结果
- 评分与 rating
- 风控与奖励
- 审计与读模型

Alpha 实际部署收口为两块：

- `harness monolith`
- `arena runtime worker`

服务边界保留为逻辑模块，不做物理微服务拆分。

---

## 2. 关键不变量

后端实现必须满足以下不变量：

- `daily anchor` 只影响 `global_reliability`
- `arena` 只通过 `arena_multiplier` 进入奖励链路
- `anti_abuse_discount` 只在 `reward_window` 级别应用一次
- `public ELO` 永不参与奖励计算
- `task_run` 只负责 `forecast` 与 `daily`
- `arena` 必须是独立 `tournament_run`
- 所有可见 pack、结果、评分、override 都必须可 replay
- 高置信 cluster 在同一 `task_run` 只允许一个 reward-eligible submission

---

## 3. 聚合根与契约矩阵

## 3.1 聚合根

| Aggregate | 作用 | 适用 lane | 契约重点 |
|---|---|---|---|
| `policy_bundle` | 一次完整生效规则集 | all | 把 scorer/rater/noise/risk/reference/baseline 绑定成单版本 |
| `task_window` | 一个预测/日线任务时窗 | forecast, daily | authoritative clock、freeze/publish/resolve 边界 |
| `task_run` | 一道可提交的任务实例 | forecast, daily | 输入 pack、提交、结果、评分 |
| `tournament_run` | 一场 Arena MTT | arena | seating、levels、hands、rating input |
| `submission_ledger` | 所有外部提交总账 | all | commit/reveal/action 的幂等与审计根 |
| `reward_window` | 一次统一奖励汇总窗口 | all | 汇总 lane 结果并应用 quality envelope |
| `risk_case` | 一个可审理的风控案件 | all | 信号、决策、override、冻结/释放 |
| `settlement_batch` | 一批待落链/待发放奖励 | all | anchor、payout、失败重试 |

## 3.2 lane 与聚合映射

- `forecast`
  - `task_window`
  - `task_run`
  - `submission_ledger`
  - `reward_window`
- `daily`
  - `task_window`
  - `task_run`
  - `daily_reconciliation`
  - `submission_ledger`
  - `reward_window`
- `arena`
  - `tournament_run`
  - `arena_table`
  - `arena_hand`
  - `submission_ledger`
  - `reward_window`

---

## 4. 服务链条

## 4.1 Control Plane

### Policy Registry

职责：

- 维护 `policy_bundle`
- 维护市场白名单
- 维护 season 配置
- 管理 lane 权重和 rollout gate

要求：

- 配置只增不改
- 每个运行对象都必须引用完整 `policy_bundle_version`

### Operator Authority

职责：

- 定义自动权限、人工权限、双签权限
- 记录 override 审计日志

至少区分：

- `automatic`
- `manual_single`
- `manual_dual`

---

## 4.2 Data Plane

### Feed Ingestors

职责：

- 接入 Polymarket
- 接入 Binance
- 接入内部聚合流

所有原始数据必须带：

- `source_timestamp`
- `ingest_timestamp`
- `schema_version`
- `source_id`

### Scheduler / Clock Authority

职责：

- 创建 `task_window`
- 创建 `task_run`
- 创建 `reward_window`
- 创建 `tournament_run`

原则：

- 不依赖进程内 cron 为单一真相
- 所有 deadline 必须落库

### Snapshot Freezer

职责：

- 按 `task_window` 冻结统一快照
- 生成 `snapshot_bundle`
- 写入对象存储并返回 `artifact_ref`

失败只允许：

- `degraded`
- `voided`

### Feature Builder

职责：

- 从 frozen snapshot 生成 deterministic feature bundle
- 产出可重放的结构化特征

### Noise Injection

职责：

- 只改 miner 可见表面
- 不改底层语义
- 生成版本化 `noise_manifest`

### Pack Publisher

职责：

- 发布 `task_pack`
- 返回 `pack_hash`
- 支持 polling / retry / immutable fetch

---

## 4.3 Outcome Plane

### BaselineForecaster

职责：

- 生成公开可复算的 `baseline_q`
- 只服务 forecast/daily

Alpha 默认方法：

```text
baseline_q
  = clamp(0.05, 0.95, 0.85 * q_pm + 0.15 * q_bin)
```

其中：

- `q_pm = midpoint_implied_probability`
- `q_bin = sigmoid(0.45 * depth_imbalance_z + 0.35 * trade_imbalance_z + 0.20 * microprice_drift_z)`
- 若 `q_pm` 不健康，则降级为 `q_bin_only`
- `q_pm` 不健康条件：
  - 无双边盘口
  - staleness `> 15s`
  - implied spread `> 0.10`

### ReferencePriceService

职责：

- 生成 `start_ref_price`
- 生成 `end_ref_price`
- 提供 fallback hierarchy 与 void 逻辑

Alpha 默认方法：

- `commit_close_ref_price = midpoint TWAP(5s, 1s cadence)`
- `end_ref_price = midpoint TWAP(5s, 1s cadence)`
- `fallback_1 = Binance VWAP(5s)`
- `fallback_2 = cross-venue median TWAP(5s)`，仅在接入时启用
- `<4` 个有效样本：`degraded`
- `<3` 个有效样本：`voided`
- primary 与 `fallback_1` 偏离 `> 15 bps`：`degraded`
- primary 与 `fallback_2` 偏离 `> 25 bps`：`voided`

### DailyReconciler

职责：

- 管理 `daily` 的 `provisional -> matured -> reconciled`
- 记录 `market_health_snapshot`
- 生成 `daily_anchor_record`

当前 runtime 最小实现：

- 只做 `daily_anchor`
- 只更新 `model_reliability`
- 不写 `slow_direct_score`
- 若拿不到 daily resolution，则 task 进入 `awaiting_resolution`

### ArenaRuntimeResolver

职责：

- 推进 Arena tournament state
- 生成 `arena_rating_input`
- 输出 tournament 完赛结果

当前 runtime 最小实现：

- 不实现 tournament runtime
- 只接收已完赛 Arena 结果
- 只生成 `arena_result_entries`
- 只 patch 已存在的共享 miner 行
- 只允许写 lane-owned 字段：
  - `arena_multiplier`
- 不得插入 stub miner
- 不得覆盖 `public_key`、`economic_unit_id`、reward / hold / forecast counters、`admission_state`、`ops_reliability`
- Poker MTT admin apply 路径同理，只允许 patch `poker_mtt_multiplier`
- 若目标 miner 不存在，runtime 必须显式报错，而不是 silent no-op
- Forecast service 内部对共享 miner 的写入也已按职责拆成显式 writer：
  - `cluster_identity`
  - `forecast_participation`
  - `forecast_settlement`
  - `public_ranking`
- Reward / settlement shared objects 也已按职责拆分 update path：
  - `link_reward_window_settlement_batch`
  - `sync_open_settlement_batch`
  - `mark_settlement_batch_anchor_ready`
  - `mark_settlement_batch_anchor_submitted`
  - `mark_settlement_batch_terminal`
- `save_reward_window / save_settlement_batch` 的 update 语义在 Fake / Postgres 两个 repo 中保持一致，都是 merge-preserving；窄变更优先走显式 helper，generic save 只保留给 create 或 full materialization

---

## 4.4 Submission Plane

### Submission Gateway

职责：

- 验签
- nonce 校验
- 时窗校验
- 速率限制
- 幂等

原则：

- 所有提交先写 `submission_ledger`
- 再 fan-out 到 lane-specific tables
- 高置信 cluster 的重复同题提交会被标记为 `audit_only`

### submission_ledger 作为提交根表

统一字段至少包括：

- `submission_id`
- `request_id`
- `lane`
- `aggregate_type`
- `aggregate_id`
- `miner_id`
- `submission_kind`
- `received_at`
- `validation_status`
- `signature_digest`
- `client_version`
- `payload_artifact_ref`

子类型：

- `submission_commit`
- `submission_reveal`
- `arena_action`

重复/冲突 contract：

- 相同 `request_id` 二次到达：返回已有结果，不重复入账
- 同一 `task_run` 同一经济单位出现多个 reward-eligible reveal：仅最早有效 reveal 保留 reward eligibility，其余转为 `audit_only`
- 当前 runtime 在两类情形自动打开 `risk_case`：
  - `economic_unit_cluster`：服务端证据图把多个 miner 合并进同一 economic unit
  - `economic_unit_duplicate`：同一 `task_run` 内，同 economic unit 出现多个 reveal
- Arena action 若 `expected_state_seq` 不匹配：拒绝，不做延迟重放

---

## 4.5 Score / Rating / Risk / Settlement Plane

### Scoring Engine

职责：

- 只计算 lane 内 raw score
- 只写追加式 `score_revision`

### Rating Engine

职责：

- 管理 hidden `mu/sigma`
- 管理 `reliability_state`
- 管理 `calibration_state`
- 投影 `public_ladder_snapshot`

### Anti-Abuse Engine

Anti-Abuse 必须拆成三层：

1. `signal layer`
   - 产出 `risk_signal`
2. `decision layer`
   - 汇总为 `risk_case`
   - 产出 `risk_decision`
3. `enforcement layer`
   - 应用 `reward_hold`
   - 应用 `anti_abuse_discount`
   - 应用 `multiplier_clamp`
   - 必要时 `freeze/review`

### Reward Window Aggregator

职责：

- 汇总 `fast_direct_score`
- 汇总 `slow_direct_score`
- 汇总 `model_reliability`
- 汇总 `ops_reliability`
- 汇总 `arena_multiplier`
- 应用一次 `anti_abuse_discount`
- 生成 `reward_component`
- 生成 `reward_intent`

`reward_window` 是 lane 结果和链侧 epoch 之间的唯一中间层。

Alpha 默认采用 **forecast-led aggregation**：

- 一个 `reward_window` 只包含该窗口内 finalized 的 `forecast task_runs`
- 只叠加窗口关闭时最近已 finalized 的 `daily anchor snapshot`
- 只叠加窗口关闭时最近已 finalized 的 `arena multiplier snapshot`
- late-arriving 的 daily 或 arena 结果不回滚历史 reward window，只 carry-forward 到下一个窗口

当前 runtime 最小实现：

- 只实现 `forecast_15m` 的 hourly finalized window
- window id 采用 `rw_YYYYMMDDHH`
- membership 先落在 `forecast_task_runs.reward_window_id` 和 `forecast_submissions.reward_window_id`
- 当前只记录 `task_count / submission_count / miner_count / total_reward_amount`
- `reward_window -> settlement_batch` link 已通过显式 helper 更新，避免 shared window row 被 generic patch 覆盖
- 还没有 `daily snapshot merge`、`arena snapshot merge`、链锚定和 replay-proof materialization

### Settlement Batch Builder

当前 runtime 最小实现：

- `settlement_batch` 先作为服务端 skeleton 落库
- 采用 `reward_window -> settlement_batch` 一对一映射
- batch id 采用 `sb_YYYYMMDDHH`
- 当前只记录：
  - `reward_window_ids`
  - `task_count`
  - `miner_count`
  - `total_reward_amount`
- `retry-anchor` 时补充：
  - `anchor_payload_json`
  - `anchor_payload_hash`
  - `anchor_schema_version`
  - `canonical_root`
- open-sync、anchor-ready、anchor-submitted、anchor-terminal 都通过显式 writer 推进，避免 batch row 在状态迁移时丢失未改字段
- 当前 runtime 已有最小 `anchor_job` 状态机：
  - `anchor_ready`
  - `anchor_submitted`
  - `anchored`
  - `anchor_failed`
- 当前 anchor payload 已按链兼容对象收口：
  - `schema_version`
  - `policy_bundle_version`
  - `reward_window_ids_root`
  - `task_run_ids_root`
  - `miner_reward_rows_root`
  - `canonical_root`
- `miner_reward_rows[]` 当前作为链前可审计材料保留在 payload 内；后续如果上链只提交 root，rows 仍可留在 artifact plane
- 当前 runtime 已有最小 build-only chain adapter：
  - 输入：`anchor_job + anchor_payload_json + canonical_root`
  - 输出：`future_msg + typed_tx_intent + fallback_memo + plan_hash`
- 当前 runtime 还可在本地将 `typed_tx_intent` 编译成：
  - `tx_body_bytes`
  - `auth_info_bytes`
  - `sign_doc_bytes`
  - `unsigned_tx_bytes`
  - 输入依赖 `sender_address + account_number + sequence + public_key`
- 当前 runtime 还支持最小 typed CLI broadcaster：
  - 调用 `clawchaind tx settlement anchor-batch ... --generate-only`
  - 然后 `clawchaind tx sign unsigned.json --offline --account-number N --sequence S`
  - 最后 `clawchaind tx broadcast signed.json`
  - `keyring_dir` 同样支持根目录或 `keyring-test` 目录并会先规范化
  - `account_number` / `next_sequence` 解析逻辑与 fallback path 复用
  - 单进程内串行执行 broadcasts，降低 sequence 冲突
  - 若返回 `sequence mismatch / incorrect account sequence`，会自动重试一次
  - 成功回写 `broadcast_tx_hash / broadcast_status`
  - `chain_broadcast_receipt` artifact 会记录 `account_number / sequence / attempt_count / broadcast_method`
  - 不自动推进到 `anchored`
- 当前 runtime 还支持最小链确认 reconciler：
  - 通过 persisted `broadcast_tx_hash` 查询 RPC `tx(hash=...)`
  - 归一化为 `confirmed / pending / failed`
  - `confirmed` 时推进到 `anchored`
  - `failed` 时推进到 `anchor_failed`
  - `pending` 时保持 `anchor_submitted`
  - `chain_confirmation_receipt` artifact 会记录 `height / code / raw_log`
  - 通过 `POST /admin/anchor-jobs/reconcile-chain` 提供最小批量 sweep 面
  - runtime 默认可启动最小后台 loop 周期性执行同一 sweep
  - 通过 `GET /admin/chain/health` 暴露 loop metrics、stale pending 和 alert 聚合
  - 通过 `GET /admin/anchor-jobs/action-queue` 暴露 failed / stale pending 的 operator triage 队列
  - 通过 `POST /admin/anchor-jobs/{id}/retry-broadcast-typed|fallback` 提供 failed job remediation 写面
  - remediation 会保留旧 failed job，并把 batch `anchor_job_id` 切到新的 replacement job
  - loop interval、stale pending 阈值、consecutive error alert 阈值都可配置
- 当前 runtime 还支持最小 CLI fallback broadcaster：
  - 调用 `clawchaind tx bank send ... --note anchor:v1:... --offline --account-number N --sequence S`
  - `keyring_dir` 可传根目录或 `keyring-test` 目录，运行前会规范化
  - 若未配置 `anchor_to_address`，默认解析 source key 并做 self-transfer memo anchor
  - `account_number` 优先取显式配置，否则从 `normalized keyring dir/config/genesis.json` 解析
  - `next_sequence` 通过 Comet RPC `tx_search(message.sender=...)` 推导
  - 单进程内会串行执行 broadcasts，降低 sequence 冲突
  - 若返回 `sequence mismatch / incorrect account sequence`，会用 error hint 或刷新后的 sequence 自动重试一次
  - 当前假设 anchor sender 是单写入、专用账户；如有 out-of-band tx，可用 sequence override 兜底
  - 成功回写 `broadcast_tx_hash / broadcast_status`
  - `chain_broadcast_receipt` artifact 会记录 `command / account_number / sequence / attempt_count`
  - 不自动推进到 `anchored`
- 当前 runtime 还提供 `GET /admin/chain/preflight` 最小 readiness 检查
- 当前 runtime 还提供 `GET /admin/chain/health` 最小 health 读面
- 当前 runtime 还提供 `GET /admin/anchor-jobs/action-queue` 最小 operator triage 读面
- 当前 runtime 还提供 `POST /admin/anchor-jobs/{id}/retry-broadcast-typed|fallback` 最小 failed-anchor remediation 写面
- 还没有 payout job 或自动失败重试编排；后台确认 loop 目前仍是最小实现
- 链侧已落最小 `x/settlement` 模块骨架，typed Msg submitter 当前通过 CLI 组合链路实现，不是 in-process SDK broadcaster

### Chain Adapter

职责：

- 将 `settlement_batch` 锚定到链上
- 管理 payout job

当前 runtime 最小实现：

- 提供 `build_only` tx plan
- 提供 typed CLI broadcaster
- 提供 memo-based CLI fallback broadcaster
- 提供最小 tx confirmation reconciler
- typed broadcaster 负责：
  - `tx settlement anchor-batch --generate-only`
  - offline sign document generation through CLI JSON tx flow
  - `tx sign` + `tx broadcast`
  - sender sequence inference
  - local broadcast serialization
  - single retry on sequence mismatch
- 当前 fallback broadcaster 负责：
  - offline signing
  - genesis account-number resolve
  - sender sequence inference
  - local broadcast serialization
  - single retry on sequence mismatch
- 当前 confirmation reconciler 负责：
  - 按 tx hash 查询链上结果
  - 归一化 `confirmed / pending / failed`
  - 驱动 `anchor_submitted -> anchored / anchor_failed`
- 输出同时包含：
  - 未来链模块的 `future_msg`
  - 最小 typed Msg adapter `typed_tx_intent`
  - 可本地编译的 sign-doc / unsigned-tx material
  - 当前 CLI 兼容的 `fallback_memo`
  - deterministic `plan_hash`

失败策略：

- 不回滚评分与 rating
- batch 停在 `anchor_pending`

---

## 4.6 Audit & Read Plane

### Replay / Audit

职责：

- 存档 snapshot / feature / noise / pack
- 存档提交、结果、评分、风控、奖励
- 支持 deterministic replay

当前 runtime 最小实现：

- 先不接对象存储
- 用本地 `artifact` ledger 承载最小 replay surface
- 当前 artifact 种类：
  - `task_pack`
  - `reward_window_membership`
  - `settlement_anchor_payload`
  - `chain_tx_plan`
  - `chain_broadcast_receipt`
  - `chain_confirmation_receipt`

### Audience-specific Projectors

读模型必须按 audience 拆开：

- `miner_read`
- `public_read`
- `ops_read`

原因：

- 权限不同
- freshness 目标不同
- debug 深度不同

当前 runtime 最小 read-model 已经包含：

- `GET /v1/miners/{miner_id}/status`
- `GET /v1/miners/{miner_id}/submissions`
- `GET /v1/miners/{miner_id}/reward-holds`
- `GET /v1/miners/{miner_id}/reward-windows`
- `GET /v1/miners/{miner_id}/tasks/history`
- `GET /v1/artifacts/{artifact_id}`
- `GET /v1/leaderboard`
- `GET /admin/risk-cases/open`
- `GET /admin/settlement-batches`
- `GET /admin/anchor-jobs`
- `GET /admin/anchor-jobs/action-queue`
- `GET /admin/anchor-jobs/{id}/chain-tx-plan`
- `POST /admin/anchor-jobs/{id}/broadcast-fallback`
- `POST /admin/anchor-jobs/{id}/broadcast-typed`
- `POST /admin/anchor-jobs/{id}/confirm-chain`
- `POST /admin/anchor-jobs/{id}/retry-broadcast-fallback`
- `POST /admin/anchor-jobs/{id}/retry-broadcast-typed`
- `POST /admin/anchor-jobs/reconcile-chain`

当前 runtime 在启用真实 Postgres repository 时要求配置 `CLAWCHAIN_ADMIN_API_TOKEN`，并对全部 `/admin/*` 路由启用 bearer / header token 校验。

---

## 5. 状态模型

不再使用单一长状态串。  
V1 使用多维状态。

## 5.1 task_run 四维状态

### execution_state

```text
scheduled
-> freezing
-> frozen
-> features_ready
-> published
-> commit_open
-> reveal_open
-> submission_closed
-> scored
```

异常分支：

- `degraded`
- `voided`
- `aborted`

### outcome_state

- `forecast`: `pending -> final | voided`
- `daily`: `pending -> provisional -> matured -> reconciled | voided`

### rating_state

- `pending`
- `applied`
- `recomputed`

### settlement_state

- `unready`
- `queued`
- `settled`
- `anchor_pending`
- `anchor_failed`
- `anchored`
- `released`

## 5.2 risk_state 与 maturity_state

### risk_state

```text
clean
-> monitored
-> discounted
-> clamped
-> frozen
-> reviewed
```

### maturity_state

```text
none
-> held
-> maturing
-> released
-> forfeited
```

Alpha 默认 maturity 曲线：

- `clean_established = 70% immediate + 30% 72h`
- `new_or_probation = 20% immediate + 80% 7d`
- `monitored = 0% immediate + 100% 14d hold`
- `frozen = 0% release until review`
- `admission_hold = 0% immediate + 100% forfeitable hold until 7d or 500 fast reveals + 4 daily reveals`
- 当前 runtime 原型简化为 `20% immediate + 80% held`，graduate gate 为 `7d or 500 fast reveals`
- daily gate 继续保留在目标架构里，但不作为当前代码路径的 release blocker
- 当前代码已经实现 `reward_hold_entries` 级别的 hold ledger，并按 miner graduate 自动释放
- 更细粒度的 forfeiture / review workflow 仍保留到下一轮

Alpha 自动路径收口：

- 自动系统只区分 `clean` 与 `probation_held`
- `monitored / discounted / clamped / frozen` 作为人工 review 结果使用

## 5.3 tournament_run 状态

```text
scheduled
-> seating
-> live
-> rebalancing
-> final_table
-> completed
-> rated
-> settled
```

附加标志位：

- `exhibition = true|false`
- `no_multiplier = true|false`
- `cancelled = true|false`

Arena 还需要：

- `table_state`: `open -> hand_live -> waiting_phase -> closed`
- `seat_state`: `active -> sit_out -> eliminated`

## 5.4 reward_window 状态

```text
open
-> collecting
-> scored
-> rated
-> risk_evaluated
-> settled
-> anchored
-> finalized
```

## 5.5 settlement_batch / anchor_job 状态

当前 runtime 收口成一条最小 batch progression：

```text
open
-> anchor_ready
-> anchor_submitted
-> anchored
```

失败分支：

```text
anchor_submitted
-> anchor_failed
-> anchor_ready
```

确认分支：

```text
anchor_submitted
-> confirm-chain(pending)
-> anchor_submitted

anchor_submitted
-> confirm-chain(confirmed)
-> anchored

anchor_submitted
-> confirm-chain(failed)
-> anchor_failed
```

说明：

- `retry-anchor` 只负责重建 canonical payload 并把 batch 推回 `anchor_ready`
  - 仅允许在 `open / anchor_ready / anchor_failed` 调用
  - `anchor_submitted / anchored` 后 batch 进入 immutable zone，禁止重算
- `submit-anchor` 只创建最小 `anchor_job` 记录，并把 batch 推到 `anchor_submitted`
- `confirm-chain` 会先按 `broadcast_tx_hash` 查询链上 tx 结果，再通过 `abci_query` 校验链上 `x/settlement` anchor 内容与本地 canonical payload 是否一致，然后再推进状态
- `reconcile-chain` 会批量扫过 pending anchor jobs，并对每个 job 复用 `confirm-chain`
- `mark-anchored` 当前复用 `confirm-chain`，不再提供跳过链校验的裸 override
- `mark-failed` 仍保留为 operator override
- 当前 batch 上显式持久化 `anchor_job_id`

---

## 6. API 合同

## 6.1 Public Read APIs

- `GET /v1/task-runs/active`
- `GET /v1/forecast/task-runs/{task_run_id}`
- `GET /v1/daily/task-runs/{task_run_id}`
- `GET /v1/tournaments/{tournament_id}/standing`
- `GET /v1/tournaments/{tournament_id}/live-table/{table_id}`
- `GET /v1/miners/{miner_id}/status`
- `GET /v1/replays/{entity_type}/{entity_id}/proof`

Alpha 运行时建议最小 public read 面：

- `task-runs/active`
- `task run detail`
- `tournament standing/live table`
- `miner status`
- `replay proof`

统一响应 envelope 至少包含：

- `object_id`
- `lane`
- `schema_version`
- `policy_bundle_version`
- `server_time`
- `trace_id`
- `state`

## 6.2 Public Write APIs

- `POST /v1/task-runs/{task_run_id}/commit`
- `POST /v1/task-runs/{task_run_id}/reveal`
- `POST /v1/tournaments/{tournament_id}/actions`

### commit 最小字段

- `request_id`
- `task_run_id`
- `miner_id`
- `commit_hash`
- `nonce`
- `client_version`
- `signature`

### reveal 最小字段

- `request_id`
- `task_run_id`
- `miner_id`
- `p_yes_bps`
- `nonce`
- `schema_version`
- `signature`

响应至少返回：

- `accepted_at`
- `server_cutoff`
- `ledger_id`
- `pack_hash`
- `validation_status`

额外建议字段：

- `economic_unit_id`
- 当前 `economic_unit_id` 是服务端 cluster key，不把客户端自报值当作 truth source
- 当前 cluster key 基于 exact IP、user-agent hash 和连通分量闭包
- `reward_eligibility = eligible | audit_only`

### arena action 最小字段

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

## 6.3 Admin APIs

- `POST /admin/markets/activate`
- `POST /admin/policies/publish`
- `POST /admin/seasons/open`
- `POST /admin/task-runs/{id}/void`
- `POST /admin/task-runs/{id}/rerun-score`
- `POST /admin/reward-windows/{id}/rebuild`
- `POST /admin/settlement-batches/{id}/retry-anchor`
- `POST /admin/settlement-batches/{id}/submit-anchor`
- `GET /admin/anchor-jobs`
- `GET /admin/chain/health`
- `GET /admin/chain/preflight`
- `GET /admin/anchor-jobs/{id}/chain-tx-plan`
- `POST /admin/anchor-jobs/{id}/mark-anchored`
- `POST /admin/anchor-jobs/{id}/mark-failed`
- `POST /admin/risk-decisions/{id}/override`
- `POST /admin/read-models/rebuild`

## 6.4 Internal Commands

- `freeze_snapshot(task_run_id)`
- `build_features(snapshot_id)`
- `publish_pack(task_run_id)`
- `compute_baseline(task_run_id)`
- `resolve_forecast_outcome(task_run_id)`
- `reconcile_daily(task_run_id)`
- `advance_tournament(tournament_id)`
- `append_score_revision(aggregate_id)`
- `recompute_rating(subject_id, window)`
- `build_reward_window(reward_window_id)`
- `anchor_batch(batch_id)`

---

## 7. 数据模型

## 7.1 控制层

- `market_source`
- `canonical_contract`
- `policy_bundle_version`
- `policy_component_version`
- `season`
- `season_lane_weight`
- `operator_authority`

## 7.2 时钟与运行层

- `task_window`
- `task_run`
- `task_run_contract_ref`
- `task_run_policy_ref`
- `task_run_visibility`
- `task_run_finality`
- `reward_window`
- `reward_window_snapshot`
- `arena_tournament`
- `arena_level`
- `arena_table`
- `arena_hand`
- `arena_phase`
- `arena_seat`

## 7.3 Artifact 层

- `artifact_ref`
- `snapshot_bundle`
- `feature_bundle`
- `noise_manifest`
- `pack_manifest`
- `replay_artifact`

## 7.4 提交层

- `submission_ledger`
- `submission_commit`
- `submission_reveal`
- `arena_action`
- `submission_validation_error`
- `client_version_seen`

## 7.5 结果与评分层

- `outcome_revision`
- `score_revision`
- `ticket_record`
- `daily_anchor_record`
- `arena_rating_input`
- `quality_envelope_component`

## 7.6 rating 层

- `rating_state_current`
- `rating_snapshot`
- `public_ladder_snapshot`
- `reliability_state`
- `calibration_state`
- `arena_multiplier_snapshot`

## 7.7 风控层

- `risk_signal`
- `risk_case`
- `risk_decision`
- `probation_state`
- `economic_unit`
- `reward_hold`
- `account_link`
- `device_fingerprint`
- `network_fingerprint`
- `behavior_cluster`

## 7.8 daily 专用层

- `daily_reconciliation`
- `maturity_hold`
- `market_health_snapshot`
- `cross_lane_correlation_cap_record`

## 7.9 Arena 专用层

- `arena_alias_map`
- `arena_public_snapshot`
- `arena_collusion_metric`
- `arena_reseat_event`
- `arena_elimination_event`
- `arena_action_deadline`
- `arena_regime_family`

## 7.10 结算层

- `reward_component`
- `reward_intent`
- `settlement_batch`
- `anchor_job`
- `payout_job`

---

## 8. 唯一键与版本键

至少需要：

- `task_run(lane, contract_id, publish_at)`
- `artifact_ref(hash, kind)`
- `submission_ledger(request_id)`
- `outcome_revision(task_run_id, revision)`
- `score_revision(task_run_id, miner_id, scorer_revision, revision)`
- `reward_component(reward_window_id, miner_id, component_type)`
- `arena_action(hand_id, seat_id, phase_id, action_seq)`

所有评分、结果、风控决定都必须追加 revision，而不是原地覆盖。

`reward_window` membership contract 也必须可审计，至少记录：

- `reward_window_id`
- `forecast_task_run_ids[]`
- `daily_anchor_snapshot_id`
- `arena_multiplier_snapshot_id`
- `carry_forward_reason`

---

## 9. 事件与 Outbox 契约

## 9.1 Outbox event envelope

每个 outbox event 至少包含：

- `event_id`
- `aggregate_type`
- `aggregate_id`
- `stream_key`
- `lane`
- `season_id`
- `reward_window_id`
- `event_type`
- `event_version`
- `occurred_at`
- `causation_id`
- `correlation_id`
- `producer`
- `payload_hash`
- `payload_uri`
- `visibility`

## 9.2 事件家族

- `control.*`
- `task_run.*`
- `tournament.*`
- `rating_risk.*`
- `reward_settlement.*`

### forecast / daily 关键事件

- `task_run.created`
- `task_run.state_changed`
- `snapshot.frozen`
- `features.built`
- `pack.published`
- `submission.commit.accepted`
- `submission.reveal.accepted`
- `submission.reveal.rejected`
- `outcome.provisional.computed`
- `outcome.final.computed`
- `score.revision.appended`
- `rating.snapshot.updated`
- `risk.decision.applied`
- `reward.component.computed`
- `settlement.batch.assigned`

### arena 关键事件

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

## 9.3 Outbox 支撑表

- `outbox_event`
- `outbox_dispatch`
- `projector_cursor`
- `dead_letter_event`

原则：

- projector 以 `event_id` 幂等
- 大 payload 不直接塞 outbox，只保存 `artifact_ref`

---

## 10. 读模型与可见面

## 10.1 miner_read

用于：

- 当前 task packs
- 自己的 score explanation
- reward timeline
- 自己的 probation / maturity 状态

## 10.2 public_read

用于：

- 公共 leaderboard
- public ELO
- Arena 赛后榜
- season snapshot

## 10.3 ops_read

用于：

- 风控案件
- 任务 replay
- settlement trace
- operator overrides

---

## 11. 运维与 SLO

## 11.1 必要面板

- `Market Ops`
- `Settlement Ops`
- `Arena Ops`
- `Abuse Review`
- `Support Console`
- `Replay Debugger`
- `Account Timeline`

## 11.2 Authority Matrix

至少以下动作应双签：

- `void reward_window`
- `risk freeze release`
- `anchor retry with mutation`

单签人工操作至少包括：

- `task_run void`
- `score rerun`
- `daily reconcile override`

自动系统权限上限：

- 最多 `25%` reward discount
- 最多将 `arena_multiplier` 上限钳制到 `1.00`
- 更重处罚必须人工 review
- `held` 状态必须在 `72h` 内进入人工 review，否则自动降级为较轻限制

## 11.3 默认 SLO

- `15m pack publish p95 <= T+2s`
- `commit acceptance >= 99.5%`
- `reveal completion >= 97%`
- `15m provisional settlement lag p95 <= resolve_at + 120s`
- `daily provisional lag p95 <= cutoff + 10m`
- `leaderboard freshness <= 60s`
- `replay parity = 100%`

`replay parity` 必须是 blocking alert。

---

## 12. 失败模式与恢复

- `feed gap at freeze`
  - 判定 `degraded` 或 `voided`
- `duplicate publish / duplicate score`
  - 依赖 unique key + revision append
- `late reveal / clock skew`
  - 只认 server cutoff
- `daily reconciliation drift`
  - 进入 `maturity_hold`
- `rating backlog`
  - settlement 以 barrier 等待必需 snapshot
- `anti-abuse false positive`
  - 先 soft discount，再 review
- `anchor failure`
  - batch 停在 `anchor_pending`
- `artifact missing`
  - checksum 巡检 + 冷热备份
- `arena table stalls`
  - phase timeout 自动动作
- `read model drift`
  - 以 source-of-truth + projector rebuild 恢复

---

## 13. Alpha 默认参数收口

- `baseline_q = 0.85 * q_pm + 0.15 * q_bin`
- `ReferencePriceService = commit_close_ref_price + end_ref_price`，基于 `5s midpoint TWAP`
- fast lane `commit_deadline = T+3s`，`reveal_deadline = T+13s`
- daily canonical contract：`00:00 UTC` 发布、`24h` cutoff、day-1 仅作为 anchor lane
- high-confidence cluster：同题只保留一个 reward-eligible submission，其余 `audit_only`
- `admission_hold` 作为 Alpha 资本约束层；`new_or_probation = 20/80`
- anti-abuse 自动权限上限：`25%` reward discount + `1.00` arena cap
- public ladder：每 `60m` 快照一次；Arena `public ELO` post-rating 更新
- Arena multiplier rolling window：最近 `20` 场 eligible tournaments

---

## 14. 结论

后端实现不应围绕“几个 worker 串起来”来组织，而应围绕：

- `task_run`
- `tournament_run`
- `reward_window`
- `submission_ledger`
- `policy_bundle`

这几个聚合根来组织。

V1 真正需要的不是更多服务名，而是：

> **清晰的契约边界、可重放的状态变迁、统一的奖励聚合层，以及对 forecast / daily / arena 三条 lane 的硬不变量约束。**

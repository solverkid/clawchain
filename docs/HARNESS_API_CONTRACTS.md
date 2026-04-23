# ClawChain Harness API Contracts

**版本**: 0.1  
**日期**: 2026-04-09  
**状态**: Alpha day-1 API / event contract baseline  
**上游文档**:
- [docs/MINING_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md)
- [docs/HARNESS_BACKEND_ARCHITECTURE.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_BACKEND_ARCHITECTURE.md)
- [docs/DYNAMIC_ARENA_ALPHA_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/DYNAMIC_ARENA_ALPHA_DESIGN.md)

---

## 1. 目标与范围

本文档把 Alpha day-1 需要真正对外和对内稳定下来的契约写死，包括：

- public read APIs
- public write APIs
- admin APIs
- event envelope
- 核心事件 payload
- 错误语义
- 强不变量

本文档不定义：

- 完整数据库 DDL
- auth / wallet onboarding UX
- chain anchor payload 细节
- internal worker runtime implementation

---

## 2. 全局约定

## 2.1 标识与时间

- 所有主键使用字符串 ID
- 时间字段统一为 RFC3339 UTC
- 所有对外时钟以 `server_time` 为准
- 所有写请求都必须带 `request_id`

## 2.2 fixed-point 与概率

- `p_yes_bps` 取值范围：`1500..8500`
- `baseline_q_bps` 取值范围：`500..9500`
- 所有概率字段都使用整数 basis points

## 2.3 lane

允许的 `lane`：

- `forecast_15m`
- `daily_anchor`
- `arena_rated`
- `arena_practice`
- `poker_mtt_daily`
- `poker_mtt_weekly`

## 2.4 经济单位

Alpha day-1 引入 `economic_unit_id` 作为 reward eligibility 约束层。

规则：

- 高置信 cluster 在同一 `task_run` 只允许一个 reward-eligible submission
- 其余同题提交保留用于审计，但标记 `audit_only`
- `economic_unit_id` 由服务端绑定和回传；客户端可传旧字段做兼容，但服务端不把它当作 truth source
- 当前原型的 cluster 证据来自 exact IP、user-agent hash 和它们形成的连通分量

---

## 3. 通用响应 envelope

所有 public read 和 write 响应都至少包含：

```json
{
  "object_id": "string",
  "object_type": "string",
  "lane": "forecast_15m",
  "schema_version": "v1",
  "policy_bundle_version": "pb_2026_04_09_a",
  "server_time": "2026-04-09T09:00:03Z",
  "trace_id": "trc_...",
  "state": {
    "execution_state": "published",
    "outcome_state": "pending",
    "rating_state": "pending",
    "settlement_state": "unready"
  },
  "data": {}
}
```

Arena tournament/read models可以省略与对象无关的状态维度，但不得省略：

- `object_id`
- `lane`
- `schema_version`
- `policy_bundle_version`
- `server_time`
- `trace_id`

---

## 4. Public Read APIs

## 4.1 `GET /v1/task-runs/active`

用途：

- 返回当前可参与的 `forecast_15m` 和 `daily_anchor` 任务卡片

响应 `data`：

```json
{
  "items": [
    {
      "task_run_id": "tr_123",
      "lane": "forecast_15m",
      "asset": "BTCUSDT",
      "question_type": "above_below",
      "publish_at": "2026-04-09T09:00:00Z",
      "commit_deadline": "2026-04-09T09:00:03Z",
      "reveal_deadline": "2026-04-09T09:00:13Z",
      "resolve_at": "2026-04-09T09:15:00Z",
      "pack_hash": "sha256:...",
      "snapshot_health": "healthy"
    }
  ]
}
```

## 4.2 `GET /v1/forecast/task-runs/{task_run_id}`

返回：

- 任务元信息
- pack 摘要
- `baseline_q_bps`
- `baseline_method`
- `commit_close_ref_price` 规则说明

关键字段：

```json
{
  "task_run_id": "tr_123",
  "lane": "forecast_15m",
  "asset": "BTCUSDT",
  "baseline_q_bps": 5360,
  "baseline_method": "q_pm_85_q_bin_15",
  "pack_hash": "sha256:...",
  "snapshot_health": "healthy",
  "commit_window": {
    "publish_at": "2026-04-09T09:00:00Z",
    "commit_deadline": "2026-04-09T09:00:03Z",
    "reveal_deadline": "2026-04-09T09:00:13Z"
  }
}
```

## 4.3 `GET /v1/daily/task-runs/{task_run_id}`

返回：

- daily canonical contract
- `publish_at`
- `cutoff_at`
- `anchor_only = true|false`
- maturity / reconciliation 状态

## 4.4 `GET /v1/tournaments/{tournament_id}/standing`

返回：

- `tournament_state`
- `rated_or_practice`
- `players_remaining`
- `current_level`
- `self_rank`
- `non_table_rank_band`
- `no_multiplier`

## 4.5 `GET /v1/tournaments/{tournament_id}/live-table/{table_id}`

返回：

- `button_seat`
- `blind_level`
- `pot_main`
- `seat_public_actions`
- `visible_stacks`
- `acting_seat`
- `phase`

## 4.6 `GET /v1/miners/{miner_id}/status`

Alpha 最小矿工状态视图合并：

- score explanation
- reward timeline
- quality envelope
- probation / maturity
- Arena multiplier

关键字段：

```json
{
  "miner_id": "m_123",
  "public_rank": 142,
  "public_elo": 1218,
  "model_reliability": 1.01,
  "ops_reliability": 0.99,
  "arena_multiplier": 1.00,
  "anti_abuse_discount": 0.25,
  "admission_release_ratio": 0.20,
  "admission_state": "probation",
  "maturity_state": "pending_resolution",
  "risk_review_state": "review_required",
  "open_risk_case_count": 1,
  "open_risk_case_types": ["economic_unit_cluster"],
  "held_rewards": 12345,
  "reward_eligibility_status": "eligible",
  "score_explanation": {
    "latest_fast": {
      "task_run_id": "tr_fast_202604100900_btcusdt",
      "asset": "BTCUSDT",
      "p_yes_bps": 6200,
      "baseline_q_bps": 5500,
      "outcome": 1,
      "score": 0.043,
      "reward_amount": 43000,
      "reward_eligibility_status": "eligible",
      "state": "resolved"
    },
    "latest_daily": {
      "task_run_id": "tr_daily_20260410_btc",
      "asset": "BTC",
      "p_yes_bps": 8500,
      "outcome": 1,
      "anchor_multiplier": 1.015,
      "state": "resolved"
    },
    "latest_arena": {
      "tournament_id": "arena-rated-15",
      "rated_or_practice": "rated",
      "eligible_for_multiplier": true,
      "arena_score": 0.9,
      "arena_multiplier_after": 1.0135
    }
  },
  "reward_timeline": {
    "released_rewards": 8600,
    "held_rewards": 34400,
    "admission_state": "probation",
    "anti_abuse_discount": 0.25,
    "admission_release_ratio": 0.20,
    "open_risk_case_count": 1,
    "open_hold_entry_count": 1,
    "pending_resolution_count": 0,
    "latest_fast_reward_amount": 43000,
    "latest_daily_anchor_multiplier": 1.015,
    "latest_arena_multiplier_after": 1.0135
  }
}
```

说明：
- `anti_abuse_discount` 反映当前 open risk cases 对 forecast payout 的实时折扣
- `admission_release_ratio` 只控制 probation miner 的 released/held 拆分，不再复用为 anti-abuse 字段

## 4.7 `GET /v1/miners/{miner_id}/submissions`

Alpha 当前最小 miner submission history。

返回：

- `items[]`
  - `id`
  - `task_run_id`
  - `miner_address`
  - `economic_unit_id`
  - `state`
  - `eligibility_status`
  - `p_yes_bps`
  - `score`
  - `reward_amount`
  - `reward_window_id`
  - `accepted_commit_at`
  - `accepted_reveal_at`
  - `updated_at`
- `limit`

说明：

- 当前实现按 miner 维度读取已持久化 submission ledger
- 默认倒序，以 `accepted_reveal_at / updated_at` 排序
- `daily_anchor` submission 允许存在，但其 `reward_window_id` 可能为空

## 4.8 `GET /v1/miners/{miner_id}/reward-holds`

Alpha 当前最小 held reward history。

返回：

- `items[]`
  - `id`
  - `miner_address`
  - `task_run_id`
  - `submission_id`
  - `amount_held`
  - `amount_released`
  - `state`
  - `release_after`
  - `created_at`
  - `updated_at`
- `limit`

## 4.9 `GET /v1/miners/{miner_id}/reward-windows`

Alpha 当前最小 miner reward-window history。

返回：

- `items[]`
  - `id`
  - `lane`
  - `state`
  - `window_start_at`
  - `window_end_at`
  - `task_count`
  - `submission_count`
  - `miner_count`
  - `total_reward_amount`
  - `task_run_ids`
  - `miner_addresses`
  - `created_at`
  - `updated_at`
- `limit`

说明：

- 当前 runtime 只为 `forecast_15m` 生成最小 `reward_window`
- `reward_window` 为按小时聚合的 finalized fast-task 窗口
- `reward_window` 还不是链锚定对象，但当前已经产出：
  - `reward_window_membership`
  - `reward_window_replay_bundle`
  两份 artifact；后者专门承载 replay-proof 的 reward composition lineage

## 4.10 `GET /v1/miners/{miner_id}/tasks/history`

Alpha 当前最小 miner task history。

返回：

- `items[]`
  - `task_run_id`
  - `lane`
  - `asset`
  - `publish_at`
  - `resolve_at`
  - `task_state`
  - `submission_state`
  - `pending_resolution`
  - `reward_window_id`
  - `settlement_batch_id`
  - `eligibility_status`
  - `p_yes_bps`
  - `score`
  - `reward_amount`
  - `outcome`
  - `updated_at`
- `limit`

说明：

- 这是 miner 已参与 task 的 join-read，不是全网 task catalog
- `pending_resolution=true` 表示 miner 已 reveal，但官方结果还没回来
- 当前 `settlement_batch_id` 只对已进入 hourly fast-lane window 的 task 可见

## 4.11 `GET /v1/leaderboard`

Alpha 当前最小 public network read-model。

返回：

- `items[]`
  - `address`
  - `name`
  - `public_rank`
  - `public_elo`
  - `total_rewards`
  - `settled_tasks`
  - `model_reliability`
  - `ops_reliability`
  - `arena_multiplier`
  - `admission_state`
  - `risk_review_state`
  - `open_risk_case_count`
- `limit`
- `total_miners`

说明：

- 这是 public surface，不返回私有 anti-abuse 证据
- 读取时不强制重算 public ELO / rank，只返回当前已持久化 ladder

## 4.12 `GET /v1/replays/{entity_type}/{entity_id}/proof`

允许的 `entity_type`：

- `task_run`
- `reward_window`
- `tournament`

返回：

- artifact refs
- policy bundle version
- outcome revision
- score revision
- replay proof hash

当前 runtime 最小实现：

- 支持 `entity_type = task_run | reward_window`
- proof 为 deterministic hash，不依赖外部 artifact store
- proof 背后的 artifact 当前落在服务端本地 artifact ledger
- `reward_window` proof 会返回 membership：
  - `task_run_ids`
  - `miner_addresses`
  - `settlement_batch_id`
- `reward_window` proof 还会返回 `reward_composition`：
  - `reward_window_membership_payload_hash`
  - `reward_component_rows_root`
  - `reward_component_rows_count`
  - `anti_abuse_input_rows_root`
  - `anti_abuse_input_rows_count`
  - `overlay_merge_state`
  当前 `overlay_merge_state` 会显式标注：
  - `daily_snapshot_merge = deferred`
  - `arena_snapshot_merge = deferred`
  也就是说 proof 会承认当前 pass 只 materialize 了 forecast-side component payout，而没有假装 daily / arena overlay 已完成合并

## 4.13 `GET /v1/artifacts/{artifact_id}`

返回单个 artifact。

当前 runtime 已支持的 `kind`：

- `task_pack`
- `reward_window_membership`
- `reward_window_replay_bundle`
- `settlement_anchor_payload`
- `chain_tx_plan`
- `chain_broadcast_receipt`
- `chain_confirmation_receipt`

返回：

- `id`
- `kind`
- `entity_type`
- `entity_id`
- `payload_json`
- `payload_hash`
- `created_at`
- `updated_at`

## 4.14 `GET /admin/risk-cases/open`

Alpha 当前最小 operator 查询面。

返回：

- `id`
- `case_type`
- `severity`
- `state`
- `economic_unit_id`
- `miner_address`
- `task_run_id`
- `submission_id`
- `evidence_json`
- `created_at`
- `updated_at`

## 4.15 `GET /admin/settlement-batches`

当前 runtime 的最小 settlement read surface。

返回：

- `items[]`
  - `id`
  - `lane`
  - `state`
  - `window_start_at`
  - `window_end_at`
  - `reward_window_ids`
  - `task_count`
  - `miner_count`
  - `total_reward_amount`
  - `created_at`
  - `updated_at`

说明：

- Alpha 当前实现为 `reward_window -> settlement_batch` 一对一映射
- 该 endpoint 当前是 pure read，不再隐式触发 forecast progression `reconcile()`
- 这是链前 skeleton，但已开始按链兼容 payload 收口
- `anchor_payload_json/hash` 只有在触发 retry-anchor 后才出现
- 当前 `anchor_payload_json` 已包含：
  - `schema_version`
  - `policy_bundle_version`
  - `reward_window_ids_root`
  - `task_run_ids_root`
  - `miner_reward_rows_root`
  - `canonical_root`
  - `miner_reward_rows[]`
- 当前 `miner_reward_rows[]` 是按 miner 聚合的 `gross_reward_amount` 行，不代表最终 payout execution 语义

## 4.15A `POST /admin/reconcile`

当前 runtime 的最小 forecast progression / operator recovery 写面。

返回：

- `success`
- `reconciled_at`
- `task_count`
- `reward_window_count`
- `settlement_batch_count`

说明：

- 该接口显式触发 `ForecastMiningService.reconcile()`
- 负责 task publication、task settlement、hold release、reward-window build 和 settlement-batch preparation
- public miner/task/history reads 不再承担这条 progression 责任
- 本地调试、operator 恢复和无后台 loop 场景下，应通过这个 endpoint 显式推进

## 4.16 `POST /admin/arena/results/apply`

当前 runtime 的最小 Arena 写入口。

请求字段：

- `tournament_id`
- `rated_or_practice`
- `human_only`
- `results[]`
  - `miner_id`
  - `arena_score`

当前语义：

- `practice` 不更新 multiplier
- 非 `human_only rated` 不更新 multiplier
- 前 `15` 场 eligible tournaments 强制 `arena_multiplier = 1.00`

## 4.17 `GET /admin/anchor-jobs/{anchor_job_id}/chain-tx-plan`

当前 runtime 的最小 chain-adapter / tx-builder 读面。

返回：

- `adapter_version`
- `tx_builder_kind`
- `execution_mode`
- `chain_family`
- `settlement_batch_id`
- `anchor_job_id`
- `canonical_root`
- `anchor_payload_hash`
- `future_msg`
  - `type_url`
  - `value`
- `typed_tx_intent`
  - `version`
  - `body`
  - `auth_info_hints`
  - `sign_doc_hints`
  - `broadcast_hint`
- `fallback_memo`
- `plan_hash`

说明：

- 当前仅支持 `build_only`
- 该 endpoint 当前是 pure read；不会再隐式触发 forecast progression `reconcile()`
- `future_msg` 是为后续链模块预留的 canonical message shape
- `typed_tx_intent` 是当前最小 typed Msg adapter surface：
  - 将来接真实链模块时，优先消费这份结构
  - 当前 typed broadcaster 和未来更原生的链适配层都消费这份结构
- runtime 现在已可将 `typed_tx_intent + sender_address + account_number + sequence + public_key`
  编译成 `tx_body_bytes / auth_info_bytes / sign_doc_bytes / unsigned_tx_bytes`
  但该 endpoint 当前仍只返回 intent，不直接回传这些 runtime signing materials
- `fallback_memo` 是当前最小 Cosmos CLI 兼容兜底，不代表最终链上协议形态
- `keyring_dir` 允许传 keyring 根目录或 `keyring-{backend}` 子目录；runtime 会在执行前规范化为 CLI 需要的根目录
- 每次 build 会在 artifact ledger 中写入 `chain_tx_plan`

## 4.18 `POST /admin/anchor-jobs/{anchor_job_id}/broadcast-fallback`

当前 runtime 的最小 CLI broadcast 兜底写面。

返回：

- `anchor_job_id`
- `settlement_batch_id`
- `broadcast_status`
- `tx_hash`
- `plan_hash`
- `memo`
- `account_number`
- `sequence`
- `attempt_count`

说明：

- 当前只支持 `clawchaind tx bank send ... --note anchor:v1:...` 兜底广播
- runtime 会在单进程内串行执行 fallback broadcasts，避免本地并发抢同一 sender sequence
- 若出现 `account sequence mismatch / incorrect account sequence`，runtime 会按错误里的 expected sequence 或刷新后的 sender sequence 自动重试一次
- `anchor_to_address` 可为空；为空时 runtime 默认解析 `anchor_key_name` 对应地址并执行 self-transfer memo anchor
- 成功后只记录 `tx_hash` 和 receipt，不自动把 batch/job 变成 `anchored`
- 失败时将 `anchor_job` / batch 推到 `anchor_failed`
- 每次 broadcast 会在 artifact ledger 中写入 `chain_broadcast_receipt`
  - 当前 receipt payload 会额外记录 `account_number / sequence / attempt_count / command`

## 4.19 `POST /admin/anchor-jobs/{anchor_job_id}/broadcast-typed`

当前 runtime 的最小 typed Msg CLI 广播写面。

返回：

- `anchor_job_id`
- `settlement_batch_id`
- `broadcast_status`
- `tx_hash`
- `plan_hash`
- `memo`
- `account_number`
- `sequence`
- `attempt_count`
- `broadcast_method`

说明：

- 当前通过 `clawchaind tx settlement anchor-batch --generate-only -> tx sign -> tx broadcast` 执行 typed Msg 广播
- 该路径消费 `chain-tx-plan` 中的 `future_msg + typed_tx_intent + canonical_root`
- runtime 会在单进程内串行执行 typed broadcasts，避免本地并发抢同一 sender sequence
- 若出现 `account sequence mismatch / incorrect account sequence`，runtime 会按错误里的 expected sequence 或刷新后的 sender sequence 自动重试一次
- 成功后会返回 `broadcast_method = typed_msg`
- 成功后只记录 `tx_hash` 和 receipt，不自动把 batch/job 变成 `anchored`
- 失败时将 `anchor_job` / batch 推到 `anchor_failed`
- 每次 broadcast 会在 artifact ledger 中写入 `chain_broadcast_receipt`
  - 当前 receipt payload 会额外记录 `account_number / sequence / attempt_count / broadcast_method`

## 4.20 `POST /admin/anchor-jobs/{anchor_job_id}/confirm-chain`

当前 runtime 的最小链确认 / 状态推进写面。

返回：

- `anchor_job_id`
- `settlement_batch_id`
- `chain_confirmation_status`
  - `confirmed`
  - `pending`
  - `failed`
  - `typed_state_missing`
  - `fallback_memo_only`
  - `root_mismatch`
  - `metadata_mismatch`
- `anchor_job_state`
- `tx_hash`
- `chain_height`
- `tx_code`
- `tx_raw_log`
- `anchored_at`
- `failure_reason`

说明：

- 当前通过 RPC `tx(hash=...)` 查询已广播 tx 的链上结果
- 该路径只消费已持久化的 `broadcast_tx_hash`
- 若 tx 已确认且 `code = 0`：
  - 仍必须通过 settlement anchor query 读到 stored typed state，并匹配 batch/root/hash/metadata 后才把 `anchor_job` 和所属 batch 推进到 `anchored`
- 若 tx 已确认但 typed state 缺失、fallback memo only、root/hash drift 或 metadata drift：
  - 写入 normalized `chain_confirmation_status`
  - 推进到 `anchor_failed`，等待显式 retry/new anchor job
- 若 tx 已确认但 `code != 0`：
  - 自动把 `anchor_job` 和所属 batch 推进到 `anchor_failed`
- 若 tx 仍未查到：
  - 返回 `chain_confirmation_status = pending`
  - 保持 `anchor_submitted`
- 每次确认都会在 artifact ledger 中写入 `chain_confirmation_receipt`

Poker MTT Evidence Phase 2 的目标语义更严格：

- typed `x/settlement` anchor 不能只靠 `tx code = 0` 标记完成
- 服务端必须通过 settlement anchor query 验证 batch id、canonical root、anchor payload hash、lane、policy、window、reward roots 与本地计划一致
- fallback memo tx 如果保留，只能标记为 `fallback_memo_only`，不能等同于 typed `x/settlement` anchored
- Phase 3 Task 6 已把该加强项落到 generated gRPC/gateway/CLI query、service confirmation 和 tests；真实 local-chain smoke artifact 仍属于 release checklist。

## 4.21 `POST /admin/anchor-jobs/reconcile-chain`

当前 runtime 的最小批量链确认 sweep 写面。

返回：

- `count`
- `items[]`
  - `anchor_job_id`
  - `settlement_batch_id`
  - `chain_confirmation_status`
  - `anchor_job_state`
  - `tx_hash`
  - `chain_height`
  - `tx_code`
  - `tx_raw_log`

说明：

- 该接口会扫描当前所有 `anchor_submitted` 且已写入 `broadcast_tx_hash` 的 anchor jobs
- 对每个 job 逐个复用 `confirm-chain` 逻辑
- 当前这是 operator/脚本可显式触发的批量 sweep 面
- runtime 也可在后台 loop 中周期性复用同一条 sweep 逻辑

## 4.22 `GET /admin/chain/health`

当前 runtime 的最小链确认健康读面。

返回：

- `status`
  - `ok`
  - `degraded`
  - `critical`
- `loop`
  - `enabled`
  - `interval_seconds`
  - `active`
  - `run_count`
  - `success_count`
  - `error_count`
  - `consecutive_error_count`
  - `last_started_at`
  - `last_completed_at`
  - `last_result_count`
  - `last_error`
- `anchor_jobs`
  - `total_count`
  - `pending_confirmation_count`
  - `stale_pending_confirmation_count`
  - `awaiting_broadcast_count`
  - `anchored_count`
  - `failed_count`
  - `latest_broadcast_at`
  - `latest_anchored_at`
  - `latest_failed_at`
  - `latest_failure_reason`
- `alerts[]`
  - `code`
  - `severity`
  - `message`

说明：

- `loop` 反映当前进程内最小后台 confirmation loop 的运行状态
- `anchor_jobs` 反映当前持久化 anchor job 的摘要，不依赖后台 loop 是否启用
- `status` 根据 alerts 聚合：
  - 有 `critical` alert 时为 `critical`
  - 无 `critical` 但有 alert 时为 `degraded`
  - 无 alert 时为 `ok`
- 当前最小 alert 规则：
  - `anchor_reconcile_loop_errors`
  - `stale_pending_confirmation`
  - `failed_anchor_jobs_present`
- 当前阈值来自环境变量：
  - `CLAWCHAIN_ANCHOR_RECONCILE_LOOP_ERROR_ALERT_THRESHOLD`
  - `CLAWCHAIN_ANCHOR_PENDING_CONFIRMATION_WARNING_SECONDS`

## 4.22A `GET /admin/forecast/health`

当前 runtime 的最小 forecast progression 健康读面。

返回：

- `status`
  - `ok`
  - `degraded`
  - `critical`
- `loop`
  - `enabled`
  - `interval_seconds`
  - `active`
  - `run_count`
  - `success_count`
  - `error_count`
  - `consecutive_error_count`
  - `last_started_at`
  - `last_completed_at`
  - `last_result_count`
  - `last_error`
- `forecast`
  - `task_count`
  - `active_fast_task_count`
  - `overdue_fast_task_count`
  - `unresolved_daily_task_count`
  - `settlement_batch_count`
  - `open_settlement_batch_count`
  - `anchor_ready_batch_count`
  - `pending_anchor_batch_count`
- `alerts[]`
  - `code`
  - `severity`
  - `message`

说明：

- `loop` 反映当前进程内 forecast progression loop 的运行状态
- runtime 启动时会先执行一次 startup progression pass，然后在启用时进入后台 loop
- 当前最小 alert 规则：
  - `forecast_progression_loop_errors`
  - `overdue_forecast_tasks`
- 当前阈值来自环境变量：
  - `CLAWCHAIN_FORECAST_PROGRESSION_LOOP_ERROR_ALERT_THRESHOLD`

## 4.23 `GET /admin/anchor-jobs/action-queue`

当前 runtime 的最小 operator triage 读面。

返回：

- `count`
- `items[]`
  - `action_type`
    - `review_failed_anchor`
    - `review_stale_pending_confirmation`
  - `severity`
  - `anchor_job_id`
  - `settlement_batch_id`
  - `state`
  - `tx_hash`
  - `last_broadcast_at`
  - `updated_at`
  - `age_seconds`
  - `failure_reason`

说明：

- 该接口只输出需要 operator 处理的 anchor jobs
- `anchor_failed` 会进入 `review_failed_anchor`
- 超过 `CLAWCHAIN_ANCHOR_PENDING_CONFIRMATION_WARNING_SECONDS` 的 pending confirmation 会进入 `review_stale_pending_confirmation`
- 当前只是 read-only 队列，不会自动重试、自动改状态或自动重播交易
- operator 当前的最小 follow-up 是：
  - failed job -> `POST /admin/anchor-jobs/{id}/retry-broadcast-typed` 或 `.../retry-broadcast-fallback`
  - stale pending -> `POST /admin/anchor-jobs/{id}/confirm-chain`

## 4.24 `GET /admin/chain/preflight`

当前 runtime 的最小链路就绪检查面。

返回：

- `adapter_version`
- `chain_id`
- `node_rpc`
- `binary`
  - `configured`
  - `resolved_path`
  - `available`
- `keyring`
  - `backend`
  - `configured_dir`
  - `normalized_dir`
  - `exists`
- `source_key`
  - `name`
  - `address`
  - `ok`
  - `error?`
- `target_address`
- `target_mode`
  - `configured`
  - `self_transfer`
- `rpc`
  - `reachable`
  - `status_url`
  - `latest_block_height?`
  - `network?`
  - `moniker?`
  - `error?`
- `ready`
- `warnings[]`

说明：

- 该接口只检查 fallback broadcast 的 operator 前置条件，不检查真实链模块语义
- `ready = true` 的条件是：
  - binary 可执行
  - source key 可解析
  - target address 可确定
  - RPC `status` 可访问
- 该接口是当前 runtime 对旧 `doctor` 的最小替代，不代表最终链上 health model

## 4.25 `POST /admin/anchor-jobs/{anchor_job_id}/retry-broadcast-typed`

当前 runtime 的最小 failed-anchor remediation 写面。

返回：

- `previous_anchor_job_id`
- `new_anchor_job_id`
- `settlement_batch_id`
- `broadcast_mode`
- `anchor_job_state`
- `broadcast_status`
- `tx_hash`
- `plan_hash`
- `account_number`
- `sequence`
- `attempt_count`
- `broadcast_method`

说明：

- 只允许当前状态为 `anchor_failed` 的 anchor job 调用
- 内部执行链路是：
  - `retry_anchor_settlement_batch`
  - `submit_anchor_job`
  - `broadcast_chain_tx_typed`
- 旧 failed job 会保留用于审计；batch 的 `anchor_job_id` 会切到新的 active job
- 如果同一秒内重发导致 ID 冲突，runtime 会给新 job 追加递增后缀，避免覆盖旧 job

## 4.26 `POST /admin/anchor-jobs/{anchor_job_id}/retry-broadcast-fallback`

与 `retry-broadcast-typed` 相同，但最终广播链路改为 fallback CLI path：

- `clawchaind tx bank send ... --note anchor:v1:...`

其余返回字段和状态语义保持一致。

---

## 4.25 Poker MTT Phase 2 load / artifact contract

Poker MTT 的万人 MTT 初期会出现约 2,000 桌并发完成手牌和 20k 级别 reward projection 行数。Phase 2 的 harness contract 是：

- completed hand 一手结束后进入 hand-history ingest，不按单个 action 入库
- `POST /admin/poker-mtt/reward-windows/build` 的正常响应不得返回 20k 条 `miner_reward_rows`
- reward window 主 projection artifact 只保留：
  - `projection_root`
  - `miner_reward_rows_root`
  - `budget_root`
  - `aggregation_policy_version`
  - `budget_disposition`
  - `artifact_page_count`
  - `artifact_pages[]`，每个 page 只含 `page_index / row_count / page_root`
- 每个 miner reward page 单独保存为 artifact：
  - `kind = poker_mtt_reward_window_projection_page`
  - `id = art:reward_window:{reward_window_id}:poker_mtt_projection:miner_rewards:{page_index}`
  - `payload_json.miner_reward_rows[]` 是该页完整 rows
- small window 可以保留 inline rows，但超过 configured page size 后必须转为 page refs

`POST /admin/poker-mtt/reward-windows/build` 额外返回的 Phase 2 摘要字段：

```json
{
  "artifact_page_count": 4,
  "miner_reward_rows_root": "sha256:...",
  "budget_root": "sha256:...",
  "aggregation_policy_version": "capped_top3_mean_v1",
  "projection_artifact_id": "art:reward_window:rw_...:poker_mtt_projection"
}
```

本地 load contract：

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_load_contract.py
bash scripts/poker_mtt/run_phase2_load_check.sh --players 30 --local
```

`run_phase2_load_check.sh --local` 是 offline synthetic check，不依赖 donor game server、Redis 或 WebSocket。它必须覆盖：

- 30-player smoke MTT
- 300-player medium field shape
- 20k-player synthetic reward projection paging
- 2,000-table early-stage hand-ingest burst shape

这个 local check 只证明 projection/page contract 的形状，不证明 production reward-window path。Phase 2 production harness 还必须单独覆盖 DB-backed `POST /admin/poker-mtt/reward-windows/build`、bounded query count、no N+1 final-ranking/rating lookup、真实 metric/log emission，以及 donor sidecar 30-player non-mock play-to-finish gate。

Phase 3 production-readiness 进一步要求：

- 20k check 必须走真实 Postgres-backed admin endpoint，不再只走 offline helper。
- reward-window build 主路径 SQL statements under 30；unchanged rebuild under 5 and no artifact rewrites。
- automatic reconcile 必须走 bounded closed-window query，不能调用全量 `list_poker_mtt_results()` 后内存分组。
- settlement batch/admin response 不能通过 `anchor_payload_json` 重新内联 20k `miner_reward_rows`；默认只返回 summary/root/page refs。
- external settlement query 必须能通过 gRPC/gateway/CLI 读取 stored anchor state，并让 mining-service 完成 typed full-field confirmation。
- Phase 3 Task 6 已补 `x/settlement` gRPC/gateway/CLI query 以及 mining-service confirmation-state persistence；20k settlement anchor rows 进入 `settlement_anchor_miner_reward_rows_page` artifacts，admin/list response 仍需保持 < 256 KB。
- 30-player non-mock sidecar gate 必须成为 hard assertion，不再只记录 smoke summary。2026-04-18 Task 8 已在 `non_mock_play_harness.py --until-finish` 中加入 `validate_finish_summary()`。
- `make test-poker-mtt-phase3-ops` 是本地 Phase 3 ops gate：sidecar retry tests、load contract tests、Phase 3 DB load check。
- `make test-poker-mtt-phase3-fast` 是合并前 fast gate：Go authadapter/Poker MTT/settlement/reputation packages，加 mining-service / poker_mtt Python contract tests。
- `make test-poker-mtt-phase3-heavy` 是 staging/manual gate：20k DB load、30-player non-mock WS play-to-finish、local-chain settlement query receipt。

Phase 3 artifact locations:

```text
artifacts/poker-mtt/phase3/db-load-20k.log
artifacts/poker-mtt/phase3/non-mock-30-finish-summary.json
artifacts/poker-mtt/phase3/local-run-log-check.json
artifacts/poker-mtt/phase3/settlement-anchor-query-receipt.json
```

Expected evidence inside those artifacts:

- 20k reward-window response under 256 KB
- exactly 4 reward-row page artifacts at 5,000 rows per page
- SQL count / rebuild / bounded reconcile assertions from `test_poker_mtt_phase3_db_load.py`
- RSS or peak-memory sample from the load contract
- 30 joined users, 30 current-ranking receipts, users sending legal chip actions, 1 survivor, 29 eliminated, 0 pending
- settlement query response matching settlement batch id, canonical root, anchor payload hash, lane, policy, reward roots, reputation delta root, and terminal confirmation state

`artifacts/` is ignored by git. Attach these files to release review or staging run records; do not commit local evidence blobs.

Canonical Phase 3 spec: `docs/POKER_MTT_PHASE3_PRODUCTION_READINESS_SPEC.md`

最小 observability fields：

```text
poker_mtt.hand_ingest.count
poker_mtt.hand_ingest.conflict_count
poker_mtt.hud.project.duration_ms
poker_mtt.reward_window.query.duration_ms
poker_mtt.reward_window.selected_count
poker_mtt.reward_window.omitted_count
poker_mtt.reward_window.artifact_page_count
poker_mtt.mq.lag
poker_mtt.mq.dlq_count
poker_mtt.settlement_anchor.confirmation_state
```

这些字段名只是 contract。production harness 必须证明它们被真实 metrics/log sink 发出，不能只靠常量或文档声明通过。

## 5. Public Write APIs

### Canonical signing payloads

Alpha prototype 目前锁定以下签名 preimage，字段使用 ASCII `|` 连接后做 `SHA256`：

- commit:
  - `task_run_id | commit_hash | nonce | miner_id | request_id`
- reveal:
  - `task_run_id | p_yes_bps | nonce | miner_id | request_id`

其中：

- `nonce` 在 forecast lane 中作为 reveal nonce / commit salt 复用
- `request_id` 用于幂等与重放保护
- `miner_id` 当前等于 miner address

后续如果引入独立 auth nonce，需要版本化 `schema_version`，不能 silent change。

## 5.1 `POST /v1/task-runs/{task_run_id}/commit`

请求：

```json
{
  "request_id": "req_123",
  "task_run_id": "tr_123",
  "miner_id": "m_123",
  "economic_unit_id": "eu_123",
  "commit_hash": "0xabc...",
  "nonce": "random_123",
  "client_version": "skill-v0.4.0",
  "signature": "0xsig..."
}
```

响应关键字段：

```json
{
  "object_id": "sub_123",
  "lane": "forecast_15m",
  "server_time": "2026-04-09T09:00:02Z",
  "trace_id": "trc_123",
  "data": {
    "ledger_id": "sl_123",
    "accepted_at": "2026-04-09T09:00:02Z",
    "server_cutoff": "2026-04-09T09:00:03Z",
    "validation_status": "accepted"
  }
}
```

## 5.2 `POST /v1/task-runs/{task_run_id}/reveal`

请求：

```json
{
  "request_id": "req_124",
  "task_run_id": "tr_123",
  "miner_id": "m_123",
  "economic_unit_id": "eu_123",
  "p_yes_bps": 6420,
  "nonce": "random_123",
  "schema_version": "v1",
  "signature": "0xsig..."
}
```

响应关键字段：

```json
{
  "object_id": "sub_124",
  "lane": "forecast_15m",
  "server_time": "2026-04-09T09:00:09Z",
  "trace_id": "trc_124",
  "data": {
    "ledger_id": "sl_124",
    "accepted_at": "2026-04-09T09:00:09Z",
    "server_cutoff": "2026-04-09T09:00:13Z",
    "pack_hash": "sha256:...",
    "validation_status": "accepted",
    "reward_eligibility": "eligible"
  }
}
```

可能的 `reward_eligibility`：

- `eligible`
- `audit_only`
- `ineligible`

## 5.3 `POST /v1/tournaments/{tournament_id}/actions`

请求：

```json
{
  "request_id": "req_200",
  "tournament_id": "tour_123",
  "table_id": "tbl_3",
  "hand_id": "hand_88",
  "phase_id": "phase_wager_1",
  "seat_alias": "A7",
  "action_type": "raise_small",
  "action_amount_bucket": "bb_plus_1",
  "expected_state_seq": 184,
  "signature": "0xsig..."
}
```

响应关键字段：

```json
{
  "object_id": "aa_123",
  "lane": "arena_rated",
  "server_time": "2026-04-09T09:01:42Z",
  "trace_id": "trc_200",
  "data": {
    "accepted_at": "2026-04-09T09:01:42Z",
    "state_seq": 185,
    "validation_status": "accepted"
  }
}
```

---

## 6. Write-path conflict contract

## 6.1 duplicate `request_id`

- 返回第一次写入结果
- 不重复入账

## 6.2 同一经济单位同题多 reveal

- 最早有效 reveal 保留 `eligible`
- 后续 reveal 记为 `audit_only`
- 同时产出 risk signal

## 6.3 Arena stale action

- `expected_state_seq` 不匹配时拒绝
- 不做“延迟执行”

## 6.4 Late submissions

- 只认 `server_cutoff`
- 超时直接返回 `late_submission`

---

## 7. Admin APIs

Alpha 最小 admin 面：

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
- `GET /admin/anchor-jobs/action-queue`
- `GET /admin/chain/preflight`
- `GET /admin/anchor-jobs/{id}/chain-tx-plan`
- `POST /admin/anchor-jobs/reconcile-chain`
- `POST /admin/anchor-jobs/{id}/broadcast-fallback`
- `POST /admin/anchor-jobs/{id}/broadcast-typed`
- `POST /admin/anchor-jobs/{id}/confirm-chain`
- `POST /admin/anchor-jobs/{id}/retry-broadcast-fallback`
- `POST /admin/anchor-jobs/{id}/retry-broadcast-typed`
- `POST /admin/anchor-jobs/{id}/mark-anchored`
- `POST /admin/anchor-jobs/{id}/mark-failed`
- `POST /admin/risk-decisions/{id}/override`
- `POST /admin/read-models/rebuild`

所有 admin 响应必须带：

- `operator_id`
- `authority_level`
- `trace_id`
- `override_log_id`

当前 runtime 最小实现：

- `POST /admin/reward-windows/{id}/rebuild`
  - 重算当前 membership 下的 `task_count / submission_count / miner_count / total_reward_amount`
  - 不做 retroactive mutation beyond current persisted membership
- `POST /admin/settlement-batches/{id}/retry-anchor`
  - 将 batch 推进到 `anchor_ready`
  - 生成 canonical `anchor_payload_json/hash`
  - 清空当前 `anchor_job_id`
- `POST /admin/settlement-batches/{id}/submit-anchor`
  - 创建最小 `anchor_job`
  - 将 batch 推进到 `anchor_submitted`
  - 不执行真实链提交
- `GET /admin/anchor-jobs`
  - 返回当前持久化 `anchor_job` 列表
- `GET /admin/chain/health`
  - 返回当前进程内 anchor reconcile loop metrics
  - 返回当前持久化 anchor job 的 pending / stale / failed / anchored 摘要
  - 返回 alerts 聚合后的 `ok / degraded / critical` 状态
- `GET /admin/anchor-jobs/action-queue`
  - 返回当前需要 operator 处理的 failed / stale anchor jobs
  - 当前是 read-only triage surface，不执行 remediation
- `GET /admin/chain/preflight`
  - 返回当前 typed / fallback broadcaster 共用的 binary / keyring / rpc readiness
  - 返回 signing readiness：
    - `mode`
    - `account_number`
    - `next_sequence`
- `GET /admin/anchor-jobs/{id}/chain-tx-plan`
  - 构造最小 `build_only` chain tx plan
  - 消费当前 batch 的 canonical payload 和 `canonical_root`
- `POST /admin/anchor-jobs/reconcile-chain`
  - 批量扫描当前 `anchor_submitted + broadcast_tx_hash` jobs
  - 对每个 job 复用 `confirm-chain` 逻辑
  - 返回本轮 sweep 的确认结果列表
- `POST /admin/anchor-jobs/{id}/broadcast-typed`
  - 通过 `clawchaind tx settlement anchor-batch -> tx sign -> tx broadcast` 执行 typed Msg 广播
  - 消费当前 `future_msg / typed_tx_intent / canonical_root`
  - `account_number` 由配置或 genesis 解析
  - `sequence` 由 `message.sender` 的 committed tx count 推导
  - 成功后记录 `tx_hash`
  - receipt artifact 额外记录 `account_number / sequence / attempt_count / broadcast_method`
  - 不自动转成 `anchored`
- `POST /admin/anchor-jobs/{id}/confirm-chain`
  - 通过已持久化 `broadcast_tx_hash` 查询链上 tx 结果
  - `confirmed` 时自动推进到 `anchored`
  - `failed` 时自动推进到 `anchor_failed`
  - `pending` 时保持 `anchor_submitted`
  - confirmation artifact 额外记录 `chain_height / tx_code / tx_raw_log`
- `POST /admin/anchor-jobs/{id}/retry-broadcast-typed`
  - 只允许 failed anchor job 调用
  - 内部执行 `retry-anchor -> submit-anchor -> broadcast-typed`
  - 保留旧 failed job，新建 replacement anchor job 并回写 batch pointer
- `POST /admin/anchor-jobs/{id}/retry-broadcast-fallback`
  - 只允许 failed anchor job 调用
  - 内部执行 `retry-anchor -> submit-anchor -> broadcast-fallback`
  - 保留旧 failed job，新建 replacement anchor job 并回写 batch pointer
- `POST /admin/anchor-jobs/{id}/broadcast-fallback`
  - 通过 `clawchaind` CLI 执行兜底广播
  - 当前默认走 offline sign + real broadcast
  - `account_number` 由配置或 genesis 解析
  - `sequence` 由 `message.sender` 的 committed tx count 推导
  - 若未配置 `anchor_to_address`，默认走 self-transfer memo anchor
  - 成功后记录 `tx_hash`
  - receipt artifact 额外记录 `account_number / sequence / command`
  - 不自动转成 `anchored`
- `POST /admin/anchor-jobs/{id}/mark-anchored`
  - 将 `anchor_job` 与所属 batch 推进到 `anchored`
- `POST /admin/anchor-jobs/{id}/mark-failed`
  - 将 `anchor_job` 与所属 batch 推进到 `anchor_failed`

---

## 8. 错误语义

标准错误响应：

```json
{
  "error_code": "late_submission",
  "message": "reveal arrived after server cutoff",
  "trace_id": "trc_124",
  "retryable": false,
  "details": {
    "server_cutoff": "2026-04-09T09:00:13Z"
  }
}
```

Alpha 必备错误码：

- `validation_error`
- `signature_invalid`
- `nonce_invalid`
- `late_submission`
- `task_voided`
- `task_degraded`
- `audit_only_submission`
- `economic_unit_duplicate`
- `state_seq_mismatch`
- `tournament_no_multiplier`
- `reward_on_hold`

---

## 9. Event Envelope

所有 outbox 事件统一 envelope：

```json
{
  "event_id": "evt_123",
  "aggregate_type": "task_run",
  "aggregate_id": "tr_123",
  "stream_key": "forecast_15m:tr_123",
  "lane": "forecast_15m",
  "season_id": "s_2026_w15",
  "reward_window_id": "rw_123",
  "event_type": "task_run.state_changed",
  "event_version": "v1",
  "occurred_at": "2026-04-09T09:00:00Z",
  "causation_id": "cmd_123",
  "correlation_id": "trc_123",
  "producer": "scheduler",
  "payload_hash": "sha256:...",
  "payload_uri": "s3://...",
  "visibility": "internal"
}
```

---

## 10. 核心事件 payload

## 10.1 `task_run.state_changed`

payload 至少包含：

- `from_state`
- `to_state`
- `trigger_reason`
- `policy_bundle_version`
- `barrier_id`

## 10.2 `submission.commit.accepted`

- `submission_id`
- `task_run_id`
- `miner_id`
- `economic_unit_id`
- `accepted_at`

## 10.3 `submission.reveal.accepted`

- `submission_id`
- `task_run_id`
- `miner_id`
- `economic_unit_id`
- `p_yes_bps`
- `reward_eligibility`

## 10.4 `outcome.final.computed`

- `task_run_id`
- `commit_close_ref_price`
- `end_ref_price`
- `outcome_y`
- `outcome_revision`

## 10.5 `score.revision.appended`

- `aggregate_id`
- `scorer_revision`
- `edge_score`
- `fast_ticket`
- `copy_cap`
- `direction_bonus`

## 10.6 `risk.decision.applied`

- `subject_type`
- `subject_id`
- `risk_state_before`
- `risk_state_after`
- `discount_applied`
- `maturity_action`
- `review_required`

## 10.7 `reward_window.finalized`

- `reward_window_id`
- `forecast_task_run_ids`
- `daily_anchor_snapshot_id`
- `arena_multiplier_snapshot_id`
- `carry_forward_reason`

## 10.8 `tournament.completed`

- `tournament_id`
- `rated_or_practice`
- `field_size`
- `bot_present`
- `time_cap_finish`
- `no_multiplier`

---

## 11. 契约不变量

- public read models 只能读 finalized 或 explicitly labeled provisional data
- `public ELO` 不得出现在任何 reward calculation payload
- `daily_anchor` 不得直接写入 `fast_direct_score`
- `arena_practice` 不得写入 multiplier
- `reward_window` 必须显式记录 membership
- replay proof 必须能追溯到：
  - `policy_bundle_version`
  - `artifact_ref`
  - `outcome_revision`
  - `score_revision`

---

## 12. Alpha day-1 最小契约集

真正必须先稳定的只有：

- `task-runs/active`
- `forecast task run detail`
- `daily task run detail`
- `commit`
- `reveal`
- `tournament standing/live table`
- `miner status`
- `replay proof`
- `task_run.state_changed`
- `submission.reveal.accepted`
- `outcome.final.computed`
- `score.revision.appended`
- `risk.decision.applied`
- `reward_window.finalized`

其他契约可以先存在文档中，但不必在 day-1 一次性做满。

补充说明：

- 当前 runtime 的 `daily task run detail` 已可参与统一 `commit / reveal`
- 当前 runtime 只在 daily 结算后更新 `model_reliability`
- 当前 runtime 不发放 daily direct reward

# Poker MTT Phase 2 Harness Specs

**日期**: 2026-04-17
**状态**: Phase 2 harness spec + P1 code gates closeout；不是 production rollout approval
**范围**: `poker mtt` 独立 skill-game mining lane
**相关文档**:
- `docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md`
- `docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md`
- `docs/POKER_MTT_SIDECAR_INTEGRATION.md`
- `docs/HARNESS_API_CONTRACTS.md`
- `docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2.md`

---

## 1. 评审结论

本文件记录两轮 6-agent review 后冻结的 Phase 2 harness 口径。

当前代码已经形成一条有价值的 local beta slice:

- completed hand event 的幂等 ingest 合同
- hand-history / HUD / hidden eval / final ranking / reward window / settlement batch 的本地链路
- Go sidecar / finalizer / projector 的基础结构
- `x/settlement` root registry 的本地 keeper 测试
- 30-player smoke、300-player shape、20k synthetic projection paging 的离线检查

2026-04-17 closeout 已把 Phase 2 最容易误伤 reward/settlement 的 P1 code gates 落成测试和实现:

- `accepted_degraded` 不再自动 reward-ready；缺 hidden eval 默认 audit-only
- legacy/admin apply 不能靠 caller-provided hidden / consistency / spoofed economic unit 进入 reward-ready path
- reward-window selection 按 locked range、evidence、eligibility、policy/evaluation version 过滤
- settlement confirmation 区分 tx-only 和 typed state；adapter / keeper 拒绝 full-field metadata drift
- `/admin/*` 在 auth enabled 时统一 bearer 保护；非本地默认打开 admin auth
- Go final-ranking projector client 支持 bearer token、retryable backoff，并把 401/403 视为非重试配置错误

但当前仍不能称为 reward-bearing production ready。Phase 2 之后还缺少几类 production 硬门槛:

- 20k 测试还不是 DB-backed production reward-window service path
- MQ checkpoint / replay / DLQ / lag 还只是设计，不是实现
- donor `lepoker-auth` 的 MTT finalization / scheduler / hand history parity 不能过度宣称
- durable reward-bound miner identity / local mock identity 非奖励化还需要 production adapter 证明

因此本文件的最终口径是:

**Phase 2 可以继续作为 gated local beta / harness construction phase 推进；自动发奖和 poker settlement anchoring 继续默认关闭；只有本文件的 acceptance gates 通过后，才能把 `poker_mtt_daily` / `poker_mtt_weekly` 作为 reward-bearing rollout 打开。**

---

## 2. Non-goals

Phase 2 不做:

- raw hand history 上链
- per-hand / per-game on-chain write
- 单场即时大奖
- public ELO 直接作为正向 reward weight
- `x/reputation` 直接写入
- donor Java `MttService` / `HandHistoryService` monolith port
- RocketMQ consumer 直接变 scoring engine
- wallet / ticket / clan / private room / gold coin / bounty / rebuy / add-on / dynamic prize pool 迁移
- high-value mainnet rewards 默认打开

`x/reputation` 的正确接入点仍是后续 window-level `reputation_delta`，不是单场 hidden eval、raw HUD 或单场 total score。

---

## 3. Canonical Terms And Lanes

Poker MTT 是独立 lane，不混入 `arena`。

允许的 Poker MTT reward lanes:

- `poker_mtt_daily`
- `poker_mtt_weekly`

必须随每个 reward window / settlement batch 显式携带:

- `lane`
- `policy_bundle_version`
- `window_start_at`
- `window_end_at`
- reward budget source
- score formula version
- evidence readiness policy
- accepted-degraded allowlist
- correction / supersession policy
- canonical roots and page roots

`policy_bundle_version` 不是展示字段。它必须参与 reward-window row selection、projection root、settlement batch payload 和 chain confirmation。

---

## 4. Evidence Readiness Matrix

| Component | Reward-ready 要求 | Degraded 是否可进 reward | Artifact/root | Storage source |
|---|---|---:|---|---|
| final ranking | canonical final ranking 已保存、rank state 可解释、refs 匹配 | no-show / waiting 只进 archive，不进 reward | `final_rankings_root` | donor Redis + registration snapshot -> Go finalizer -> mining-service |
| hand history | completed-hand event 幂等 ingest，`hand_id + version + checksum` 稳定 | policy 显式允许前不能进 reward | `hand_history_root` | SQL/local beta；DynamoDB 是生产候选 adapter |
| short-term HUD | 可从 hand events replay，root 稳定 | 缺失时 hidden eval 不可 reward-ready | `short_term_hud_root` | HUD projector |
| long-term HUD | 用于 consistency / risk / multiplier 慢变量 | 缺失时 consistency component 必须 disabled 或 audit-only | `long_term_hud_root` | HUD/rating projector |
| hidden eval | service-owned row，不能由 admin/client payload 注入 | 缺失默认不进 reward | `hidden_eval_root` | hidden eval service |
| rating snapshot | public display / audit / multiplier input | 不直接发币 | `rating_snapshot_root` | rating projector |
| multiplier snapshot | 慢变量，窗口级审计 | 不替代 evidence gate | `multiplier_snapshot_root` | multiplier projector |
| consumer checkpoint | replay watermark 明确，lag 不 stale | stale 时 block reward finalization | `consumer_checkpoint_root` | MQ/checkpoint worker |
| settlement state | typed chain query 全字段匹配 | fallback memo 只能 degraded，不等同 anchored | `anchor_payload_hash` | `x/settlement` |

`accepted_degraded` 不是自动 reward-ready。它只能表示“有可审计降级原因”。是否能进入 reward，必须由当前 policy 的 degraded allowlist 决定，并且 degraded reason 必须进入 projection root。

---

## 5. Review Findings To Preserve

这些 findings 已经过第二波复核，必须进入 harness backlog。

### 5.1 Reward / Economic Correctness

P1 blockers:

- `accepted_degraded` 当前可能绕过 hidden eval requirement，进入 locked / reward-window path。
- legacy/admin `apply` 路径虽然不再信任 caller hidden score，但仍信任 caller `tournament_result_score` / `consistency_input_score`。
- reward-window repository 接收 `policy_bundle_version`，但 Fake/Postgres selection 没有按 policy/evaluation version 过滤。
- Poker MTT `economic_unit_id` 仍可能来自 donor row / caller payload，而不是服务端 miner binding。

P2 gaps:

- `0.20 consistency` component 目前没有 service-owned projector；如果继续为 `0.0`，必须在 policy 中显式标记 component unavailable。
- public rating / ELO 当前不直接发币，这是正确边界，不能误改成 reward weight。

Harness acceptance:

- `accepted_degraded` + missing hidden eval must stay audit-only unless policy explicitly allows that degraded kind.
- legacy/admin payload cannot create reward-ready scores; score must be recomputed from canonical final ranking and service-owned evidence, or row remains audit-only.
- reward-window query must filter by lane, locked range, evidence state, eligibility, and policy/evaluation version.
- stored `economic_unit_id` must come from server-side miner/economic-unit binding.
- consistency component must be service-owned, policy-disabled, or block reward readiness.

### 5.2 Settlement / Chain

P0/P1 blockers:

- `x/settlement` query registration is currently not externally wired; direct keeper tests do not prove gRPC/gateway/CLI query.
- chain confirmation can still promote a batch to `anchored` from tx success alone.
- typed confirmation compares too few fields: batch id, canonical root, payload hash are not enough.
- duplicate anchors with same root/hash but drifted lane/policy/window/roots/amount/submitter can be treated as idempotent.

Harness acceptance:

- external `x/settlement` query round trip must work through generated gRPC client, gateway, and CLI.
- typed confirmation must compare:
  - `settlement_batch_id`
  - `canonical_root`
  - `anchor_payload_hash`
  - `lane`
  - `policy_bundle_version`
  - `window_start_at`
  - `window_end_at`
  - reward roots
  - row/page roots
  - total amount / count metadata
  - submitter / authorization context where applicable
- tx success without typed state must remain `anchor_submitted` or `degraded`, not `anchored`.
- duplicate submit with identical full metadata is idempotent; same id with any metadata drift is conflict.

### 5.3 Scale / Load / Ops

P1 blockers:

- current 20k load check exercises offline projection paging, not production reward-window service path.
- production reward-window build has per-result final-ranking lookups and per-miner rating snapshot lookups.
- automatic reconcile scans all historical Poker MTT results before grouping windows.
- observability is currently a field/constant contract, not emitted metrics/logs.

P2 gaps:

- Go projector classifies retryable errors but performs only one request.
- 30-player non-mock play-to-finish harness exists, but is not a reproducible acceptance gate.

Harness acceptance:

- Postgres-backed 20k reward-window build through `POST /admin/poker-mtt/reward-windows/build`.
- Response body remains bounded; large rows only in page artifacts.
- Query count, latency, memory, artifact page count, root reconstruction, and idempotent rebuild must be asserted.
- automatic reconcile must use bounded/indexed closed-window query, not full historical scan.
- projector apply must retry 429/503/network with backoff and not retry 400/401/403.
- one-command local 30-player non-mock WS join/action-to-finish gate must produce final standings with exactly one survivor and 29 eliminated/finished records.

### 5.4 Auth / Admin / Identity

P1 blockers:

- admin mutation auth is default-off and reward-critical endpoints are only protected if explicitly configured.
- Go `Principal.PokerMTTRewardEligible()` exists, but mining-service reward selection does not enforce equivalent durable identity binding.
- projector client posts to admin endpoint without bearer auth, so it only works if admin auth stays open.
- donor `token_verify` proves user identity, not ClawChain miner ownership or reward-bound economic unit.

Harness acceptance:

- non-local/default deployment must reject missing admin auth for Poker MTT mutation endpoints.
- all reward/settlement-critical admin POSTs must reject missing/wrong bearer token when auth is enabled.
- projector must send configured bearer token and treat 401/403 as non-retryable config/auth failures.
- `claw1local-*`, synthetic identities, and donor responses without explicit miner/economic-unit binding must not become reward-bearing.
- local mock auth remains valid for harness participation only.

### 5.5 Donor Parity

P1 blocker:

- Redis-only finalization can miss waiting/no-show entrants. Donor `lepoker-auth` final ranking merges Redis ranking with DB registration/waiting state and appends waiting users.

P2 gaps:

- confirmed donor MTT raw hand ingest path is `RecordListener` / `RecordCalculateListener` -> `HandHistoryService`, not a proven `DynamoDBUserHistoryService` MTT ingest path.
- donor MQ path has RocketMQ + DB-backed `bizId` idempotency; ClawChain has hand id/version/checksum, but no production MQ consumer/checkpoint/DLQ/lag harness yet.
- donor scheduler handles start windows, failed-to-start, late-reg transition, notices, and stale hand-history detection; current Go orchestrator is a sidecar/session adapter, not scheduler parity.

Harness acceptance:

- finalizer must merge Redis live state plus registration/waitlist snapshot.
- registered-but-never-joined users must appear in final archive as waiting/no-show and be reward-ineligible.
- MQ replay harness must cover crash-after-write, out-of-order versions, malformed event, checksum conflict, DLQ/conflict storage, lag/watermark, and deterministic replay roots.
- scheduler harness must cover idempotent start, start failure/no callback, stuck running tournament with stale hand watermark, and explicitly deferred late-reg/notice behavior.

### 5.6 Corrections

P1/P2 gap:

- correction persistence is currently upsert-like. For anchored or externally referenced evidence, correction history must be append/supersede, not in-place mutation.

Harness acceptance:

- anchored roots immutable.
- correction id reuse with changed payload is conflict.
- superseding correction points to previous correction id and emits a new root/version.
- reward-window rebuild after correction creates a new superseding window/batch; it does not mutate an anchored root.

---

## 6. Harness Gates

### G0 - Docs Consistency

Pass criteria:

- No doc claims Phase 2 is production complete.
- Product docs say `local beta slice` and `production harness gates pending`.
- `poker_mtt_daily` and `poker_mtt_weekly` appear in harness lane contracts.
- `run_phase2_load_check.sh --local` is described as offline synthetic coverage only.
- donor Dynamo wording says `HandHistoryService.upsertHandHistory()` is the confirmed MTT raw hand path; DynamoDB user history is a production/read-model candidate unless a specific MTT call site is proven.

### G1 - Unit And Contract Baseline

Pass criteria:

```bash
PYTHONPATH=mining-service pytest -q \
  tests/mining_service/test_poker_mtt_history.py \
  tests/mining_service/test_poker_mtt_hud.py \
  tests/mining_service/test_poker_mtt_evidence.py \
  tests/mining_service/test_poker_mtt_reward_gating.py \
  tests/mining_service/test_forecast_engine.py \
  tests/mining_service/test_chain_adapter.py \
  tests/mining_service/test_poker_mtt_load_contract.py \
  tests/mining_service/test_poker_mtt_phase2_e2e.py

go test ./authadapter ./pokermtt/... ./x/settlement/... -v
```

These tests are necessary but not sufficient for production rollout.

### G2 - Reward-Readiness Service Contract

Pass criteria:

- `accepted_degraded` without hidden eval stays audit-only.
- legacy/admin score injection cannot change reward-ready total score.
- policy version mismatch excludes otherwise-valid rows from the reward window.
- local/synthetic miner identity cannot enter reward window without durable binding.
- final ranking archive can include waiting/no-show entrants while reward rows exclude them.

### G3 - Chain Settlement Contract

Pass criteria:

- `x/settlement` external query is wired and tested.
- typed confirmation checks full metadata.
- tx-only confirmation cannot mark typed anchored.
- duplicate anchor metadata drift fails.
- fallback memo is never equivalent to typed state confirmation.

### G4 - Load And Scale Contract

Pass criteria:

- 30-player non-mock WS explicit join/action-to-finish gate passes.
- 300-player DB-backed service path passes reward-window build with bounded response.
- 20k-player Postgres-backed reward-window build produces page artifacts, not inline rows.
- 2,000-table early burst shape covers hand ingest and finalizer inputs.
- automatic reconcile avoids full historical scans.
- query count, memory, and latency thresholds are asserted in staging.

Suggested initial thresholds:

- 20k reward window response body under 256 KB
- page size 5,000, exactly 4 page artifacts for 20k rows
- root reconstruction covers 20k rows exactly
- reward-window SQL statements under 30 for the main build path
- process RSS delta under 512 MB for local/staging gate
- idempotent rebuild does no rewrites and uses under 5 SQL statements when unchanged

These numbers are harness thresholds, not final production SLOs.

### G5 - MQ / HUD / Recovery Contract

Pass criteria:

- same hand id + same version + same checksum is idempotent.
- same hand id + same version + different checksum creates conflict/manual-review and blocks reward readiness.
- higher version supersedes lower version; stale lower version is ignored.
- crash after hand write but before checkpoint can replay without duplicate side effects.
- HUD projector replay from hand events produces stable manifest roots.
- consumer lag/watermark is exposed and blocks reward finalization when stale.
- malformed messages route to dead-letter/conflict storage with alertable reason.

### G6 - Auth / Abuse / Rollout Contract

Pass criteria:

- admin auth enabled in non-local harness.
- projector auth configured and tested.
- reward windows and settlement anchoring remain disabled by default.
- high-value rewards require explicit environment gate.
- local mock auth cannot become reward-bearing.
- `x/reputation` direct Poker MTT writes remain absent.

---

## 7. Implementation Order

Recommended next execution order:

1. Docs consistency: wire this spec into product/reward/harness docs.
2. Reward-readiness blockers:
   - policy filter
   - accepted-degraded handling
   - server economic unit
   - legacy/admin score recompute or audit-only
3. Admin/auth blockers:
   - default non-local admin protection
   - projector bearer token
   - durable reward-bound identity check
4. Settlement blockers:
   - generated query service/gateway/CLI
   - full-field typed confirmation
   - duplicate metadata drift rejection
5. Scale blockers:
   - bulk final-ranking/miner/rating snapshot lookups
   - bounded automatic reconcile
   - production-path 20k Postgres gate
6. Donor parity blockers:
   - registration/waitlist snapshot merge
   - one-command 30-player non-mock finish gate
   - MQ checkpoint/replay/DLQ/lag harness
7. Observability:
   - real metric/log sink
   - emitted metrics tests
8. Correction append-only policy.

---

## 8. Rollout Rule

Before all P1 gates pass:

- `CLAWCHAIN_POKER_MTT_REWARD_WINDOWS_ENABLED` stays false by default.
- `CLAWCHAIN_POKER_MTT_SETTLEMENT_ANCHORING_ENABLED` stays false by default.
- Poker MTT rewards can be shown as simulated/provisional/internal only.
- Settlement anchor may be exercised in local/staging with fake or degraded state, but cannot be represented as reward-ready typed chain confirmation unless full-field query proof exists.

After all P1 gates pass:

- low-value internal reward window can be enabled in staging.
- typed anchor confirmation can be enabled only with external query proof.
- production reward rollout still needs separate release review, load evidence, and ops runbook.

---

## 9. Final Product Alignment

This spec keeps the original product design intact:

- no single-tournament jackpot as the main reward
- daily/weekly reward windows stay the primary economic surface
- hidden eval reduces solver/local edge, but remains private and service-owned
- public ELO/rating is display/matchmaking/risk context, not direct reward weight
- long-term reputation is delayed until window-level deltas are clean
- chain integration remains window-root anchoring, not raw gameplay settlement

The practical meaning is simple:

**Copy the stable donor structure, not the donor monolith. Keep rewards off until evidence, identity, policy, settlement, and scale gates are all real.**

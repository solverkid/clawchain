# Poker MTT Phase 3 Production Readiness Spec

**日期**: 2026-04-17
**状态**: Phase 3 spec after 6-agent xhigh review；不是 reward-bearing rollout approval
**范围**: `poker mtt` independent skill-game mining lane
**主线 commit**: Phase 2 closeout 已 fast-forward merge 并 push 到 `main` at `2cd78de`

相关文档:

- `docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md`
- `docs/POKER_MTT_PHASE2_HARNESS_SPECS.md`
- `docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md`
- `docs/POKER_MTT_SIDECAR_INTEGRATION.md`
- `docs/HARNESS_API_CONTRACTS.md`
- `docs/superpowers/plans/2026-04-17-poker-mtt-phase3-production-readiness.md`

---

## 1. Executive Decision

Phase 3 的定义不是“打开 poker MTT 主网奖励”，而是把 Phase 2 local beta 里已经跑通的 evidence-to-anchor 链路补成 production readiness gate。

在 Phase 3 所有 P0 gates 通过之前:

- `CLAWCHAIN_POKER_MTT_REWARD_WINDOWS_ENABLED` 继续默认关闭
- `CLAWCHAIN_POKER_MTT_SETTLEMENT_ANCHORING_ENABLED` 继续默认关闭
- `poker_mtt_daily` / `poker_mtt_weekly` 只能作为 staging、internal、provisional 或 simulated reward
- public ELO / public rating 不进入正向 reward weight
- `x/reputation` 不接单场结果、raw HUD、hidden eval 原始分或单场 total score

Phase 3 完成后，系统应当具备低价值 reward-bearing staging rollout 的资格。高价值 mainnet reward 仍需要单独 release review、load evidence 和 ops runbook。

---

## 2. Review Inputs And GitNexus Status

本 spec 综合了 6 个 `gpt-5.4 xhigh` review agents 的结论:

- Product/economics/reward design
- Mining-service data/evidence pipeline
- Go sidecar/finalizer/projector/authadapter
- Chain/settlement/reputation integration
- Security/auth/identity/admin boundaries
- Scale/ops/test harness

GitNexus was used for structural orientation across `clawchain` and `lepoker-auth`.

Important caveat: current MCP `clawchain` index points at `/Users/yanchengren/Documents/Projects/clawchain` and is stale relative to this isolated merged-main worktree. Therefore this document treats local files in the merged `main` worktree as source of truth, and uses GitNexus primarily to confirm existing high-level symbols and donor reference flows. `lepoker-auth` GitNexus is still useful for donor MTT/HUD/MQ architecture references, especially `MttService`, `MttUserService`, `HandHistoryService`, `RecordListener`, `RecordCalculateListener`, and DynamoDB/user-history read models.

---

## 3. Canonical Phase 3 Architecture

Phase 3 keeps the existing product architecture:

```mermaid
flowchart LR
  A["Donor gameserver runtime"] --> B["Go sidecar / WS / HTTP adapter"]
  B --> C["Go finalizer: Redis + registration/waitlist snapshot"]
  C --> D["Go projector: canonical final ranking contract"]
  D --> E["Mining service: evidence store and result projection"]
  E --> F["HUD / hidden eval / rating / multiplier snapshots"]
  F --> G["Daily / weekly reward_window"]
  G --> H["settlement_batch roots and page artifacts"]
  H --> I["x/settlement typed anchor"]
  I --> J["External query confirmation"]
  G --> K["window-level reputation_delta draft"]
```

Design boundaries:

- Donor runtime remains external. ClawChain copies stable contracts, not the Java monolith.
- Raw hand history remains off-chain and off-ledger; one completed hand is the durable event unit.
- Postgres remains the local beta truth for result/evidence/window state; DynamoDB is a production candidate adapter/read model for raw hand history, not the settlement source of truth.
- Chain integration anchors window roots and immutable artifact hashes, not per-hand or per-game state.
- Reputation is a long-term, window-level derivative after settlement proof, not a direct scoring input.

---

## 4. P0 Acceptance Gates

### G0 - Cross-Doc And Rollout Truth

Acceptance:

- Product docs, reward design, harness contracts, sidecar docs, and implementation plan all say Phase 3 is production readiness, not automatic production launch.
- Feature flags remain default-off.
- GitNexus staleness is recorded when reviews use local source as source of truth.
- A single Phase 3 plan file exists under `docs/superpowers/plans/`.

### G1 - Final Ranking And Donor Parity

Current blockers:

- Redis-only finalizer can miss registered/waiting/no-show users absent from runtime ranking keys.

Completed on 2026-04-18:

- Go projector JSON now has a golden cross-language fixture validated by Python `ApplyPokerMTTFinalRankingProjectionRequest`.
- The projection contract requires `schema_version`, `projection_id`, `source_mtt_id`, `standing_snapshot_id`, `standing_snapshot_hash`, `final_ranking_root`, and payload `locked_at`.
- Go projector carries donor final-ranking row fields needed by mining-service: snapshot status, standing status, player name, start chip, stand-up status, source rank metadata, zset score, and row create/update timestamps.
- `/admin/poker-mtt/final-rankings/project` uses payload `locked_at`, writes a `poker_mtt_final_ranking_projection` artifact marker, returns the existing projection for same `projection_id` and root, and returns 409 for same `projection_id` with a changed root.
- Go finalizer now accepts a separate registration/waitlist snapshot source, archives registration-only waiting/no-show users as reward-ineligible final-ranking rows, and exposes optional terminal/quiet, entrant count, alive/died/waiting count, and total chip drift barriers.

Acceptance:

- Add a cross-language golden fixture where Go emits projection JSON and Python validates it through the FastAPI schema.
- Add `projection_id` or equivalent idempotency key derived from `tournament_id + standing_snapshot_id + policy_bundle_version + final_ranking_root`.
- Same projection root returns the existing projection; changed root for same identity returns conflict.
- Server uses payload `locked_at` after validation, not request-time `now()`.
- Finalizer merges Redis live ranking plus registration/waitlist/no-show source data.
- Registered-but-never-joined and waiting users are archived with reward-ineligible rank states.
- Terminal-state or quiet-period watermark plus count/chip invariants must pass before projection.

### G2 - Evidence, MQ, Replay, And Artifact Immutability

Current blockers:

- `/admin/poker-mtt/hands/ingest` is direct ingest, not a production MQ consumer.
- Same hand/version checksum conflicts are returned to caller but not durably persisted as conflict/DLQ/replay-blocking rows.
- Evidence completeness is partly caller-driven via `accepted_degraded_kinds`.
- Hidden eval accepts request-provided `evidence_root` and is not policy/seed/baseline isolated.
- Evidence artifact IDs are stable per tournament/kind and can overwrite old roots.

Acceptance:

- Define MQ contract: topic/queue, consumer group, offset, donor `bizId`, message ID, hand identity, version, checksum, source timestamp, replay root.
- Add checkpoint table/model with watermark, lag, last message ID, consumer group, and replay state.
- Add conflict/DLQ table/model for malformed payloads, same-version checksum conflicts, stale lower versions, and crash recovery.
- Reward readiness is policy-owned: required component list, degraded allowlist, policy compatibility matrix, and stale checkpoint block are enforced by service code.
- Missing required hand/HUD/checkpoint/hidden-eval components cannot produce `complete`.
- Hidden eval rows are keyed by policy/evidence/seed/baseline and cannot unlock a projection under a different policy.
- Evidence artifacts become content-addressed or versioned so old roots remain retrievable after rebuilds.

2026-04-18 implementation status:

- Mining service now persists MQ checkpoints, conflicts, and DLQ rows with topic, queue, consumer group, offset, donor `bizId`, message ID, hand ID, replay root, lag, and source payload metadata.
- Hand ingest writes checkpoint state for inserted, duplicate, updated, stale, conflict, and DLQ outcomes. A replay after a crash between hand write and checkpoint write repairs the missing checkpoint via duplicate ingest.
- Same hand/version checksum drift is persisted as `manual_review` conflict and blocks evidence readiness.
- Malformed completed-hand payloads are persisted to DLQ and checkpointed as `dlq` instead of crashing the consumer loop.
- Evidence readiness is policy-owned: hand history and consumer checkpoint cannot be caller-degraded; hidden eval and short/long HUD can be policy-degraded but still produce `accepted_degraded`, not `complete`.
- Open conflicts, open DLQ rows, or nonzero checkpoint lag produce `evidence_state=blocked`.
- Evidence artifacts are content-addressed by manifest root so old roots remain retrievable after rebuilds.
- Remaining G2 production hardening: hidden eval still needs a stricter seed/baseline/evidence policy binding before high-value rollout.

### G3 - Auth, Admin, Identity, And Abuse Boundaries

Current blockers:

- Unset `CLAWCHAIN_ENV` defaults to local, so admin auth can fail open in production-like deployments.
- Go principal has `PokerMTTRewardEligible()`, but Python reward projection/window selection has no durable reward-bound identity gate.
- Donor `/token_verify` without miner binding can become `claw1local-*`, valid for harness participation but not production rewards.
- Admin mutation audit fields are self-declared payload, not resolved admin principal.
- Late economic-unit merges can leave duplicate submissions eligible.

Acceptance:

- Non-local/shared runtime startup fails without `CLAWCHAIN_ADMIN_AUTH_ENABLED=1` and non-empty admin token.
- Reward-critical admin POSTs log resolved admin principal and role, not self-attested `operator_id`.
- Final-ranking projector requires bearer auth for non-local targets; 401/403 are non-retryable config/auth failures.
- Add durable reward identity model: `miner_address`, `user_id`, `auth_source`, `economic_unit_id`, `reward_bound_at`, `expires_at`, `revoked_at`, `is_synthetic`, `is_reward_bound`.
- Reward projection and reward-window selection reject `claw1local-*`, donor-only, synthetic, expired, revoked, or unmapped identities.
- Duplicate enforcement uses refreshed server-side economic-unit state and backfills/demotes same-task duplicates when clusters merge late.

2026-04-18 implementation status:

- FastAPI startup now fails closed for non-local runtime without admin auth/token and for external bind without admin auth. Local/test external bind without auth requires an explicit insecure-local override.
- Admin route middleware resolves an audit principal from the bearer token or local harness context; risk override ignores self-attested `operator_id` / `authority_level`.
- Go donor auth marks `/token_verify` responses without miner binding as synthetic `claw1local-*` principals. They can join local harness flows but are not Poker MTT reward eligible without an explicit reward-bound role.
- Miner rows now persist Poker MTT reward identity metadata: user id, auth source, reward-bound flag/time, synthetic flag, expiry, and revocation.
- Final ranking projection and reward-window selection both reject missing, synthetic, not-bound, expired, revoked, or `claw1local-*` identities.
- Remaining G3 production hardening: late economic-unit duplicate demotion/backfill still belongs with the 20k/bulk reward-window wave because it needs the same refreshed bulk miner state path.

### G4 - 20k DB-Backed Reward Window And Budget Contract

Current blockers:

- Current 20k check is offline shape, not `POST /admin/poker-mtt/reward-windows/build`.
- Reward-window build still does per-result final-ranking lookup and per-miner rating snapshot lookup.
- Automatic reconcile scans all historical poker MTT results.
- Reward pool amount is direct input/config, not yet tied to a production budget ledger.
- Current aggregation uses max score per economic unit, which may over-reward one lucky window result.
- Multiplier can update immediately, creating same-window feedback risk.

Acceptance:

- Seed 300 and 20k reward-ready rows in Postgres and call the real admin endpoint.
- Main 20k build path uses under 30 SQL statements; unchanged rebuild uses under 5 and no artifact rewrites.
- Response body under 256 KB; 5,000-row page size; exactly 4 page artifacts for 20k rows.
- Root reconstruction validates exactly 20k rows from page artifacts.
- Local/staging RSS delta under 512 MB; p50/p95/p99 latency captured in artifacts.
- Automatic reconcile uses bounded/indexed closed-window query and has EXPLAIN evidence.
- Budget ledger exists with `budget_source_id`, emission epoch/range, daily/weekly split, unused/forfeited/rolled amount, and lane cap.
- Daily plus weekly payouts cannot exceed the configured emission slice.
- Window aggregation policy is explicit and versioned. The default should not silently be `max()` unless product explicitly freezes "best-of-window".
- Multiplier snapshots have `effective_window_id` or `effective_at` and cannot affect the same window's payout.

### G5 - Settlement External Query And Bounded Anchor Artifacts

Current blockers:

- `x/settlement` query registration is a no-op placeholder; CLI query is stubbed.
- Default mining-service confirmer checks tx inclusion but does not fetch stored `x/settlement` state.
- Current tx/query fields do not cover all documented Phase 3 confirmation fields.
- Anchor payload can inline all reward rows and re-expand 20k payloads through settlement/admin paths.
- Metadata mismatches can remain pending instead of terminal/degraded states.

Acceptance:

- Generate and wire gRPC query server, gateway, and CLI for `SettlementAnchor`.
- Production confirmer waits for tx inclusion, queries stored anchor state, normalizes proto JSON casing, and compares all required fields.
- Confirmation covers batch id, canonical root, anchor payload hash, lane, policy, window start/end, reward roots, page roots, total amount, row count, submitter/authorization context, and correction lineage.
- If fields stay inside `anchor_payload_hash` rather than first-class tx fields, artifact retrieval and hash verification must be part of confirmation.
- Mismatch statuses are explicit: `pending`, `tx_failed`, `typed_state_missing`, `root_mismatch`, `metadata_mismatch`, `fallback_memo_only`, `confirmed`.
- Settlement/admin response surfaces summaries by default and page/artifact refs for large rows.
- Fallback memo tx never equals typed anchored state.

### G6 - Reputation Delta, Not Direct Reputation Writes

Current blockers:

- `x/reputation` has useful primitives but is not ready for Poker MTT writes: service/query/CLI wiring, challenge interface alignment, and EndBlock ordering need review.
- Direct single-result reputation writes would over-amplify hidden eval and public rank noise.

Acceptance:

- Define window-level `reputation_delta_rows_root` only after reward/evidence/settlement gates are stable.
- Reputation delta rows include window id, settlement batch id, policy version, prior score reference, delta reason, cap, and correction lineage.
- Authorized controller applies append-only compensating deltas only after settlement confirmation.
- No single tournament, raw HUD, public ELO, hidden eval raw score, or client/admin payload writes directly to `x/reputation`.

### G7 - Sidecar Reliability, WS Finish Gate, And Observability

Current blockers:

- Sidecar HTTP operations are mostly one-shot despite idempotency keys.
- WS adapter is mostly connect-spec level; production behavior needs reconnect, PING/PONG, room migration, and disconnect semantics.
- 30-player non-mock finish harness exists but is not a hard one-command gate.
- Observability fields are contract names, not proven emitted metrics/logs.

Acceptance:

- Add retry/backoff policy for idempotent sidecar operations only: start, get-room, join, reentry, cancel. Do not retry betting actions.
- Add tests for 503-then-OK, timeout-then-OK, non-retryable 400/401, and donor error body propagation.
- 30-player explicit join/action-to-finish gate asserts: 30 joined, 30 ranking, 30 users sent actions, 1 survivor, 29 eliminated/finished, 0 pending, 0 unexpected WS errors after allowed bust/kick close reasons.
- 2,000-table burst test generates completed-hand/finalizer ingest attempts, not just metadata.
- Metrics/log sink receives hand ingest count/conflict, HUD duration, reward-window query duration, selected/omitted counts, artifact page count, MQ lag, DLQ count, and settlement confirmation state.

---

## 5. Implementation Waves

Recommended execution order:

1. Final ranking contract and donor parity: cross-language fixture, idempotent projection, registration/waitlist/no-show archive.
2. Admin and reward identity: fail-closed startup, admin principal, durable reward-bound identity, late economic-unit duplicate handling.
3. Evidence and MQ recovery: conflict/DLQ/checkpoint, policy-owned completeness, immutable artifacts, hidden eval policy ownership.
4. 20k DB-backed reward-window gate: bulk APIs, indexes, EXPLAIN, page artifacts, response-size and SQL-count thresholds.
5. Settlement query and anchor proof: generated query path, production confirmer, bounded anchor artifacts, explicit mismatch states.
6. Economics hardening: budget ledger, aggregation policy, multiplier effective-window snapshots.
7. Sidecar and ops gate: retry policy, WS behavior, one-command finish harness, real observability.
8. Reputation delta draft: schema and dry-run artifact only, no direct chain writes until previous gates pass.

---

## 6. Release Rule

Phase 3 passes only when:

- all P0 gates above have tests and runnable commands
- all large-artifact paths are bounded by root/page refs
- local/staging runbooks exist for 30-player sidecar, 300 DB service path, and 20k DB reward window
- settlement proof uses external query, not tx success
- reward selection is identity-bound and policy-bound
- all docs point to this spec as the Phase 3 source of truth

Only after that should `poker_mtt_daily` / `poker_mtt_weekly` be considered for reward-bearing staging rollout.

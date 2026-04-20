# Poker MTT Phase 3 Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Poker MTT local beta into a donor-compatible production-readiness gated system for locked final ranking, evidence, reward identity, bounded reward windows, budget reservation, and settlement proof.

**Architecture:** Keep donor gameserver/auth as external references. Donor gameserver remains authoritative for live table/runtime/WS behavior, and donor auth remains a runtime-admission interface only. ClawChain owns the adapter/finalizer/projector/evidence/reward/settlement gates around that donor runtime. Phase 3 does not enable high-value production rewards by default; it closes only the minimum gates required before reward-bearing rollout.

**Tech Stack:** Go sidecar/authadapter/pokermtt packages, Python FastAPI mining service, SQLAlchemy/Postgres repository, pytest, Go tests, Cosmos SDK module tests, GitNexus for graph orientation.

---

## 2026-04-20 Wave 1 Scope Reset

This plan was revalidated against `lepoker-auth`, `lepoker-gameserver`, current `clawchain` source, and four GPT-5.4 xhigh review swarms. The result is a deliberate scope reduction.

### P0 required

- Locked canonical final ranking produced from donor runtime plus registration/waitlist/no-show inputs.
- Unique contiguous payout rank for reward-bearing rows, while preserving donor `display_rank` / `source_rank` for audit.
- Donor-shaped completed-hand ingest: `POKER_RECORD_TOPIC` mainline, idempotent checkpoint/replay, conflict/DLQ, and freshness watermark.
- Runtime admission via donor-compatible `token_verify`, but reward eligibility via durable ClawChain reward identity.
- Bounded DB-backed reward-window build over locked eligible rows only.
- Minimal shared emission-slice budget reservation before a batch becomes anchorable.
- Typed settlement query confirmation against stored chain state, not tx success alone.
- Two release-evidence gates only: one auth-backed 30-player donor finish run, and one donor-shaped 2,000-table / 20k-user ingest+reward+settlement burst proof.

### P1 later

- Window-level `reputation_delta` artifacts and any `x/reputation` write path.
- Alternative aggregation policies, richer budget lifecycle accounting, and multiplier experimentation beyond one frozen later-window rule.
- Full long-term HUD/public rating/ELO migration.
- Rich replay bundles and broader artifact lineage beyond what reward/evidence audit strictly needs.

### Explicit non-goals

- Re-implementing donor runtime or donor control-plane breadth in ClawChain.
- Porting Cognito/JWKS/social/admin auth parity instead of keeping a thin adapter.
- Requiring a live 20k-user donor tournament as a Phase 3 prerequisite.
- Positive reward weighting from hidden eval in Phase 3.
- Per-hand or per-tournament on-chain writes.

### Scope guardrails

- Admin APIs remain audit/replay/backfill surfaces. The reward-bearing mainline is finish-event finalization into locked artifacts.
- `token_verify` proves runtime admission only. It does not prove reward-bound miner or economic-unit identity.
- `POKER_RECORD_CALCULATE_TOPIC` and other secondary donor topics are replay/backfill candidates, not Phase 3 parity requirements.
- Harness/bootstrap details stay in ops docs; the Phase 3 contract only cares about the evidence they must produce.

---

## File Structure

- Modify `pokermtt/projector/result_payload.go`: cross-language final ranking payload fields and idempotency key.
- Modify `pokermtt/projector/client.go`: retry semantics and auth failure handling.
- Modify `pokermtt/ranking/*`: registration/waitlist/no-show handoff and stable finalization invariants.
- Modify `pokermtt/sidecar/*`: idempotent operation retry policy and donor error propagation.
- Modify `authadapter/*`: donor token timeout and non-local missing miner binding behavior.
- Modify `mining-service/schemas.py`: final ranking projection contract additions.
- Modify `mining-service/server.py`: projection idempotency, admin principal audit, fail-closed config checks.
- Modify `mining-service/forecast_engine.py`: reward identity enforcement, policy-owned evidence readiness, locked-row reward-window path, frozen budget contract, and anchor confirmation states.
- Modify `mining-service/repository.py` and `mining-service/pg_repository.py`: new repository APIs for MQ checkpoint/conflict/DLQ, locked final-ranking reads, reward identity, budget reservation, and correction supersession.
- Modify `mining-service/models.py`: new tables/indexes for reward identity, MQ checkpoint/conflict/DLQ, locked final-ranking artifacts, and the minimal budget ledger.
- Modify `x/settlement/**` and `proto/clawchain/settlement/v1/**`: generated query path, CLI/gateway wiring, expanded proof fields or artifact-hash proof contract.
- Add tests under `tests/mining_service/`, `pokermtt/**`, `authadapter/**`, and `x/settlement/**`.
- Update docs under `docs/` after each wave.

---

### Task 1: Lock Final Ranking Projection Contract

**Files:**
- Modify: `pokermtt/projector/result_payload.go`
- Modify: `mining-service/schemas.py`
- Modify: `mining-service/server.py`
- Test: `pokermtt/projector/*_test.go`
- Test: `tests/mining_service/test_poker_mtt_final_ranking_contract.py`

- [x] **Step 1: Write the failing cross-language fixture test**

Create a Go-produced JSON fixture for one finished entrant, one busted entrant, and one waiting/no-show entrant. Validate the fixture with Python `ApplyPokerMTTFinalRankingProjectionRequest`.

- [x] **Step 2: Run the test and confirm schema mismatch**

Run: `go test ./pokermtt/projector -run FinalRankingPayload -v && PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_final_ranking_contract.py`

Expected: Python validation fails on missing required fields or ignored top-level canonical fields.

- [x] **Step 3: Add projection identity fields**

Add `projection_id`, `final_ranking_root`, `standing_snapshot_id`, `standing_snapshot_hash`, and payload `locked_at` to the accepted schema. Either make server-generated row fields explicit or have Go populate required row fields.

- [x] **Step 4: Make projection idempotent**

Same `projection_id` plus same root returns the existing projection. Same `projection_id` plus changed root returns 409. Use payload `locked_at` after validation.

- [x] **Step 5: Verify**

Run: `go test ./pokermtt/projector -v && PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_final_ranking_contract.py tests/mining_service/test_poker_mtt_final_ranking.py`

Commit: `git commit -m "feat(pokermtt): lock final ranking projection contract"`

2026-04-18 implementation note:

- Added `tests/fixtures/poker_mtt/final_ranking_projection_from_go.json` and cross-language Go/Python tests.
- Go projector now emits `projection_id`, final-ranking root, standing snapshot refs, payload/row `locked_at`, and donor-derived row metadata required by the FastAPI schema.
- FastAPI projection request now requires the canonical top-level fields.
- `/admin/poker-mtt/final-rankings/project` persists a projection artifact marker and is idempotent for same `projection_id`/root while returning 409 for same `projection_id` with a different root.
- Projection uses payload `locked_at`, not request-time `now()`.

### Task 2: Add Registration/Waitlist Finalizer Parity

**Files:**
- Modify: `pokermtt/ranking/finalizer.go`
- Modify: `pokermtt/ranking/redis_store.go`
- Add/modify tests: `pokermtt/ranking/*_test.go`
- Update docs: `docs/POKER_MTT_SIDECAR_INTEGRATION.md`

- [x] **Step 1: Write failing finalizer tests**

Cover registered no-show absent from Redis, waiting user present only in registration snapshot, stale composite Redis snapshot, and chip/count invariant drift.

- [x] **Step 2: Add finalization input source**

Introduce a registration/waitlist snapshot interface that can be backed by donor auth, local fixtures, or future DB adapters.

- [x] **Step 3: Merge archive-only rows**

Final archive must include no-show/waiting users with reward-ineligible rank states. Runtime Redis live ranking remains insufficient by itself.

- [x] **Step 4: Add barrier invariants**

Require terminal state or quiet-period watermark plus stable repeated reads, count checks, alive/died/waiting checks, and total chip drift tolerance.

- [x] **Step 5: Verify**

Run: `go test ./pokermtt/ranking -v`

Commit: `git commit -m "feat(pokermtt): merge waitlist into final rankings"`

2026-04-18 implementation note:

- Added `RegistrationSource` / `RegistrationSnapshot` and `RedisStore.ReadStableFinalizationInput` so donor auth/local fixture/future DB registration adapters can feed finalization without pretending the data came from Redis ranking keys.
- Added `Finalizer.FinalizeWithRegistration`; legacy `Finalize(snapshot)` still works.
- Registration-only waiting/no-show users are archived as `rank_state=waiting_no_show`, `status=pending`, `snapshot_found=false`, and reward-ineligible rows.
- Optional readiness barriers now cover terminal-or-quiet gating, expected entrant count, and total chip drift tolerance.
- Existing stable Redis snapshot retry remains the stale composite snapshot guard.

### Task 3: Fail Closed On Admin/Auth And Reward Identity

**Files:**
- Modify: `mining-service/config.py`
- Modify: `mining-service/server.py`
- Modify: `authadapter/donor_tokenverify.go`
- Modify: `authadapter/principal.go`
- Modify: `mining-service/models.py`
- Modify: `mining-service/forecast_engine.py`
- Test: `tests/mining_service/test_forecast_api.py`
- Test: `tests/mining_service/test_poker_mtt_reward_identity.py`
- Test: `authadapter/*_test.go`

- [x] **Step 1: Write failing tests**

Unset `CLAWCHAIN_ENV` with external bind should not silently expose admin routes. Donor token without miner binding must not become reward-bound in non-local mode. `claw1local-*` should be able to join harness but fail reward projection/window selection.

- [x] **Step 2: Add startup validation**

Non-local/shared runtime requires admin auth enabled and token configured. Local/test can disable auth only explicitly.

- [x] **Step 3: Add durable reward identity**

Persist miner/user/economic-unit binding with source, expiry, revocation, synthetic flag, and reward-bound flag.

- [x] **Step 4: Enforce reward identity**

Final projection and reward-window selection reject missing, synthetic, expired, revoked, or donor-only identities.

- [x] **Step 5: Add admin principal audit**

Replace self-attested operator fields with resolved admin principal and role for mutation endpoints.

- [x] **Step 6: Verify and commit**

Run: `go test ./authadapter -v && PYTHONPATH=mining-service pytest -q tests/mining_service/test_forecast_api.py tests/mining_service/test_poker_mtt_reward_identity.py`

Commit: `git commit -m "feat(pokermtt): enforce reward-bound identity"`

2026-04-18 implementation note:

- Added red/green coverage for external-bind admin fail-closed startup, donor `/token_verify` missing miner binding, local harness `claw1local-*` reward rejection, missing durable identity, revoked identity, expired identity, and admin risk override principal audit.
- `AppSettings` now carries `runtime_env`, `bind_host`, and explicit insecure-local override. `create_app` rejects non-local runtime without admin auth/token and rejects external bind without admin auth unless local/test explicitly opts into insecure mode.
- `/admin/*` middleware resolves the admin principal from the bearer token or the local harness context. Risk override audit now uses that resolved principal and ignores self-attested payload operator fields.
- Go auth principals now include `AuthSource` and `IsSynthetic`; donor tokens without miner binding become synthetic `claw1local-*` principals and are not Poker MTT reward eligible.
- Miner registration now persists Poker MTT reward identity fields: user id, auth source, reward-bound flag/time, synthetic flag, expiry, and revocation.
- Final ranking projection and reward-window selection reject missing, synthetic, `claw1local-*`, not-bound, expired, or revoked reward identities.

### Task 4: Build MQ Checkpoint, Conflict, DLQ, And Policy-Owned Evidence

**Files:**
- Modify: `mining-service/models.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Modify: `mining-service/forecast_engine.py`
- Test: `tests/mining_service/test_poker_mtt_mq_recovery.py`
- Test: `tests/mining_service/test_poker_mtt_evidence.py`

- [x] **Step 1: Write failing MQ recovery tests**

Cover duplicate message, lower stale version, higher version supersession, same-version checksum conflict persisted, malformed payload DLQ, crash after hand/HUD write before checkpoint, deterministic replay root, lag/watermark blocking reward readiness.

- [x] **Step 2: Add checkpoint/conflict/DLQ models**

Model topic/queue, consumer group, offset, donor `bizId`, message ID, replay root, lag, conflict reason, and DLQ reason.

- [x] **Step 3: Persist checksum conflicts**

Same hand/version with checksum drift must create durable conflict/manual-review state and block reward readiness.

- [x] **Step 4: Make evidence readiness policy-owned**

Required components and degraded allowlist come from policy, not caller convenience. Missing required roots cannot return `complete`.

- [x] **Step 5: Version evidence artifacts**

Use content-addressed or versioned artifact IDs so old roots remain retrievable after rebuilds.

- [x] **Step 6: Verify and commit**

Run: `PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_mq_recovery.py tests/mining_service/test_poker_mtt_evidence.py tests/mining_service/test_poker_mtt_reward_gating.py`

Commit: `git commit -m "feat(pokermtt): add mq recovery evidence gates"`

2026-04-18 implementation note:

- Added MQ recovery coverage for duplicate replay, higher-version supersession, lower-version stale replay, crash after hand write before checkpoint, deterministic replay roots, same-version checksum conflict persistence, malformed payload DLQ, checkpoint lag blocking, and caller-degraded policy rejection.
- Added durable MQ checkpoint/conflict/DLQ repository models and Postgres tables keyed by topic, queue, consumer group, donor `bizId`, message ID, hand ID, offset, replay root, lag, and manual-review/DLQ reason.
- `ingest_poker_mtt_hand_event` now writes checkpoint state after inserted/duplicate/updated/stale/conflict/DLQ outcomes, persists checksum conflicts as `manual_review`, and turns malformed payloads into DLQ rows rather than crashing the consumer.
- Evidence readiness is now policy-owned: final ranking, hand history, consumer checkpoint, hidden eval, and short/long HUD are the policy component set; only hidden/HUD manifests are policy-allowlisted for `accepted_degraded`. Caller-provided `accepted_degraded_kinds` cannot degrade required hand/checkpoint components.
- Open MQ conflicts, open DLQ rows, or checkpoint lag return `evidence_state=blocked`.
- Evidence artifacts are content-addressed by manifest root, so old manifest roots remain retrievable after rebuilds.

### Task 5: Prove 20k DB-Backed Reward Window Path

**Files:**
- Modify: `mining-service/pg_repository.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/models.py`
- Add: `scripts/poker_mtt/run_phase3_db_load_check.sh`
- Test: `tests/mining_service/test_poker_mtt_phase3_db_load.py`

- [x] **Step 1: Write failing Postgres-backed load tests**

Seed 300 and 20k reward-ready rows, call `POST /admin/poker-mtt/reward-windows/build`, and assert response size, page count, root reconstruction, SQL count, idempotent rebuild, and RSS delta.

- [x] **Step 2: Add bulk repository methods**

Bulk final rankings by ID, latest rating snapshots by miner set, bulk artifact upsert, and bounded closed-window candidate query.

- [x] **Step 3: Replace N+1 reward-window logic**

Remove per-result final-ranking lookups and per-miner rating snapshot queries from the main build path.

- [x] **Step 4: Replace automatic full scan**

Automatic reconcile must use indexed closed-window query, not `list_poker_mtt_results()`.

- [x] **Step 5: Add indexes and EXPLAIN assertions**

Cover locked/evidence-ready results, artifacts by entity/kind/id, rating snapshots by miner/window, and final ranking IDs.

- [x] **Step 6: Verify and commit**

Run: `PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_phase3_db_load.py`

Commit: `git commit -m "perf(pokermtt): prove db backed reward window scale"`

2026-04-18 implementation note:

- Added `tests/mining_service/test_poker_mtt_phase3_db_load.py` covering 300-row and 20k-row service-path builds, response-size gating, 5,000-row page artifacts, page-root reconstruction, RSS guard, idempotent rebuild, bounded auto reconcile, and required scale indexes.
- Added repository bulk APIs for reward-window input snapshots, final rankings by IDs, miners by addresses, latest rating snapshots by miner set, bulk artifact upsert, and closed-window candidate queries.
- `build_poker_mtt_reward_window` now consumes a bulk input snapshot instead of per-result final-ranking lookups, per-miner reward identity lookups, and per-miner rating snapshot queries.
- Unchanged rebuilds compare the stored input snapshot root and return the existing projection without rewriting reward windows or artifact rows.
- 20k reward-window responses omit the full `miner_addresses` array and return root/count/sample plus projection/page artifact refs; page artifacts reconstruct exactly 20k reward rows.
- Automatic Poker MTT reward-window reconcile now uses a lookback-bounded, indexed closed-window candidate query instead of `list_poker_mtt_results()`.

### Task 6: Wire External Settlement Query And Bounded Anchor Payloads

**Files:**
- Modify: `proto/clawchain/settlement/v1/query.proto`
- Modify: `proto/clawchain/settlement/v1/tx.proto`
- Modify: `x/settlement/types/*`
- Modify: `x/settlement/keeper/*`
- Modify: `x/settlement/client/cli/query.go`
- Modify: `x/settlement/module/module.go`
- Modify: `mining-service/chain_adapter.py`
- Modify: `mining-service/forecast_engine.py`
- Test: `x/settlement/keeper/*_test.go`
- Test: `tests/mining_service/test_chain_adapter.py`
- Test: `tests/mining_service/test_forecast_engine.py`

- [x] **Step 1: Write failing external query tests**

Test gRPC/gateway/CLI query returns stored anchor state and mining-service confirmation refuses tx-only success.

- [x] **Step 2: Generate/wire query path**

Replace placeholder query registration and stub CLI with real query server and client.

- [x] **Step 3: Expand confirmation fields or artifact proof**

Either add first-class fields or require artifact retrieval/hash proof for window, page roots, budget, submitter, policy, counts, and correction lineage.

- [x] **Step 4: Bound anchor payloads**

Settlement batches and admin list endpoints return summaries/page refs for 20k rows, not inline full rows.

- [x] **Step 5: Add terminal mismatch states**

Persist `typed_state_missing`, `root_mismatch`, `metadata_mismatch`, `fallback_memo_only`, and `confirmed` distinctly.

- [x] **Step 6: Verify and commit**

Run: `go test ./x/settlement/... -v && PYTHONPATH=mining-service pytest -q tests/mining_service/test_chain_adapter.py tests/mining_service/test_forecast_engine.py`

Commit: `git commit -m "feat(settlement): confirm anchors through external query"`

2026-04-18 implementation note:

- Added generated gogo query protobuf output for `x/settlement` and wired `SettlementAnchor` through gRPC server registration, gateway route, and CLI query.
- Added Go coverage for keeper query, gateway route, and CLI query against an in-memory gRPC server.
- Mining-service confirmation now normalizes and persists `anchor_jobs.chain_confirmation_status`; tx-only, fallback-memo-only, root drift, and metadata drift are not accepted as anchored.
- Settlement anchor payloads now page large `miner_reward_rows` into `settlement_anchor_miner_reward_rows_page` artifacts while the main payload/admin response keeps root/page refs.
- Added 20k settlement-anchor response-size/root-reconstruction coverage and admin list bounded-response coverage.

### Task 7: Harden Reward Economics And Multiplier Timing

**Files:**
- Modify: `mining-service/models.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Modify: `mining-service/forecast_engine.py`
- Test: `tests/mining_service/test_poker_mtt_reward_economics.py`

- [x] **Step 1: Write failing economics tests**

Budget source missing/oversized rejects; daily plus weekly cannot exceed same emission slice; stable performer versus lucky spike behaves according to versioned aggregation policy; multiplier cannot affect same-window payout.

- [x] **Step 2: Add budget ledger**

Track `budget_source_id`, emission epoch/range, lane caps, daily/weekly split, unused/forfeited/rolled amount, and budget root.

- [x] **Step 3: Freeze aggregation policy**

Replace implicit unversioned `max()` with explicit policy, preferably capped top-K or trimmed mean unless product freezes best-of-window.

- [x] **Step 4: Add effective-window multiplier**

Store before/after/effective window snapshots. Reward windows use prior finalized multiplier snapshots only.

- [x] **Step 5: Verify and commit**

Run: `PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_reward_economics.py tests/mining_service/test_poker_mtt_reward_gating.py`

Commit: `git commit -m "feat(pokermtt): harden reward economics"`

2026-04-18 implementation note:

- Added `tests/mining_service/test_poker_mtt_reward_economics.py` covering missing/oversized budget config, shared daily/weekly emission slices, capped aggregation against lucky spike, and next-window multiplier snapshot timing.
- Added `poker_mtt_budget_ledgers` to models, FakeRepository, and PostgresRepository with budget source, emission epoch, lane, reward window, settlement batch, requested/approved/paid/forfeited/rolled amounts, and `budget_root`.
- `build_poker_mtt_reward_window` now reserves budget before settlement when enforcement is enabled and rejects daily/weekly windows that exceed the same configured epoch slice.
- Reward-window projection now records `aggregation_policy_version`, `budget_disposition`, and `budget_root`; default aggregation is `capped_top3_mean_v1`, with `max_score_v1` only available explicitly.
- `poker_mtt_multiplier_snapshots` now persist `effective_window_start_at` and `effective_window_end_at` as the next UTC daily window after source result lock/completion.

### Task 8: Promote Sidecar Finish And Observability Gates

**Files:**
- Modify: `pokermtt/sidecar/client.go`
- Modify: `pokermtt/sidecar/ws.go`
- Modify: `scripts/poker_mtt/non_mock_play_harness.py`
- Modify: `scripts/poker_mtt/generate_hand_history_load.py`
- Modify: `deploy/docker-compose.poker-mtt-local.yml`
- Add: `scripts/poker_mtt/init_local_dynamodb.sh`
- Add: `scripts/poker_mtt/patch_donor_local_safety.py`
- Modify: `Makefile`
- Test: `pokermtt/sidecar/*_test.go`
- Test: `tests/mining_service/test_poker_mtt_load_contract.py`

- [x] **Step 1: Write failing retry and harness tests**

Cover 503-then-OK, timeout-then-OK, non-retryable 400/401, donor error body propagation, 30-player finish hard assertions, and 2,000-table completed-hand ingest shape.

- [x] **Step 2: Add sidecar retry policy**

Retry idempotent orchestration calls only. Never retry betting/action calls.

- [x] **Step 3: Make finish harness a hard gate**

Require 30 joined, 30 ranking, 30 users sent actions, 1 survivor, 29 finished/eliminated, 0 pending, and only allowed WS close reasons.

- [x] **Step 4: Add real miner action/timeout coverage**

Action policy must sample only donor-provided legal actions/chips and include `fold`, all-in/max-chip, and timeout/no-action ticks. Timeout/no-action should be separately counted so it cannot be confused with a sent WS action.

- [x] **Step 5: Add local RocketMQ/DynamoDB/Tencent safety harness**

Local compose must start Redis, RocketMQ namesrv/broker/proxy, and DynamoDB Local. DynamoDB Local bootstrap creates `poker_mtt_hands` and `poker_mtt_user_hand_history`. Local donor startup applies a reversible Tencent IM safety patch so `DeleteGroupMember()` respects `chat_group_available=false`.

- [ ] **Step 6: Add donor operation-channel backpressure gate**

Parse donor logs for `channle is full`, `timeout with seconds:5,sendCommand`, `POKER_RECORD_TOPIC`, and Tencent external calls. With RocketMQ healthy, 30-player and 2,000-table runs must have zero operation-channel overflow and zero Tencent external calls. If overflow remains, split record assembly/MQ publish from the hot `Hub.Operation` consumer or add lossless bounded spillover before reward-bearing rollout.

- [x] **Step 7: Emit real metrics/log events**

Test metrics/log sink receives hand ingest, conflict, HUD duration, reward-window query, selected/omitted counts, page count, MQ lag, DLQ count, and settlement confirmation state.

- [x] **Step 8: Verify and commit**

Run: `go test ./pokermtt/sidecar -v && PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_load_contract.py && bash scripts/poker_mtt/run_phase3_db_load_check.sh --players 300 --local`

Commit: `git commit -m "test(pokermtt): add phase3 ops gates"`

2026-04-18 implementation note:

- Added sidecar retry coverage for 503-then-OK, timeout-then-OK, non-retryable unauthorized, and donor error body propagation.
- Sidecar envelope calls now retry only transient timeout/429/502/503/504 failures. 400/401 remain single-attempt, and donor `msg` is preserved in `RequestError`.
- `non_mock_play_harness.py` now exposes and calls `validate_finish_summary()` when `--until-finish` is enabled. The gate asserts joined users, ranking receipt, sent actions, 1 alive, 29 died for 30 players, 0 pending, and no unexpected WS errors.
- `generate_hand_history_load.py` now materializes one completed-hand event per early-stage table and returns a checksum root for the 2,000-table burst shape.
- Added `make test-poker-mtt-phase3-ops` to run sidecar tests, load-contract tests, and the Phase 3 DB load check in one command.

2026-04-19 implementation note:

- `non_mock_play_harness.py` now samples `fold`, all-in/max-chip, and timeout/no-action behavior from donor legal `readyToAct` states. `--require-action-coverage` turns those paths into a hard finish-gate assertion through the emitted `action_coverage` summary.
- `deploy/docker-compose.poker-mtt-local.yml` includes DynamoDB Local; `init_local_dynamodb.sh` bootstraps local hand-history tables. RocketMQ broker config advertises `brokerIP1=host.docker.internal` with direct broker port mappings and compose `extra_hosts` so the Docker proxy can reach the broker; RocketMQ proxy config enables `useEndpointPortFromRequest=true` so the host-run donor receives `127.0.0.1:38081` from Go v5 route metadata instead of `127.0.0.1:8081`.
- Phase 3 harness hosts must pre-pull/cache `apache/rocketmq:5.3.2` and `amazon/dynamodb-local:2.5.4`; cold image pulls are environment setup evidence, not tournament runtime evidence. Local RocketMQ compose must not force `linux/amd64`, otherwise Apple Silicon pulls a second emulated image and invalidates timing evidence. Broker route must advertise `host.docker.internal:10911`; `127.0.0.1` breaks proxy containers, while Docker service DNS breaks host-run donor producers. Proxy route must preserve the host-mapped gRPC port, otherwise donor logs show `telemeter to 127.0.0.1:8081 failed` and all MQ-backed hand-history paths become contaminated.
- `patch_donor_local_safety.py` blocks Tencent IM cleanup calls locally by adding the missing `chat_group_available=false` guard to donor `DeleteGroupMember()`.
- `check_local_run_logs.py` records and fails local release gates for Tencent IM external calls, RocketMQ publish failures, and donor operation-channel overflow.
- Backpressure gate status: the historical donor-real run showed `Hub.Operation` overflow during final-table/end-ranking bursts, but the clean healthy-MQ 30-player rerun at `artifacts/poker-mtt/deep-real-auth-20260419T091505Z` finished with zero Tencent IM external calls, zero RocketMQ publish failures, and zero operation-channel overflow. The remaining open item is the 2,000-table / 20k-user burst proof; Phase 3 cannot be called production-ready until that scale gate records the same counters plus MQ lag and record-assembly timing.

2026-04-19 payout-ranking harness note:

- Auth-mode donor run `non-mock-play-1776613014` at `artifacts/poker-mtt/payout-rank-20260419T153551Z-current-position/` finished with 30 explicit joins, 30 ranking receipts, 30 users with sent WS actions, 155 total sent actions, `allIn=30`, `fold=7`, `timeout_no_action_total=8`, and `nonzero_chip_action_count=32`.
- The run produced final counts `alive=1`, `died=29`, `pending=0`, `standings=30`. Donor display ranks tied at `9`, `15`, `20`, and `25`; the post-fix complete standings check verified unique, contiguous, sorted payout ranks `1..30`.
- Harness actor tracking now treats donor `Msg` action rejection (`not permited` / `not permitted`) as a finish-gate failure and chooses action eligibility from the current `readyToAct.currentPosition`, avoiding stale seat actions from old onlooker WebSocket sessions after table movement.

### Task 9: Draft Window-Level Reputation Delta Only

**Files:**
- Modify: `docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md`
- Modify: `x/reputation/**` only if wiring is explicitly scoped after settlement gates pass
- Add/modify tests: `tests/mining_service/test_poker_mtt_reputation_delta.py`

- [x] **Step 1: Write dry-run reputation delta tests**

Window-level delta rows include window id, settlement batch id, policy, prior score ref, cap, reason, and correction lineage. No single tournament can write directly.

- [x] **Step 2: Produce delta artifact root**

Add `reputation_delta_rows_root` to reward/settlement artifacts only as dry-run output.

- [x] **Step 3: Keep chain writes disabled**

Do not add direct `x/reputation` writes until external settlement query, identity, budget, and correction gates have passed.

- [x] **Step 4: Verify and commit**

Run: `PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_reputation_delta.py`

Commit: `git commit -m "feat(pokermtt): draft window reputation deltas"`

2026-04-18 implementation note:

- Added `tests/mining_service/test_poker_mtt_reputation_delta.py` before implementation; it covers reward-window reputation delta roots, settlement anchor roots, correction lineage, and the no-direct-write guard.
- Reward-window projection payloads now include `reputation_delta_policy_version`, `reputation_delta_rows_root`, bounded sample rows, row count, top-level correction lineage root, and the predicted settlement batch id for window-level lineage.
- Settlement anchor payloads now include per-window `reputation_delta_window_roots` and a settlement-level `reputation_delta_rows_root`; `poker_projection_roots` also carry each window's reputation delta root.
- No `x/reputation` module writes or service calls were added; the output remains a dry-run contract gated behind reward/evidence/identity/budget/settlement artifacts.

### Task 10: Documentation, CI Targets, And Release Review

**Files:**
- Modify: `docs/POKER_MTT_PHASE3_PRODUCTION_READINESS_SPEC.md`
- Modify: `docs/HARNESS_API_CONTRACTS.md`
- Modify: `docs/POKER_MTT_SIDECAR_INTEGRATION.md`
- Modify: `docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md`
- Modify: `Makefile`

- [x] **Step 1: Add fast and heavy gates**

Fast gate covers unit/contracts. Heavy/manual gate covers Postgres 20k, sidecar 30-player finish, and settlement local chain query proof.

- [x] **Step 2: Add artifact locations**

Document where load result JSON, SQL counts, RSS samples, EXPLAIN plans, replay roots, and settlement receipts are written.

- [x] **Step 3: Add production release checklist**

Rollout remains disabled until a separate release review approves budget source, operator roles, chain submitter, monitoring, and rollback.

- [x] **Step 4: Verify and commit**

Run: `git diff --check && rg -n "Phase 3|POKER_MTT_PHASE3|reward-bound|settlement query|20k" docs`

Commit: `git commit -m "docs(pokermtt): finalize phase3 readiness plan"`

2026-04-18 implementation note:

- Added `make test-poker-mtt-phase3-fast` for local unit/contract coverage and `make test-poker-mtt-phase3-heavy` for staging/manual evidence.
- Heavy gate writes `db-load-20k.log`, `non-mock-30-finish-summary.json`, and `settlement-anchor-query-receipt.json` under `artifacts/poker-mtt/phase3/`.
- `.gitignore` now excludes `artifacts/`, keeping release evidence out of source commits while documenting exactly where it is produced.
- Phase 3 spec, harness contract, sidecar integration doc, and lepoker-auth reference now agree that reward-bearing rollout still requires a separate release review.

---

## Final Verification Before Rollout Consideration

Run:

```bash
pytest tests/mining_service -q
go test ./authadapter ./pokermtt/... ./x/settlement/... ./x/reputation/... -v
bash scripts/poker_mtt/run_phase3_db_load_check.sh --players 20000 --postgres "$CLAWCHAIN_DATABASE_URL"
python3 scripts/poker_mtt/non_mock_play_harness.py --user-count 30 --table-room-count-at-least 4 --until-finish --finish-timeout-seconds 1800 --max-workers 30 --timeout-action-rate 0.05 --require-action-coverage
git diff --check
```

Expected:

- all unit and integration tests pass
- 20k reward-window response under 256 KB
- exactly 4 reward row page artifacts at page size 5,000
- root reconstruction covers 20k rows
- SQL count and RSS thresholds pass
- external settlement query confirms typed anchor state
- reward-bound identity rejects local/synthetic donor-only identities
- no direct `x/reputation` writes from single tournament results

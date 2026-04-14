# Poker MTT Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production-shaped Poker MTT lane in ClawChain by driving the proven `lepoker-gameserver` runtime as a sidecar, canonicalizing final standings and evidence inside ClawChain, and feeding only locked/anchorable results into daily/weekly reward windows and settlement anchor payloads.

**Architecture:** Keep Poker MTT separate from `arena/*`. New Go code owns auth/session/runtime sidecar orchestration under `authadapter/*` and `pokermtt/*`; existing Python `mining-service` remains the reward, multiplier, evidence, and settlement projection service. Donor repos are references only: `lepoker-gameserver` supplies live table/runtime/WS/ranking behavior; `lepoker-auth` supplies auth, MQ, hand-history, HUD, final-ranking, and control-plane reference flows. Chain integration remains window-level settlement anchoring, not per-hand or per-game payout.

**Tech Stack:** Go, Python 3, FastAPI, Pydantic, SQLAlchemy async Postgres repository, Redis, donor `lepoker-gameserver` HTTP/WS sidecar, local auth mock, pytest, Go tests, GitNexus code graph.

---

## Source Inputs

- GitNexus indexed repos:
  - `clawchain`: `/Users/yanchengren/Documents/Projects/clawchain`
  - `lepoker-gameserver`: `/Users/yanchengren/Documents/Projects/clawchain/lepoker-gameserver`
  - `lepoker-auth`: `/Users/yanchengren/Documents/Projects/lepoker-auth`
- Existing ClawChain docs:
  - `docs/POKER_MTT_SIDECAR_INTEGRATION.md`
  - `docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md`
  - `docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md`
  - `docs/HARNESS_API_CONTRACTS.md`
  - `docs/superpowers/plans/2026-04-10-poker-mtt-sidecar.md`
  - `docs/superpowers/plans/2026-04-11-poker-mtt-reward-window-settlement.md`
- Current implementation anchors:
  - `mining-service/models.py`
  - `mining-service/repository.py`
  - `mining-service/pg_repository.py`
  - `mining-service/schemas.py`
  - `mining-service/forecast_engine.py`
  - `mining-service/server.py`
  - `scripts/poker_mtt/*`
  - `tests/poker_mtt/*`
  - `tests/mining_service/*`

---

## Synthesis

Six-agent revalidation converged on the same shape:

- Donor gameserver should remain a sidecar in Phase 1. It owns live MTT runtime, tables, WS, seating, stack moves, eliminations, Redis live ranking, and game-kernel behavior.
- ClawChain owns identity binding, local lifecycle intent, final standing canonicalization, evidence readiness, scoring, multiplier, reward windows, settlement batches, and chain anchor payloads.
- `lepoker-auth` should be borrowed for boundaries and dataflow, not ported as Java. The useful reference is: token verify, MQ hand-completed flow, DynamoDB hand-history persistence, HUD projectors, final ranking, and read-model separation.
- Live ranking, final ranking, and long-term ranking must be separate. Only canonical final ranking can enter result projection.
- Short-term HUD and long-term HUD must be separate. Short-term HUD is evidence/risk/hidden-eval input; long-term HUD and public rating are slow variables for multiplier/reputation, not direct reward weight.
- Chain integration should remain settlement-batch anchoring. Do not put per-hand history, hidden samples, or raw single-game scores on chain in Phase 1.
- The current Python lane is useful but not strict enough yet: it can include provisional results after a watermark, selects windows by `created_at`, lacks final-ranking/evidence gates, lacks reentry/economic-unit fields, and equal-splits all-zero weights.

---

## Hard Invariants

- Do not put Poker MTT implementation in `arena/*`.
- Do not import donor Java or donor Go structs into ClawChain domain models.
- Do not commit or stage `lepoker-gameserver` as part of ClawChain. It is a separate repo and separate GitNexus index.
- Do not trust request `miner_id` for Poker MTT mutations. Resolve `miner_address` from `Principal`.
- Do not use donor `roomID` or `sessionID` as canonical identity. `roomID` is routing; `sessionID` is connection state.
- Do not reward from `live_ranking`.
- Do not let `evaluation_state=final` alone imply anchorability. Require final-ranking artifact plus evidence readiness.
- Do not equal-split a poker reward pool when all canonical weights are zero or negative.
- Do not mutate anchored payload roots. Post-anchor corrections must append or supersede.
- Do not write raw hand history, hidden eval samples, single-game scores, or public ELO directly into `x/reputation`.
- Do not use donor `/v1/mtt/Stop` in local sidecar flows; use cancel/void semantics because the donor Stop path is known unsafe.

---

## Target State Machines

Runtime state:

```text
scheduled -> start_requested -> sidecar_starting -> seating_ready -> running -> finalizing -> standings_ready -> completed
```

Reward and evidence state:

```text
raw_ingested -> final_ranking_ready -> evidence_ready -> result_ready -> locked -> anchorable -> anchored
```

Abnormal states:

```text
failed_to_start
cancelled
void
degraded
manual_review
conflict
correction_required
```

---

## Canonical Contracts

### Sidecar Runtime Contract

The first adapter contract should wrap donor behavior without exposing donor internals:

- `StartTournament(tournament_id)`
  - Donor inner: `POST /v1/mtt/start`
  - Body: `{"ID": "<tournament_id>", "type": "mtt"}`
- `GetCurrentRoom(tournament_id, user_id)`
  - Donor inner: `GET /v1/mtt/getMTTRoomByID?userID=<user_id>&ID=<tournament_id>`
- `JoinPlayer(tournament_id, principal)`
  - Donor outer: `POST /v1/join_game?id=<tournament_id>&type=mtt`
  - Mock mode: donor `Mock-Userid`
  - Auth mode: `Authorization: Bearer <token>` at edge only
- `OpenPlayerWS(tournament_id, principal, session_id)`
  - Donor outer: `GET /v1/ws?id=<tournament_id>&type=mtt`
  - Donor websocket subprotocols: `[token_or_-1, session_id]`
- `ReadLiveStandings(tournament_id)`
  - Redis keys:
    - `rankingUserInfo:mtt:<id>`
    - `rankingNotDiedScore:mtt:<id>`
    - `rankingUserDiedInfo:mtt:<id>`
- `Reentry(tournament_id, principal, entry_number)`
  - Donor inner: `POST /v1/mtt/reentryMTTGame`
  - Treat admission as async.
- `Cancel(tournament_id, reason)`
  - Donor cancel path only; do not call donor Stop.

Idempotency keys:

- `poker_mtt:start:<tournament_id>`
- `poker_mtt:join:<tournament_id>:<user_id>:<session_epoch>`
- `poker_mtt:reentry:<tournament_id>:<user_id>:<entry_number>`
- `poker_mtt:finalize:<tournament_id>:<standing_snapshot_hash>`
- `poker_mtt:apply_results:<tournament_id>:<policy_bundle_version>`
- `poker_mtt:hand:<tournament_id>:<table_id>:<hand_no>`

### Auth Boundary Contract

Create `authadapter` and keep token logic out of domain code:

```go
type Principal struct {
    UserID         string
    MinerAddress  string
    DisplayName   string
    Roles         []string
    TokenExpiresAt time.Time
    AuthSessionID string
    TokenID       string
}
```

Rules:

- `authadapter` owns bearer parsing, donor `/token_verify`, Cognito/JWKS later, and local mock parsing.
- Domain receives only `Principal`.
- Mutating Poker MTT routes derive `miner_address` from `Principal.MinerAddress`.
- Local mock may accept `Bearer local-user:<userID>` and resolve to deterministic local users.
- Donor `Mock-Userid` remains sidecar/harness-only and must not reach ranking, reward, or settlement code.

### Final Ranking Contract

Add a canonical final-ranking layer before result entries:

```text
poker_mtt_final_rankings
```

Required fields:

- `id`
- `tournament_id`
- `source_mtt_id`
- `source_user_id`
- `miner_address`
- `economic_unit_id`
- `entry_number`
- `reentry_count`
- `rank`
- `rank_state`
- `chip`
- `chip_delta`
- `died_time`
- `waiting_or_no_show`
- `bounty`
- `defeat_num`
- `field_size_policy`
- `standing_snapshot_id`
- `standing_snapshot_hash`
- `evidence_root`
- `evidence_state`
- `policy_bundle_version`
- `locked_at`
- `anchorable_at`
- `created_at`
- `updated_at`

`poker_mtt_result_entries` should be extended with:

- `economic_unit_id`
- `entry_number`
- `reentry_count`
- `chip_delta`
- `standing_snapshot_id`
- `risk_flags`
- `no_multiplier_reason`
- `locked_at`
- `anchorable_at`
- `evidence_state`
- `rank_state`

### Hand History Event Contract

Use a ClawChain domain event, not a RocketMQ DTO:

```json
{
  "schema_version": "poker_mtt.hand_completed.v1",
  "event_type": "poker_mtt.hand_completed",
  "event_id": "poker_mtt.hand:<tournament_id>:<table_id>:<hand_no>:v<version>:<checksum_prefix>",
  "source": {
    "transport": "rocketmq",
    "topic": "POKER_RECORD_TOPIC",
    "message_id": "<message_id>",
    "biz_id": "<donor_biz_id>",
    "record_type": "recordType|showCardType|rabbitHuntingType",
    "source_mtt_id": "<donor_mtt_id>",
    "source_room_id": "<donor_room_id>"
  },
  "identity": {
    "tournament_id": "<clawchain_tournament_id>",
    "table_id": "<stable_table_id>",
    "hand_no": 123,
    "hand_id": "<tournament_id>:<table_id>:<hand_no>"
  },
  "version": 3,
  "checksum": "sha256:<canonical_hand_payload>",
  "canonicalization": {
    "algorithm": "json-sort-keys-no-whitespace-fixed-decimal-v1",
    "payload_hash": "sha256:<hash>"
  }
}
```

Idempotency rules:

- No existing item: insert.
- Higher version: update.
- Same version and same checksum: no-op.
- Same version and different checksum: conflict/manual review.
- Lower version: stale no-op.
- Missing version: accept only if checksum matches exactly; otherwise conflict.

---

## File Map

### Create Go Files

- `authadapter/principal.go`
- `authadapter/adapter.go`
- `authadapter/http.go`
- `authadapter/local.go`
- `authadapter/donor_tokenverify.go`
- `authadapter/*_test.go`
- `pokermtt/model/types.go`
- `pokermtt/identity/binding.go`
- `pokermtt/identity/store.go`
- `pokermtt/identity/postgres.go`
- `pokermtt/identity/*_test.go`
- `pokermtt/sidecar/client.go`
- `pokermtt/sidecar/ws.go`
- `pokermtt/sidecar/*_test.go`
- `pokermtt/ranking/redis_store.go`
- `pokermtt/ranking/finalizer.go`
- `pokermtt/ranking/*_test.go`
- `pokermtt/projector/result_payload.go`
- `pokermtt/projector/*_test.go`
- `pokermtt/service/orchestrator.go`
- `pokermtt/service/*_test.go`

### Create Python Files

- `mining-service/canonical.py`
- `mining-service/poker_mtt_ranking.py`
- `mining-service/poker_mtt_results.py`
- `mining-service/poker_mtt_evidence.py`
- `mining-service/poker_mtt_history.py`
- `mining-service/poker_mtt_hud.py`

### Modify Python Files

- `mining-service/models.py`
- `mining-service/repository.py`
- `mining-service/pg_repository.py`
- `mining-service/schemas.py`
- `mining-service/forecast_engine.py`
- `mining-service/server.py`

### Modify Chain Files If Needed

- `x/settlement/keeper/msg_server.go`
  - Add duplicate batch id root/payload mismatch conflict behavior if the service layer cannot fully enforce it.

### Create Or Extend Tests

- `tests/mining_service/test_poker_mtt_final_ranking.py`
- `tests/mining_service/test_poker_mtt_reward_gating.py`
- `tests/mining_service/test_poker_mtt_evidence.py`
- `tests/mining_service/test_poker_mtt_history.py`
- `tests/mining_service/test_poker_mtt_hud.py`
- `tests/mining_service/test_forecast_engine.py`
- `tests/mining_service/test_forecast_api.py`
- `tests/poker_mtt/test_complete_standings.py`
- `tests/poker_mtt/test_non_mock_actor_strategy.py`
- `tests/poker_mtt/test_prepare_local_env.py`

### Update Docs After Implementation

- `docs/POKER_MTT_SIDECAR_INTEGRATION.md`
- `docs/HARNESS_API_CONTRACTS.md`
- `docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md`
- `docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md`
- `docs/IMPLEMENTATION_STATUS_2026_04_10.md`

---

## Task 1: Freeze Contract And Fixtures

- [ ] Write contract tests for sidecar endpoint names, Redis ranking keys, local auth mock token shape, and forbidden donor Stop usage.
- [ ] Add a small fixture package for canonical tournament ids, donor user ids, miner addresses, table ids, and hand ids.
- [ ] Document the Phase 1 sidecar state machine and reward/evidence state machine in `docs/POKER_MTT_SIDECAR_INTEGRATION.md`.
- [ ] Confirm no new code imports from `arena/*` into `pokermtt/*`.

Run:

```bash
rg -n "poker_mtt|pokermtt|arena" docs/POKER_MTT_SIDECAR_INTEGRATION.md docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md
go test ./pokermtt/... -run TestContract -v
```

Exit criteria:

- Contract is explicit and does not call Poker MTT an arena mode.
- Donor Stop is forbidden by tests or adapter code.
- `pokermtt/*` exists only as a separate top-level package.

---

## Task 2: Auth Adapter And Identity Binding

- [ ] Write failing Go tests for local token verification, donor token-verify success/failure, token expiry, and request miner mismatch.
- [ ] Implement `authadapter.Principal` and adapter interfaces.
- [ ] Implement local mock adapter compatible with `Bearer local-user:<userID>`.
- [ ] Implement donor `/token_verify` adapter behind an interface using `httptest`.
- [ ] Implement `pokermtt/identity` binding store with uniqueness on `user_id` and `miner_address`.
- [ ] Enforce that mutating Poker MTT flows use `Principal.MinerAddress`, not request body `miner_id`.
- [ ] Add revocation/expiry handling contract for WS actions: reject manual actions after expiry, allow reconnect with fresh token, do not roll back accepted actions.

Run:

```bash
go test ./authadapter ./pokermtt/identity -v
```

Required test shapes:

- First bind succeeds.
- Same user plus same miner is idempotent.
- Same user plus different miner rejects.
- Different user plus same miner rejects.
- Empty or malformed user id and miner address reject.
- Address normalization is deterministic.
- Concurrent first-bind race yields one success and one conflict.
- Request `miner_id` mismatch with `Principal.MinerAddress` rejects before domain logic.
- Revoked or expired user cannot reconnect or act.

---

## Task 3: Sidecar Client, WS, And Orchestrator

- [ ] Write fake-sidecar tests for start, get room, join, WS connect metadata, reentry, cancel, and health checks.
- [ ] Implement `pokermtt/sidecar.Client` with timeouts, idempotency, and typed errors.
- [ ] Implement `pokermtt/sidecar.WS` connection wrapper with donor subprotocol handling at the adapter boundary only.
- [ ] Implement `pokermtt/service.Orchestrator` that maps runtime states without leaking donor DTOs.
- [ ] Add action retry guardrails: do not blindly retry betting actions because donor WS actions lack request id and expected state sequence.
- [ ] Keep `roomID` as routing-only and re-query room on reconnect/table moves.

Run:

```bash
go test ./pokermtt/sidecar ./pokermtt/service -v
```

Exit criteria:

- Go adapter can drive the donor paths through fakes.
- Runtime state transitions are deterministic under fake responses.
- No domain code depends on donor `roomID` or `sessionID` as identity.

---

## Task 4: Final Standings Canonicalizer

- [ ] Write tests for donor Redis live ranking snapshots using fake Redis data.
- [ ] Implement `pokermtt/ranking.RedisStore` for donor Redis key reads.
- [ ] Implement `pokermtt/ranking.Finalizer` that converts live donor ranking snapshots into canonical final-ranking rows.
- [ ] Port only the semantics from `scripts/poker_mtt/complete_standings.py`; do not make the Python script the scoring engine.
- [ ] Include reentry collapse, no-show policy, nonnumeric ranks, duplicate user rows, and missing snapshot handling.
- [ ] Add a 10,000 entrant synthetic finalizer test to validate deterministic output, memory shape, and stable root.

Run:

```bash
go test ./pokermtt/ranking -v
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/poker_mtt/test_complete_standings.py -p no:cacheprovider -q
```

Exit criteria:

- Canonical final standings are stable from the same Redis snapshot.
- `rank_state` and `waiting_or_no_show` are explicit.
- Reentries are preserved for audit but collapsed to canonical economic-unit reward rows later.

---

## Task 5: Python Final-Ranking Persistence

- [ ] Write failing repository tests for `poker_mtt_final_rankings`.
- [ ] Add SQLAlchemy table and fake repository support.
- [ ] Add Postgres repository methods for upsert/list/get by tournament/window.
- [ ] Add Pydantic schemas for final-ranking rows and projection apply requests.
- [ ] Extend `poker_mtt_result_entries` with economic-unit, reentry, evidence, lock, anchor, and risk fields.
- [ ] Add migrations or schema bootstrap changes consistent with the current project style.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_poker_mtt_final_ranking.py -p no:cacheprovider -q
```

Exit criteria:

- Final ranking is persisted before result entries.
- Existing `apply_poker_mtt_results` remains compatible or is wrapped as a legacy/admin entry point.
- Result entries can point back to `standing_snapshot_id` and `evidence_root`.

---

## Task 6: Result Projector And Lock Gate

- [ ] Write failing tests where final ranking exists but evidence is incomplete; reward windows must reject it.
- [ ] Implement `mining-service/poker_mtt_results.py` to project final-ranking rows into result entries.
- [ ] Require `rank_state=ranked`, `rated_or_practice=rated`, `human_only=true`, complete or accepted-degraded evidence, and explicit policy bundle version before `locked_at`.
- [ ] Use `locked_at` as reward-window membership time, not `created_at`.
- [ ] Preserve `evaluation_state`, `evidence_state`, `risk_flags`, and `no_multiplier_reason`.
- [ ] Persist multiplier/rating snapshots instead of relying only on `miners.poker_mtt_multiplier` mutation.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_poker_mtt_reward_gating.py -p no:cacheprovider -q
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_forecast_engine.py -k poker_mtt -p no:cacheprovider -q
```

Exit criteria:

- `FINISHED` or `evaluation_state=final` alone is not reward-ready.
- Reward window membership uses `locked_at`.
- Multiplier changes are auditable by snapshot rows/artifacts.

---

## Task 7: Reward Window Allocation And No-Positive Policy

- [ ] Write failing test for all poker MTT weights `<= 0`.
- [ ] Change poker reward-window builder so all-zero/all-negative canonical weights produce `no_positive_weight` or explicit carry-forward/forfeited state, not equal split.
- [ ] Keep `_allocate_integer_pool_by_weights` generic if needed, but call it from poker only after positive-weight eligibility is proven.
- [ ] Allocate mixed positive and non-positive rows only among positive weights.
- [ ] Fold duplicate/reentry rows to `economic_unit_id` before reward allocation and preserve audit rows.
- [ ] Ensure daily and weekly pools use explicit `ForecastSettings.poker_mtt_daily_reward_pool_amount` and `poker_mtt_weekly_reward_pool_amount`.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_forecast_engine.py -k "poker_mtt and reward_window" -p no:cacheprovider -q
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_forecast_api.py -k "poker_mtt and reward_window" -p no:cacheprovider -q
```

Exit criteria:

- No all-zero poker reward window ever silently pays an equal split.
- Positive rows receive deterministic integer allocation.
- Projection metadata records the budget disposition and policy version.

---

## Task 8: Evidence Manifests And Hand-History Hooks

- [ ] Extract canonical hashing from `forecast_engine.py` to `mining-service/canonical.py`.
- [ ] Write tests for stable roots with sorted keys, compact JSON, UTC timestamps, integer/fixed-decimal amounts, and explicit row sort keys.
- [ ] Add manifest builders in `mining-service/poker_mtt_evidence.py`.
- [ ] Add domain event schema and idempotency rules in `mining-service/poker_mtt_history.py`.
- [ ] Add hot-state storage abstraction for hand ingestion, but keep full HUD projection optional behind a flag in Phase 1.
- [ ] Build empty/stub hidden-eval and HUD manifests when policy marks them accepted-degraded.

Manifest kinds:

- `poker_mtt_final_ranking_manifest`
- `poker_mtt_hand_history_manifest`
- `poker_mtt_short_term_hud_manifest`
- `poker_mtt_long_term_hud_manifest`
- `poker_mtt_hidden_eval_manifest`
- `poker_mtt_consumer_checkpoint_manifest`
- `poker_mtt_reward_window_projection`

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_poker_mtt_evidence.py tests/mining_service/test_poker_mtt_history.py -p no:cacheprovider -q
```

Exit criteria:

- Same evidence rows produce identical roots across retries.
- Duplicate hand events do not duplicate rewards/HUD.
- Same version with different checksum goes to conflict/manual review.
- Full HUD can remain deferred, but evidence hooks are ready.

---

## Task 9: Settlement Anchor Hardening

- [ ] Write tests where poker reward window lacks final-ranking/evidence projection metadata; `retry_anchor_settlement_batch` must reject it.
- [ ] Include final-ranking root, evidence root, multiplier snapshot root, policy version, and projection root in poker settlement metadata.
- [ ] Keep anchor payload deterministic across retry.
- [ ] Add service-layer duplicate protection: same `settlement_batch_id` plus same root is idempotent; same id plus different root is conflict.
- [ ] If service-layer protection is insufficient, update `x/settlement/keeper/msg_server.go` to reject duplicate batch id with different canonical root/payload hash.
- [ ] Define post-anchor correction behavior: old root immutable, new correction or compensating batch references the original.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_forecast_engine.py -k "poker_mtt and anchor" -p no:cacheprovider -q
go test ./x/settlement/... -run 'TestAnchor' -v
```

Exit criteria:

- Poker settlement anchor cannot be built from incomplete evidence.
- Repeated retry is stable.
- Payload mismatch under the same batch id is a conflict.

---

## Task 10: End-To-End Local Sidecar Smoke

- [ ] Run a 30-player mock join smoke first.
- [ ] Run a 30-player auth-stub explicit join with real WS actions.
- [ ] Continue until tournament completion or all players are eliminated/kicked.
- [ ] Assert final standings count, no missing player rows, no duplicate member ids, one or zero alive, and complete ranking snapshot.
- [ ] Run a larger synthetic finalizer test before any real 10,000-player smoke.

Mock join run:

```bash
scripts/poker_mtt/start_local_sidecar.sh --mtt-user-count 30 --table-max-player 9
python3 scripts/poker_mtt/smoke_test.py --expected-users 30 --expected-room-count-at-least 4
python3 scripts/poker_mtt/explicit_join_harness.py --user-count 30 --table-room-count-at-least 4 --hold-seconds 60 --max-workers 30
```

Auth-stub WS run:

```bash
python3 scripts/poker_mtt/local_auth_mock.py --user-count 30 --table-max-player 9 --client-act-timeout 4
scripts/poker_mtt/start_local_sidecar.sh --mode auth --auth-host http://127.0.0.1:18090 --mtt-user-count 30 --table-max-player 9
python3 scripts/poker_mtt/non_mock_play_harness.py --user-count 30 --table-room-count-at-least 4 --until-finish --finish-timeout-seconds 1800 --max-workers 30
```

Exit criteria:

- The 30-player auth-stub WS run completes through the non-mock path.
- The harness acts only within valid WS action/chip ranges from the donor payload.
- Final standings can be projected into canonical ranking rows.

---

## Task 11: Docs And Rollout Flags

- [ ] Update sidecar contract docs with exact endpoints, Redis keys, token mode, and no-Stop policy.
- [ ] Update reward/multiplier docs to say reward windows consume locked/anchorable rows only.
- [ ] Update lepoker-auth reference docs with what was actually borrowed vs deferred.
- [ ] Update implementation status with the exact acceptance results and commands.
- [ ] Add rollout flags so poker reward windows and poker settlement anchoring can stay disabled until final-ranking/evidence tests pass.
- [ ] Document path-scoped commit guidance. Do not use `git add .` in this dirty repo.

Run:

```bash
rg -n "poker_mtt|pokermtt|final_ranking|anchorable|no_positive_weight|lepoker-auth|lepoker-gameserver" docs mining-service tests scripts
git status --short
```

Exit criteria:

- Docs agree with code behavior.
- Phase 1 disabled-by-default gates are obvious.
- Donor repos remain separate references.

---

## Full Verification Gate

Run before claiming Phase 1 is complete:

```bash
go test ./authadapter ./pokermtt/... -v
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_forecast_engine.py -k poker_mtt -p no:cacheprovider -q
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_forecast_api.py -k poker_mtt -p no:cacheprovider -q
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_poker_mtt_final_ranking.py tests/mining_service/test_poker_mtt_reward_gating.py tests/mining_service/test_poker_mtt_evidence.py tests/mining_service/test_poker_mtt_history.py -p no:cacheprovider -q
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/poker_mtt/test_complete_standings.py tests/poker_mtt/test_non_mock_actor_strategy.py tests/poker_mtt/test_prepare_local_env.py -p no:cacheprovider -q
go test ./x/settlement/... -run 'TestAnchor' -v
```

Known external gate:

```bash
make arena-db-up
ARENA_TEST_DATABASE_URL=postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable go test ./arena/rating ./arena/store/postgres ./arena/app -v
```

The arena DB gate is not a Poker MTT requirement, but it is useful before broader branch integration because the repo already has ongoing arena changes.

---

## Phase 1 Done Criteria

- Sidecar contract is frozen and tested with fake sidecar paths.
- Auth adapter and identity binding derive all mutating Poker MTT identity from `Principal`.
- One 30-player auth-stub donor MTT completes locally through real WS joins/actions.
- Final standings are canonicalized into `poker_mtt_final_rankings`.
- Result entries come from locked final-ranking rows, not live ranking.
- Reward windows select by `locked_at` and reject incomplete evidence.
- All-zero/non-positive reward weights do not equal-split.
- Settlement anchor payload includes poker projection roots and is stable across retries.
- Post-anchor correction semantics are append/supersede, not mutation.
- Docs and implementation status reflect what shipped.
- `arena/*` remains untouched by Poker MTT domain implementation except for unrelated pre-existing work.

---

## Deferred Until Phase 2+

- Porting donor Java services.
- Porting Cognito/JWKS internals into ClawChain domain code.
- Replacing donor NLH kernel.
- Full RocketMQ production consumer.
- Full DynamoDB/S3 hand-history archival.
- Full hidden-eval replay and seed-table infrastructure.
- Public ELO as a reward weight.
- Direct wallet payout.
- On-chain raw hand or per-game anchors.
- `x/reputation` writes.
- HTTP-only poker play.
- Real 10,000-user live WS load before 30-player completion and synthetic 10,000-finalizer tests are green.

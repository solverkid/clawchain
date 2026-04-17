# Poker MTT Evidence Phase 2 TDD Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute Poker MTT Evidence Phase 2 with strict TDD so completed-hand evidence, HUD, hidden eval, rating/multiplier snapshots, reward windows, and settlement anchor verification become production-grade without mixing Poker MTT into arena semantics.

**Architecture:** Keep the high-level plan in `docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2.md` as the source of product scope, and use this file as the implementation checklist. Python `mining-service` is the reward/evidence authority; Go `pokermtt/*` owns donor Redis finalization and handoff; `x/settlement` remains a tamper-evident root registry with query/verification hardening. `lepoker-auth` and `lepoker-gameserver` are donor references only.

**Tech Stack:** Python 3, FastAPI, pytest, SQLAlchemy async repository, Postgres, Go, Redis, Cosmos SDK module tests, GitNexus code graph, donor Java/Go references.

---

## Required TDD Contract

- Every production-code task below starts with one focused failing test.
- Run the test and verify it fails for the expected missing behavior before changing production code.
- If a new test passes immediately, the test is not proving new behavior; rewrite it before implementation.
- Implement the smallest production change that makes the test pass.
- Run the focused test, then the nearest existing regression slice.
- Commit after each task.
- Do not use hidden eval, ELO, or public rating as positive reward weight unless a later spec explicitly changes the frozen Phase 2 rules.

## GitNexus And Source Evidence

Use GitNexus before touching each subsystem, but treat local source as authoritative when the graph is stale.

Relevant `clawchain` graph/source findings:

- `mining-service/forecast_engine.py:ForecastMiningService` already owns Poker MTT projection, reward window construction, settlement batch creation, and chain anchor preparation.
- `mining-service/repository.py:FakeRepository` and `mining-service/pg_repository.py:PostgresRepository` have Phase 1 Poker MTT tournament/final-ranking/result methods, but no durable hand event, HUD, hidden eval, rating, multiplier snapshot, correction, or paged artifact store.
- `mining-service/poker_mtt_history.py` is in-memory only.
- `mining-service/poker_mtt_hud.py` is disabled by default and only projects basic VPIP/PFR/3-bet.
- `mining-service/poker_mtt_evidence.py` can build final-ranking and accepted-degraded stub manifests, but not real persisted hand/HUD/hidden-eval component manifests.
- `pokermtt/ranking/RedisStore.ReadLiveSnapshot` reads donor Redis keys once; it has no stable snapshot barrier yet.
- `pokermtt/ranking/Finalizer.Finalize` canonicalizes live standings and already handles many rank states, but Phase 2 needs more stability and mutation tests.
- `pokermtt/projector/BuildFinalRankingApplyPayload` builds final-ranking handoff payloads; Python still decides reward readiness.
- `proto/clawchain/settlement/v1/tx.proto` has `MsgAnchorSettlementBatch`, but no query service.
- `x/settlement/keeper/msg_server_test.go` covers idempotency, conflict, and authorized submitters; query and stricter hash validation are missing.

Donor graph boundaries:

- `lepoker-auth` is the reference for auth, MQ, hand history to DynamoDB, HUD/read models, final ranking, ELO, and MTT setup/admin.
- `lepoker-gameserver` is the reference for runtime, WebSocket, table balancing, Redis live ranking, and hand-record event production.
- Do not import donor Java structs into ClawChain domain code.

## Execution Order

The order is intentional. Do not skip ahead to hidden eval, rating, or settlement until durable evidence storage is green.

1. Durable evidence repository surface.
2. Completed-hand ingest service and manifest.
3. HUD projectors and manifests.
4. Evidence root assembly.
5. Service-owned hidden eval.
6. Rating and multiplier snapshots.
7. Go stable finalization and typed handoff.
8. Indexed reward window and correction policy.
9. Settlement query and anchor verification.
10. Admin/auth gate hardening.
11. Scale harness and observability.
12. End-to-end beta gate.

---

## Task 1: Durable Evidence Repository Surface

**Files:**
- Modify: `mining-service/models.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Test: `tests/mining_service/test_poker_mtt_history.py`
- Test: `tests/mining_service/test_poker_mtt_evidence.py`

- [ ] **Step 1: Write the failing FakeRepository test**

Append this test to `tests/mining_service/test_poker_mtt_history.py`:

```python
def test_repository_persists_hand_event_by_hand_id_version_and_checksum():
    async def scenario():
        from repository import FakeRepository

        repo = FakeRepository()
        event = hand_event(version=1, pot_amount=120)

        inserted = await repo.save_poker_mtt_hand_event(event)
        duplicate = await repo.save_poker_mtt_hand_event(hand_event(version=1, pot_amount=120))
        loaded = await repo.get_poker_mtt_hand_event("mtt-history-1:table-1:42")

        assert inserted["state"] == "inserted"
        assert duplicate["state"] == "duplicate"
        assert loaded["hand_id"] == "mtt-history-1:table-1:42"
        assert loaded["version"] == 1
        assert loaded["checksum"] == event["checksum"]
        assert loaded["payload_json"]["pot"] == 120

    import asyncio

    asyncio.run(scenario())
```

- [ ] **Step 2: Run test to verify RED**

Run:

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_history.py::test_repository_persists_hand_event_by_hand_id_version_and_checksum
```

Expected: FAIL with `AttributeError: 'FakeRepository' object has no attribute 'save_poker_mtt_hand_event'`.

- [ ] **Step 3: Implement minimal FakeRepository behavior**

In `mining-service/repository.py`, add protocol methods and FakeRepository storage:

```python
async def save_poker_mtt_hand_event(self, event: dict) -> dict: ...
async def get_poker_mtt_hand_event(self, hand_id: str) -> dict | None: ...
async def list_poker_mtt_hand_events_for_tournament(self, tournament_id: str) -> list[dict]: ...
```

Minimum FakeRepository semantics:

- primary identity is `event["identity"]["hand_id"]`
- store flattened fields plus `source_json` and `payload_json`
- same version and same checksum returns `{"state": "duplicate", ...}`
- same version and different checksum returns `{"state": "conflict", "conflict_reason": "same_version_checksum_mismatch"}`
- higher version updates
- lower version returns `{"state": "stale", ...}`

- [ ] **Step 4: Run focused tests to verify GREEN**

Run:

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_history.py
```

Expected: PASS.

- [ ] **Step 5: Add Postgres model and repository test**

Add schema objects in `mining-service/models.py`:

```text
poker_mtt_hand_events:
  hand_id primary key
  tournament_id not null
  table_id not null
  hand_no not null
  version nullable integer
  checksum not null
  event_id not null
  source_json json not null
  payload_json json not null
  ingest_state not null
  conflict_reason nullable
  created_at not null
  updated_at not null
```

Add indexes:

```text
ix_poker_mtt_hand_events_tournament_hand_no
ix_poker_mtt_hand_events_tournament_ingest_state
ix_poker_mtt_hand_events_table_hand_no
```

The Postgres test may live beside existing repository integration tests if the project already has a database fixture; otherwise keep this step pending and document the fixture gap in the commit message.

- [ ] **Step 6: Commit**

```bash
git add mining-service/models.py mining-service/repository.py mining-service/pg_repository.py tests/mining_service/test_poker_mtt_history.py tests/mining_service/test_poker_mtt_evidence.py
git commit -m "feat(pokermtt): persist completed hand evidence"
```

---

## Task 2: Completed-Hand Ingest Service And Manifest

**Files:**
- Modify: `mining-service/poker_mtt_history.py`
- Modify: `mining-service/poker_mtt_evidence.py`
- Modify: `mining-service/schemas.py`
- Modify: `mining-service/server.py`
- Modify: `mining-service/forecast_engine.py`
- Test: `tests/mining_service/test_poker_mtt_history.py`
- Test: `tests/mining_service/test_poker_mtt_evidence.py`

- [ ] **Step 1: Write failing service-level ingest test**

Append this to `tests/mining_service/test_poker_mtt_history.py`:

```python
def test_repository_backed_hand_history_store_ingests_and_lists_tournament_hands():
    async def scenario():
        from repository import FakeRepository

        store = poker_mtt_history.RepositoryHandHistoryStore(FakeRepository())
        first = await store.ingest(hand_event(version=1, pot_amount=120))
        second = await store.ingest(hand_event(version=1, pot_amount=120))
        rows = await store.list_for_tournament("mtt-history-1")

        assert first.state == "inserted"
        assert second.state == "duplicate"
        assert [row["hand_id"] for row in rows] == ["mtt-history-1:table-1:42"]

    import asyncio

    asyncio.run(scenario())
```

- [ ] **Step 2: Run RED**

Run:

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_history.py::test_repository_backed_hand_history_store_ingests_and_lists_tournament_hands
```

Expected: FAIL with `AttributeError: module 'poker_mtt_history' has no attribute 'RepositoryHandHistoryStore'`.

- [ ] **Step 3: Implement repository-backed store**

Add `RepositoryHandHistoryStore` to `mining-service/poker_mtt_history.py`. It should wrap the repository methods from Task 1 and return the existing `HandHistoryIngestResult` dataclass.

- [ ] **Step 4: Write failing hand-history manifest test**

Append this to `tests/mining_service/test_poker_mtt_evidence.py`:

```python
def test_hand_history_manifest_uses_persisted_hand_event_rows():
    generated_at = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    rows = [
        {
            "tournament_id": "mtt-evidence-1",
            "hand_id": "mtt-evidence-1:table-2:9",
            "table_id": "table-2",
            "hand_no": 9,
            "version": 1,
            "checksum": "sha256:" + "a" * 64,
            "ingest_state": "inserted",
        }
    ]

    manifest = poker_mtt_evidence.build_hand_history_manifest(
        tournament_id="mtt-evidence-1",
        rows=rows,
        policy_bundle_version="poker_mtt_v1",
        generated_at=generated_at,
    )

    assert manifest["kind"] == "poker_mtt_hand_history_manifest"
    assert manifest["evidence_state"] == "complete"
    assert manifest["row_count"] == 1
    assert manifest["row_sort_keys"] == ["tournament_id", "table_id", "hand_no", "hand_id"]
    assert manifest["manifest_root"].startswith("sha256:")
```

- [ ] **Step 5: Run RED**

Run:

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_evidence.py::test_hand_history_manifest_uses_persisted_hand_event_rows
```

Expected: FAIL with missing `build_hand_history_manifest`.

- [ ] **Step 6: Implement manifest builder and internal endpoint**

Add:

- `poker_mtt_evidence.build_hand_history_manifest(...)`
- Pydantic request model in `mining-service/schemas.py`
- internal endpoint `POST /admin/poker-mtt/hands/ingest` in `mining-service/server.py`
- service wrapper in `ForecastMiningService` only if endpoint logic would otherwise duplicate repository calls

Endpoint must require admin/internal access once Task 10 hardens auth.

- [ ] **Step 7: Run focused tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_history.py tests/mining_service/test_poker_mtt_evidence.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add mining-service/poker_mtt_history.py mining-service/poker_mtt_evidence.py mining-service/schemas.py mining-service/server.py mining-service/forecast_engine.py tests/mining_service/test_poker_mtt_history.py tests/mining_service/test_poker_mtt_evidence.py
git commit -m "feat(pokermtt): ingest completed hand evidence"
```

---

## Task 3: Short-Term And Long-Term HUD Projectors

**Files:**
- Modify: `mining-service/poker_mtt_hud.py`
- Modify: `mining-service/poker_mtt_evidence.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Test: `tests/mining_service/test_poker_mtt_hud.py`

- [ ] **Step 1: Write failing short-term HUD metric test**

Append to `tests/mining_service/test_poker_mtt_hud.py`:

```python
def test_short_term_hud_projects_cbet_showdown_and_won_showdown_idempotently():
    store = poker_mtt_hud.InMemoryHUDHotStore()
    settings = poker_mtt_hud.HUDProjectionSettings(enabled=True, window="short_term")
    event = hand_event_with_showdown()

    first = store.project_hand(event, settings=settings)
    duplicate = store.project_hand(event, settings=settings)
    rows = store.snapshot_rows(tournament_id="mtt-hud-1")
    alice = next(row for row in rows if row["miner_address"] == "claw1alice")

    assert first.state == "projected"
    assert duplicate.state == "duplicate"
    assert alice["cbet_count"] == 1
    assert alice["went_to_showdown_count"] == 1
    assert alice["won_showdown_count"] == 1
```

Add a local helper `hand_event_with_showdown()` that includes a preflop raise, flop continuation bet, showdown marker, and winner marker.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_hud.py::test_short_term_hud_projects_cbet_showdown_and_won_showdown_idempotently
```

Expected: FAIL with missing `cbet_count`, `went_to_showdown_count`, or `won_showdown_count`.

- [ ] **Step 3: Implement minimal short-term metrics**

Extend row fields in `InMemoryHUDHotStore`:

```text
cbet_count
went_to_showdown_count
won_showdown_count
unknown_hand_count
```

Do not add speculative poker stats beyond these tests.

- [ ] **Step 4: Write failing long-term snapshot test**

```python
def test_long_term_hud_manifest_is_separate_from_short_term_manifest():
    rows = [
        {
            "miner_address": "claw1alice",
            "hud_window": "long_term",
            "hands_seen": 100,
            "itm_count": 18,
            "win_count": 3,
            "profitable_count": 41,
            "confidence": 0.8,
        }
    ]

    manifest = poker_mtt_hud.build_hud_manifest(
        tournament_id="mtt-hud-1",
        rows=rows,
        policy_bundle_version="poker_mtt_policy_v1",
        generated_at="2026-04-10T12:00:00Z",
        kind=poker_mtt_hud.LONG_TERM_HUD_MANIFEST_KIND,
    )

    assert manifest["kind"] == "poker_mtt_long_term_hud_manifest"
    assert manifest["row_count"] == 1
```

- [ ] **Step 5: Run RED**

Expected: FAIL with missing `LONG_TERM_HUD_MANIFEST_KIND`.

- [ ] **Step 6: Implement long-term HUD constants and persistence hooks**

Add separate snapshot repository methods:

```python
async def save_poker_mtt_hud_snapshot(self, row: dict) -> dict: ...
async def list_poker_mtt_hud_snapshots(self, *, tournament_id: str | None = None, miner_address: str | None = None, hud_window: str | None = None) -> list[dict]: ...
```

Postgres tables:

```text
poker_mtt_short_term_hud_snapshots
poker_mtt_long_term_hud_snapshots
```

- [ ] **Step 7: Run tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_hud.py
```

- [ ] **Step 8: Commit**

```bash
git add mining-service/poker_mtt_hud.py mining-service/poker_mtt_evidence.py mining-service/repository.py mining-service/pg_repository.py tests/mining_service/test_poker_mtt_hud.py
git commit -m "feat(pokermtt): project hud evidence snapshots"
```

---

## Task 4: Evidence Root Assembly Uses Real Components

**Files:**
- Modify: `mining-service/poker_mtt_evidence.py`
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/repository.py`
- Test: `tests/mining_service/test_poker_mtt_evidence.py`

- [ ] **Step 1: Write failing integration-style evidence test**

Add a test that saves final rankings and one completed hand, then builds evidence without accepting the hand-history stub:

```python
def test_service_uses_real_hand_history_manifest_when_hand_events_exist():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await repo.save_poker_mtt_final_ranking(
            {"id": "poker_mtt_final_ranking:mtt-evidence-1:1:1", **final_ranking_row("1:1", rank=1, chip=Decimal("7000.75"))}
        )
        await repo.save_poker_mtt_hand_event(
            {
                **completed_hand_row("mtt-evidence-1", "table-1", 1),
                "source_json": {"transport": "rocketmq"},
                "payload_json": {"pot": 120},
            }
        )

        result = await service.build_poker_mtt_evidence_manifests(
            tournament_id="mtt-evidence-1",
            policy_bundle_version="poker_mtt_v1",
            accepted_degraded_kinds=["poker_mtt_hidden_eval_manifest", "poker_mtt_short_term_hud_manifest", "poker_mtt_long_term_hud_manifest"],
            now=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
        )
        artifacts = await repo.list_artifacts_for_entity("poker_mtt_tournament", "mtt-evidence-1")
        hand_manifest = next(artifact for artifact in artifacts if artifact["kind"] == "poker_mtt_hand_history_manifest")

        assert result["evidence_state"] == "accepted_degraded"
        assert hand_manifest["payload"]["evidence_state"] == "complete"
        assert hand_manifest["payload"]["row_count"] == 1

    import asyncio

    asyncio.run(scenario())
```

Use a small `completed_hand_row(...)` helper in the test file.

- [ ] **Step 2: Run RED**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_evidence.py::test_service_uses_real_hand_history_manifest_when_hand_events_exist
```

Expected: FAIL because the service always requires or emits stubs for missing component kinds.

- [ ] **Step 3: Implement component resolution**

`ForecastMiningService.build_poker_mtt_evidence_manifests(...)` should:

- always build final-ranking manifest from final ranking rows
- build hand-history manifest when persisted hand rows exist
- build HUD manifests when persisted HUD rows exist
- build hidden-eval manifest when persisted hidden-eval rows exist
- require explicit `accepted_degraded_kinds` for missing required components
- compute tournament evidence root from sorted component manifest roots

- [ ] **Step 4: Run focused tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_evidence.py tests/mining_service/test_poker_mtt_reward_gating.py
```

- [ ] **Step 5: Commit**

```bash
git add mining-service/poker_mtt_evidence.py mining-service/forecast_engine.py mining-service/repository.py tests/mining_service/test_poker_mtt_evidence.py
git commit -m "feat(pokermtt): assemble evidence roots from persisted components"
```

---

## Task 5: Service-Owned Hidden Eval

**Files:**
- Modify: `mining-service/poker_mtt_results.py`
- Modify: `mining-service/poker_mtt_evidence.py`
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/schemas.py`
- Modify: `mining-service/server.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Test: `tests/mining_service/test_poker_mtt_reward_gating.py`
- Test: `tests/mining_service/test_poker_mtt_evidence.py`

- [ ] **Step 1: Write failing reward-gate test for caller-supplied hidden score**

Add to `tests/mining_service/test_poker_mtt_reward_gating.py`:

```python
def test_legacy_apply_caller_hidden_score_does_not_unlock_reward_readiness():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(address="claw1hidden", name="hidden", public_key="pubkey", miner_version="0.4.0")

        applied = await service.apply_poker_mtt_results(
            tournament_id="mtt-hidden",
            rated_or_practice="rated",
            human_only=True,
            field_size=30,
            policy_bundle_version="poker_mtt_v1",
            results=[
                {
                    "miner_address": "claw1hidden",
                    "final_rank": 1,
                    "hidden_eval_score": 0.9,
                    "consistency_input_score": 0.2,
                }
            ],
            completed_at=datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc),
        )
        stored = applied["items"][0]

        assert stored["hidden_eval_score"] == 0.0
        assert stored["eligible_for_multiplier"] is False
        assert stored["no_multiplier_reason"] in {"missing_hidden_eval", "missing_final_ranking_ref"}

    asyncio.run(scenario())
```

- [ ] **Step 2: Run RED**

Expected: FAIL because current legacy apply may accept caller scores or fail for a different reason. The expected final behavior is service-derived hidden eval only.

- [ ] **Step 3: Implement hidden-eval entry model**

Add table:

```text
poker_mtt_hidden_eval_entries:
  id primary key
  tournament_id not null
  miner_address not null
  final_ranking_id not null
  seed_assignment_id not null
  baseline_sample_id nullable
  hidden_eval_score not null
  score_components_json not null
  evidence_root not null
  manifest_root not null
  policy_bundle_version not null
  visibility_state not null
  created_at not null
  updated_at not null
```

- [ ] **Step 4: Add service-derived finalize method**

Add a method such as:

```python
async def finalize_poker_mtt_hidden_eval(
    self,
    *,
    tournament_id: str,
    policy_bundle_version: str,
    seed_assignment_id: str,
    baseline_sample_id: str | None,
    entries: list[dict],
    now: datetime,
) -> dict:
    ...
```

It must clamp `hidden_eval_score` to `[-1.0, 1.0]`, persist rows, and emit a hidden-eval manifest root.

- [ ] **Step 5: Update result projection gate**

Reward-ready rows require:

- canonical final ranking reference
- evidence root
- locked final ranking
- hidden eval row from service-owned table, unless the policy explicitly marks hidden eval accepted-degraded
- no caller-supplied hidden eval as reward-ready provenance

- [ ] **Step 6: Run tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_reward_gating.py tests/mining_service/test_poker_mtt_evidence.py
```

- [ ] **Step 7: Commit**

```bash
git add mining-service/models.py mining-service/repository.py mining-service/pg_repository.py mining-service/poker_mtt_results.py mining-service/poker_mtt_evidence.py mining-service/forecast_engine.py mining-service/schemas.py mining-service/server.py tests/mining_service/test_poker_mtt_reward_gating.py tests/mining_service/test_poker_mtt_evidence.py
git commit -m "feat(pokermtt): derive hidden eval from service evidence"
```

---

## Task 6: Rating And Multiplier Snapshots

**Files:**
- Modify: `mining-service/models.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/schemas.py`
- Modify: `mining-service/server.py`
- Test: `tests/mining_service/test_forecast_engine.py`
- Test: `tests/mining_service/test_poker_mtt_final_ranking.py`

- [ ] **Step 1: Write failing test that Poker MTT public rating is separate**

Add to the nearest Poker MTT forecast test file:

```python
def test_poker_mtt_rating_snapshot_does_not_mutate_forecast_public_elo():
    async def scenario():
        repo = FakeRepository()
        service = forecast_engine.ForecastMiningService(repo, forecast_engine.ForecastSettings())
        await service.register_miner(address="claw1rating", name="rating", public_key="pubkey", miner_version="0.4.0")
        before = await repo.get_miner("claw1rating")

        snapshot = await service.build_poker_mtt_rating_snapshot(
            miner_address="claw1rating",
            window_start_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
            public_rating=1512.5,
            public_rank=42,
            confidence=0.72,
            policy_bundle_version="poker_mtt_v1",
            now=datetime(2026, 4, 8, 1, tzinfo=timezone.utc),
        )
        after = await repo.get_miner("claw1rating")

        assert snapshot["public_rating"] == 1512.5
        assert snapshot["public_rank"] == 42
        assert after["public_elo"] == before["public_elo"]
        assert after["public_rank"] == before["public_rank"]

    asyncio.run(scenario())
```

- [ ] **Step 2: Run RED**

Expected: FAIL with missing `build_poker_mtt_rating_snapshot`.

- [ ] **Step 3: Implement rating snapshot repository and service**

Add:

```text
poker_mtt_rating_snapshots
poker_mtt_multiplier_snapshots
```

Do not write Poker MTT rating into global forecast `miners.public_elo` or `miners.public_rank`.

- [ ] **Step 4: Write failing test that rating is not positive reward weight**

Assert reward rows and settlement weights are unchanged when only public rating differs.

- [ ] **Step 5: Implement multiplier snapshot writes**

When `poker_mtt_multiplier` changes, persist an auditable snapshot bound to:

```text
miner_address
source_result_id
multiplier_before
multiplier_after
rolling_score
policy_bundle_version
```

- [ ] **Step 6: Run tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_forecast_engine.py -k "poker_mtt and (rating or multiplier or reward)"
```

- [ ] **Step 7: Commit**

```bash
git add mining-service/models.py mining-service/repository.py mining-service/pg_repository.py mining-service/forecast_engine.py mining-service/schemas.py mining-service/server.py tests/mining_service/test_forecast_engine.py tests/mining_service/test_poker_mtt_final_ranking.py
git commit -m "feat(pokermtt): snapshot rating and multiplier state"
```

---

## Task 7: Go Stable Redis Finalization And Typed Handoff

**Files:**
- Modify: `pokermtt/ranking/redis_store.go`
- Modify: `pokermtt/ranking/finalizer.go`
- Modify: `pokermtt/projector/result_payload.go`
- Add: `pokermtt/projector/client.go`
- Test: `pokermtt/ranking/finalizer_test.go`
- Test: `pokermtt/projector/result_payload_test.go`

- [ ] **Step 1: Write failing stable snapshot test**

Add a fake Redis client that returns different hashes/zsets on consecutive reads:

```go
func TestRedisStoreReadStableSnapshotRejectsDrift(t *testing.T) {
    client := &driftingRedisClient{}
    store := ranking.RedisStore{Client: client, GameType: model.GameTypeMTT}

    _, err := store.ReadStableLiveSnapshot(context.Background(), "mtt-drift", ranking.StableSnapshotPolicy{MaxAttempts: 2})

    require.Error(t, err)
    require.Contains(t, err.Error(), "unstable poker mtt live ranking snapshot")
}
```

- [ ] **Step 2: Run RED**

```bash
go test ./pokermtt/ranking -run TestRedisStoreReadStableSnapshotRejectsDrift -v
```

Expected: build FAIL because `ReadStableLiveSnapshot` and `StableSnapshotPolicy` do not exist.

- [ ] **Step 3: Implement minimal stable snapshot read**

Read live snapshot twice, canonical-hash the source payload, and accept only if hashes match. On drift, retry up to policy limit and return an unresolved/degraded error if still unstable.

- [ ] **Step 4: Write finalizer edge tests**

Cover:

- duplicate alive/died member
- equal zset score ties
- waiting/no-show excluded from reward field size
- missing entry number
- post-lock mutation attempt emits changed root

- [ ] **Step 5: Add typed handoff client tests**

The client posts `projector.FinalRankingApplyPayload` to Python and must treat non-2xx responses as retryable/non-retryable according to status code.

- [ ] **Step 6: Run Go tests**

```bash
go test ./pokermtt/... -v
```

- [ ] **Step 7: Commit**

```bash
git add pokermtt/ranking/redis_store.go pokermtt/ranking/finalizer.go pokermtt/projector/result_payload.go pokermtt/projector/client.go pokermtt/ranking/finalizer_test.go pokermtt/projector/result_payload_test.go
git commit -m "feat(pokermtt): stabilize final ranking handoff"
```

---

## Task 8: Indexed Reward Window And Correction Policy

**Files:**
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Modify: `mining-service/models.py`
- Test: `tests/mining_service/test_forecast_engine.py`
- Test: `tests/mining_service/test_poker_mtt_reward_gating.py`

- [ ] **Step 1: Write failing repository-window test**

```python
def test_poker_mtt_reward_window_uses_indexed_locked_range_query():
    async def scenario():
        repo = FakeRepository()
        await repo.save_poker_mtt_result(locked_result("mtt-in", "claw1in", locked_at="2026-04-10T10:00:00Z"))
        await repo.save_poker_mtt_result(locked_result("mtt-out", "claw1out", locked_at="2026-04-09T10:00:00Z"))
        rows = await repo.list_poker_mtt_results_for_reward_window(
            lane="poker_mtt_daily",
            window_start_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
            window_end_at=datetime(2026, 4, 11, tzinfo=timezone.utc),
            include_provisional=False,
            policy_bundle_version="poker_mtt_v1",
        )

        assert [row["tournament_id"] for row in rows] == ["mtt-in"]

    asyncio.run(scenario())
```

- [ ] **Step 2: Run RED**

Expected: FAIL with missing `list_poker_mtt_results_for_reward_window`.

- [ ] **Step 3: Implement indexed query and replace all-result scan**

`ForecastMiningService.build_poker_mtt_reward_window(...)` must call the repository window method, not scan every Poker MTT result.

- [ ] **Step 4: Add correction table and tests**

Add:

```text
poker_mtt_corrections:
  id primary key
  target_entity_type
  target_entity_id
  previous_root
  corrected_root
  reason
  operator_id
  created_at
```

Test anchored rows are never mutated; corrections append records and produce a later batch/root.

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_forecast_engine.py -k "poker_mtt and reward_window" tests/mining_service/test_poker_mtt_reward_gating.py
```

- [ ] **Step 6: Commit**

```bash
git add mining-service/forecast_engine.py mining-service/repository.py mining-service/pg_repository.py mining-service/models.py tests/mining_service/test_forecast_engine.py tests/mining_service/test_poker_mtt_reward_gating.py
git commit -m "feat(pokermtt): query reward windows by locked evidence"
```

---

## Task 9: Settlement Anchor Query And Verification

**Files:**
- Add: `proto/clawchain/settlement/v1/query.proto`
- Modify generated files required by the repo toolchain
- Modify: `x/settlement/types/msgs.go`
- Modify: `x/settlement/keeper/msg_server.go`
- Add: `x/settlement/keeper/query_server.go`
- Modify: `x/settlement/client/cli/query.go`
- Modify: `mining-service/chain_adapter.py`
- Test: `x/settlement/keeper/msg_server_test.go`
- Test: `tests/mining_service/test_chain_adapter.py`

- [ ] **Step 1: Write failing hash validation test**

Add to settlement type tests:

```go
func TestAnchorSettlementBatchRejectsMalformedSha256Roots(t *testing.T) {
    msg := testAnchorMsg()
    msg.CanonicalRoot = "sha256:x"

    err := msg.ValidateBasic()

    require.Error(t, err)
    require.Contains(t, err.Error(), "canonical_root")
}
```

Expected RED: test fails because current validation accepts broad `sha256:` values.

- [ ] **Step 2: Tighten hash validation**

Require:

```text
^sha256:[0-9a-f]{64}$
```

Apply to all root/hash fields that claim SHA-256.

- [ ] **Step 3: Write failing query-server test**

```go
func TestQuerySettlementAnchorReturnsStoredAnchor(t *testing.T) {
    msgServer, k, ctx := setupSettlementMsgServer(t, testAnchorSubmitter())
    msg := testAnchorMsg()
    _, err := msgServer.AnchorSettlementBatch(sdk.WrapSDKContext(ctx), msg)
    require.NoError(t, err)

    queryServer := keeper.NewQueryServerImpl(k)
    resp, err := queryServer.SettlementAnchor(sdk.WrapSDKContext(ctx), &types.QuerySettlementAnchorRequest{SettlementBatchId: msg.SettlementBatchId})

    require.NoError(t, err)
    require.Equal(t, msg.CanonicalRoot, resp.Anchor.CanonicalRoot)
    require.Equal(t, msg.AnchorPayloadHash, resp.Anchor.AnchorPayloadHash)
}
```

Expected RED: missing query proto/server types.

- [ ] **Step 4: Implement query proto/server/CLI**

Expose at least:

- `SettlementAnchor(settlement_batch_id)`
- optional paged list by prefix/lane later if needed

- [ ] **Step 5: Write failing Python chain adapter verification test**

```python
def test_chain_adapter_confirms_anchor_by_querying_stored_state():
    adapter = FakeSettlementChainAdapter(
        query_response={
            "settlement_batch_id": "sb_1",
            "canonical_root": "sha256:" + "a" * 64,
            "anchor_payload_hash": "sha256:" + "b" * 64,
        }
    )

    result = adapter.confirm_settlement_anchor(
        settlement_batch_id="sb_1",
        canonical_root="sha256:" + "a" * 64,
        anchor_payload_hash="sha256:" + "b" * 64,
    )

    assert result["confirmed"] is True
```

Expected RED: no state-query confirmation path.

- [ ] **Step 6: Implement state confirmation**

`mining-service/chain_adapter.py` should distinguish:

- typed settlement anchor confirmed by query
- tx accepted but state missing
- fallback memo tx accepted but not typed settlement state
- root/hash mismatch

- [ ] **Step 7: Run tests**

```bash
go test ./x/settlement/... -v
PYTHONPATH=mining-service pytest -q tests/mining_service/test_chain_adapter.py
```

- [ ] **Step 8: Commit**

```bash
git add proto/clawchain/settlement/v1/query.proto x/settlement/types x/settlement/keeper x/settlement/client/cli mining-service/chain_adapter.py tests/mining_service/test_chain_adapter.py
git commit -m "feat(settlement): query and verify poker mtt anchors"
```

---

## Task 10: Admin/Auth Gate Hardening

**Files:**
- Modify: `mining-service/server.py`
- Modify: `mining-service/settings.py` or existing settings source
- Modify: `authadapter/donor_tokenverify.go`
- Test: `tests/mining_service/test_forecast_api.py`
- Test: `authadapter/*_test.go`

- [ ] **Step 1: Write failing API test**

Use existing FastAPI test patterns and assert Poker MTT mutation endpoints reject requests without internal/admin authorization when auth is enabled:

```python
def test_poker_mtt_hand_ingest_requires_admin_token_when_auth_enabled():
    app = create_app(...)
    response = client.post("/admin/poker-mtt/hands/ingest", json={})
    assert response.status_code == 401
```

Expected RED: endpoint is currently unprotected or does not exist yet.

- [ ] **Step 2: Implement minimal admin/internal dependency**

Use the project existing auth/test patterns. Do not create a full Cognito implementation in Phase 2.

- [ ] **Step 3: Write synthetic miner non-rewardable Go test**

Assert local mock/auth-generated identities cannot be reward-eligible unless explicitly bound to a production miner/economic unit.

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_forecast_api.py -k "poker_mtt and admin"
go test ./authadapter -v
```

- [ ] **Step 5: Commit**

```bash
git add mining-service/server.py mining-service/settings.py tests/mining_service/test_forecast_api.py authadapter
git commit -m "feat(pokermtt): gate admin evidence mutations"
```

---

## Task 11: Scale Harness And Observability

**Files:**
- Add: `scripts/poker_mtt/generate_hand_history_load.py`
- Add: `scripts/poker_mtt/run_phase2_load_check.sh`
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/server.py`
- Modify: `docs/HARNESS_API_CONTRACTS.md`
- Test: `tests/mining_service/test_poker_mtt_load_contract.py`

- [ ] **Step 1: Write failing contract test for paged artifacts**

```python
def test_large_poker_mtt_reward_window_returns_page_references_not_full_payload():
    window = build_large_window_for_test(player_count=20000)

    assert window["artifact_page_count"] > 1
    assert "miner_reward_rows_root" in window
    assert "miner_reward_rows" not in window
```

Expected RED: no paged artifact strategy yet.

- [ ] **Step 2: Implement paged artifact metadata**

Do not store 20k rows in one normal response. Store roots plus page references.

- [ ] **Step 3: Add local load generator**

Generator should produce:

- 30-player smoke MTT
- 300-player medium check
- 20k-player synthetic projection check
- about 2k early table hand-ingest burst shape

- [ ] **Step 4: Add metrics/log fields**

Minimum:

```text
poker_mtt.hand_ingest.count
poker_mtt.hand_ingest.conflict_count
poker_mtt.hud.project.duration_ms
poker_mtt.reward_window.query.duration_ms
poker_mtt.settlement_anchor.confirmation_state
```

- [ ] **Step 5: Run tests and smoke harness**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_load_contract.py
bash scripts/poker_mtt/run_phase2_load_check.sh --players 30 --local
```

- [ ] **Step 6: Commit**

```bash
git add scripts/poker_mtt docs/HARNESS_API_CONTRACTS.md mining-service/forecast_engine.py mining-service/server.py tests/mining_service/test_poker_mtt_load_contract.py
git commit -m "test(pokermtt): add evidence phase2 load harness"
```

---

## Task 12: End-To-End Beta Gate

**Files:**
- Modify: `docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md`
- Modify: `docs/PRODUCT_SPEC.md`
- Modify: `docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md`
- Modify: `docs/protocol-spec.md`
- Modify: any touched code from previous tasks if final wiring reveals gaps
- Test: all focused test suites below

- [ ] **Step 1: Write final E2E regression test**

Add one local end-to-end test that runs:

```text
hand ingest
-> hand-history manifest
-> HUD projection
-> hidden eval finalize
-> final ranking projection
-> reward window build
-> settlement batch build
-> anchor plan and query confirmation
```

Expected RED until earlier slices are wired.

- [ ] **Step 2: Make only minimal final wiring changes**

Do not introduce new product behavior in this task. This task only connects previously tested components.

- [ ] **Step 3: Run Python tests**

```bash
PYTHONPATH=mining-service pytest -q \
  tests/mining_service/test_poker_mtt_history.py \
  tests/mining_service/test_poker_mtt_hud.py \
  tests/mining_service/test_poker_mtt_evidence.py \
  tests/mining_service/test_poker_mtt_reward_gating.py \
  tests/mining_service/test_forecast_engine.py \
  tests/mining_service/test_chain_adapter.py
```

- [ ] **Step 4: Run Go tests**

```bash
go test ./authadapter ./pokermtt/... ./x/settlement/... -v
```

- [ ] **Step 5: Run repository-wide sanity checks**

```bash
git diff --check
rg -n "arena_multiplier|public_elo|x/reputation|accepted_degraded|poker_mtt_daily|poker_mtt_weekly" mining-service pokermtt x docs
```

Expected:

- no Poker MTT code writes forecast `arena_multiplier`
- no Poker MTT code writes forecast `public_elo` as canonical Poker MTT rating
- no Phase 2 code writes `x/reputation`
- accepted-degraded is explicit and policy-bound
- daily/weekly Poker MTT rewards remain rollout-gated

- [ ] **Step 6: Commit final docs/wiring**

```bash
git add docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md docs/PRODUCT_SPEC.md docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md docs/protocol-spec.md
git commit -m "docs(pokermtt): finalize evidence phase2 beta gate"
```

---

## Rollout Gate

Phase 2 is not complete until all are true:

- Completed hands are durably stored and idempotent by `hand_id`, version, and checksum.
- Evidence manifests use real persisted components where available and accepted-degraded stubs only by explicit policy.
- Short-term HUD and long-term HUD are separate.
- Hidden eval is service-owned, not caller supplied.
- Public rating/ELO is separate from forecast `public_elo` and not a positive reward weight.
- Multiplier changes have snapshot rows.
- Reward windows use indexed locked/evidence-ready queries, not all-result scans.
- Anchors are confirmed by chain state query, not only tx success.
- Admin/internal mutation endpoints are gated.
- 30-player explicit join smoke, synthetic 300-player check, and 20k projection/load checks have documented results.
- Poker MTT reward windows and settlement anchoring remain disabled by default until explicit rollout config enables them.

## Handoff Notes

- Use this plan for execution; use `docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2.md` for broader scope context.
- If a task is too large in execution, split it by the same RED/GREEN/COMMIT loop and update this plan with the split before proceeding.
- If donor behavior conflicts with ClawChain docs, ClawChain product docs win; donor repos are references, not sources of truth.

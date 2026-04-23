# Three-Lane Integration Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the current three-lane integration boundary so the active `forecast_15m` settlement path, the Arena shared-state bridge, and the Poker MTT reward-window path match the repo’s intended contracts before adding any new mining surface area.

**Architecture:** Keep the current service-led settlement shape. First repair chain confirmation and remove the direct anchor bypass, then freeze shared `miners` ownership between `mining-service` and Arena, then move forecast rewards from bare `reward_amount` aggregation to deterministic reward-component composition with actual anti-abuse enforcement, then repair the Poker MTT Postgres drift and add a real cross-service Arena bridge test, and finally align replay/proof and docs with the resulting code truth.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLAlchemy async/Postgres, pytest, Go 1.x Arena runtime/repository tests, Cosmos-style typed settlement adapter, local Postgres

---

### Status Update: 2026-04-22

Landed from this plan:

- Task 1: default verified chain confirmer
- Task 2: bare `mark-anchored` bypass removal
- Task 3: shared `miners` ownership freeze between Arena and `mining-service`
- Task 4: legacy Arena apply path collapsed behind an explicit opt-in flag
- Task 5: forecast reward components / quality-envelope composition for reward-window and settlement payload materialization
- Task 6: anti-abuse payout enforcement landed, and stale reveal duplicate gating is fixed to use refreshed service-side `economic_unit_id` truth
- Task 7: real Postgres Poker MTT loader now honors `include_provisional`, with a live Postgres regression test
- Task 8: read-triggered forecast progression coupling reduction landed; public/admin reads are snapshot-only
- Task 9: a real Arena -> shared DB -> `mining-service` bridge verification now exists across Go write-side and Python read-side tests

Still open from the original plan:

- Task 10 replay/proof and documentation alignment
- Task 11 final verification + commit/push pass

---

### Execution Prerequisites

- Use a real local Postgres instance for all DB-backed verification.
- Python service tests should run against a dedicated test DB URL, not the main dev DB.
- Go Arena integration tests should run against `ARENA_TEST_DATABASE_URL`.
- The new Arena -> `mining-service` bridge test must use a single shared dedicated DB URL for both phases.

Recommended local env for this plan:

```bash
export TEST_DATABASE_URL='postgresql://clawchain:clawchain_dev_pw@127.0.0.1:55432/clawchain_test?sslmode=disable'
export ARENA_TEST_DATABASE_URL='postgres://clawchain:clawchain_dev_pw@127.0.0.1:55432/arena_runtime_test?sslmode=disable'
export CLAWCHAIN_SHARED_TEST_DATABASE_URL='postgres://clawchain:clawchain_dev_pw@127.0.0.1:55432/clawchain_integration_test?sslmode=disable'
```

Harness rule for the new bridge test:
- the Python bridge test owns DB reset for `CLAWCHAIN_SHARED_TEST_DATABASE_URL`
- phase 1: reset schema and invoke the Go Arena writer phase against that DB
- phase 2: without resetting, boot the Python `mining-service` repository/service against the same DB and verify read/reconcile behavior
- do not share the default dev DB with the bridge test

Scope boundary for this implementation pass:
- implement forecast reward components and quality-envelope enforcement
- do not materialize daily/arena overlay membership into forecast reward windows in this pass
- keep daily/arena overlay merge as a follow-on plan after the payout contract and shared-state boundaries are correct

---

### File Map

**Modify:**
- `mining-service/server.py`
  - Wire a real default chain confirmer
  - Route or remove the `mark-anchored` bypass
  - Keep admin/operator APIs aligned with the verified chain path
- `mining-service/chain_adapter.py`
  - Add the default combined `tx(hash) + settlement query` confirmation helper
  - Reuse current query-normalization helpers instead of duplicating chain parsing
- `mining-service/forecast_engine.py`
  - Enforce verified anchoring only
  - Materialize forecast reward components instead of relying on raw `reward_amount`
  - Apply actual anti-abuse enforcement
  - Fix stale `economic_unit_id` reveal duplicate gating
  - Extend replay-proof materialization
- `mining-service/models.py`
  - Add any additive storage needed for reward components / reward intent composition if artifacts alone are insufficient
- `mining-service/repository.py`
  - Add narrow repository surfaces for reward-component persistence/readback if needed
- `mining-service/pg_repository.py`
  - Implement Postgres reward-component reads/writes if needed
  - Fix Poker MTT `include_provisional` handling in the real reward-window input path
- `mining-service/schemas.py`
  - Add additive response fields only if read surfaces need to expose `admission_release_ratio` separately from real `anti_abuse_discount`
- `tests/mining_service/test_chain_adapter.py`
  - Add combined confirmer contract coverage
- `tests/mining_service/test_forecast_engine.py`
  - Add anchor confirmation, bypass, reward-component, anti-abuse, duplicate-gating, and replay-proof tests
- `tests/mining_service/test_forecast_api.py`
  - Add API-level chain confirmation and admin route regression coverage
- `tests/mining_service/test_poker_mtt_phase3_db_load.py`
  - Add a real Postgres regression test for `include_provisional`
- `arena/store/postgres/repository.go`
  - Narrow Arena’s shared `miners` patch to the fields Arena is allowed to own
- `arena/rating/mapper.go`
  - Stop mapping global rank/reliability state into shared miner updates if Arena no longer owns those fields
- `arena/integration/runtime_flow_test.go`
  - Assert the narrowed shared-state contract
- `docs/HARNESS_BACKEND_ARCHITECTURE.md`
  - Align runtime truth after implementation
- `docs/HARNESS_API_CONTRACTS.md`
  - Align API/read-model and chain-confirmation contracts after implementation
- `docs/IMPLEMENTATION_STATUS_2026_04_10.md`
  - Update implementation truth after landing
- `docs/THREE_LANE_INTEGRATION_HARDENING_REVIEW_2026_04_21.md`
  - Mark findings resolved / updated after landing

**Create:**
- `tests/integration/test_arena_mining_bridge.py`
  - Cross-service integration check: Arena writes shared state, `mining-service` consumes it without corruption
- `tests/mining_service/test_forecast_reward_components.py`
  - Focused reward-component / anti-abuse contract tests if `test_forecast_engine.py` becomes too dense

---

### Task 1: Wire The Default Verified Chain Confirmer

**Files:**
- Modify: `mining-service/server.py`
- Modify: `mining-service/chain_adapter.py`
- Test: `tests/mining_service/test_chain_adapter.py`
- Test: `tests/mining_service/test_forecast_engine.py`

- [ ] **Step 1: Write the failing confirmation-contract tests**

Add tests that prove:
- the default runtime confirmer returns both tx confirmation data and settlement `query_response`
- tx-only success is not sufficient for a fully verified typed anchor path

- [ ] **Step 2: Run the focused tests to confirm the current runtime contract is incomplete**

Run:

```bash
python3 -m pytest tests/mining_service/test_chain_adapter.py tests/mining_service/test_forecast_engine.py -k "confirm or anchor" -q
```

Expected:
- at least one failure showing default wiring still lacks a combined tx + query confirmer

- [ ] **Step 3: Implement a single default confirmer helper in `chain_adapter.py`**

Implementation requirements:
- start from the existing tx inspection helper
- call the settlement query helper using the known `settlement_batch_id`
- return one normalized receipt carrying:
  - `confirmed`
  - `confirmation_status`
  - `height`
  - `code`
  - `raw_log`
  - `query_response`

- [ ] **Step 4: Wire `create_app()` to use the combined confirmer**

Implementation requirements:
- replace the tx-only default confirmer in `mining-service/server.py`
- keep injected custom confirmers supported for tests and explicit overrides

- [ ] **Step 5: Re-run the focused tests and confirm the verified path is now the default**

Run:

```bash
python3 -m pytest tests/mining_service/test_chain_adapter.py tests/mining_service/test_forecast_engine.py -k "confirm or anchor" -q
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```bash
git add mining-service/server.py mining-service/chain_adapter.py tests/mining_service/test_chain_adapter.py tests/mining_service/test_forecast_engine.py
git commit -m "fix: wire verified default anchor confirmer"
```

---

### Task 2: Remove The Bare `mark-anchored` Bypass

**Files:**
- Modify: `mining-service/server.py`
- Modify: `mining-service/forecast_engine.py`
- Test: `tests/mining_service/test_forecast_engine.py`
- Test: `tests/mining_service/test_forecast_api.py`

- [ ] **Step 1: Write failing service and API tests for the bypass**

Add tests that prove:
- `/admin/anchor-jobs/{id}/mark-anchored` cannot directly force terminal success without verified chain confirmation
- the operator path either calls `confirm_anchor_job_on_chain()` or returns a clear 400/409 when verification prerequisites are missing

- [ ] **Step 2: Run the focused bypass tests to verify they fail on current behavior**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -k "mark_anchor or mark_anchored" -q
```

Expected:
- FAIL because the route still force-marks `anchored`

- [ ] **Step 3: Replace the bypass with a verified operator path**

Implementation choice for this plan:
- keep the route name for operator compatibility
- internally route it through `confirm_anchor_job_on_chain()`
- reject requests that cannot produce verified confirmation

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -k "mark_anchor or mark_anchored" -q
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add mining-service/server.py mining-service/forecast_engine.py tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py
git commit -m "fix: remove direct anchor success bypass"
```

---

### Task 3: Freeze Shared `miners` Ownership Between Arena And `mining-service`

**Files:**
- Modify: `arena/store/postgres/repository.go`
- Modify: `arena/rating/mapper.go`
- Modify: `arena/integration/runtime_flow_test.go`
- Test: `arena/store/postgres/repository_test.go`
- Test: `arena/integration/runtime_flow_test.go`

- [ ] **Step 1: Write failing Go tests for shared miner ownership**

Add tests that prove Arena shared writes:
- may update `arena_multiplier`
- may not update global `model_reliability`
- may not update global `public_rank`
- may not update global `public_elo`

- [ ] **Step 2: Run the focused Go tests and confirm the current ownership leak**

Run:

```bash
go test -p 1 ./arena/store/postgres/... ./arena/integration/... -run 'Test.*(MinerCompatibility|SharedMiner|RuntimeFlow).*'
```

Expected:
- FAIL because Arena currently writes the full compatibility set into shared `miners`

- [ ] **Step 3: Narrow the Arena shared write contract**

Implementation choice for this plan:
- `mining-service` owns global `model_reliability`, `public_rank`, `public_elo`
- Arena shared writeback owns only `arena_multiplier` on `miners`
- keep Arena’s own runtime/rating tables as the authoritative source for Arena-specific ranking state

- [ ] **Step 4: Update the mapper and repository implementation to match**

Implementation requirements:
- stop mapping unsupported global fields into the shared `miners` patch
- make the shared SQL update only touch the owned field set

- [ ] **Step 5: Re-run the focused Go tests**

Run:

```bash
go test -p 1 ./arena/store/postgres/... ./arena/integration/... -run 'Test.*(MinerCompatibility|SharedMiner|RuntimeFlow).*'
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```bash
git add arena/store/postgres/repository.go arena/rating/mapper.go arena/integration/runtime_flow_test.go arena/store/postgres/repository_test.go
git commit -m "fix: narrow arena shared miner ownership"
```

---

### Task 4: Collapse Arena To One Authoritative Multiplier Contract

**Files:**
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/server.py`
- Modify: `mining-service/config.py` (only if a legacy-compat flag is needed)
- Test: `tests/mining_service/test_forecast_engine.py`
- Test: `tests/mining_service/test_forecast_api.py`

- [ ] **Step 1: Write failing tests around the legacy Python Arena apply path**

Add tests that prove:
- the Python `apply_arena_results()` path is not allowed to remain the default authoritative multiplier producer
- normal runtime must prefer the Go Arena completion path

- [ ] **Step 2: Run the focused Arena-apply tests**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -k "apply_arena_results" -q
```

Expected:
- FAIL because the legacy path is still active by default

- [ ] **Step 3: Make the authoritative contract explicit**

Implementation choice for this plan:
- Go Arena runtime remains authoritative for `arena_result_entries` and multiplier state
- Python `apply_arena_results()` becomes explicit legacy/backfill-only behavior behind a disabled-by-default `CLAWCHAIN_LEGACY_ARENA_APPLY_ENABLED` flag
- when the flag is off, the route returns a deterministic operator error (`409 legacy_arena_apply_disabled`) instead of mutating shared state

- [ ] **Step 4: Update tests to prove only the intended path remains live by default**

- [ ] **Step 5: Re-run the focused tests**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -k "apply_arena_results" -q
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```bash
git add mining-service/forecast_engine.py mining-service/server.py mining-service/config.py tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py
git commit -m "fix: make go arena path authoritative"
```

---

### Task 5: Introduce Forecast Reward Components And Quality-Envelope Composition

**Files:**
- Modify: `mining-service/models.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Modify: `mining-service/forecast_engine.py`
- Test: `tests/mining_service/test_forecast_engine.py`
- Create: `tests/mining_service/test_forecast_reward_components.py`

- [ ] **Step 1: Write failing tests for reward-component materialization**

Add tests that prove a finalized forecast reward window can deterministically produce per-miner composition rows containing:
- `fast_direct_score`
- `model_reliability`
- `ops_reliability`
- `arena_multiplier`
- `anti_abuse_discount`
- `base_score`
- `quality_envelope`
- `final_mining_score`
- `released_reward_amount`
- `held_reward_amount`

Phase boundary for this task:
- `slow_direct_score` remains out of scope for this pass because daily/arena overlay merge is intentionally deferred
- the component contract for this pass is forecast direct score plus quality-envelope and anti-abuse enforcement

- [ ] **Step 2: Run the focused tests and confirm current runtime only aggregates bare `reward_amount`**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_reward_components.py -k "reward_component or quality_envelope or reward_window" -q
```

Expected:
- FAIL because the current reward window only sums `reward_amount`

- [ ] **Step 3: Add additive storage for reward components only if artifacts are insufficient**

Implementation choice for this plan:
- prefer additive deterministic persistence
- if current artifact storage is enough, do not add a new SQL table
- if artifact-only becomes too opaque for replay/proof or query needs, add a narrow additive table rather than mutating submission semantics further

- [ ] **Step 4: Materialize reward components during reward-window build**

Implementation requirements:
- stop treating `reward_amount` on submissions as the full settlement truth
- build reward components from current miner state plus finalized task results
- keep `reward_amount` on submissions temporarily for backward compatibility, but derive settlement-grade reward rows from the composed component set

- [ ] **Step 5: Re-run focused reward-component tests**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_reward_components.py -k "reward_component or quality_envelope or reward_window" -q
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```bash
git add mining-service/models.py mining-service/repository.py mining-service/pg_repository.py mining-service/forecast_engine.py tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_reward_components.py
git commit -m "feat: compose forecast reward components"
```

---

### Task 6: Enforce Anti-Abuse State And Fix Duplicate Gating

**Files:**
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/server.py`
- Modify: `mining-service/schemas.py` (only if additive status fields are needed)
- Test: `tests/mining_service/test_forecast_engine.py`
- Test: `tests/mining_service/test_forecast_api.py`

- [x] **Step 1: Write failing tests for real anti-abuse enforcement**

Add tests that prove:
- open high-severity duplicate or cluster cases can affect reward-component composition
- `anti_abuse_discount` is no longer just the admission/probation release ratio
- miner status can distinguish `admission_release_ratio` from real anti-abuse discount if both are exposed

- [x] **Step 2: Write failing tests for stale `economic_unit_id` duplicate gating**

Add tests that prove the service uses the refreshed service-side cluster identity, not the stale API-passed value, when deciding duplicate reveal cases.

- [x] **Step 3: Run the focused tests and confirm current failures**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -k "duplicate or anti_abuse or risk_case" -q
```

Expected:
- FAIL

- [x] **Step 4: Implement actual anti-abuse enforcement**

Implementation requirements:
- derive enforcement from open risk cases
- apply it in the reward-component / payout path
- keep operator overrides meaningful by making them influence settlement outcomes, not just bookkeeping rows

- [x] **Step 5: Fix duplicate gating to use the refreshed cluster identity**

Implementation requirements:
- refresh miner/cluster truth before duplicate comparison
- use the refreshed `economic_unit_id` everywhere in the reveal-time duplicate path

- [x] **Step 6: Re-run the focused tests**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -k "duplicate or anti_abuse or risk_case" -q
```

Expected:
- PASS

- [ ] **Step 7: Commit**

Status note:
- landed without `server.py` or `schemas.py` edits
- miner status now exposes `anti_abuse_discount` separately from `admission_release_ratio`
- forecast fast settlement now discounts open cluster/duplicate risk cases in the materialized reward-component path

```bash
git add mining-service/forecast_engine.py mining-service/server.py mining-service/schemas.py tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py
git commit -m "fix: enforce anti-abuse in forecast payout"
```

---

### Task 7: Fix Poker MTT `include_provisional` In Real Postgres Mode

**Files:**
- Modify: `mining-service/pg_repository.py`
- Test: `tests/mining_service/test_poker_mtt_phase3_db_load.py`
- Test: `tests/mining_service/test_forecast_engine.py`

- [ ] **Step 1: Write or tighten the failing Postgres regression test**

Add a test that proves:
- `include_provisional=True` includes provisional eligible rows in the real Postgres loader
- `include_provisional=False` keeps the current strict-final behavior

- [ ] **Step 2: Run the focused Poker DB-load tests**

Run:

```bash
python3 -m pytest tests/mining_service/test_poker_mtt_phase3_db_load.py -k provisional -q
```

Expected:
- FAIL because the Postgres loader still hard-codes `evaluation_state == "final"`

- [ ] **Step 3: Fix the Postgres loader query**

Implementation requirements:
- match the repository contract already implied by service logic
- keep final-only behavior unchanged when `include_provisional=False`

- [ ] **Step 4: Re-run the focused Poker tests**

Run:

```bash
python3 -m pytest tests/mining_service/test_poker_mtt_phase3_db_load.py -k provisional -q
python3 -m pytest tests/mining_service/test_forecast_engine.py -k "poker_mtt and reward_window" -q
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add mining-service/pg_repository.py tests/mining_service/test_poker_mtt_phase3_db_load.py tests/mining_service/test_forecast_engine.py
git commit -m "fix: honor poker provisional reward-window inputs"
```

---

### Task 8: Reduce Remaining Read-Triggered Forecast Progression Coupling

**Files:**
- Modify: `mining-service/server.py`
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/config.py`
- Test: `tests/mining_service/test_forecast_engine.py`
- Test: `tests/mining_service/test_forecast_api.py`

- [x] **Step 1: Write failing tests that prove forecast progression has a dedicated background path**

Add tests that prove:
- task publication, settlement, reward-window build, and batch preparation can advance without public read endpoints invoking `reconcile()`
- public read paths stay read-oriented and do not remain the fallback progression trigger

- [x] **Step 2: Run the focused progression tests**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -k "reconcile_loop or progression_loop or public_read" -q
```

Observed before implementation:
- FAIL because public reads still participated in progression and there was no explicit progression loop contract

- [x] **Step 3: Add a dedicated forecast progression loop**

Implementation choice for this plan:
- add a dedicated in-process progression loop for publish/settle/release/reward-window/batch preparation
- keep the existing anchor reconcile loop for chain confirmation only
- keep explicit admin reconcile surfaces for manual recovery

- [x] **Step 4: Remove read-path dependence on `reconcile()` where safe**

Implementation requirements:
- public GET paths should no longer be the normal state-progression mechanism
- any unavoidable remaining reconcile call should be documented and covered by tests
- landed note:
  - `GET /admin/anchor-jobs/{id}/chain-tx-plan` was initially left as a high-risk exception, then removed in the follow-up slice once direct service/API regressions were in place

- [x] **Step 5: Re-run the focused progression tests**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -k "reconcile_loop or progression_loop or public_read" -q
```

Observed after implementation:
- PASS

- [ ] **Step 6: Commit**

```bash
git add mining-service/server.py mining-service/forecast_engine.py mining-service/config.py tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py
git commit -m "fix: add dedicated forecast progression loop"
```

---

### Task 9: Add A Real Arena -> `mining-service` Bridge Verification

**Files:**
- Create: `tests/integration/test_arena_mining_bridge.py`
- Modify: `arena/integration/runtime_flow_test.go`
- Modify: `tests/mining_service/test_forecast_engine.py`

- [x] **Step 1: Decide the integration harness shape and write the failing test first**

Implementation choice for this plan:
- prefer one cross-service test that proves:
  1. Arena completion persists shared state
  2. `mining-service` can read/reconcile that state
  3. no forbidden shared-field mutation or corruption occurs

- [x] **Step 2: Run the bridge test and confirm the current gap**

Run:

```bash
go test -p 1 ./arena/integration/... -run Test.*RuntimeFlow.*
python3 -m pytest tests/integration/test_arena_mining_bridge.py -q
```

Expected:
- at least one missing or failing assertion about cross-service safety

- [x] **Step 3: Implement the minimum bridge harness**

Implementation requirements:
- reuse the shared Postgres test database
- avoid hand-waved fixture-only proof
- validate both the Go write side and the Python read/reconcile side

- [x] **Step 4: Re-run the bridge verification**

Run:

```bash
go test -p 1 ./arena/integration/... -run Test.*RuntimeFlow.*
python3 -m pytest tests/integration/test_arena_mining_bridge.py -q
```

Expected:
- PASS

- [ ] **Step 5: Commit**

Status note:
- landed as a two-part bridge proof
- Go integration test forces warm eligible history so shared `miners.arena_multiplier` actually changes
- Python integration test reuses the same DB and proves `ForecastMiningService.get_miner_status()` consumes the Arena-written multiplier without mutating forecast-owned ledger fields

```bash
git add arena/integration/runtime_flow_test.go tests/integration/test_arena_mining_bridge.py tests/mining_service/test_forecast_engine.py
git commit -m "test: add arena mining-service bridge verification"
```

---

### Task 10: Align Replay/Proof Surfaces And Docs With The New Runtime Truth

**Files:**
- Modify: `mining-service/forecast_engine.py`
- Modify: `scripts/poker_mtt/build_release_review_bundle.py`
- Modify: `docs/HARNESS_BACKEND_ARCHITECTURE.md`
- Modify: `docs/HARNESS_API_CONTRACTS.md`
- Modify: `docs/IMPLEMENTATION_STATUS_2026_04_10.md`
- Modify: `docs/MINING_DESIGN.md`
- Modify: `docs/THREE_LANE_INTEGRATION_HARDENING_REVIEW_2026_04_21.md`
- Test: `tests/mining_service/test_forecast_engine.py`
- Test: `tests/poker_mtt/test_release_review_bundle.py`

- [x] **Step 1: Write failing tests for richer forecast replay proof**

Add tests that prove replay proof now carries enough structure to attest to:
- reward-component roots
- anti-abuse enforcement inputs
- the explicit deferred state of daily/arena overlay merge in this pass, rather than silently pretending those inputs already exist

- [x] **Step 2: Write failing tests for richer Poker release-review bundle lineage**

Add tests that require the bundle to include the already-available lineage roots rather than the narrow current summary only.

- [x] **Step 3: Run the focused proof/bundle tests**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py -k "replay_proof or reward_component_root" -q
python3 -m pytest tests/poker_mtt/test_release_review_bundle.py -q
```

Expected:
- FAIL

- [x] **Step 4: Implement the proof and bundle upgrades**

Implementation requirements:
- extend reward-window / artifact materialization first
- then update replay-proof read surfaces
- then widen the Poker release-review bundle contract
- landed as:
  - additive `reward_window_replay_bundle` artifact for forecast windows
  - richer `reward_window` replay proof carrying reward-component / anti-abuse lineage and explicit deferred overlay state
  - additive `lineage_roots` summary in Poker release-review bundle

- [x] **Step 5: Update architecture, API, implementation-status, and review docs**

Documentation requirements:
- remove outdated claims
- describe the actual verifier path
- describe the actual reward composition path
- describe Arena’s shared ownership boundary
- describe Poker’s provisional behavior and release-bundle lineage
- reconcile `docs/MINING_DESIGN.md` with the implemented V1 forecast reward and resolution truth

- [x] **Step 6: Re-run the focused proof/bundle tests**

Run:

```bash
python3 -m pytest tests/mining_service/test_forecast_engine.py -k "replay_proof or reward_component_root" -q
python3 -m pytest tests/poker_mtt/test_release_review_bundle.py -q
```

Expected:
- PASS

- [ ] **Step 7: Commit**

```bash
git add mining-service/forecast_engine.py mining-service/server.py scripts/poker_mtt/build_release_review_bundle.py docs/HARNESS_BACKEND_ARCHITECTURE.md docs/HARNESS_API_CONTRACTS.md docs/IMPLEMENTATION_STATUS_2026_04_10.md docs/MINING_DESIGN.md docs/THREE_LANE_INTEGRATION_HARDENING_REVIEW_2026_04_21.md tests/mining_service/test_forecast_engine.py tests/poker_mtt/test_release_review_bundle.py
git commit -m "docs: align replay proofs and integration contracts"
```

---

### Task 11: Final Verification Sweep

**Files:**
- No planned product-code changes
- Update docs only if verification exposes a truth drift

- [x] **Step 1: Run the Python verification sweep**

Run:

```bash
python3 -m pytest \
  tests/mining_service/test_chain_adapter.py \
  tests/mining_service/test_forecast_engine.py \
  tests/mining_service/test_forecast_api.py \
  tests/mining_service/test_forecast_reward_components.py \
  tests/mining_service/test_poker_mtt_phase3_db_load.py \
  tests/poker_mtt/test_release_review_bundle.py \
  tests/integration/test_arena_mining_bridge.py \
  -q
```

Expected:
- PASS

- [x] **Step 2: Run the Go verification sweep**

Run:

```bash
ARENA_TEST_DATABASE_URL='postgres://clawchain:clawchain_dev_pw@127.0.0.1:55432/arena_runtime_test?sslmode=disable' \
go test -p 1 ./arena/store/postgres/... ./arena/integration/... ./arena/rating/...
```

Expected:
- PASS

- [x] **Step 3: Run static sanity checks**

Run:

```bash
python3 -m py_compile mining-service/server.py mining-service/chain_adapter.py mining-service/forecast_engine.py mining-service/pg_repository.py
git diff --check
```

Expected:
- no syntax errors
- no whitespace / merge-marker issues

- [x] **Step 4: Update the review document’s resolution status**

Document:
- which findings are fully resolved
- which ones intentionally remain out of scope

- [ ] **Step 5: Create the final integration-hardening commit**

```bash
git add mining-service arena tests docs scripts
git commit -m "feat: harden three-lane settlement integration"
```

---

### Notes For Execution

- Do not expand product scope while doing this pass.
- Do not reopen new mining lanes.
- Do not redesign the service-led architecture while hardening the current boundary.
- Keep all changes additive or compatibility-preserving unless this plan explicitly replaces a broken path.
- Prefer small commits after every task; do not batch all tasks into one giant diff.

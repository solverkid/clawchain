# Polymarket Short-Horizon Forecast Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current forecast-first prototype into a complete, auditable `forecast_15m` Polymarket short-horizon mining path with deterministic task publishing, resolution, settlement, replay, operator controls, and chain anchoring.

**Architecture:** Keep the current FastAPI + Postgres modular monolith as the runtime authority for task lifecycle, miner submissions, reward windows, and settlement batches. Make `forecast_15m` the only reward-bearing lane that must be fully correct, keep `daily_anchor` as calibration-only scaffolding, and use `x/settlement` only to anchor canonical settlement batch roots instead of trying to move the whole protocol on-chain in one pass.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, `asyncpg`, Postgres, `requests`, `pytest`, Cosmos SDK `x/settlement`, Go tests, Next.js read surfaces

---

### Scope Lock

This plan is intentionally narrow.

Ship in this plan:

- `forecast_15m` task publish -> commit -> reveal -> resolve -> reward window -> settlement batch -> anchor job
- deterministic replay and artifact-backed audit surfaces
- operator APIs for risk decisions and settlement rebuild / retry
- typed chain anchor path hardened enough for repeated use

Do not expand in this plan:

- live-market-backed `daily_anchor`
- Arena runtime service
- staking / slashing / payout execution on-chain
- a microservice split

### File Structure

**Files:**
- Modify: `mining-service/config.py`
- Modify: `mining-service/market_data.py`
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Modify: `mining-service/models.py`
- Modify: `mining-service/schemas.py`
- Modify: `mining-service/server.py`
- Modify: `mining-service/chain_adapter.py`
- Modify: `skill/scripts/mine.py`
- Modify: `skill/scripts/status.py`
- Modify: `skill/scripts/doctor.py`
- Modify: `website/src/app/dashboard/page.tsx`
- Modify: `website/src/app/network/page.tsx`
- Modify: `website/src/app/risk/page.tsx`
- Modify: `docs/MINING_DESIGN.md`
- Modify: `docs/IMPLEMENTATION_STATUS_2026_04_10.md`
- Create: `proto/clawchain/settlement/v1/tx.proto`
- Modify: `x/settlement/types/msgs.go`
- Modify: `x/settlement/types/msgs_test.go`
- Modify: `x/settlement/keeper/msg_server.go`
- Test: `tests/mining_service/test_market_data.py`
- Test: `tests/mining_service/test_forecast_engine.py`
- Test: `tests/mining_service/test_forecast_api.py`
- Test: `tests/mining_service/test_chain_adapter.py`
- Test: `tests/mining_service/test_miner_script.py`

**Responsibilities:**
- `mining-service/config.py`: Canonical settings for publish cadence, snapshot freshness, void/degraded thresholds, reward-window sizing, and anchor retry policy.
- `mining-service/market_data.py`: Market discovery, snapshot freezing, freshness checks, reference price / outcome resolution, and degraded-task classification.
- `mining-service/forecast_engine.py`: State machine for publish, commit/reveal validation, resolution, reward-window construction, settlement-batch canonicalization, replay, and anchor-job lifecycle.
- `mining-service/repository.py`: Repository contract for task runs, submissions, reward windows, settlement batches, anchor jobs, artifacts, and risk decisions.
- `mining-service/pg_repository.py`: Postgres persistence and migration-safe field wiring for all new lifecycle and audit fields.
- `mining-service/models.py`: SQLAlchemy table definitions for the lifecycle state that the service now treats as authoritative.
- `mining-service/schemas.py`: Stable API models for miner, operator, replay, risk, and anchor surfaces.
- `mining-service/server.py`: HTTP layer for miner traffic and operator/admin flows.
- `mining-service/chain_adapter.py`: Typed anchor payload generation, readiness checks, retry classification, and fallback CLI behavior.
- `skill/scripts/mine.py`: Miner loop that only submits reward-eligible fast tasks and reacts correctly to degraded / void tasks.
- `skill/scripts/status.py`: CLI surface for reward windows, settlement status, and latest anchor state.
- `skill/scripts/doctor.py`: Pre-flight checks aligned with the forecast-first stack instead of the old challenge-mining assumptions.
- `website/src/app/dashboard/page.tsx`: Miner-facing reward, replay, and task status surface.
- `website/src/app/network/page.tsx`: Network view of batches, anchors, and aggregate protocol health.
- `website/src/app/risk/page.tsx`: Operator-facing queue surface for open risk cases and review outcomes.
- `proto/clawchain/settlement/v1/tx.proto` and `x/settlement/...`: Source-of-truth message definition and on-chain validation for settlement anchors.

### Task 1: Lock the Fast-Lane Lifecycle in Tests

**Files:**
- Test: `tests/mining_service/test_forecast_engine.py`
- Test: `tests/mining_service/test_forecast_api.py`
- Test: `tests/mining_service/test_market_data.py`

- [ ] **Step 1: Write failing tests for the missing lifecycle invariants**

Add or expand tests that cover:

- publish exactly one canonical `forecast_15m` task per asset / bucket
- task snapshot contains frozen market metadata and freshness fields
- a settled task can only enter one `reward_window_id`
- a `reward_window` can rebuild into the same canonical row set and root
- a `settlement_batch` stays stable across replay

- [ ] **Step 2: Run the targeted Python tests and confirm the red state**

Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py tests/mining_service/test_market_data.py -q`
Expected: FAIL on missing freshness, lifecycle, replay, or canonical-root behavior.

- [ ] **Step 3: Add shared fixtures for deterministic buckets and frozen snapshots**

Add helpers such as:

```python
def fixed_now() -> datetime:
    return datetime(2026, 4, 10, 3, 15, tzinfo=timezone.utc)

def make_snapshot(...):
    return {
        "snapshot_taken_at": "...",
        "binance_best_bid": ...,
        "polymarket_yes_price": ...,
    }
```

- [ ] **Step 4: Re-run the same tests until failures are only about missing implementation**

Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py tests/mining_service/test_market_data.py -q`
Expected: FAIL without fixture or import noise.

- [ ] **Step 5: Commit the red-test baseline**

```bash
git add tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py tests/mining_service/test_market_data.py
git commit -m "test: lock fast-lane lifecycle invariants"
```

### Task 2: Harden Snapshot Freshness and Reference Resolution

**Files:**
- Modify: `mining-service/config.py`
- Modify: `mining-service/market_data.py`
- Modify: `mining-service/forecast_engine.py`
- Test: `tests/mining_service/test_market_data.py`
- Test: `tests/mining_service/test_forecast_engine.py`

- [ ] **Step 1: Write failing tests for stale and degraded data paths**

Add tests for:

- stale Binance data marks task as `degraded`
- missing Polymarket discovery voids the task instead of scoring it
- resolution prefers canonical reference-price logic over a raw market poll
- task packs record why a task is reward-eligible, degraded, or void

- [ ] **Step 2: Run the focused tests to confirm the current gap**

Run: `python3 -m pytest tests/mining_service/test_market_data.py tests/mining_service/test_forecast_engine.py -q`
Expected: FAIL because the current provider and engine do not fully encode stale / degraded / void reasons.

- [ ] **Step 3: Implement the minimal data-plane hardening**

Implement:

- freshness thresholds in `ForecastSettings`
- snapshot envelopes that store `snapshot_taken_at`, source latencies, and source status
- reference-price resolution helpers that compute the exact settlement price / outcome once and reuse it
- explicit task fields such as `task_state`, `degraded_reason`, `void_reason`, and `resolution_source`

- [ ] **Step 4: Re-run market and engine tests**

Run: `python3 -m pytest tests/mining_service/test_market_data.py tests/mining_service/test_forecast_engine.py -q`
Expected: PASS

- [ ] **Step 5: Commit the data-plane slice**

```bash
git add mining-service/config.py mining-service/market_data.py mining-service/forecast_engine.py tests/mining_service/test_market_data.py tests/mining_service/test_forecast_engine.py
git commit -m "feat: harden forecast snapshot freshness and resolution"
```

### Task 3: Make Reward Windows and Settlement Batches Deterministic

**Files:**
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Modify: `mining-service/models.py`
- Test: `tests/mining_service/test_forecast_engine.py`

- [ ] **Step 1: Write failing tests for replay and rebuild determinism**

Add tests that assert:

- `rebuild_reward_window()` reproduces the same miner rows and totals
- `retry_anchor_settlement_batch()` preserves `canonical_root` when inputs are unchanged
- one risk-adjusted discount is applied exactly once per reward window
- task artifacts and reward-window artifacts reference the same canonical IDs

- [ ] **Step 2: Run the engine tests to see the failure clearly**

Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py -q`
Expected: FAIL because the current engine still mixes reconciliation phases and does not fully guarantee canonical rebuilds.

- [ ] **Step 3: Split the lifecycle into explicit engine phases**

Implement:

- publish / resolve / reward-window / settlement-batch / anchor-job methods with stable call order
- stored versions for settlement policy and artifact schema
- canonical row ordering before hashing roots
- repository fields for `policy_bundle_version`, `canonical_root`, `artifact_refs`, `void_reason`, and batch state transitions

- [ ] **Step 4: Re-run the engine suite**

Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py -q`
Expected: PASS

- [ ] **Step 5: Commit the deterministic settlement slice**

```bash
git add mining-service/forecast_engine.py mining-service/repository.py mining-service/pg_repository.py mining-service/models.py tests/mining_service/test_forecast_engine.py
git commit -m "feat: make reward windows and settlement batches deterministic"
```

### Task 4: Expose Operator Workflow and Miner Read Models

**Files:**
- Modify: `mining-service/schemas.py`
- Modify: `mining-service/server.py`
- Modify: `skill/scripts/status.py`
- Modify: `skill/scripts/doctor.py`
- Modify: `skill/scripts/mine.py`
- Modify: `website/src/app/dashboard/page.tsx`
- Modify: `website/src/app/network/page.tsx`
- Modify: `website/src/app/risk/page.tsx`
- Test: `tests/mining_service/test_forecast_api.py`
- Test: `tests/mining_service/test_miner_script.py`

- [ ] **Step 1: Write failing API and CLI tests for the operator loop**

Add tests for:

- risk-case review action endpoint
- reward-window replay and settlement-batch retry endpoints
- miner status output showing latest reward window / anchor state
- doctor warnings when the service is reachable but anchor readiness is degraded

- [ ] **Step 2: Run the targeted tests**

Run: `python3 -m pytest tests/mining_service/test_forecast_api.py tests/mining_service/test_miner_script.py -q`
Expected: FAIL because the current read models and admin surfaces are still partial.

- [ ] **Step 3: Implement the minimal operator / miner surface**

Implement:

- stable API shapes for risk decisions, replay, rebuild, and anchor retry
- CLI status output for `released_reward`, `held_reward`, latest `reward_window`, and latest `settlement_batch`
- doctor checks that point at forecast-service health instead of challenge-era assumptions
- dashboard / network / risk pages that render the new fields without inventing a second source of truth

- [ ] **Step 4: Run Python and website verification**

Run: `python3 -m pytest tests/mining_service/test_forecast_api.py tests/mining_service/test_miner_script.py -q`
Expected: PASS

Run: `npm --prefix website run build`
Expected: PASS

- [ ] **Step 5: Commit the read-surface slice**

```bash
git add mining-service/schemas.py mining-service/server.py skill/scripts/status.py skill/scripts/doctor.py skill/scripts/mine.py website/src/app/dashboard/page.tsx website/src/app/network/page.tsx website/src/app/risk/page.tsx tests/mining_service/test_forecast_api.py tests/mining_service/test_miner_script.py
git commit -m "feat: add operator workflow and miner read models"
```

### Task 5: Harden the Typed Chain Anchor Path

**Files:**
- Create: `proto/clawchain/settlement/v1/tx.proto`
- Modify: `x/settlement/types/msgs.go`
- Modify: `x/settlement/types/msgs_test.go`
- Modify: `x/settlement/keeper/msg_server.go`
- Modify: `mining-service/chain_adapter.py`
- Test: `tests/mining_service/test_chain_adapter.py`

- [ ] **Step 1: Write failing tests around typed anchor intent and on-chain validation**

Add tests that cover:

- the Python adapter and Go message use the same required fields
- retrying an already-anchored batch is idempotent and clearly classified
- invalid schema version or missing canonical root is rejected before broadcast

- [ ] **Step 2: Run Python and Go tests in the red state**

Run: `python3 -m pytest tests/mining_service/test_chain_adapter.py -q`
Expected: FAIL on missing alignment or retry handling.

Run: `go test ./x/settlement/... ./cmd/clawchaind/...`
Expected: FAIL if message validation and server handling do not match the new contract.

- [ ] **Step 3: Implement the minimal typed-anchor contract**

Implement:

- a checked-in `proto` source file that matches the generated message contract
- validation symmetry between `chain_adapter.py` and `x/settlement`
- retry / finality classification that distinguishes `ready`, `broadcast_submitted`, `anchored`, and `needs_operator_review`

- [ ] **Step 4: Re-run chain adapter and Go tests**

Run: `python3 -m pytest tests/mining_service/test_chain_adapter.py -q`
Expected: PASS

Run: `go test ./x/settlement/... ./cmd/clawchaind/...`
Expected: PASS

- [ ] **Step 5: Commit the anchoring slice**

```bash
git add proto/clawchain/settlement/v1/tx.proto x/settlement/types/msgs.go x/settlement/types/msgs_test.go x/settlement/keeper/msg_server.go mining-service/chain_adapter.py tests/mining_service/test_chain_adapter.py
git commit -m "feat: harden typed settlement anchoring"
```

### Task 6: Update Canonical Docs and Run Full Verification

**Files:**
- Modify: `docs/MINING_DESIGN.md`
- Modify: `docs/IMPLEMENTATION_STATUS_2026_04_10.md`
- Review: `docs/superpowers/plans/2026-04-10-polymarket-short-horizon-forecast-chain.md`

- [ ] **Step 1: Update the authority docs to match the shipped path**

Document:

- `forecast_15m` is the only fully-complete reward-bearing lane
- `daily_anchor` remains calibration-only
- exact operator responsibilities for risk review, replay, and anchor retry
- what remains deferred to a later plan

- [ ] **Step 2: Run the full backend verification suite**

Run: `python3 -m pytest tests/mining_service -q`
Expected: PASS

Run: `go test ./x/settlement/... ./cmd/clawchaind/...`
Expected: PASS

- [ ] **Step 3: Run the frontend verification**

Run: `npm --prefix website run build`
Expected: PASS

- [ ] **Step 4: Review the diff for drift before the final commit**

Run: `git status --short`
Expected: only intended files for the forecast-first chain completion remain changed.

- [ ] **Step 5: Commit the documentation and verification pass**

```bash
git add docs/MINING_DESIGN.md docs/IMPLEMENTATION_STATUS_2026_04_10.md
git commit -m "docs: align forecast-first chain documentation"
```

### Notes for the Implementer

- Start from the current working tree, not a fresh worktree from clean `HEAD`, because the active forecast-first files are still uncommitted locally.
- Keep `daily_anchor` code compiling, but do not spend time making it market-backed in this plan.
- Prefer extending existing modules over inventing new services.
- Preserve replay determinism: no timestamp, sort-order, or JSON-encoding drift in canonical hash inputs.
- Treat `origin` as the writable remote (`solverkid/clawchain`) and `upstream` as read-only reference.

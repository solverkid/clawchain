# Forecast-First Mining Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old challenge-based Python mining flow with a minimal runnable forecast-first mining prototype that matches the new V1 direction.

**Architecture:** Replace the old mining service with a FastAPI-based forecast-first service. Keep the protocol and engine modular, back the runtime with Postgres-oriented repositories, and use a fake repository in tests so the protocol can be validated locally even when no Postgres instance is available in the workspace.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy, `asyncpg`, existing secp256k1 auth helpers, `requests`, `pytest`

---

### Prototype Architecture and Tech-Stack Selection

**Prototype architecture choice:** `FastAPI modular monolith`

- Keep the mining service and forecast protocol in one FastAPI process for the first runnable slice.
- Split behavior by module boundaries (`config`, `schemas`, `forecast_engine`, `repository`, `pg_repository`, `server`, miner client), not by deployment units.
- Use Postgres-oriented repositories in runtime, but inject a fake repository in tests so API behavior can be verified without a local Postgres server.

**Why this is the right prototype shape now**

- It matches the current repository entrypoints, so replacement cost stays low.
- It lets us validate the new mining protocol before we pay migration cost on framework, database, and ops.
- It avoids mixing two risky changes at once: protocol rewrite and infrastructure rewrite.

**Prototype stack choice**

- API runtime: `FastAPI`
- Persistence: `Postgres` at runtime, repository fake in tests
- Query layer: `SQLAlchemy`
- Driver: `asyncpg`
- Auth/signing: existing secp256k1 helpers in `mining-service/crypto_auth.py`
- Client transport: `requests`
- Verification: `pytest` + FastAPI `TestClient`

**Target-stack alignment**

- Keep table names and engine boundaries close to the long-term harness design so the next step is adding the actual Postgres deployment and feed services, not redesigning the protocol again.
- Avoid sqlite-only assumptions and avoid coupling the API layer directly to SQLAlchemy sessions.

### File Structure

**Files:**
- Modify: `mining-service/models.py`
- Create: `mining-service/config.py`
- Create: `mining-service/schemas.py`
- Create: `mining-service/repository.py`
- Create: `mining-service/pg_repository.py`
- Modify: `mining-service/server.py`
- Modify: `skill/scripts/mine.py`
- Modify: `skill/scripts/setup.py`
- Modify: `skill/scripts/status.py`
- Modify: `skill/scripts/config.json`
- Create: `mining-service/forecast_engine.py`
- Create: `tests/mining_service/test_forecast_engine.py`
- Create: `tests/mining_service/test_forecast_api.py`

**Responsibilities:**
- `mining-service/models.py`: Define SQLAlchemy metadata and Postgres-oriented table definitions for miners + forecast task runs + forecast submissions + simple leaderboard state.
- `mining-service/config.py`: Centralize runtime settings such as database URL, lane durations, and API defaults.
- `mining-service/schemas.py`: Define FastAPI request/response models for register, active tasks, commit, reveal, stats, and miner status.
- `mining-service/repository.py`: Define repository protocol and fake in-memory implementation for tests.
- `mining-service/pg_repository.py`: Implement runtime repository against Postgres using SQLAlchemy + asyncpg.
- `mining-service/forecast_engine.py`: Generate active forecast task runs, canonicalize payloads, compute baseline probability, validate commit/reveal windows, and score settled submissions.
- `mining-service/server.py`: Expose the new V1 FastAPI app, wire dependencies, call the forecast engine on reads/writes, and serve miner status/leaderboard data.
- `skill/scripts/mine.py`: Become the default forecast mining client that registers if needed, fetches active tasks, signs commit/reveal payloads, and submits probability predictions.
- `skill/scripts/setup.py`: Make registration reliably send the miner public key in the new flow.
- `skill/scripts/status.py`: Show forecast-centric miner status instead of challenge counters.
- `skill/scripts/config.json`: Rename or add fields needed by the forecast miner loop without breaking local setup.
- `tests/mining_service/test_forecast_engine.py`: Unit-test task generation, baseline/scoring, and commit/reveal lifecycle logic.
- `tests/mining_service/test_forecast_api.py`: Integration-test the FastAPI layer against a fake repository for register, active tasks, commit, reveal, settlement, and stats.

### Task 1: Write the Failing Forecast Engine Tests

**Files:**
- Create: `tests/mining_service/test_forecast_engine.py`
- Create: `tests/mining_service/test_forecast_server.py`

- [ ] **Step 1: Write the failing forecast engine tests**

```python
def test_ensure_active_fast_task_creates_open_window(tmp_path):
    ...

def test_score_submission_rewards_edge_over_baseline():
    ...

def test_duplicate_reveal_from_same_miner_is_rejected(tmp_path):
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -q`
Expected: FAIL with import errors or missing symbols for `forecast_engine` and new server behaviors.

- [ ] **Step 3: Add minimal test fixtures**

```python
def make_temp_db(tmp_path):
    ...
```

- [ ] **Step 4: Re-run the same tests to verify red state is stable**

Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -q`
Expected: FAIL only on missing implementation, not on broken fixtures.

### Task 2: Define Postgres-Oriented Tables and Repository Contracts

**Files:**
- Modify: `mining-service/models.py`
- Create: `mining-service/repository.py`
- Create: `mining-service/pg_repository.py`
- Test: `tests/mining_service/test_forecast_engine.py`

- [ ] **Step 1: Write a failing migration/schema test if needed**

```python
def test_init_db_creates_forecast_tables(tmp_path):
    ...
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py::test_init_db_creates_forecast_tables -q`
Expected: FAIL because the forecast tables do not exist.

- [ ] **Step 3: Replace schema logic and define repository contracts**

Implement:
- SQLAlchemy table metadata for miners, forecast task runs, and forecast submissions
- repository protocol for runtime/test access
- Postgres repository skeleton using `asyncpg`
- fake repository for API tests

- [ ] **Step 4: Run the engine tests**

Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py -q`
Expected: Some schema tests pass; lifecycle and scoring tests still fail.

### Task 3: Implement the Forecast Engine

**Files:**
- Create: `mining-service/forecast_engine.py`
- Test: `tests/mining_service/test_forecast_engine.py`

- [ ] **Step 1: Write a failing scoring/lifecycle test for the next behavior**

```python
def test_settle_task_marks_best_submission_and_updates_rewards(tmp_path):
    ...
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py::test_settle_task_marks_best_submission_and_updates_rewards -q`
Expected: FAIL because settlement logic is not implemented.

- [ ] **Step 3: Implement minimal engine behavior**

Implement:
- active fast-lane task creation with deterministic IDs and time buckets
- optional daily anchor task metadata
- task payload builder
- commit hash verification
- reveal validation
- baseline probability helper
- scoring formula: improvement over baseline + light direction bonus + anti-copy cap
- settlement that updates miner rewards and reliability

- [ ] **Step 4: Run all engine tests**

Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py -q`
Expected: PASS

### Task 4: Replace the HTTP Protocol Surface with FastAPI

**Files:**
- Modify: `mining-service/server.py`
- Create: `mining-service/schemas.py`
- Create: `mining-service/config.py`
- Test: `tests/mining_service/test_forecast_api.py`

- [ ] **Step 1: Write failing HTTP tests for the new endpoints**

```python
def test_register_fetch_commit_reveal_flow(tmp_path):
    ...

def test_stats_endpoint_reports_forecast_state(tmp_path):
    ...
```

- [ ] **Step 2: Run the server tests to verify they fail**

Run: `python3 -m pytest tests/mining_service/test_forecast_api.py -q`
Expected: FAIL because the old challenge endpoints and response shapes do not match.

- [ ] **Step 3: Replace `mining-service/server.py` main path**

Implement:
- keep `miner/register`, `miner/{address}`, `stats`, `version`
- remove challenge-specific API surface from the default path
- add active forecast tasks endpoint
- add commit endpoint
- add reveal endpoint
- add FastAPI dependency wiring
- call engine reconciliation on read/write paths so tasks settle without a scheduler

- [ ] **Step 4: Run server tests**

Run: `python3 -m pytest tests/mining_service/test_forecast_api.py -q`
Expected: PASS

### Task 5: Replace the Miner Client

**Files:**
- Modify: `skill/scripts/mine.py`
- Modify: `skill/scripts/config.json`
- Modify: `skill/scripts/status.py`

- [ ] **Step 1: Write a failing client-oriented integration test if practical, otherwise define a manual verification target**

Manual target:
- miner can fetch active task
- miner can commit and reveal one prediction
- status script reflects forecast counters

- [ ] **Step 2: Replace `skill/scripts/mine.py`**

Implement:
- reuse wallet loading and public-key registration
- fetch active forecast task
- compute a simple prototype probability from provided pack fields
- sign commit/reveal payloads with secp256k1
- submit one or more forecasts per loop

- [ ] **Step 3: Update `skill/scripts/config.json` and `skill/scripts/status.py`**

Implement:
- forecast-specific miner config defaults
- status fields aligned to the new backend

- [ ] **Step 3.5: Fix `skill/scripts/setup.py` registration payload**

Implement:
- always include `public_key` derived from the wallet in register calls
- keep legacy auth secret only as optional extra metadata

- [ ] **Step 4: Run a focused manual smoke flow against a local server**

Run:
- `uvicorn server:create_app --factory --host 127.0.0.1 --port 1317`
- `python3 skill/scripts/setup.py --non-interactive`
- `python3 skill/scripts/mine.py --once`
- `python3 skill/scripts/status.py`

Expected:
- miner registers
- at least one task commit/reveal succeeds
- status endpoint shows forecast-era counters and rewards

### Task 6: Verify End-to-End and Remove Old Main-Path Assumptions

**Files:**
- Modify: `mining-service/server.py`
- Modify: `skill/scripts/mine.py`
- Modify: `skill/scripts/status.py`

- [ ] **Step 1: Run the full focused verification set**

Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_server.py -q`
Run: `python3 -m pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -q`
Expected: PASS

- [ ] **Step 2: Run the local smoke commands**

Run:
- `python3 mining-service/server.py --no-scheduler`
- `python3 skill/scripts/setup.py --non-interactive`
- `python3 skill/scripts/mine.py --once`

Expected:
- service starts
- miner loop completes without challenge-era endpoint errors

- [ ] **Step 3: Clean up leftover old-main-path strings and logs**

Check:
- no startup log still advertises challenge mining as the primary API
- no client message still says “challenge” when meaning forecast task

- [ ] **Step 4: Summarize follow-on gaps**

Record remaining gaps for later:
- real market data pack ingestion
- daily lane scoring beyond anchor-only mode
- arena multiplier integration
- admission hold / anti-abuse deeper policy engine

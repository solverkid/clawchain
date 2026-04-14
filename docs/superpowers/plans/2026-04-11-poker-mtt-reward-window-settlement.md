# Poker MTT Reward Window And Settlement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first minimal `poker mtt` daily/weekly reward-window pipeline that aggregates persisted poker MTT results into reward windows, creates settlement batches, and produces chain anchor input using the existing settlement machinery.

**Architecture:** Reuse the shared `reward_windows`, `settlement_batches`, `anchor_jobs`, artifact, and chain-tx-plan flow already used by forecast tasks. Add a manual poker-MTT-specific reward-window builder that groups `poker_mtt_result_entries` by an explicit time range, stores tournament ids in the shared reward-window membership field, and teaches settlement retry to materialize poker-specific miner reward rows.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLAlchemy async Postgres repository, existing fake repository, pytest

---

### File Map

**Modify:**
- `mining-service/repository.py`
  - Add list-all poker MTT result repository surface
- `mining-service/pg_repository.py`
  - Implement list-all poker MTT result reads
- `mining-service/schemas.py`
  - Add admin request model for poker MTT reward-window build
- `mining-service/forecast_engine.py`
  - Add poker MTT reward-window builder
  - Add poker-lane settlement-row materialization inside retry-anchor flow
- `mining-service/server.py`
  - Add `/admin/poker-mtt/reward-windows/build`
- `tests/mining_service/test_forecast_engine.py`
  - Add poker MTT reward-window / anchor tests
- `tests/mining_service/test_forecast_api.py`
  - Add poker MTT reward-window API test

---

### Task 1: Repository Surface

**Files:**
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`

- [ ] **Step 1: Write failing service test that needs list-all poker MTT results**
- [ ] **Step 2: Add repository protocol and fake repository support**
- [ ] **Step 3: Add Postgres read path for all poker MTT results**
- [ ] **Step 4: Run focused engine test to make sure repository surface is sufficient**

Run:

```bash
pytest tests/mining_service/test_forecast_engine.py -k poker_mtt_reward_window -v
```

---

### Task 2: Reward Window Builder

**Files:**
- Modify: `mining-service/schemas.py`
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/server.py`
- Test: `tests/mining_service/test_forecast_engine.py`
- Test: `tests/mining_service/test_forecast_api.py`

- [ ] **Step 1: Write failing tests for poker MTT reward-window build**
- [ ] **Step 2: Add request schema with lane, time range, and reward pool**
- [ ] **Step 3: Implement manual poker MTT reward-window build**
- [ ] **Step 4: Ensure shared settlement batch creation refreshes from the built reward window**
- [ ] **Step 5: Run focused tests and make sure reward-window build passes**

Run:

```bash
pytest tests/mining_service/test_forecast_engine.py -k poker_mtt_reward_window -v
pytest tests/mining_service/test_forecast_api.py -k poker_mtt_reward_window -v
```

---

### Task 3: Poker-Lane Settlement Anchor Input

**Files:**
- Modify: `mining-service/forecast_engine.py`
- Test: `tests/mining_service/test_forecast_engine.py`

- [ ] **Step 1: Write failing test for poker-lane retry-anchor payload**
- [ ] **Step 2: Branch settlement materialization by lane and build poker miner reward rows**
- [ ] **Step 3: Reuse existing anchor artifacts and chain-tx-plan machinery**
- [ ] **Step 4: Run focused tests and make sure anchor payload is stable**

Run:

```bash
pytest tests/mining_service/test_forecast_engine.py -k "poker_mtt and anchor" -v
```

---

### Task 4: Verification

**Files:**
- Modify: `docs/IMPLEMENTATION_STATUS_2026_04_10.md` (only if needed after landing)

- [ ] **Step 1: Run focused engine and API test files**
- [ ] **Step 2: Review lane naming and shared-field reuse (`task_run_ids` carrying tournament ids)**
- [ ] **Step 3: Summarize what remains open in payout economics**

Run:

```bash
pytest tests/mining_service/test_forecast_engine.py tests/mining_service/test_forecast_api.py -v
```

# Poker MTT Results Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first minimal `poker mtt` result pipeline so the system can accept tournament results, compute total score and a bounded `poker_mtt_multiplier`, persist the records, and expose the updated miner status.

**Architecture:** Mirror the existing `arena` result flow with a parallel `poker mtt` path that keeps its own field names and storage models. Persist structured `poker mtt` results in Postgres/shared repository, update a dedicated `poker_mtt_multiplier` on miners, and expose a management endpoint for applying results without touching hand-history storage yet.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLAlchemy async Postgres repository, existing fake repository, pytest

---

### File Map

**Modify:**
- `mining-service/models.py`
  - Add `poker_mtt_multiplier` on `miners`
  - Add `poker_mtt_tournaments`
  - Add `poker_mtt_result_entries`
- `mining-service/repository.py`
  - Extend repository protocol and fake repository for poker MTT tournament/result persistence
- `mining-service/pg_repository.py`
  - Add row/value helpers and Postgres persistence methods for poker MTT tables
- `mining-service/schemas.py`
  - Add request models for poker MTT result application
- `mining-service/forecast_engine.py`
  - Initialize `poker_mtt_multiplier`
  - Add `apply_poker_mtt_results`
  - Include `poker_mtt_multiplier` in miner status
- `mining-service/server.py`
  - Add `/admin/poker-mtt/results/apply`
- `tests/mining_service/test_forecast_engine.py`
  - Add focused poker MTT service tests
- `tests/mining_service/test_forecast_api.py`
  - Add focused poker MTT API test

---

### Task 1: Schema And Repository Surface

**Files:**
- Modify: `mining-service/models.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`

- [ ] **Step 1: Add failing repository-level tests through service usage**
- [ ] **Step 2: Add `poker_mtt_multiplier` and new poker MTT tables to `models.py`**
- [ ] **Step 3: Extend repository protocol and fake repository with poker MTT save/list methods**
- [ ] **Step 4: Extend `pg_repository.py` with helper conversions and Postgres save/list methods**
- [ ] **Step 5: Run focused tests and make sure schema/repository surface passes**

Run:

```bash
pytest tests/mining_service/test_forecast_engine.py -k poker_mtt -v
```

---

### Task 2: Forecast Service Poker MTT Apply Flow

**Files:**
- Modify: `mining-service/forecast_engine.py`
- Test: `tests/mining_service/test_forecast_engine.py`

- [ ] **Step 1: Write failing tests for practice/rated poker MTT flows**
- [ ] **Step 2: Add `poker_mtt_multiplier` miner initialization**
- [ ] **Step 3: Implement `apply_poker_mtt_results` with weighted total score**
- [ ] **Step 4: Implement bounded multiplier update after minimum sample threshold**
- [ ] **Step 5: Expose `poker_mtt_multiplier` in miner status**
- [ ] **Step 6: Run focused engine tests and make sure they pass**

Run:

```bash
pytest tests/mining_service/test_forecast_engine.py -k "poker_mtt or arena_multiplier" -v
```

---

### Task 3: API Surface

**Files:**
- Modify: `mining-service/schemas.py`
- Modify: `mining-service/server.py`
- Test: `tests/mining_service/test_forecast_api.py`

- [ ] **Step 1: Write failing API test for admin poker MTT result application**
- [ ] **Step 2: Add request schemas with explicit score components**
- [ ] **Step 3: Add `/admin/poker-mtt/results/apply` route**
- [ ] **Step 4: Run focused API tests and make sure they pass**

Run:

```bash
pytest tests/mining_service/test_forecast_api.py -k poker_mtt -v
```

---

### Task 4: Verification

**Files:**
- Modify: `docs/IMPLEMENTATION_STATUS_2026_04_10.md` (only if needed after code lands)

- [ ] **Step 1: Run focused engine and API tests together**
- [ ] **Step 2: Review changed files for naming/field boundary consistency**
- [ ] **Step 3: Summarize what landed and what remains for reward windows / settlement**

Run:

```bash
pytest tests/mining_service/test_forecast_engine.py -k poker_mtt -v
pytest tests/mining_service/test_forecast_api.py -k poker_mtt -v
```

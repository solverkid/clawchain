# Poker MTT Payout-Grade Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Poker MTT final ranking payout-grade by preserving donor display ties while enforcing unique contiguous payout ranks before reward projection and settlement.

**Architecture:** Keep donor-compatible rank evidence in `display_rank` / `source_rank`, and define existing `rank` as the unique payout rank used by `poker_mtt_result_entries.final_rank`. Enforce the invariant twice: once in the Go finalizer output and again in mining-service schema/service projection so DB or admin bypasses cannot leak tied ranks into rewards.

**Tech Stack:** Go `pokermtt/ranking` and `pokermtt/projector`; Python Redis helper; FastAPI/Pydantic mining-service; SQLAlchemy model definitions; pytest and Go tests.

---

## File Structure

- Modify `pokermtt/ranking/types.go`
  - Add `DisplayRank`, `RankBasis`, and `RankTiebreaker` fields to `FinalRankingRow`.
- Modify `pokermtt/ranking/finalizer.go`
  - Preserve donor display rank separately from payout rank.
  - Assign unique payout ranks after duplicate economic-unit collapse.
  - Strip payout rank from non-ranked rows.
  - Validate unique contiguous payout ranks.
- Modify `scripts/poker_mtt/complete_standings.py`
  - Add payout `rank` while preserving donor `display_rank`.
- Modify `mining-service/schemas.py`
  - Add final-ranking evidence fields.
  - Add model-level validation for payout rank uniqueness and contiguity.
- Modify `mining-service/models.py`
  - Add nullable DB columns for `display_rank`, `rank_basis`, `rank_tiebreaker`.
- Modify `mining-service/pg_repository.py`
  - Add idempotent migration columns for the new final-ranking fields.
- Modify `mining-service/forecast_engine.py`
  - Revalidate persisted/canonicalized rows before projection.
- Modify `tests/fixtures/poker_mtt/final_ranking_projection_from_go.json`
  - Include the new rank evidence fields.
- Modify tests:
  - `pokermtt/ranking/finalizer_test.go`
  - `tests/poker_mtt/test_complete_standings.py`
  - `tests/mining_service/test_poker_mtt_final_ranking.py`
  - `tests/mining_service/test_poker_mtt_final_ranking_contract.py`
  - `tests/mining_service/test_poker_mtt_reward_gating.py`

## Task 1: Go Finalizer TDD

**Files:**
- Modify: `pokermtt/ranking/finalizer_test.go`
- Modify: `pokermtt/ranking/types.go`
- Modify: `pokermtt/ranking/finalizer.go`

- [ ] **Step 1: Write failing test for tied donor died display rank**

Add a test where one survivor is rank 1 and two died rows have the same donor `rank`. Assert:

- tied rows have same `DisplayRank`
- tied rows have unique `Rank`
- higher `startChip` gets better payout rank
- ranks across ranked rows are exactly `1..N`

- [ ] **Step 2: Verify red**

Run:

```bash
go test ./pokermtt/ranking -run TestFinalizerAssignsUniquePayoutRanksForTiedDiedDisplayRank -v
```

Expected: fail because `DisplayRank` / payout-rank split does not exist yet.

- [ ] **Step 3: Implement finalizer fields and unique rank assignment**

Add `DisplayRank`, `RankBasis`, and `RankTiebreaker`.

Finalizer rules:

- Alive rows: `display_rank = rank`, `rank_basis = alive_zset_score`.
- Died rows: first compute donor display rank; then assign unique payout rank by `display_rank ASC`, `start_chip DESC`, `member_id ASC`.
- Non-ranked rows: `rank = nil`, `display_rank` may remain if useful for audit.
- After duplicate collapse, reassign ranked payout ranks to `1..ranked_count`.

- [ ] **Step 4: Verify green**

Run:

```bash
go test ./pokermtt/ranking -v
```

Expected: pass.

## Task 2: Redis Complete Standings Helper TDD

**Files:**
- Modify: `tests/poker_mtt/test_complete_standings.py`
- Modify: `scripts/poker_mtt/complete_standings.py`

- [ ] **Step 1: Write failing test for `display_rank` ties plus unique `rank`**

Extend `test_build_complete_standings_preserves_tied_died_rank_groups()` to assert:

- users in the same donor group keep duplicate `display_rank`
- payout `rank` values are unique and contiguous
- pending rows have null payout rank

- [ ] **Step 2: Verify red**

Run:

```bash
python3 -m pytest tests/poker_mtt/test_complete_standings.py -q
```

Expected: fail because output has no payout `rank`.

- [ ] **Step 3: Implement `assign_unique_payout_ranks()`**

Add helper to assign payout ranks to alive/died rows only, sorted by:

```text
display_rank ASC
start_chip DESC for tied died display groups
member_id ASC
```

- [ ] **Step 4: Verify green**

Run:

```bash
python3 -m pytest tests/poker_mtt/test_complete_standings.py -q
```

Expected: pass.

## Task 3: Mining-Service Schema/API TDD

**Files:**
- Modify: `tests/mining_service/test_poker_mtt_final_ranking.py`
- Modify: `tests/mining_service/test_poker_mtt_final_ranking_contract.py`
- Modify: `mining-service/schemas.py`
- Modify: `mining-service/models.py`
- Modify: `mining-service/pg_repository.py`

- [ ] **Step 1: Write failing schema tests**

Add tests that build `ApplyPokerMTTFinalRankingProjectionRequest` with:

- duplicate ranked payout ranks
- skipped ranked payout ranks
- non-ranked row carrying payout rank

Expected: Pydantic validation error with `non_unique_payout_rank`, `non_contiguous_payout_rank`, or `non_ranked_row_has_payout_rank`.

- [ ] **Step 2: Verify red**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_poker_mtt_final_ranking.py tests/mining_service/test_poker_mtt_final_ranking_contract.py -q
```

Expected: fail because validation is missing.

- [ ] **Step 3: Add schema fields and validators**

Add optional fields to `PokerMTTFinalRankingRow`:

- `display_rank`
- `rank_basis`
- `rank_tiebreaker`

Add `@model_validator(mode="after")` to `ApplyPokerMTTFinalRankingProjectionRequest`.

- [ ] **Step 4: Add DB model/migration fields**

Add columns to `poker_mtt_final_rankings` and idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements in `PostgresRepository.ensure_schema`.

- [ ] **Step 5: Verify green**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_poker_mtt_final_ranking.py tests/mining_service/test_poker_mtt_final_ranking_contract.py -q
```

Expected: pass.

## Task 4: Reward Projection Fail-Closed TDD

**Files:**
- Modify: `tests/mining_service/test_poker_mtt_reward_gating.py`
- Modify: `mining-service/forecast_engine.py`

- [ ] **Step 1: Write failing service test**

Seed two persisted ranked rows with complete evidence and duplicate payout `rank`. Register both miners. Call `project_poker_mtt_final_rankings()`.

Expected: `ValueError("non_unique_payout_rank...")`.

- [ ] **Step 2: Verify red**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_poker_mtt_reward_gating.py::test_final_ranking_projection_rejects_duplicate_payout_ranks -q
```

Expected: fail because service currently projects both rows.

- [ ] **Step 3: Implement persisted-row validation**

After `_canonical_poker_mtt_projection_rows()`, validate:

- ranked rows have ranks
- ranked ranks are unique
- ranked ranks are contiguous `1..ranked_count`
- non-ranked rows do not carry payout rank
- `field_size >= ranked_count`

- [ ] **Step 4: Verify green**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service/test_poker_mtt_reward_gating.py -q
```

Expected: pass.

## Task 5: Cross-Language Fixture And Full Verification

**Files:**
- Modify: `pokermtt/projector/result_payload_test.go`
- Modify: `tests/fixtures/poker_mtt/final_ranking_projection_from_go.json`

- [ ] **Step 1: Update fixture generation/expected payload**

Make the Go fixture include `display_rank`, `rank_basis`, and `rank_tiebreaker` for ranked rows.

- [ ] **Step 2: Run targeted tests**

Run:

```bash
go test ./pokermtt/ranking ./pokermtt/projector -v
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/poker_mtt/test_complete_standings.py tests/mining_service/test_poker_mtt_final_ranking.py tests/mining_service/test_poker_mtt_final_ranking_contract.py tests/mining_service/test_poker_mtt_reward_gating.py -p no:cacheprovider -q
```

Expected: pass.

- [ ] **Step 3: Run phase-level verification**

Run:

```bash
make test-poker-mtt-phase3-fast
```

Expected: pass, or document the exact unrelated failure if the gate is wider than this change.

- [ ] **Step 4: Document final outcome**

Update the final response with:

- whether current real-time ranking is correct
- whether current final ranking is reward-safe after the change
- test commands run
- any remaining non-blocking production gates


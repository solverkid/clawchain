# Poker MTT Phase 3 Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` when implementing this plan. Keep the scope donor-first and subtractive.

**Goal:** Deliver the minimal donor-compatible Phase 3 path for `poker mtt`: locked final ranking, completed-hand evidence, reward identity binding, bounded reward windows, budget reservation artifact, and on-chain anchor confirmation.

**Architecture:** `lepoker-gameserver` stays the live runtime and WS source of truth. `lepoker-auth` stays a donor reference for token verify shape, MQ hand-history flow, ranking separation, and HUD projection boundaries. ClawChain owns the finalizer, evidence readiness, reward window builder, settlement batch construction, and chain confirmation proof.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy async Postgres repository, Redis, donor MQ input or equivalent adapter, local harness scripts, pytest, GitNexus code graph

---

## Source Inputs

- `docs/POKER_MTT_PHASE3_PRODUCTION_READINESS_SPEC.md`
- `docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md`
- `docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md`
- `docs/POKER_MTT_SIDECAR_INTEGRATION.md`
- `docs/PRODUCT_SPEC.md`
- `docs/MINING_DESIGN.md`
- donor repos:
  - `lepoker-gameserver`
  - `lepoker-auth`

Current local anchors:

- `mining-service/models.py`
- `mining-service/repository.py`
- `mining-service/pg_repository.py`
- `mining-service/forecast_engine.py`
- `mining-service/server.py`
- `mining-service/schemas.py`
- `scripts/poker_mtt/*`
- `tests/mining_service/*`
- `tests/poker_mtt/*`

---

## Hard Invariants

- Do not move `poker mtt` into `arena/*`.
- Do not replatform donor runtime into ClawChain.
- Do not let admin apply APIs become the reward-bearing mainline.
- Do not use runtime token validity as reward identity.
- Do not reward from live ranking.
- Do not block Phase 3 on `x/reputation`, public ELO, or positive hidden eval.
- Do not use live 20k tournament execution as the only scale proof.
- Do not use `/v1/snapshot`, ws `currentMTTRanking`, or new standings HTTP APIs as reward truth.

---

## Workstream 1: Canonical Contracts And Storage

**Files:**

- Modify: `mining-service/models.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Modify: `mining-service/schemas.py`
- Test: `tests/mining_service/*`

- [x] Add explicit storage for locked final rankings, reward identity, MQ checkpoints, and settlement confirmation metadata
- [x] Separate donor `display_rank` / `source_rank` from ClawChain `payout_rank`
- [x] Add `rank_state`, `eligibility_state`, `exclusion_reason`, `locked_at`, `economic_unit_id`, `reward_owner_address`, `reward_identity_state`, `chain_confirmation_state`
- [x] Add repository methods that read only locked / eligible rows for window build
- [x] Add tests for rank-state gating and deterministic payout-rank fallback

Exit criteria:

- storage shape can represent reward-ready vs non-settleable rows
- repository surface no longer needs ad hoc full scans over provisional rows

---

## Workstream 2: Final Ranking Locker

**Files:**

- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/server.py`
- Test: `tests/poker_mtt/test_complete_standings.py`
- Test: `tests/mining_service/*`

- [x] Introduce a finalizer step that locks donor final standings before reward projection
- [x] Freeze the only approved ranking inputs as donor Redis standings or donor-auth persisted final-ranking artifacts derived from them
- [x] Preserve donor display/source ordering while generating unique contiguous `payout_rank`
- [x] Exclude no-show, waiting, cancelled, and failed-to-start samples from eligible reward rows
- [x] Exclude joins after the configured late-join grace window from eligible reward rows; current default is `600` seconds
- [x] Canonicalize in this order: donor ranking -> numeric rank filter -> re-entry fold -> economic-unit dedupe -> reward-identity bind -> `payout_rank` assignment -> lock
- [x] Mark missing/conflicting reward identity as non-settleable without inventing new clustering heuristics
- [x] Add replay/idempotency tests for the same standing snapshot

Exit criteria:

- same donor standing snapshot always produces the same locked ranking rows
- reward rows are built only from locked final standings

---

## Workstream 3: Completed-hand Evidence Mainline

**Files:**

- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Modify: `scripts/poker_mtt/prepare_local_env.py`
- Modify: `scripts/poker_mtt/non_mock_play_harness.py`
- Test: `tests/poker_mtt/*`
- Test: `tests/mining_service/*`

- [x] Define a donor-shaped completed-hand event contract with monotonic `version`; treat checksum as optional hardening only if upstream provides it
- [x] Add raw hand upsert before any HUD or reward projection
- [x] Add `POKER_RECORD_STANDUP_TOPIC` companion handling for bust / stand-up end-state
- [x] Add MQ checkpoint, stale-lower-version ignore, idempotency, and DLQ path
- [x] Add freshness watermark used by finalization/readiness gates
- [x] Prove `POKER_RECORD_TOPIC` parity locally; keep `POKER_RECORD_CALCULATE_TOPIC` and other donor topics replay-only

Exit criteria:

- raw hand evidence is durable before reward projection
- poison/conflict messages cannot silently corrupt locked results

---

## Workstream 4: Reward Window And Budget Reservation

**Files:**

- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/server.py`
- Modify: `mining-service/schemas.py`
- Test: `tests/mining_service/test_forecast_engine.py`
- Test: `tests/mining_service/test_forecast_api.py`

- [x] Freeze one minimal reward policy for daily / weekly windows
- [x] Build windows only from locked eligible rows
- [x] Key reward-window membership by `locked_at` only; watermark delays locking but never releases provisional rows into settlement windows
- [x] Add explicit lane-cap / budget-reservation data carried into settlement prep
- [x] Carry `final_ranking_root`, `hand_history_evidence_root`, and `reward_identity_root` in the reward-window artifact
- [x] Aggregate settlement-facing reward rows over reward-owned economic units, not raw donor entrants
- [x] Ensure rebuild is idempotent and stable for unchanged inputs
- [x] Reject windows with missing final-ranking root, reward identity, or evidence watermark
- [x] Freeze `no_positive_weight` behavior so empty-positive windows hold instead of implicitly equal-splitting

Exit criteria:

- reward-window build is bounded, stable, and auditable
- zero innovation on multiplier/payout logic inside Phase 3 mainline

---

## Workstream 5: Settlement Query Confirmation

**Files:**

- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Test: `tests/mining_service/*`

- [x] Extend settlement metadata so completion depends on on-chain anchor query confirmation, not submit only
- [x] Store batch/root/payload-hash/total-reward confirmation payloads for audit
- [x] Keep correction path append-only or superseding, never in-place root mutation
- [x] Enforce: same batch ID + same root is idempotent; same batch ID + different root is conflict
- [x] Add retry behavior for submit-success / query-mismatch cases
- [x] Add tests for idempotent repeat confirmation and mismatch rejection

Exit criteria:

- anchored means query-confirmed
- tx hash alone is never treated as final proof

---

## Workstream 6: Release Gates And Harness

**Files:**

- Modify: `scripts/poker_mtt/non_mock_play_harness.py`
- Modify: `scripts/poker_mtt/explicit_join_harness.py`
- Add: `scripts/poker_mtt/burst_harness.py`
- Modify: `scripts/poker_mtt/smoke_test.py`
- Test: `tests/poker_mtt/*`
- Doc: `docs/ARENA_MTT_EDGE_CASES_AND_HARDENING.md` if new runtime findings appear

- [x] Prove non-mock donor gameserver runtime plus local `token_verify` stub 30-player real finish with explicit joins and WS play
- [x] Capture minimal donor contract proof: inner-port start/get room, outer-port join/ws, terminal finish, locked ranking, reward window, query-confirmed settlement
- [x] Record action coverage, payout-rank uniqueness, elimination order, `timeout_no_action`, Tencent outbound count, and MQ failure signatures in the evidence pack
- [x] Build donor-shaped 2,000-table / 20k-user burst harness for completed-hand ingest, reward build, and settlement prep
- [x] Record burst metrics: MQ lag high-water mark, checkpoint advance, DLQ/conflict totals, `POKER_RECORD_TOPIC` and stand-up ingest totals, reward-window query latency

Evidence captured on 2026-04-20:

- runtime artifact: `build/poker-mtt/non-mock-play-evidence-r5.json`
- settlement replay artifact: `build/poker-mtt/non-mock-release-evidence-r5.json`
- same-run emitted-MQ replay artifact: `build/poker-mtt/non-mock-emitted-mq-replay-r5.json`
- operator release pack: `build/poker-mtt/non-mock-release-pack-r5.json`
- tournament: `phase3-non-mock-30-r5-1776679820`
- `joined_users=30`, `received_current_mtt_ranking=30`, `sent_action_total=297`
- `timeout_no_action_total=30`
- final standings converged to `snapshot_count=30`, `alive_count=1`, `died_count=29`, `pending_count=0`, `standings_count=30`
- winner `user_id=13`, runner-up `user_id=28`
- main donor log recorded `roomID_not_correct=0`, `onLooker_action=0`
- recorder log still emitted `roomID not correct` text; treat it as recorder noise, not runtime rejection truth
- same-run donor `POKER_RECORD_TOPIC` / `POKER_RECORD_STANDUP_TOPIC` payloads were broker-acked and replayed through the ClawChain projector with zero DLQ
- replay harness drove the same donor sample through `apply -> finalize -> reward_window -> settlement_batch -> broadcast -> confirm-chain`
- donor main-log emitted payloads were replayed through the same completed-hand projector path; `56/56` emitted payloads were accepted and rooted into the finalizer
- replay proof finished with `reward_window.state=finalized`, `settlement_batch.chain_confirmation_state=confirmed`, `anchor_job.state=anchored`
- release pack now bundles runtime realism, release-chain proof, same-run emitted-MQ replay, broker-acked live MQ/projector proof, and 20k burst/projector proof into one operator-facing artifact with `phase3_release_pack_complete=true`

Exit criteria:

- release evidence exists for both 30-player runtime realism and 20k-scale burst handling
- Phase 3 does not ship on mock-only proof

---

## Out Of Scope For This Plan

- `x/reputation` implementation
- hidden seed table / shadow eval expansion
- new public ELO weighting
- new multiplier experiments
- donor admin/control-plane parity beyond what the harness needs

---

## Verification Strategy

Before execution is called complete:

- run focused unit tests for final ranking, reward-window gating, and settlement confirmation
- run local donor-backed 30-player harness to terminal state
- run donor-shaped burst harness and collect logs / metrics
- diff docs against product/design docs to ensure no scope contradiction remains

Representative commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/mining_service -k "poker_mtt or settlement" -q
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/poker_mtt -q
python3 scripts/poker_mtt/non_mock_play_harness.py
python3 scripts/poker_mtt/burst_harness.py
python3 scripts/poker_mtt/smoke_test.py
```

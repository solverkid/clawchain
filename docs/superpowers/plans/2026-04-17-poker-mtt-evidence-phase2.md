# Poker MTT Evidence Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the evidence-backed Poker MTT rewards beta: completed-hand evidence, deterministic HUD/hidden-eval/rating projectors, stronger final-ranking handoff, scalable reward windows, and verifiable settlement anchoring.

**Architecture:** Keep `poker mtt` separate from `arena/*`. Go owns auth/session/runtime adapters, donor Redis finalization, and typed handoff; Python `mining-service` owns evidence persistence, scoring, multiplier/rating snapshots, reward windows, settlement artifacts, and chain-anchor preparation; `x/settlement` stays a tamper-evident root registry until a later payout/reputation phase. `lepoker-gameserver` and `lepoker-auth` remain independent donor references, not code imported into ClawChain domain models.

**Tech Stack:** Go, Python 3, FastAPI, SQLAlchemy async repository, Postgres, Redis, donor `lepoker-gameserver` HTTP/WS/Redis sidecar, optional DynamoDB completed-hand store, settlement Cosmos SDK module, pytest, Go tests, GitNexus code graph.

---

## Source Inputs

- Current clean ClawChain base: `main@9e194f2`.
- TDD execution checklist: `docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2-tdd-execution.md`.
- GitNexus repos:
  - `clawchain`, stale relative to `main@9e194f2`; local source inspection is authoritative for Phase 1 hardening.
  - `lepoker-auth`, independent donor reference for auth, MQ, hand history, HUD, final ranking, ELO/read models.
  - `lepoker-gameserver`, independent donor reference for runtime, WebSocket, table balancing, Redis live ranking, hand-record MQ.
- Six GPT-5.4 xhigh review agents:
  - Go architecture and runtime boundaries.
  - Mining service reward/settlement/hidden-eval path.
  - Chain settlement and anchor verification.
  - Product/spec coherence.
  - Donor/GitNexus borrow matrix.
  - Scale, operations, security, and load testing.

---

## Synthesis

The design is coherent, but Phase 2 must be named narrowly: **Poker MTT Evidence Phase 2**, not generic ClawChain product Phase 2.

The agreed shape:

- Phase 1 already established the strict path: canonical final ranking -> result entries -> reward window -> settlement batch -> typed anchor payload.
- Phase 2 should not expand into full donor Java migration, direct payouts, or `x/reputation` writes.
- Phase 2 should first make evidence real: completed-hand durable ingest, HUD projectors, hidden-eval entries, rating/multiplier snapshots, replay roots, and correction policy.
- Go should produce stable final standings and handoff artifacts. Python remains the reward/evidence authority until there is an intentional migration.
- Chain work should harden verification: query settlement anchors, confirm stored state, distinguish fallback memo anchoring from typed settlement anchoring, and tighten duplicate/root validation.
- Scale work must be designed into Phase 2: 20k entrants and about 2k early tables require indexed window queries, paged artifacts, metrics, and load harnesses before high-value rewards.

---

## Non-Goals

- No donor Java monolith port.
- No raw hand history or per-hand event on chain.
- No per-game or per-hand direct wallet payout.
- No `x/reputation` write from raw hands, hidden eval, or single-tournament score.
- No public ELO/rating as a direct positive reward weight.
- No giant single-tournament jackpot.
- No high-value or mainnet reward rollout until evidence, abuse, scale, and anchor verification gates pass.
- No `arena/*` reuse for Poker MTT business semantics.

---

## Target Flow

```text
donor sidecar running
-> stable Redis live ranking snapshot
-> Go finalizer canonical standings
-> mining-service final ranking rows
-> completed-hand evidence ingest
-> short-term HUD / long-term HUD
-> hidden eval entries
-> rating + multiplier snapshots
-> locked poker_mtt_result_entries
-> daily / weekly reward_window
-> settlement_batch
-> typed x/settlement anchor
-> optional later reputation_delta phase
```

Canonical state machine:

```text
raw_ingested
-> replay_ready
-> hud_ready
-> hidden_eval_ready
-> final_ranking_ready
-> result_ready
-> locked
-> anchorable
-> anchored
```

Abnormal states:

```text
degraded
manual_review
conflict
correction_required
superseded
void
```

---

## File Map

### Modify Python Mining Service

- `mining-service/models.py`
  - Add persistent Poker MTT evidence, HUD, hidden eval, rating, multiplier snapshot, and correction tables.
  - Add operational indexes for 20k-player windows.
- `mining-service/repository.py`
  - Add repository protocol methods for evidence and window-range reads.
- `mining-service/pg_repository.py`
  - Implement durable persistence and indexed queries.
- `mining-service/poker_mtt_history.py`
  - Promote in-memory semantics into durable store interfaces and manifest builders.
- `mining-service/poker_mtt_hud.py`
  - Add deterministic short-term and long-term HUD projector surfaces.
- `mining-service/poker_mtt_evidence.py`
  - Build real component manifests over persisted rows, not only accepted-degraded stubs.
- `mining-service/poker_mtt_results.py`
  - Tighten reward gates around evidence provenance and service-owned hidden eval.
- `mining-service/forecast_engine.py`
  - Add hidden-eval/rating/multiplier snapshot jobs, indexed window selection, correction/supersession, and anchor-state propagation.
- `mining-service/schemas.py`
  - Add admin/internal request and response models.
- `mining-service/server.py`
  - Add protected/internal endpoints for ingest, evidence build, hidden-eval finalize, rating snapshot, and public-safe Poker MTT reads.

### Modify Go Poker MTT Runtime

- `pokermtt/ranking/redis_store.go`
  - Add stable snapshot barrier/retry support.
- `pokermtt/ranking/finalizer.go`
  - Harden empty member IDs, duplicate alive/died entries, field-size policy, and post-lock correction output.
- `pokermtt/projector/result_payload.go`
  - Keep DTO builder but align payload with evidence-first workflow.
- `pokermtt/service/orchestrator.go`
  - Add durable workflow boundaries or delegate them to a new control/read-model package.
- `authadapter/donor_tokenverify.go`
  - Make synthetic local miner addresses explicitly non-production / non-rewardable.

### Modify Settlement

- `proto/clawchain/settlement/v1/query.proto`
  - Add query service for settlement anchors.
- `x/settlement/types/msgs.go`
  - Tighten `sha256:` validation.
- `x/settlement/keeper/msg_server.go`
  - Compare full duplicate anchor fields or return stored fields.
- `x/settlement/keeper/query_server.go`
  - Add `GetSettlementAnchor` and list support.
- `x/settlement/client/cli/query.go`
  - Add query CLI.
- `mining-service/chain_adapter.py`
  - Confirm typed anchor state by batch id and root/hash, not just tx code.

### Modify Tests

- `tests/mining_service/test_poker_mtt_history.py`
- `tests/mining_service/test_poker_mtt_hud.py`
- `tests/mining_service/test_poker_mtt_evidence.py`
- `tests/mining_service/test_poker_mtt_final_ranking.py`
- `tests/mining_service/test_poker_mtt_reward_gating.py`
- `tests/mining_service/test_forecast_engine.py`
- `tests/mining_service/test_forecast_api.py`
- `pokermtt/ranking/finalizer_test.go`
- `pokermtt/projector/result_payload_test.go`
- `authadapter/*_test.go`
- `x/settlement/types/msgs_test.go`
- `x/settlement/keeper/msg_server_test.go`
- New load/scale harness tests under `tests/poker_mtt/` or `scripts/poker_mtt/`.

### Modify Docs

- `docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md`
- `docs/POKER_MTT_SIDECAR_INTEGRATION.md`
- `docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md`
- `docs/PRODUCT_SPEC.md`
- `docs/HARNESS_API_CONTRACTS.md`
- `docs/protocol-spec.md`

---

## Task 1: Freeze Phase 2 Source Of Truth

**Files:**
- Modify: `docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md`
- Modify: `docs/POKER_MTT_SIDECAR_INTEGRATION.md`
- Modify: `docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md`
- Modify: `docs/PRODUCT_SPEC.md`
- Create/maintain: `docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2.md`

- [ ] **Step 1: Update docs to use `Poker MTT Evidence Phase 2`**

Clarify that this is not the same as product launch Phase 2 or governance/reputation Phase 3.

- [ ] **Step 2: Freeze the Phase 2 non-goals**

Ensure all touched docs say: no direct `x/reputation`, no ELO reward weight, no raw hand history on chain, no Java monolith port, no high-value rewards until scale/abuse gates pass.

- [ ] **Step 3: Align state machines**

Use this single canonical state machine:

```text
raw_ingested -> replay_ready -> hud_ready -> hidden_eval_ready -> final_ranking_ready -> result_ready -> locked -> anchorable -> anchored
```

- [ ] **Step 4: Verify doc references**

Run:

```bash
rg -n "Poker MTT Evidence Phase 2|raw_ingested -> replay_ready|public rating.*reward|x/reputation" docs
```

Expected: references point to the new plan or explicitly mark deferred/non-goal behavior.

- [ ] **Step 5: Commit docs**

```bash
git add docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md docs/POKER_MTT_SIDECAR_INTEGRATION.md docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md docs/PRODUCT_SPEC.md docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2.md
git commit -m "docs(pokermtt): define evidence phase2 plan"
```

---

## Task 2: Persistent Evidence Schema And Indexes

**Files:**
- Modify: `mining-service/models.py`
- Modify: `mining-service/repository.py`
- Modify: `mining-service/pg_repository.py`
- Test: `tests/mining_service/test_poker_mtt_history.py`
- Test: `tests/mining_service/test_poker_mtt_evidence.py`

- [ ] **Step 1: Write failing repository tests**

Cover these table concepts:

```text
poker_mtt_hand_events
poker_mtt_table_upload_states
poker_mtt_consumer_checkpoints
poker_mtt_short_term_hud_snapshots
poker_mtt_long_term_hud_snapshots
poker_mtt_hidden_eval_entries
poker_mtt_rating_snapshots
poker_mtt_multiplier_snapshots
poker_mtt_corrections
```

- [ ] **Step 2: Add model definitions**

Minimum required keys:

```text
poker_mtt_hand_events:
  hand_id primary key
  tournament_id, table_id, hand_no, version, checksum
  event_id, source_json, payload_json
  ingest_state, conflict_reason
  created_at, updated_at

poker_mtt_hidden_eval_entries:
  id primary key
  tournament_id, miner_address, final_ranking_id
  seed_assignment_id, baseline_sample_id
  hidden_eval_score, score_components_json
  evidence_root, manifest_root, policy_bundle_version
  visibility_state
  created_at, updated_at

poker_mtt_rating_snapshots:
  id primary key
  miner_address, window_start_at, window_end_at
  public_rating, public_rank, confidence
  long_term_hud_root, policy_bundle_version
  created_at, updated_at

poker_mtt_multiplier_snapshots:
  id primary key
  miner_address, source_result_id, multiplier_before, multiplier_after
  rolling_score, policy_bundle_version
  created_at, updated_at
```

- [ ] **Step 3: Add operational indexes**

Add indexes for:

```text
tournament_id + hand_no
tournament_id + ingest_state
tournament_id + miner_address
miner_address + window_end_at
locked_at + evidence_state + eligible_for_multiplier
lane + window_start_at + window_end_at
```

- [ ] **Step 4: Implement repository methods**

Repository methods must support range and state filters, not only `list_all`.

- [ ] **Step 5: Run focused tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_history.py tests/mining_service/test_poker_mtt_evidence.py
```

Expected: new persistence tests pass.

---

## Task 3: Durable Completed-Hand Ingest

**Files:**
- Modify: `mining-service/poker_mtt_history.py`
- Modify: `mining-service/server.py`
- Modify: `mining-service/schemas.py`
- Test: `tests/mining_service/test_poker_mtt_history.py`
- Optional: add DynamoDB adapter module after Postgres/local contract is green.

- [ ] **Step 1: Write failing ingest tests**

Test cases:

```text
new hand with version inserts
same version + same checksum is duplicate
same version + different checksum is conflict/manual_review
higher version updates
lower version is stale
missing version only accepted when checksum matches existing
```

- [ ] **Step 2: Implement durable store interface**

Keep the current in-memory store as a test double, then add repository-backed storage.

- [ ] **Step 3: Add internal ingest endpoint**

Endpoint should be internal/admin only, for example:

```text
POST /admin/poker-mtt/hands/ingest
```

It accepts `poker_mtt.hand_completed.v1` and returns ingest state.

- [ ] **Step 4: Add hand-history manifest builder**

Manifest rows should bind:

```text
tournament_id
hand_id
version
checksum
ingest_state
```

- [ ] **Step 5: Add optional DynamoDB adapter design gate**

If implemented now, use conditional writes keyed by `hand_id`, with `version` and `checksum` as conflict guards. If AWS credentials are not available in local CI, keep adapter tests isolated behind mocks or a local emulator.

- [ ] **Step 6: Run focused tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_history.py
```

---

## Task 4: HUD Projectors

**Files:**
- Modify: `mining-service/poker_mtt_hud.py`
- Modify: `mining-service/poker_mtt_evidence.py`
- Modify: `mining-service/forecast_engine.py`
- Test: `tests/mining_service/test_poker_mtt_hud.py`

- [ ] **Step 1: Expand short-term HUD tests**

Include deterministic VPIP, PFR, 3-bet, c-bet, WTSD, WSSD, hands seen, and skipped/unknown hands.

- [ ] **Step 2: Add long-term HUD snapshot tests**

Long-term HUD should summarize rolling hands, ITM, win, profitable, showdown, and confidence.

- [ ] **Step 3: Implement projectors over persisted hand events**

Projectors must be replayable and idempotent. Duplicate hands must not double count.

- [ ] **Step 4: Build HUD manifests**

Produce separate roots:

```text
short_term_hud_root
long_term_hud_root
```

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_hud.py
```

---

## Task 5: Service-Owned Hidden Eval

**Files:**
- Modify: `mining-service/poker_mtt_results.py`
- Modify: `mining-service/poker_mtt_evidence.py`
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/server.py`
- Test: `tests/mining_service/test_poker_mtt_evidence.py`
- Test: `tests/mining_service/test_poker_mtt_reward_gating.py`

- [ ] **Step 1: Write failing tests that reject caller-supplied hidden scores**

Legacy/admin apply may preserve compatibility, but reward-ready hidden eval must be service-derived.

- [ ] **Step 2: Add hidden seed assignment records**

Record only enough to audit and replay later:

```text
seed_assignment_id
tournament_id
policy_bundle_version
sealed_seed_commitment
visibility_state
```

- [ ] **Step 3: Add baseline/control sample manifests**

Baseline bot/control samples are evidence, not public leaderboard data.

- [ ] **Step 4: Implement hidden-eval entry builder**

Inputs:

```text
final_ranking
hand_history_manifest
short_term_hud_manifest
hidden_seed_assignment
baseline/control manifest
```

Output:

```text
poker_mtt_hidden_eval_entries
hidden_eval_root
hidden_eval_score
risk_flags
```

- [ ] **Step 5: Lock only after evidence provenance is complete**

No result can move to `locked` unless final ranking, hand history or accepted-degraded policy, HUD, hidden eval, and policy bundle are consistent.

- [ ] **Step 6: Run focused tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_poker_mtt_evidence.py tests/mining_service/test_poker_mtt_reward_gating.py
```

---

## Task 6: Rating And Multiplier Snapshots

**Files:**
- Modify: `mining-service/models.py`
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/server.py`
- Test: `tests/mining_service/test_poker_mtt_final_ranking.py`
- Test: `tests/mining_service/test_forecast_engine.py`

- [ ] **Step 1: Add failing tests for separate public rating**

Ensure Poker MTT does not mutate or reuse forecast `public_rank` / `public_elo` as the canonical Poker MTT public ladder.

- [ ] **Step 2: Implement `poker_mtt_public_rank` / `poker_mtt_public_rating` snapshots**

Public rating uses final ranking and long-term HUD. It must not use raw hidden eval as a public field.

- [ ] **Step 3: Persist multiplier snapshots**

Every multiplier update should have an auditable snapshot row bound to the source result and policy bundle.

- [ ] **Step 4: Assert ELO is not a reward weight**

Tests should verify reward rows do not include positive ELO/rating weight.

- [ ] **Step 5: Run focused tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_forecast_engine.py -k "poker_mtt and (rating or multiplier or reward)"
```

---

## Task 7: Go Finalization Worker And Typed Handoff

**Files:**
- Modify: `pokermtt/ranking/redis_store.go`
- Modify: `pokermtt/ranking/finalizer.go`
- Modify: `pokermtt/projector/result_payload.go`
- Add: `pokermtt/projector/client.go` or equivalent
- Add/modify: `pokermtt/service/*`
- Test: `pokermtt/ranking/finalizer_test.go`
- Test: `pokermtt/projector/result_payload_test.go`

- [ ] **Step 1: Write tests for stable Redis snapshot reads**

Simulate `userInfo`, alive zset, and died list changing between reads.

- [ ] **Step 2: Add snapshot barrier/retry policy**

The finalizer should either observe a stable snapshot or mark the attempt unresolved/degraded.

- [ ] **Step 3: Harden finalizer edge cases**

Cover:

```text
empty member id
duplicate alive/died member
equal zset score tie
missing entryNumber
no-show / waiting player
field-size mismatch
post-lock mutation
```

- [ ] **Step 4: Add mining-service client**

The Go side should post final rankings as canonical rows. Python evidence enrichment decides when rows become reward-ready.

- [ ] **Step 5: Make local synthetic miner addresses non-rewardable**

Production reward identity must require explicit miner/economic-unit binding.

- [ ] **Step 6: Run Go tests**

```bash
go test ./authadapter ./pokermtt/... -v
```

---

## Task 8: Reward Window Scalability And Correction Policy

**Files:**
- Modify: `mining-service/forecast_engine.py`
- Modify: `mining-service/pg_repository.py`
- Modify: `mining-service/poker_mtt_results.py`
- Test: `tests/mining_service/test_forecast_engine.py`

- [ ] **Step 1: Replace hot-path all-result scans**

Reward windows should query by indexed `locked_at`, lane, evidence state, and eligibility.

- [ ] **Step 2: Add paged projection artifact strategy**

Large windows should store roots plus page references. Avoid requiring every miner row in one normal API payload.

- [ ] **Step 3: Freeze budget policy**

Document and test:

```text
no positive weight -> no_positive_weight / forfeit / configured carry-forward
daily/weekly pools must be explicit emission-budget slices
manual build allowed, auto build gated
```

- [ ] **Step 4: Add correction/supersession records**

Anchored roots must never mutate. Corrections append or supersede via new records and new batches.

- [ ] **Step 5: Propagate batch anchor state**

If product surfaces expose per-result anchor state, update result rows from containing batch state or explicitly document batch-only anchoring.

- [ ] **Step 6: Run tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_forecast_engine.py -k "poker_mtt and (reward_window or anchor or correction)"
```

---

## Task 9: Settlement Anchor Query And Verification

**Files:**
- Add: `proto/clawchain/settlement/v1/query.proto`
- Modify generated settlement protobuf files as required by the project toolchain
- Modify: `x/settlement/keeper/*`
- Modify: `x/settlement/types/*`
- Modify: `x/settlement/client/cli/*`
- Modify: `mining-service/chain_adapter.py`
- Test: `x/settlement/...`
- Test: `tests/mining_service/test_chain_adapter.py`

- [ ] **Step 1: Add query tests first**

Test `GetSettlementAnchor(batch_id)` and list/prefix behavior.

- [ ] **Step 2: Tighten SHA-256 validation**

Reject malformed roots such as `sha256:x`.

- [ ] **Step 3: Compare duplicate full anchor fields**

Duplicate submission should be exact or return stored anchor state. It should not emit misleading new fields.

- [ ] **Step 4: Confirm typed state, not just tx success**

Mining service must verify that chain state contains the expected batch id, root, hash, lane, policy, roots, window end, and total before marking typed anchor confirmed.

- [ ] **Step 5: Separate fallback memo anchoring**

If fallback remains, its state is `memo_anchor_confirmed`, not `x_settlement_anchored`.

- [ ] **Step 6: Run tests**

```bash
go test ./x/settlement/... -v
PYTHONPATH=mining-service pytest -q tests/mining_service/test_chain_adapter.py
```

---

## Task 10: Admin/Auth Security Gate

**Files:**
- Modify: `mining-service/server.py`
- Modify: `mining-service/config.py`
- Modify: `authadapter/*`
- Test: `tests/mining_service/test_forecast_api.py`
- Test: `authadapter/*_test.go`

- [ ] **Step 1: Add tests for protected admin mutations**

Admin endpoints that mutate results, evidence, reward windows, or settlement state must be protected or explicitly network-isolated.

- [ ] **Step 2: Add production identity gate**

Local mock identities can run harnesses but cannot be reward-eligible in production mode.

- [ ] **Step 3: Add expired/wrong-token tests**

Cover expired token, wrong miner, missing miner binding, and mismatched economic unit.

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=mining-service pytest -q tests/mining_service/test_forecast_api.py -k "admin or poker_mtt"
go test ./authadapter -v
```

---

## Task 11: Scale Harness And Observability

**Files:**
- Modify/add: `scripts/poker_mtt/*`
- Modify/add: `tests/poker_mtt/*`
- Modify/add docs: `docs/POKER_MTT_SIDECAR_INTEGRATION.md`
- Optional: metrics module depending on current observability stack.

- [ ] **Step 1: Define SLOs**

Minimum metrics:

```text
active tournaments/tables/players
ws connected count
join/action p95/p99 latency
reconnects
kicked/busted disconnect classification
table stuck age
hand close rate
finalizer duration/memory
Redis key sizes
RocketMQ lag
Dynamo throttles/conflicts/retry age
reward rows selected/omitted by reason
settlement anchor state
```

- [ ] **Step 2: Add staged load profiles**

Profiles:

```text
30 players non-mock auth explicit join/action to finish
300 players synthetic/staged finalizer
2k tables synthetic routing/finalizer stress
10k-20k final-ranking and reward-window projection
```

- [ ] **Step 3: Add reconnect and table-move cases**

Cover stale room, table move, bust/kick disconnect, rapid reconnect, and action spam.

- [ ] **Step 4: Add recovery runbook**

Include pending hand upload sweeper, checkpoint replay, dead-letter/conflict queue, sidecar restart recovery, and settlement root conflict alarm.

- [ ] **Step 5: Run available local checks**

```bash
PYTHONPATH=mining-service pytest -q tests/poker_mtt
```

---

## Task 12: End-To-End Phase 2 Gate

**Files:**
- All touched code/docs.

- [ ] **Step 1: Run focused Phase 2 checks**

```bash
make test-poker-mtt-phase1
go test ./authadapter ./pokermtt/... ./x/settlement/... -v
PYTHONPATH=mining-service pytest -q tests/mining_service tests/poker_mtt
```

- [ ] **Step 2: Run 30-player non-mock WS harness**

Use the existing local auth mock and sidecar flow documented in `docs/POKER_MTT_SIDECAR_INTEGRATION.md`.

Expected:

```text
30 joined users
all final standings present
one or zero alive at finish
canonical final ranking generated
evidence roots generated
reward window built only after locked state
settlement batch root stable across retry
```

- [ ] **Step 3: Run scale synthetic tests**

At minimum:

```text
10k finalizer test
20k result-window projection benchmark
large settlement artifact/root stability test
```

- [ ] **Step 4: Run diff checks**

```bash
git diff --check
```

- [ ] **Step 5: Commit**

Commit in small slices. Do not include donor repos, `website/out`, local testnet artifacts, or binary `clawchaind`.

---

## Acceptance Criteria

- `poker mtt` remains independent from `arena/*`.
- Completed-hand evidence is durable or explicitly excluded from the rollout gate.
- Replaying the same hand events produces identical hand-history, HUD, hidden-eval, and projection roots.
- Duplicate hand events do not duplicate HUD/reward effects.
- Same hand version with different checksum creates conflict/manual-review and blocks locking.
- `FINISHED` alone never enters reward windows.
- Reward windows use `locked_at`, not donor completion time or row creation time.
- Reentries collapse to one economic-unit reward row while preserving audit rows.
- Non-positive windows never equal-split the pool.
- Public APIs never expose hidden eval internals, bot identities, or internal `total_score`.
- Public rating/ELO is absent from positive reward weight tests.
- Settlement payload roots are stable across retry and conflict on drift.
- Chain confirmation checks typed `x/settlement` state by batch id, root, and hash.
- Poker reward windows and settlement anchoring remain disabled by default until explicit rollout.
- Admin mutation endpoints are protected or private-only before shared environments.
- Load tests or synthetic benchmarks cover 20k result rows and large reward windows before high-value rewards.

---

## Review Notes

When implementing this plan, treat agent review findings as hard constraints unless a later code review disproves them:

- `clawchain` GitNexus index was stale for Phase 1 hardening; source files in the clean worktree are authoritative.
- `x/settlement` currently stores roots but does not execute payouts.
- `x/reputation` is not ready as a window-level reputation-delta sink.
- Existing hand-history/HUD code is in-memory and should not be presented as production evidence.
- Donor Redis reads are acceptable only behind a versioned adapter/finalizer contract.
- DynamoDB is a good production candidate for completed-hand storage, but ClawChain core should depend on a storage interface, not AWS-specific code in the domain model.

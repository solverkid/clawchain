# Three-Lane Integration Hardening Review

Date: 2026-04-21

Scope:
- `forecast_15m` / Polymarket short-horizon lane
- Poker MTT lane
- MTT-like bluff arena lane
- shared chain anchoring / settlement bridge
- shared `miners` / reward-window / settlement-batch integration surfaces

Method:
- 3 parallel `gpt-5.4 xhigh` domain reviews
- 1 `gpt-5.4 xhigh` meta-review over the synthesized findings
- local code/doc cross-check against current repository truth
- second-pass re-validation against the landed review, including 6 additional `gpt-5.4 xhigh` reviewer runs and local code re-check of disputed claims

This document is a review artifact, not a product-spec rewrite. The goal is to state the current integration reality, identify the highest-risk drifts, and define the hardening order.

## Status Update: 2026-04-22

Resolved from the original review:

- forecast default runtime now routes chain confirmation through `tx(hash) + settlement query`, and `/admin/anchor-jobs/{id}/mark-anchored` no longer bypasses that path
- Arena -> shared `miners` ownership is narrowed to Arena-owned compatibility fields only
- forecast reward windows and settlement-anchor payloads now materialize explicit reward-component rows instead of aggregating only bare `reward_amount`
- forecast fast payout now applies forecast-side `quality_envelope`, including risk-case derived `anti_abuse_discount`, and miner status separates that field from `admission_release_ratio`
- local/dev registration no longer clusters miners just because they come from loopback IPs or generic HTTP-library user agents
- forecast reveal duplicate gating now uses refreshed service-side `economic_unit_id` truth in the reveal path
- the real Postgres Poker MTT reward-window loader now honors `include_provisional`
- forecast replay proof now carries bounded reward-composition lineage through additive `reward_window_replay_bundle` artifacts
- forecast proof now exposes `reward_component_rows_root`, `anti_abuse_input_rows_root`, and explicit `overlay_merge_state`
- forecast proof now marks `daily_snapshot_merge` and `arena_snapshot_merge` as `deferred` instead of implying those overlays already exist
- Poker MTT release-review bundle now emits explicit `lineage_roots`

Remaining highest-value follow-on items:

- complete the broader daily/arena overlay merge that the architecture prose still describes but the runtime does not yet materialize
- reduce remaining docs/review drift now that the biggest forecast hardening deltas have landed
- finish replay/proof and documentation alignment against the current runtime truth

## 1. Executive Verdict

Current repo truth is not "three lanes deeply integrated on-chain".

What exists today is:
- `forecast_15m` is the only lane that fully runs through `submission -> scoring -> reward window -> settlement batch -> anchor job`.
- Poker MTT is materially integrated into the shared reward-window / settlement-batch path, but it is still rollout-gated and has correctness/documentation gaps that matter before treating it as a fully trusted reward-bearing lane.
- Arena has a real Go runtime, rating pipeline, replay/state artifacts, and shared-miner writeback, but it is not yet a first-class settlement lane. It currently behaves more like a sidecar system that writes compatibility state into shared miner records.

The highest-risk hardening gaps are:
1. Forecast still does not materialize the broader daily/arena overlay merge described by the architecture prose, even though the forecast-side quality envelope is now wired.
2. Replay/proof and docs still lag behind the current runtime truth in multiple places.
3. Poker MTT remains rollout-gated and still needs stronger release-evidence alignment before being treated as fully trusted.
4. Arena is still not a first-class settlement lane.

## 2. Source-Of-Truth Matrix

| Surface | Current code truth | Main drift / risk |
| --- | --- | --- |
| Forecast lane | `mining-service` owns the active task, scoring, reward, and anchoring pipeline | Forecast-side `quality_envelope` and risk-case anti-abuse are now wired, but the broader daily/arena overlay merge described by the docs is still absent |
| Poker MTT lane | Reward windows, settlement batches, anchor jobs, and release bundle flow are implemented in `mining-service` | DB input path ignores `include_provisional`; docs understate how far the lane already goes |
| Arena lane | Go runtime persists tournament/rating state and writes compatibility state back into shared `miners` | Not a true settlement lane; shared-field ownership collides with mining-service |
| Chain integration | `x/settlement` typed anchoring exists, with service-side batch/root assembly | Main confirmation/bypass gap is closed, but local runtime and docs still need better alignment around operator/replay surfaces |
| Cross-lane economics | Shared `miners`, reward-window, settlement-batch, anchor job objects exist | Forecast-side component payout is wired, but daily/arena overlays are still not actually merged into the fast payout path |

## 3. Lane Review: Forecast 15m / Polymarket Short-Horizon

### 3.1 Current truth

`forecast_15m` is the most complete lane in the repo. It publishes BTC/ETH fast tasks, accepts commit/reveal, settles resolved tasks, builds hourly reward windows, and creates settlement batches that can be anchored through the chain adapter path.

Primary code path:
- `mining-service/forecast_engine.py`
- `mining-service/server.py`
- `mining-service/market_data.py`
- `mining-service/chain_adapter.py`

### 3.2 P0 findings

#### P0-A. Default runtime does not actually wire the documented `tx + settlement-query` confirmation contract
The problem is not that the default runtime "accepts a weaker confirmer and still passes". The more precise problem is that the default app wiring only injects tx inspection, while `confirm_anchor_job_on_chain()` relies on the confirmer to also provide `query_response`; the service never performs the settlement query itself.

Evidence:
- default confirmer wiring: `mining-service/server.py:456`
- tx-only normalization path: `mining-service/chain_adapter.py:808`
- optional query payload path: `mining-service/chain_adapter.py:850`
- service confirm logic only performs full semantic validation when `query_response` is present: `mining-service/forecast_engine.py:2410`
- contract claims a stronger verification shape: `docs/HARNESS_API_CONTRACTS.md:644`
- tx-only receipts fail closed rather than silently succeeding: `tests/mining_service/test_forecast_engine.py:658`

Practical implication:
- the default typed anchor flow does not satisfy the documented `tx(hash) + typed settlement state` confirmation contract out of the box. This is a missing end-to-end wiring problem before it is a "weak verifier lets bad anchors through" problem.

#### P0-B. `/admin/anchor-jobs/{id}/mark-anchored` remains a real chain-bypass

Evidence:
- route: `mining-service/server.py:914`
- implementation: `mining-service/forecast_engine.py:2563`
- terminal force-mark path: `mining-service/forecast_engine.py:2579`
- architecture doc says it should conceptually reuse the verification path: `docs/HARNESS_BACKEND_ARCHITECTURE.md:773`

Practical implication:
- operator-facing surface still allows a direct terminal state transition that is materially weaker than the verified anchoring path; it does not even require a `broadcast_tx_hash`.

### 3.3 P1 findings

#### P1-A. Freshness hardening is effectively disabled in the live provider path

Evidence:
- freshness classifier exists: `mining-service/market_data.py:213`
- provider returns zero freshness ages: `mining-service/market_data.py:369`, `mining-service/market_data.py:412`

Practical implication:
- the system structurally looks like it can degrade or void stale packs, but the currently wired provider path does not supply meaningful age signals.

#### P1-B. Reveal duplicate gating can miss a first-time cluster merge

Evidence:
- stale `economic_unit_id` passed from API layer: `mining-service/server.py:1152`, `mining-service/server.py:1162`
- reveal path refreshes miner identity but still compares against the stale argument: `mining-service/forecast_engine.py:1535`, `mining-service/forecast_engine.py:1556`, `mining-service/forecast_engine.py:1564`

Practical implication:
- first-merge duplicate suppression is not as strong as designed for the reveal path.

#### P1-C. Forecast progression is only partially read-driven, but less severely than the first pass stated

Evidence:
- central reconcile path: `mining-service/forecast_engine.py:1332`
- public reads invoke it: `mining-service/forecast_engine.py:1425`, `mining-service/forecast_engine.py:1446`, `mining-service/forecast_engine.py:1593`, `mining-service/server.py:605`
- only explicit background loop currently present is the anchor reconcile loop: `mining-service/server.py:232`, `mining-service/server.py:433`
- default runtime loop calls full `service.reconcile()` before sweeping anchor jobs: `mining-service/server.py:476`, `mining-service/server.py:479`, `mining-service/forecast_engine.py:2502`

Practical implication:
- public reads still trigger reconcile, but the default runtime is not mainly dependent on traffic to progress task publication, settlement, and reward-window creation.

#### P1-D. Forecast payout path now applies a forecast-side `quality_envelope`, but the broader overlay contract remains incomplete

Status update: mostly landed on 2026-04-22.

Current truth:
- forecast settlement now persists `model_reliability_component`, `ops_reliability_component`, `arena_multiplier_component`, and `anti_abuse_discount`
- fast payout computes `reward_amount` from `fast_direct_score * quality_envelope`
- reward windows and settlement anchors now consume materialized reward-component rows instead of only bare `reward_amount`

Remaining gap:
- the broader daily/arena overlay merge described by the architecture prose is still not implemented, so the runtime is only on the forecast-side subset of the full documented envelope

#### P1-E. Anti-abuse review state is not actually enforced in the payout path

Status update: landed in the forecast lane on 2026-04-22.

Current truth:
- open risk cases now derive `anti_abuse_discount` in the fast settlement path
- open `economic_unit_cluster` cases currently discount to `0.25`
- open `economic_unit_duplicate` / `high` / `critical` cases currently discount to `0.0`
- miner status and reward timeline now expose real `anti_abuse_discount` separately from `admission_release_ratio`
- operator case overrides matter because closing the case removes the live discount on later settlements/status reads

Remaining gap:
- current enforcement is still a minimal severity-to-discount mapping; richer clamp/freeze semantics remain future work

### 3.4 P2 findings

#### P2-A. Daily/arena overlays are not actually wired into forecast payout math

Evidence:
- docs say reward windows should incorporate daily/arena overlays: `docs/HARNESS_BACKEND_ARCHITECTURE.md:400`
- fast payout still only uses raw score -> reward: `mining-service/forecast_engine.py:4189`, `mining-service/forecast_engine.py:4194`
- daily path updates reliability but pays zero: `mining-service/forecast_engine.py:4281`, `mining-service/forecast_engine.py:4287`
- reward-window build still aggregates fast-lane submission rewards: `mining-service/forecast_engine.py:4360`

Practical implication:
- even if the broader `quality_envelope` were fixed, the current runtime still would not be doing the daily/arena snapshot merge described by the architecture prose.

#### P2-B. Resolution source still drifts from the design story

Evidence:
- design says settle against Claw reference prices / TWAP-like reference rule: `docs/MINING_DESIGN.md:107`, `docs/MINING_DESIGN.md:469`
- live provider resolves off Polymarket Gamma and leaves `end_ref_price=None`: `mining-service/market_data.py:349`, `mining-service/market_data.py:359`

Practical implication:
- the lane is materially closer to "Polymarket-derived short-horizon tasks" than the older design description implies.

#### P2-C. Forecast replay/proof surface has moved from thin membership proof to bounded reward-composition lineage, but is still not a full replay bundle

Evidence:
- architecture expects replay/audit surfaces to carry daily/arena snapshot membership and carry-forward context: `docs/HARNESS_BACKEND_ARCHITECTURE.md:54`, `docs/HARNESS_BACKEND_ARCHITECTURE.md:791`, `docs/HARNESS_BACKEND_ARCHITECTURE.md:1019`
- current runtime now emits additive `reward_window_replay_bundle` artifacts for forecast windows, carrying:
  - `reward_component_rows_root`
  - `anti_abuse_input_rows_root`
  - explicit `overlay_merge_state`
- replay proof now reuses that artifact and exposes the same lineage on the public proof surface

Practical implication:
- current replay proof can now attest to forecast-side reward composition and anti-abuse lineage, while still explicitly declaring that the broader daily/arena overlay merge is deferred in this pass.

## 4. Lane Review: Poker MTT

### 4.1 Current truth

Poker MTT is substantially more integrated than older repo-wide status language suggests.

Current implemented path includes:
- final ranking projection and hidden-eval gating
- reward-window materialization for `poker_mtt_daily` and `poker_mtt_weekly`
- settlement-batch preparation
- anchor job creation and chain submission path
- release review bundle and evidence-pack flow

Primary code/docs:
- `mining-service/forecast_engine.py`
- `mining-service/pg_repository.py`
- `docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md`
- `docs/POKER_MTT_PHASE3_PRODUCTION_READINESS_SPEC.md`
- `scripts/poker_mtt/build_release_review_bundle.py`

### 4.2 P1 findings

#### P1-A. Real Postgres reward-window input path ignores `include_provisional`

Evidence:
- reconciler expects provisional-aware behavior: `mining-service/forecast_engine.py:4431`
- Postgres loader hard-codes `evaluation_state == "final"` semantics: `mining-service/pg_repository.py:2188`

Practical implication:
- reward-window inputs in real DB mode can diverge from the contract that the service logic assumes.

This is the highest-priority Poker MTT correctness issue found in this pass.

### 4.3 P2 findings

#### P2-A. Release-review bundle undercaptures available lineage roots

The runtime already computes richer economics/projection roots than the bundle currently requires.

Evidence:
- lineage roots emitted in service path: `mining-service/forecast_engine.py:910`, `mining-service/forecast_engine.py:1996`, `mining-service/forecast_engine.py:3970`
- bundle contract is narrower: `scripts/poker_mtt/build_release_review_bundle.py:31`

Practical implication:
- the rollout evidence bundle is weaker than the runtime provenance already available.

#### P2-B. Docs understate the implemented Poker MTT path and underspecify miner/public surfaces

Evidence:
- `docs/IMPLEMENTATION_STATUS_2026_04_10.md:243`
- `docs/IMPLEMENTATION_STATUS_2026_04_10.md:290`
- `docs/HARNESS_BACKEND_ARCHITECTURE.md:400`
- `docs/HARNESS_API_CONTRACTS.md:199`
- `docs/HARNESS_API_CONTRACTS.md:315`
- `docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md:1437`

Practical implication:
- external readers can get the wrong answer about what is actually implemented versus what is still rollout-gated.

### 4.4 Still-missing integrations

These are not review surprises, but they remain real non-completions:
- no real payout execution / validator-side reward disbursement
- `x/reputation` remains effectively dry-run
- miner/public read contracts are still not lane-native enough
- release replay script still defaults to a local harness style rather than a production-grade replay posture

## 5. Lane Review: Arena / MTT-like Bluff Arena

### 5.1 Current truth

Arena is more real than the older broad status docs imply:
- it has a Go runtime
- it persists tournament/rating state
- it emits replay and measurement artifacts
- it writes compatibility state back into shared miner records

Primary code/docs:
- `arena/rating/mapper.go`
- `arena/rating/writer.go`
- `arena/store/postgres/repository.go`
- `docs/ARENA_RUNTIME_ARCHITECTURE.md`
- `docs/ARENA_MEASUREMENT_SPEC.md`

### 5.2 P0 findings

#### P0-A. Shared `miners` ownership is incoherent between arena and mining-service

Arena Go path writes shared compatibility fields:
- `arena/rating/mapper.go:145`
- `arena/store/postgres/repository.go:3680`

Mining-service also mutates overlapping fields:
- `mining-service/forecast_engine.py:4205`
- `mining-service/forecast_engine.py:4291`
- `mining-service/forecast_engine.py:4961`

Affected fields include:
- `model_reliability`
- `public_rank`
- `public_elo`
- `arena_multiplier`

Practical implication:
- this is still a last-writer-wins ownership problem, not a clean integration boundary.

#### P0-B. Two incompatible arena result/multiplier semantics still coexist

Evidence:
- Python bridge path writes `arena_result_entries` / last-20-average multiplier semantics: `mining-service/forecast_engine.py:4089`
- Go path writes confidence-weighted rating inputs, ladder state, multiplier snapshots, and compatibility state: `arena/rating/mapper.go:158`, `arena/rating/writer.go:80`

Practical implication:
- there is no single authoritative arena result contract yet.

### 5.3 P1 findings

#### P1-A. Shared DB hardening is still thin

Status update: landed on 2026-04-22.

Current truth:
- `arena/integration/TestWarmMultiplierSharedMinerWriteback` now seeds warm eligible history, forces a non-default `arena_multiplier`, and proves the Go runtime writes that shared miner field back into Postgres
- `tests/integration/test_arena_mining_bridge.py` then reuses the same shared DB and proves `ForecastMiningService.get_miner_status()` consumes the Go-written `arena_multiplier` without corrupting forecast-owned fields

Remaining gap:
- shared DB verification now exists for `arena_multiplier`, but Arena is still not a full settlement lane and still does not own reward-window / settlement-batch objects

### 5.4 Structural missing integration

Arena is still not a true settlement lane.

Evidence:
- docs conceptually place arena snapshots into the reward-window composition path: `docs/HARNESS_BACKEND_ARCHITECTURE.md:402`
- actual reward-window builder still only walks forecast submissions: `mining-service/forecast_engine.py:4360`
- mining-service only exposes a manual bridge path for arena application: `mining-service/forecast_engine.py:4067`

Practical implication:
- current arena integration is compatibility-state writeback, not payout-grade lane integration.

## 6. Cross-Lane Integration Reality

### 6.1 What is actually shared today

The three lanes currently converge mainly through shared service-owned objects:
- shared `miners`
- shared reward windows
- shared settlement batches
- shared anchor jobs / artifacts

This statement has one important nuance:
- Poker MTT has its own substantial lane-specific pipeline before converging on the settlement surfaces.
- Arena has its own substantial Go persistence/rating system before converging on shared miner fields.

So the system is not "one flat mining-service only". It is better described as:

1. lane-specific runtime or scoring systems
2. partial convergence into shared service-owned economic surfaces
3. chain anchoring of service-assembled canonical payloads

### 6.2 What is not shared deeply enough yet

The repo still does not have a clean, fully unified cross-lane economic envelope.

Specifically:
- Arena does not feed a first-class settlement lane.
- Forecast payout now applies a forecast-side `quality_envelope`, but it still does not perform the daily/arena overlay merge described by the architecture prose.
- Shared miner-field ownership is still not stable enough across all writers.
- Replay/proof quality is uneven between lanes.

## 7. Hardening Order

### 7.1 P0 hardening order

#### P0-1. Fix forecast/chain anchor correctness first

Why first:
- it affects the only lane already fully driving end-to-end settlement objects
- background reconciliation loop currently amplifies the same weakness if the default confirmer is weak

Required outcome:
- default app wiring must actually provide both tx confirmation and settlement-anchor-state verification as one end-to-end confirmer
- no successful terminal state without matching anchored root/payload semantics
- remove or strictly route `mark-anchored` through the same verification contract

### 7.2 P0-2. Freeze arena shared-state ownership

Why second:
- current overlap over `model_reliability`, `public_rank`, `public_elo`, `arena_multiplier` is structurally unsafe

Required outcome:
- one authoritative writer or one authoritative merge contract for every shared `miners` field
- one authoritative arena result/multiplier semantic path

### 7.3 P1 hardening order

#### P1-1. Complete the remaining forecast reward contract after component enforcement

Why:
- the active lane now has settlement-grade reward components, but it still stops short of the broader daily/arena overlay merge described by the architecture prose

Required outcome:
- preserve the landed component rows / anti-abuse enforcement
- add only the remaining daily/arena overlay semantics that the architecture still claims, or narrow the docs to the implemented forecast-side contract

#### P1-2. Fix forecast duplicate gating to use refreshed service-side `economic_unit` truth

Why:
- this is a direct fairness / anti-abuse contract breach in the active mining lane

#### P1-3. Fix Poker MTT `include_provisional` correctness in real Postgres mode

Why:
- this remains the highest-value correctness gap in a lane that is otherwise much closer to reward-bearing readiness than the older docs admit

#### P1-4. Add one real cross-service arena integration test

Required scenario:
- complete Go arena tournament
- write compatibility/miner state into shared DB
- run mining-service reconcile or refresh path
- verify no corruption and expected downstream visibility

#### P1-5. Reduce remaining read-triggered forecast progression coupling

Required outcome:
- keep a deterministic background progression surface for task publication, settlement, release, reward-window build, and batch preparation, without relying on public reads as a secondary trigger

Status update: landed.

- runtime now does a startup forecast progression pass and can run a dedicated in-process forecast progression loop
- public miner/task/history/replay/artifact reads are snapshot-oriented and no longer invoke `reconcile()` as their fallback progression path
- operator/manual recovery now has an explicit `POST /admin/reconcile` surface
- `GET /admin/settlement-batches` is now a pure read
- `GET /admin/anchor-jobs/{id}/chain-tx-plan` is now a pure read too; the endpoint and underlying service path require prebuilt anchor payload state instead of silently triggering `reconcile()`

### 7.4 P2 hardening order

#### P2-1. Align docs with actual repo truth

Current problem:
- older status/docs simultaneously understate Poker MTT, overstate some forecast-chain assurances, and imply deeper cross-lane economics than code actually applies.

#### P2-2. Improve replay/proof surfaces

Targets:
- richer Poker MTT release bundle lineage
- durable forecast fast-task resolution artifacts
- clearer cross-lane audit surfaces

## 8. Concrete Decisions To Make

These decisions should be made explicitly rather than drifting:

1. Is arena supposed to become a first-class settlement lane in this phase, or remain a calibration sidecar that only writes multiplier/reliability state?
2. Is forecast supposed to remain Polymarket-derived in V1, or do we intend to return to a Claw-native reference-price settlement rule?
3. Is `public_rank/public_elo/model_reliability` owned by mining-service, arena, or a dedicated projection job?
4. Is Poker MTT being prepared for reward-bearing rollout in the near term, or should docs clearly label it as integrated-but-gated?

Until these are answered in code and docs, "deep integration" will remain partial.

## 9. Recommended Immediate Work Queue

If the next implementation pass follows this review, the highest-leverage order is:

1. Replace the default forecast chain confirmer with mandatory tx + settlement-anchor query verification.
2. Remove the bare `mark-anchored` bypass or force it through the same validated path.
3. Freeze shared `miners` field ownership between arena and mining-service.
4. Collapse arena to one authoritative result/multiplier contract.
5. Wire forecast payout to explicit reward components / quality-envelope enforcement instead of bare `reward_amount`.
6. Fix forecast reveal duplicate detection to use refreshed `economic_unit` identity.
7. Fix Poker MTT `include_provisional` behavior in the Postgres reward-window input loader.
8. Keep the new arena -> shared DB -> mining-service bridge test green as the compatibility contract while Arena remains a sidecar lane.
9. Then update the broader architecture/status docs and replay/proof surfaces to match the resulting code truth.

## 10. Drift Appendix

Important doc/code drifts observed in this pass:

- `docs/HARNESS_BACKEND_ARCHITECTURE.md` conceptually describes stronger anchor verification and deeper lane composition than the current default runtime wiring guarantees.
- `docs/MINING_DESIGN.md` and `docs/HARNESS_BACKEND_ARCHITECTURE.md` describe a richer forecast reward contract than the current raw `score -> reward_amount` payout path implements.
- `docs/IMPLEMENTATION_STATUS_2026_04_10.md` still reads too forecast-first in places and does not cleanly reflect how far Poker MTT integration already goes.
- Arena runtime implementation is ahead of older repo-wide summaries, but still behind the economic integration story implied by the architecture prose.
- Forecast design prose still sounds more Claw-reference-price-native than the currently wired Polymarket-driven short-horizon resolution path.

## 11. Bottom Line

The repo has real multi-lane progress, but the integration depth is uneven:
- forecast is the only lane with a genuinely complete settlement skeleton
- Poker MTT is materially integrated and closer to reward-bearing readiness than older summaries suggest
- arena is operationally real but still economically sidecar-shaped

The next hardening pass should not start by adding more surfaces. It should start by making the existing shared boundaries correct and unambiguous.

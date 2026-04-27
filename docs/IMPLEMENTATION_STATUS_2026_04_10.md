# ClawChain Implementation Status

Last updated: 2026-04-23

This document is the current memory checkpoint for the forecast-first mining rebuild.

It answers three questions:

1. What is actually implemented and runnable today?
2. What is still legacy drift or partial implementation?
3. What are the next major protocol/data workstreams, ordered by miner user flow value and chain value?

## 0. How To Read This Document

> **Authority:** This file is the current runtime and implementation truth for the miner path.
>
> **Rule:** If this file conflicts with `PRODUCT_SPEC.md`, `PRODUCT_SPEC_EN.md`, `SETUP.md`, or `skill/SKILL.md`, this file wins on what is actually implemented and runnable today.
>
> **Scope:** Product language and companion-shell goals still live in `PRODUCT_SPEC.md`. Protocol and settlement design still live in `MINING_DESIGN.md`.

This file distinguishes three things:

1. **Public miner path today**: what a miner can actually run, see, and rely on.
2. **Operator integration paths**: admin-only or release-review-only bridge paths such as Arena ingestion and Poker MTT reward-window work.
3. **Target-state product shell**: companion-first UX that may be defined elsewhere but is not yet implemented by default.

## Update: 2026-04-22 Hardening Delta

Landed since this checkpoint:

- forecast reward windows no longer rely only on bare submission `reward_amount`; the service now materializes per-miner reward-component rows, persists additive component fields on forecast submissions, and carries `miner_reward_rows_root` through reward-window membership and settlement-anchor payloads
- forecast fast settlement now derives `anti_abuse_discount` from open risk cases, applies it inside `quality_envelope`, and exposes real `anti_abuse_discount` separately from `admission_release_ratio` on miner status/timeline surfaces
- reward-window replay proof is no longer just membership; forecast windows now also materialize `reward_window_replay_bundle`, carrying `reward_component_rows_root`, `anti_abuse_input_rows_root`, and explicit `daily/arena overlay = deferred` state
- loopback IPs and generic transport UAs (`python-requests`, `curl`, `python-urllib`, `httpx`, `aiohttp`, `wget`) are now ignored as cluster signals, so local/dev miners do not get auto-grouped just for using a default HTTP client
- reveal duplicate gating now uses refreshed service-side `economic_unit_id` truth in the reveal path instead of the stale API-passed value
- the real Postgres Poker MTT reward-window loader now honors `include_provisional=True` and has a live Postgres regression test
- local/dev/test runtime now defaults the anchor reconcile loop to disabled unless explicitly enabled, which removes the default local-RPC connection-failure loop during service startup
- forecast progression now has a dedicated in-process loop plus an explicit `POST /admin/reconcile` operator surface; public miner/task/history reads are snapshot-oriented and no longer drive settlement/window/batch progression
- `GET /admin/anchor-jobs/{id}/chain-tx-plan` is now snapshot-only as well; it no longer hides a `reconcile()` side effect before building the typed tx plan
- a real Arena -> shared DB -> `mining-service` bridge verification now exists: the Go arena runtime can write a non-default shared `arena_multiplier`, and `ForecastMiningService.get_miner_status()` consumes that same value from the shared Postgres database

Still not finished:

- forecast still does not perform the broader daily/arena overlay merge described by the architecture prose; the landed `quality_envelope` is forecast-side only
- a local runtime with old pending anchor jobs in Postgres can still show degraded chain health until those jobs are cleared or a real RPC node is configured

## Update: 2026-04-23 Operator Integration Acceptance

Validated on local Postgres + local FastAPI + local arena runtime with a shared 33-miner manifest:

- `scripts/three_lane/run_local_acceptance.py` now drives forecast swarm using `33` submit workers per task by default; with two fast tasks this produces `66` concurrent submit workers, matching the 33-miner local acceptance target instead of under-driving the 3 second commit window
- `scripts/three_lane/run_forecast_swarm.py` now scales submit workers by `task_count`, so the local 33-miner swarm no longer collapses to a single global worker cap when two fast tasks publish together
- forecast swarm now treats `400 commit window closed` as a reveal-compensation case and still attempts reveal; this closes the edge race where the commit landed server-side but the client classified the response as a terminal failure
- `scripts/three_lane/run_local_acceptance.py` now triggers bounded `POST /admin/reconcile` calls after `forecast_capture_ready=true` and before `forecast_ready=true`; this keeps local acceptance deterministic when Polymarket Gamma has resolved but reward-window materialization is waiting on the service progression loop
- `scripts/three_lane/run_local_acceptance.py` now tears down the local forecast and arena runtime services by default after the acceptance run; pass `--leave-stack-running` only when an operator deliberately wants to keep `127.0.0.1:1317` / `127.0.0.1:18117` open for debugging
- local acceptance proof is now clean for the main three-lane path:
  - Poker MTT: `33` miners, reward window built, total reward `3300`
  - Arena: `33` results, `20` non-default multipliers written back to shared miner state
  - Forecast: `05:25` bucket reached `66 committed / 66 revealed / 33 miners / 2 tasks`, then resolved through Polymarket Gamma and finalized reward window `rw_2026042305` with total reward `343104`
- `build/three-lane/status.json` reached `all_ready=true`, `forecast.ready=true`, `poker.ready=true`, and `arena.ready=true`

Important runtime truth from this acceptance:

- the forecast hot path is now locally launchable with the 33-miner shared identity set
- Polymarket-backed fast-task resolution is not instantaneous; the `05:25` bucket had `resolve_at=05:30:00Z` but the reward window finalized at `05:32:13Z`
- a clean completed acceptance run should not leave `forecast-service` or `arenad` listening on the local ports unless `--leave-stack-running` was explicitly supplied
- the correct operator expectation is therefore:
  - `forecast_capture_ready=true` appears first when the bucket is fully revealed
  - `forecast_ready=true` follows after the service progression loop or the local acceptance harness calls `POST /admin/reconcile` and builds the reward window

This acceptance result is **not** the same thing as the current public miner contract. It proves local operator-side integration of forecast, Poker MTT, and Arena inputs; it does not mean all three are public miner-facing activities or read models today.

## 1. Current Product Reality

The active default path is no longer challenge mining.

### 1.1 Public miner path today

The public miner path today is:

- `forecast_15m` fast lane
- `daily_anchor` slow calibration lane
- externally-ingested `arena_multiplier`
- FastAPI + Postgres service ledger
- miner CLI scripts for setup, mine, and status

What this means in practice:

- `forecast_15m` is the only fully correct public reward-bearing lane today
- `daily_anchor` is calibration-only scaffolding
- `arena_multiplier` is a read-only shared-state bridge field from the miner perspective
- repo website read surfaces (`dashboard`, `network`, `risk`) are custom ClawChain read surfaces, not stock OpenClaw Control UI pages

The system is currently **service-led**, not chain-led.

That means:

- reward state lives in Postgres
- settlement logic lives in `mining-service/forecast_engine.py`
- market discovery and resolution live in `mining-service/market_data.py`
- no onchain reward window, proof anchoring, validator consensus, or staking/slashing pipeline is active yet

### 1.2 Operator integration paths under validation

Separate from the public miner path, the repo also contains operator-side integration work for:

- Arena result ingestion and multiplier bridge
- Poker MTT evidence, projection, rating, reward-window, and settlement-gating pipelines
- release-review and rollback bundles

These paths are real, but they should not be described as default public miner-facing activities unless the corresponding miner contract, read model, and rollout gate are explicitly closed.

## 2. What A Miner Can Actually Do Today

### 2.1 Onboarding

Implemented:

- generate wallet
- register miner with `public_key`
- save config pointing to the FastAPI mining service

Primary files:

- `skill/scripts/setup.py`
- `skill/scripts/config.json`
- `skill/scripts/wallet_crypto.py`

Notes:

- `setup.py --non-interactive` works
- service-side miner registration binds `economic_unit_id`
- local wallet storage path and RPC config are now aligned with the forecast path

### 2.2 Mining Loop

Implemented:

- fetch active tasks
- prioritize `daily_anchor`
- then process limited `forecast_15m` tasks
- commit
- reveal
- append local mining log

Primary files:

- `skill/scripts/mine.py`
- `mining-service/server.py`
- `mining-service/forecast_engine.py`

Current runtime shape:

- miner uses built-in `heuristic_v1`
- no tool-using harness runtime yet
- no multi-model miner strategy switching yet
- no dedicated miner-facing `History` IA yet; history is still fragmented across local JSON log, `status.py`, and repo website read surfaces

### 2.3 Status / Read Surfaces

Implemented:

- CLI status
- miner dashboard
- network view
- risk queue view

Primary files:

- `skill/scripts/status.py`
- `website/src/app/dashboard/page.tsx`
- `website/src/app/network/page.tsx`
- `website/src/app/risk/page.tsx`

Current visible data:

- public rank / ELO
- released vs held rewards
- pending resolution count
- latest fast / daily / arena artifacts
- miner task history
- miner submission history
- miner reward hold history
- miner reward window history
- artifact-backed replay proof
- public leaderboard
- open risk cases

Notes:

- miner-primary accessible surfaces today:
  - `status.py`
  - repo `/dashboard`
  - repo `/network`
- operator-oriented accessible surface today:
  - repo `/risk`
- `dashboard`, `network`, and `risk` are repo-local ClawChain read surfaces, not stock OpenClaw Control UI pages.
- There is still no shipped `Companion Home`, `Activities`, or dedicated `History` IA surface in the current repo.
- `/risk` is closer to an operator-oriented read surface than a miner-primary IA node.

## 3. Protocol / Data Chain Status

## 3.1 Fast Lane: `forecast_15m`

Implemented:

- active task generation
- BTC/ETH live Polymarket 5m market discovery by direct slug
- Binance + Polymarket snapshot pack
- baseline probability blend
- commit / reveal signatures
- settlement scoring
- anti-copy cap
- `pending_resolution` / `awaiting_resolution`
- official Polymarket resolution read when Gamma reports resolved outcome

Primary files:

- `mining-service/forecast_engine.py`
- `mining-service/market_data.py`
- `mining-service/server.py`
- `mining-service/models.py`
- `mining-service/pg_repository.py`

What is still true:

- fast lane is the most complete part of the new system
- resolution is still service-side polling / reconcile, not an independent scheduler or operator workflow
- reward is still ledgered in Postgres, not anchored to chain state

## 3.2 Daily Lane: `daily_anchor`

Implemented:

- task creation
- miner participation
- resolution
- update of `model_reliability`
- zero direct reward

Primary files:

- `mining-service/forecast_engine.py`
- `skill/scripts/mine.py`

Important limitation:

- daily is still **synthetic**, not live-market-backed
- `build_daily_anchor_task()` and `resolve_daily_task()` are deterministic local generators
- this means daily is currently useful as scaffolding and reliability plumbing, not as final market-backed protocol behavior

## 3.3 Arena Multiplier

Implemented:

- arena result ingestion
- practice vs rated handling
- human-only gating
- multiplier clamp and warmup behavior
- bridge writes are now restricted to existing shared miners and lane-owned fields only
- forecast service shared-miner writes are now routed through explicit helper categories:
  - `cluster_identity`
  - `forecast_participation`
  - `forecast_settlement`
  - `public_ranking`
  - `arena_multiplier`
  - `poker_mtt_multiplier`
- reward window / settlement batch shared updates are now routed through explicit helper paths instead of generic state patches:
  - `link_reward_window_settlement_batch`
  - `sync_open_settlement_batch`
  - `mark_settlement_batch_anchor_ready`
  - `mark_settlement_batch_anchor_submitted`
  - `mark_settlement_batch_terminal`
  - `cancel_settlement_batch`
- anchor job shared updates are now routed through explicit helper paths:
  - `update_anchor_job_broadcast`
  - `update_anchor_job_confirmation`
  - `mark_anchor_job_terminal`
- `save_reward_window / save_settlement_batch / save_anchor_job / save_artifact` now preserve unspecified fields on update in both Fake and Postgres repos
- `forecast_engine.py` no longer calls generic `update_miner()` directly; fast lane, daily lane, arena, poker MTT, cluster rebinding, and public rank refresh all route through explicit helper writers
- `forecast_engine.py` no longer uses generic `save_settlement_batch()` for partial state transitions; settlement state flips now route through explicit helpers, while `save_reward_window()` remains only for full materialization paths

Primary files:

- `mining-service/forecast_engine.py`
- `mining-service/repository.py`
- `mining-service/pg_repository.py`
- `mining-service/server.py`
- `mining-service/models.py`

Important limitation:

- there is no arena runtime in this session
- current service only accepts completed arena outcomes from elsewhere
- multiplier is therefore a bridge, not a standalone subsystem yet
- the arena admin bridge may patch only `arena_multiplier`
- the poker MTT admin bridge may patch only `poker_mtt_multiplier`
- forecast lane no longer uses direct service-level generic miner patches; shared writes are routed through explicit helper groups
- it may not insert stub miners or overwrite shared registration / anti-abuse / reward ledger fields
- missing shared miners now fail fast instead of degrading silently

## 3.4 Anti-Abuse / Economic Unit / Risk

Implemented:

- service-side `economic_unit_id`
- evidence-graph clustering from IP + user-agent hash
- same-economic-unit duplicate detection
- risk case persistence
- `admission_hold`
- held reward ledger
- rolling 1d participation stats
- open risk queue API

Primary files:

- `mining-service/forecast_engine.py`
- `mining-service/models.py`
- `mining-service/pg_repository.py`
- `mining-service/server.py`

Important limitation:

- this is still a heuristic risk graph, not a full sybil graph
- operator review is now minimal and explicit, not policy-driven:
  - read queue: `/admin/risk-cases` and `/admin/risk-cases/open`
  - decision write path: `/admin/risk-decisions/{id}/override`
  - supported outcomes today: `clear`, `suppress`, `escalate`

## 3.5 Public Read Models

Implemented:

- miner status read model
- miner submission history read model
- miner reward hold history read model
- miner reward window history read model
- public leaderboard
- basic network stats
- miner-facing settlement snapshot:
  - latest `reward_window`
  - latest `settlement_batch`
  - latest `anchor_job`
- website read surfaces:
  - `/dashboard`
  - `/network`
  - `/risk`

Primary files:

- `mining-service/forecast_engine.py`
- `mining-service/server.py`
- `website/src/lib/dashboard-data.js`
- `website/src/lib/network-data.js`
- `website/src/lib/risk-data.js`

Important limitation:

- reward window is still a minimal hourly finalized fast-lane skeleton, not a chain-facing settlement object
- public read surfaces are still operator/service-backed views, not chain-derived truth

## 3.6 Reward Window Skeleton

Implemented:

- hourly `reward_window` creation for resolved `forecast_15m`
- membership persisted on task and submission
- aggregate fields:
  - `task_count`
  - `submission_count`
  - `miner_count`
  - `total_reward_amount`
- reward window to settlement-batch linking now uses an explicit narrow writer instead of generic reward-window patching

Primary files:

- `mining-service/forecast_engine.py`
- `mining-service/models.py`
- `mining-service/pg_repository.py`

Important limitation:

- only `forecast_15m` tasks enter runtime reward windows today
- no `daily_anchor` snapshot merge
- no `arena_multiplier` snapshot merge
- no chain anchor or multi-lane merge worker

## 3.7 Settlement Batch Skeleton

Implemented:

- one-to-one `reward_window -> settlement_batch` service-led skeleton
- admin read surface for persisted settlement batches
- minimal `anchor_job` ledger
- versioned canonical anchor payload
- deterministic roots for:
  - `reward_window_ids`
  - `task_run_ids`
  - `miner_reward_rows`
- batch-level `canonical_root`
- minimal `x/settlement` typed Msg module skeleton
  - `MsgAnchorSettlementBatch`
  - keeper-backed anchor persistence
  - repeated anchor of the same `settlement_batch_id` is now idempotent onchain
  - app/module registration and genesis wiring
- build-only `chain adapter / tx builder`
  - `future_msg`
  - `typed_tx_intent`
  - `fallback_memo`
- typed anchor contract hardening
  - Python adapter rejects invalid schema / missing canonical root before CLI generation
  - Go `ValidateBasic()` and Python adapter now enforce the same required fields
  - `plan_hash`
- typed signing material compiler
  - resolves sender `submitter`
  - compiles `typed_tx_intent` into:
    - `tx_body_bytes`
    - `auth_info_bytes`
    - `sign_doc_bytes`
    - `unsigned_tx_bytes`
- typed CLI broadcast path
  - `clawchaind tx settlement anchor-batch ... --generate-only`
  - `clawchaind tx sign unsigned.json --offline --account-number N --sequence S`
  - `clawchaind tx broadcast signed.json`
  - returns `broadcast_method = typed_msg`
  - retries once on `account sequence mismatch / incorrect account sequence`
  - success writes `broadcast_tx_hash`
- CLI fallback broadcast path
  - `clawchaind tx bank send ... --note anchor:v1:... --offline --account-number N --sequence S`
  - supports keyring-dir normalization to the CLI root directory
  - resolves account number from explicit config or local genesis
  - derives next sequence from Comet `tx_search(message.sender=...)`
  - serializes local broadcasts per process
  - retries once on `account sequence mismatch / incorrect account sequence`
  - defaults to self-transfer when `anchor_to_address` is unset
  - success writes `broadcast_tx_hash`
- admin chain preflight
  - binary / key / keyring / rpc readiness
  - signing readiness: mode / account_number / next_sequence
- admin chain health
  - loop metrics: run / success / error / consecutive_error_count / last_error
  - anchor summary: pending confirmation / stale pending / failed / latest failure reason
  - alert surface: `ok / degraded / critical`
  - operator queue: stale pending confirmations and failed anchor jobs
- admin chain confirmation path
  - `confirm-chain` by persisted `broadcast_tx_hash`
  - `confirmed / pending / failed` receipt normalization
  - `confirmed` path now also verifies the persisted batch against on-chain `x/settlement` anchor content through RPC `abci_query`
  - auto progression from `anchor_submitted` to `anchored` or `anchor_failed`
- admin chain reconciliation sweep
  - `reconcile-chain` batches all `anchor_submitted + broadcast_tx_hash` jobs
  - serves as the operator/manual bulk sweep surface
- admin chain remediation write path
  - failed jobs can be re-issued through typed or fallback rebroadcast endpoints
  - remediation preserves the old failed job for audit and rebinds the batch to a new active anchor job
- background anchor confirmation loop
  - runtime can periodically call the same sweep path
  - default FastAPI runtime now starts the loop automatically
  - interval / stale-warning / consecutive-error threshold are env-configurable
  - keeps pending anchor jobs moving without manual intervention
- settlement immutability guard
  - `retry-anchor` only works for `open / anchor_ready / anchor_failed`
  - `rebuild_reward_window` is blocked after anchor preparation
  - `anchor_submitted / anchored` batches are append-only
- admin auth guard
  - default runtime now requires `CLAWCHAIN_ADMIN_API_TOKEN`
  - all `/admin/*` routes accept bearer or `X-Clawchain-Admin-Token`
- explicit batch state progression:
  - `anchor_ready`
  - `anchor_submitted`
  - `anchored`
  - `anchor_failed`
- explicit narrow batch writers:
  - open sync
  - anchor-ready materialization
  - anchor-submitted binding
  - anchored / failed terminal update

Primary files:

- `mining-service/forecast_engine.py`
- `mining-service/models.py`
- `mining-service/pg_repository.py`
- `mining-service/server.py`
- `mining-service/chain_adapter.py`
- `x/settlement/types`
- `x/settlement/keeper`
- `x/settlement/module`

Important limitation:

- no payout job
- typed Msg submit runtime now exists, but it is CLI-driven rather than an in-process SDK submitter
- current real chain submission path has two modes:
  - typed `x/settlement` path through `tx settlement anchor-batch -> tx sign -> tx broadcast`
  - memo-based fallback path through `tx bank send --note anchor:v1:...`
- chain confirmation path now has both manual and background-loop execution, but the loop is still process-local and not a durable worker/scheduler
- operator action queue is still a read-only triage surface, not an auto-remediation workflow
- failed anchor remediation is now implemented, but only as operator-triggered rebroadcast; there is still no automatic retry policy
- no end-to-end validator settlement / payout execution yet
- current sequence strategy assumes a dedicated anchor sender or explicit override

## 3.8 Artifact / Replay Surface

Implemented:

- local artifact ledger
- replay proof for `task_run`
- replay proof for `reward_window`
- artifact read surface

Current artifact kinds:

- `task_pack`
- `reward_window_membership`
- `reward_window_replay_bundle`
- `settlement_anchor_payload`
- `chain_tx_plan`
- `chain_broadcast_receipt`
- `chain_confirmation_receipt`

Primary files:

- `mining-service/forecast_engine.py`
- `mining-service/models.py`
- `mining-service/pg_repository.py`
- `mining-service/server.py`

Important limitation:

- artifacts are stored in Postgres, not object storage
- no large snapshot/feature/noise archival yet
- replay proof is still lightweight and deterministic, not a full object-storage replay bundle; current richness is reward composition lineage, not full event-log archival

## 4. Codebase Reality: Active Path vs Legacy Drift

## 4.1 Active Path

These are the real forecast-first files now:

- `mining-service/config.py`
- `mining-service/forecast_engine.py`
- `mining-service/market_data.py`
- `mining-service/models.py`
- `mining-service/pg_repository.py`
- `mining-service/repository.py`
- `mining-service/schemas.py`
- `mining-service/server.py`
- `skill/scripts/setup.py`
- `skill/scripts/mine.py`
- `skill/scripts/status.py`
- `website/src/app/dashboard/page.tsx`
- `website/src/app/network/page.tsx`
- `website/src/app/risk/page.tsx`

## 4.2 Legacy / Drifted Path

These still exist and should be treated as legacy or partially misleading:

- `mining-service/challenge_engine.py`
- `mining-service/epoch_scheduler.py`
- `mining-service/rewards.py`
- `website/src/app/page.tsx`
- `website/src/app/layout.tsx`
- `docs/protocol-spec.md`
- `docs/security-model.md`
- parts of `docs/KNOWN_LIMITATIONS.md`

Current drift examples:

- old challenge / Proof-of-Availability language is still present in website landing copy and site metadata
- website landing and navigation still point miners toward `/risk`, which does not match the desired miner-vs-operator IA split
- dashboard still has a field-label mismatch: the “Release ratio” label currently reflects `anti_abuse_discount`, not `admission_release_ratio`
- parts of `docs/KNOWN_LIMITATIONS.md` still describe future wallet and UX goals such as BIP-39 style recovery rather than the current wallet/runtime contract
- old protocol docs still describe `/clawchain/challenges/*` APIs as if they were the main path

Helper but not authority:

- `skill/scripts/doctor.py` is forecast-aware and useful as a pre-flight helper, but it is not an authority for companion control, browser IA, or miner product contract

This is now one of the largest sources of cognitive load in the repo.

## 5. Chain Perspective: What Is Not Built Yet

From the chain point of view, the current system is still **pre-chain-integration infrastructure**.

Not implemented yet:

- external artifact store
- chain-side anchoring of task / settlement roots
- validator-based settlement
- onchain staking / slashing / delegation
- chain module integration for forecast rewards
- chain-aware dispute lifecycle

So the honest protocol statement today is:

> ClawChain currently has a working service-led forecast mining path for `forecast_15m`, including deterministic reward windows, settlement batches, replay/artifact proofs, operator review/anchor APIs, and a typed `x/settlement` anchor path. It still does not have chain-executed payout settlement, validator economic state, or a background reconciliation worker.

## 6. Remaining Major Work, Grouped By Value

## 6.1 Miner User Flow Gaps

These are the biggest missing pieces from a miner’s point of view:

1. service-owned companion state store and cross-surface identity envelope
2. deterministic extension command registration for `/buddy` / `/brief` / `/pause` / `/resume`
3. `daily_anchor` idempotency hardening on repeated already-committed / already-revealed paths
4. dedicated miner-facing `Companion Home / Activities / History` IA instead of fragmented read surfaces
5. richer local doctor checks around actual anchor sender health and sequence drift
6. more than one built-in miner strategy
7. clearer miner-facing explanation of why a reward was reduced or held
8. richer replay / proof surface for one task or reward window

## 6.2 Protocol / Data Gaps

These are the biggest missing protocol/data chunks:

1. live-market-backed daily lane
2. richer replay / proof material beyond the current minimal artifact ledger
3. arena runtime bridge once the other session stabilizes the arena engine
4. append-only operator decision ledger / audit export
5. typed anchor reconciliation beyond the current operator-triggered flow

## 6.3 Chain / Settlement Gaps

These are the biggest missing chain-side chunks:

1. background chain reconciliation / finality worker
2. auditable chain-facing reward windows
3. onchain miner economic state
4. staking / slash / delegation
5. payout execution against chain state

## 7. Recommended Next Major Workstreams

If we optimize for miner value first, then protocol correctness, then chain integration, the next order should be:

### Priority 1: Daily Lane Live Upgrade

Why:

- `forecast_15m` is now the only fully correct reward-bearing lane
- `daily_anchor` still exists only as calibration-only scaffolding
- that is now the biggest design/runtime gap inside the forecast-first path

Recommended scope:

- live market-backed daily build
- live market-backed daily resolution
- keep zero direct reward if needed

### Priority 2: Replay / Artifact Upgrade

Why:

- local artifact-backed proof now exists for `task_run` and `reward_window`
- the next gap is turning the current minimal artifact ledger into richer replay material and optional object-storage refs

Recommended scope:

- richer artifact refs for one `task_run`
- richer artifact refs for one `reward_window`
- keep proof deterministic even when artifacts are absent

### Priority 3: Batch-to-Anchor Progression

Why:

- `settlement_batch` now exists and can generate anchor-shaped payload
- typed CLI submission path and onchain idempotent keeper path now exist
- the next step is to harden confirmation/reconciliation around receipts and eventual payout execution

Recommended scope:

- keep the current minimal anchor job state machine
- keep canonical chain payload/versioning stable
- keep both typed and fallback broadcast paths, with typed as the preferred anchor route
- upgrade the current operator-triggered confirmation path into a background reconciliation worker before any payout work

### Priority 4: Risk Queue Operator Decisions

Why:

- risk queue now supports minimal operator decisions
- before scale, the next gap is durable audit export and richer decision tooling

Recommended scope:

- append-only decision log
- reviewed-case export / audit trail
- no policy engine explosion

### Priority 5: Chain Anchoring

Why:

- necessary long-term
- but should come after reward window and replay surfaces exist

## 8. My Current Recommendation

The next protocol/data chain should **not** be chain anchoring yet.

The most leverageful next chain is:

> **replay/artifact upgrade + batch-to-anchor progression**

Reason:

- best protocol leverage without duplicating already-shipped history reads
- directly grounded in the current Postgres ledger
- extends deterministic proof into fuller auditability
- extends the settlement-batch skeleton toward chain anchoring
- does not conflict with the separate arena runtime work

## 9. Short Bottom Line

The rebuild has already crossed the line from “idea + docs” into “working service-led prototype”.

What is strongest today:

- fast forecast lane
- miner setup / mine / status loop
- anti-abuse and hold ledger basics
- dashboard / network / risk read surfaces

What is weakest today:

- daily lane is still synthetic
- reward windows exist only as a minimal hourly fast-lane skeleton
- replay proofs now cover reward composition lineage, but they still stop short of a full large-artifact replay bundle
- chain anchoring is real, but payout execution and background reconciliation are not
- some docs still describe larger target architecture rather than the forecast-first shipped slice

The next rational protocol/data step is to finish the forecast-first path by upgrading daily market backing, replay richness, and background anchor reconciliation, not to jump directly to full chain payout settlement.

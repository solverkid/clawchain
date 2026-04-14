# Poker MTT Sidecar Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a separate `poker mtt` runtime for ClawChain by driving the external `lepoker-gameserver` as an independent sidecar service first, without mixing it into the current Arena / Bluff tournament runtime.

**Decision:** This track is explicitly **not** an extension of the current Arena runtime. It is a second tournament line with its own naming, adapter boundary, metrics, and operational flow.

**Source Donor:** `lepoker-gameserver` on branch `dev`, treated as an independent repository and GitNexus index.

---

## Scope Check

This plan covers one shippable direction:

- run `lepoker-gameserver` as a standalone Poker MTT sidecar
- add a thin ClawChain adapter that talks to it over process or network boundaries
- define a minimal contract for tournament lifecycle, seat assignment, ranking, and completion
- keep Poker MTT terminology and storage separate from Arena / Bluff Arena

This plan intentionally does **not** cover:

- merging donor code into `arena/*`
- renaming Arena concepts to fit poker
- replacing the donor NLH kernel in phase 1
- unifying rating / multiplier logic with current Arena rating
- deleting features from `lepoker-gameserver` before the sidecar path works

If those become in-scope, write follow-up plans after the sidecar path is stable.

## Naming And Boundary Rules

These rules are mandatory. They exist to stop `poker mtt` from contaminating the current Bluff Arena line.

### Product language

- Current line keeps its existing names: `arena`, `bluff arena`, `arena mtt`, `arena runtime`
- New line is always called: `poker mtt`
- Do not call the new line `arena poker`
- Do not reuse `arena` as a generic synonym for all tournaments

### Code and package language

- Existing `arena/*` packages remain Bluff Arena only
- New code should live under a distinct prefix such as `pokermtt/*` or `poker_mtt/*`
- New env vars, metrics, logs, config keys, DB tables, and API routes should use `poker_mtt`
- Do not place donor code under `arena/*`
- Do not make GitNexus queries against `lepoker-gameserver` using the `clawchain` repo name

### Data and operational boundaries

- `poker mtt` gets its own tournament IDs, state machine, standings, and completion records
- `arena` and `poker mtt` should not share projector tables or event topics in phase 1
- observability must separate `arena_*` and `poker_mtt_*`
- test fixtures must distinguish poker entrants from arena entrants

## Why Plan B Is The Right First Move

`lepoker-gameserver` has already run real MTT traffic for years. The stability you want is not only in its card logic. It is in the full shell around it:

- tournament creation and admission
- table hub lifecycle
- seat allocation and split tables
- serialized command handling
- ranking snapshots and death notices
- final-table style tournament progression

If we copy packages directly into `clawchain` before proving the boundary, we inherit its globals, Redis assumptions, HTTP surface, room modes, and operational coupling all at once. That would be a donor merge, not a controlled adoption.

Using it as a sidecar first preserves the stable shell while keeping the blast radius small.

## Donor Components To Reuse First

The donor code has clear centers of gravity. Phase 1 should treat these as the authoritative shell:

- `run_server/main.go`: process entry and HTTP surface
- `service/http_client.go`: MTT start flow and creation endpoints
- `server/hub.go`: room and table runtime, client loop wiring
- `server/mtt.go`: `MTTController`, participant and tournament control
- `server/ranking.go`: MTT ranking, died ordering, ranking snapshots
- `server/game_mode_interface.go`: kernel abstraction point
- `server/game_nlh_handler.go`: current NLH rules implementation

Key proven flows already exist in donor code:

- `StartMTT`
- `NewMTTOrSNG`
- `PreSplitTable`
- `RunWriteAndRead`
- `calculateRanking`
- `calculateMTTRanking`

## Target Architecture

```text
ClawChain Control Plane
        |
        v
Poker MTT Adapter (inside clawchain)
        |
        v
Poker MTT Sidecar (lepoker-gameserver)
        |
        +--> ranking snapshots
        +--> seat assignments
        +--> elimination / completion events
```

### ClawChain responsibilities

- decide when a Poker MTT tournament should exist
- register the entrant set
- invoke start / stop / query operations on the sidecar
- persist only the ClawChain-facing projection it needs
- keep Arena and Poker MTT schedules separate

### Sidecar responsibilities

- own the live poker tournament state machine
- own seating, table balancing, ranking, and completion
- own poker-specific action semantics
- expose enough read APIs for ClawChain to observe progress

### What not to do in phase 1

- do not import donor `server/*` packages into root `clawchain` code
- do not share in-memory structs across repo boundaries
- do not rewrite donor ranking logic before the shell path is proven
- do not try to make one runtime serve both Bluff Arena and Poker MTT

## Phase Plan

### Phase 0: Donor Isolation And Reproducible Local Run

- [ ] keep `lepoker-gameserver` as its own git repo and branch line
- [ ] keep GitNexus indexed separately as `lepoker-gameserver`
- [ ] verify local startup path with donor-local config only
- [ ] document required backing services and mock-friendly startup flags

Exit criteria:

- donor repo can be started without touching `arena/*`
- donor repo stays clean in its own git status
- parent `clawchain` repo does not try to commit donor artifacts

### Phase 1: Freeze The Sidecar Contract

- [ ] define the minimal ClawChain-facing contract for Poker MTT
- [ ] choose transport for first integration: HTTP/JSON by default
- [ ] define external IDs and status enums owned by ClawChain
- [ ] define which fields are mirrored from donor ranking vs owned locally

Recommended first contract:

- `create_tournament`
- `register_players`
- `start_tournament`
- `get_tournament_state`
- `get_table_assignments`
- `get_ranking_snapshot`
- `submit_action` or `submit_bot_action`
- `close_tournament` or `abort_tournament`

Outbound event or poll states:

- `scheduled`
- `seating`
- `running`
- `player_eliminated`
- `table_rebalanced`
- `final_table`
- `completed`
- `aborted`

Exit criteria:

- one written contract exists that never mentions `arena` as a generic name
- ClawChain side uses `poker_mtt` types only

### Phase 2: Build The ClawChain Poker MTT Adapter

- [ ] create a dedicated adapter namespace such as `pokermtt/`
- [ ] add a sidecar client module with retries, idempotency, and timeouts
- [ ] add a ClawChain-facing service that translates between local models and donor models
- [ ] store minimal projection records under `poker_mtt_*` naming
- [ ] keep Arena runtime code untouched

Suggested internal module split:

- `pokermtt/client`: HTTP client for sidecar
- `pokermtt/model`: ClawChain-owned DTOs and IDs
- `pokermtt/service`: orchestration and mapping logic
- `pokermtt/store`: local projection persistence if needed
- `pokermtt/integration`: end-to-end smoke tests

Exit criteria:

- ClawChain can create and observe a Poker MTT without importing donor runtime packages
- no `arena/*` package depends on `pokermtt/*`

### Phase 3: Run A Narrow End-To-End Flow

- [ ] start donor sidecar in local mode
- [ ] create one Poker MTT from ClawChain
- [ ] register mock entrants
- [ ] launch tournament
- [ ] read seat assignments and ranking snapshots
- [ ] observe elimination and tournament completion

Phase 3 is successful when:

- one local Poker MTT can be created, started, observed, and completed through ClawChain
- ClawChain can show standings without reading donor internals directly

### Phase 4: Tighten Reliability And Operational Controls

- [ ] add circuit-breaking and timeout behavior in the adapter
- [ ] add local replay or audit logging on the ClawChain side
- [ ] define health checks for sidecar reachability and tournament freshness
- [ ] separate dashboards and alerts for `poker_mtt`

Exit criteria:

- a broken sidecar does not take down Arena code paths
- `poker_mtt` health is observable independently

### Phase 5: Start Controlled Reduction

Only after the sidecar path is stable:

- [ ] identify donor features not needed for ClawChain
- [ ] remove unneeded room modes from the sidecar deployment path
- [ ] isolate poker-kernel-specific interfaces behind a thinner adapter
- [ ] evaluate whether selected shell components should later be extracted or reimplemented

This is where subtraction starts. Not before.

## External Contract Sketch

The first contract should be deliberately small and boring.

### Command surface

| ClawChain command | Purpose | Notes |
| --- | --- | --- |
| `create_tournament` | Create donor tournament record | returns `poker_mtt_tournament_id` |
| `register_players` | Supply entrants or late registrations | batch friendly |
| `start_tournament` | Transition to live execution | must be idempotent |
| `submit_action` | Forward a player or bot action | only needed once player control exists |
| `abort_tournament` | Administrative stop | phase 1 may stub this |

### Read surface

| Read API | Purpose | Notes |
| --- | --- | --- |
| `get_tournament_state` | lifecycle and counters | poll-safe |
| `get_table_assignments` | seat map and table membership | needed for UI and bots |
| `get_ranking_snapshot` | current standings | can be eventually consistent |
| `get_player_status` | alive / eliminated / chip state | optional in v1 |

## Model Mapping

The mapping should be explicit and one-way at first.

| ClawChain concept | Poker MTT concept | Donor concept |
| --- | --- | --- |
| `poker_mtt_tournament_id` | tournament identity | `MTTID` |
| entrant | tournament participant | `participant` / session user |
| table | live poker table | `Hub` |
| seat assignment | player-to-seat mapping | room seat state |
| standing snapshot | tournament ranking view | ranking snapshot keys |
| elimination event | player busted out | died rank notice |

Rule: ClawChain owns its own external IDs even when donor IDs are mirrored internally.

## Risks And Mitigations

### Risk: donor runtime has deep Redis or infra assumptions

Mitigation:

- keep phase 0 focused on a reproducible local run
- use donor mock switches where available
- isolate missing infra behind dev-only startup notes instead of rewriting immediately

### Risk: naming drift causes poker logic to leak into arena code

Mitigation:

- enforce `pokermtt/*` package boundary
- reserve `arena/*` for Bluff Arena only
- reject mixed naming in new files, env vars, and routes

### Risk: adapter starts mirroring too much donor internals

Mitigation:

- keep the first contract narrow
- mirror only what ClawChain needs to schedule, observe, and settle Poker MTT
- avoid re-exporting donor structs

### Risk: premature subtraction breaks the stable shell

Mitigation:

- do not delete donor features before end-to-end proof
- first prove startup, seating, ranking, completion
- subtract only after observability exists

## Immediate Next Tasks

- [ ] write the Poker MTT sidecar contract doc
- [ ] run donor locally with explicit startup notes
- [ ] add a `pokermtt/` adapter skeleton in `clawchain`
- [ ] implement one smoke path: create -> register -> start -> observe ranking -> complete

## Success Criteria

This plan is successful when all of the following are true:

- `poker mtt` is treated as a separate product line from Bluff Arena
- `lepoker-gameserver` runs as an external sidecar, not a package dump into `arena/*`
- ClawChain can drive one full Poker MTT lifecycle through an adapter boundary
- naming, metrics, and operational ownership remain separate
- only after that do we begin controlled reduction of donor complexity

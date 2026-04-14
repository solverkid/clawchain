# Arena Runtime Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-ready Go Arena runtime worker that implements the frozen MTT state machine, persists authoritative tournament truth in Postgres, exposes Arena action/read APIs, and writes multiplier-compatible Arena outputs into the shared harness database.

**Architecture:** Add a new `arenad` worker inside the root Go module using focused `arena/*` packages. Use a hub actor per tournament and a table actor per table over a Postgres event log + snapshot store, then derive standing/live-table/postgame read models and rating outputs from authoritative events; keep the existing Python `mining-service` compatible by writing the existing `miners` and `arena_result_entries` tables directly from the Go rating writer.

**Tech Stack:** Go 1.22, standard library (`net/http`, `database/sql`, `context`, `encoding/json`, `log/slog`), Postgres via `github.com/lib/pq`, current root `Makefile`, existing shared harness Postgres schema, `go test`

---

### Scope Check

This plan intentionally covers one shippable subsystem: the Arena runtime worker plus the shared-database compatibility writes required for current reward/miner-status surfaces.

This plan intentionally does **not** cover:

- website / operator console work
- chain settlement / on-chain anchor integration
- replacing the Python harness monolith
- production deploy automation beyond local/dev startup

If those become in-scope, write separate plans after this worker lands.

### Execution Rules

- Use `@superpowers:test-driven-development` on every task.
- Use `@superpowers:verification-before-completion` before claiming any task is done.
- Keep commits small and vertical; one task should map to one or two commits, not one giant branch dump.
- Do not add a second storage abstraction or a message bus unless a test proves the simpler path fails.
- Follow the frozen truth in [docs/ARENA_RUNTIME_STATE_MACHINE_SPEC.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_RUNTIME_STATE_MACHINE_SPEC.md), [docs/ARENA_RUNTIME_ARCHITECTURE.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_RUNTIME_ARCHITECTURE.md), [docs/ARENA_MTT_USER_FLOW.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_MTT_USER_FLOW.md), and [docs/ARENA_MEASUREMENT_SPEC.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_MEASUREMENT_SPEC.md).

### File Structure

**Files:**
- Create: `cmd/arenad/main.go`
- Create: `arena/app/app.go`
- Create: `arena/app/app_test.go`
- Create: `arena/config/config.go`
- Create: `arena/config/config_test.go`
- Create: `arena/model/types.go`
- Create: `arena/model/state.go`
- Create: `arena/model/ids.go`
- Create: `arena/model/types_test.go`
- Create: `arena/store/repository.go`
- Create: `arena/store/postgres/migrate.go`
- Create: `arena/store/postgres/repository.go`
- Create: `arena/store/postgres/migrate_test.go`
- Create: `arena/store/postgres/repository_test.go`
- Create: `arena/store/postgres/schema/001_runtime_core.sql`
- Create: `arena/store/postgres/schema/002_runtime_projectors.sql`
- Create: `arena/store/postgres/schema/003_runtime_rating.sql`
- Create: `arena/testutil/clock.go`
- Create: `arena/testutil/store.go`
- Create: `arena/testutil/fixtures.go`
- Create: `arena/hub/commands.go`
- Create: `arena/hub/events.go`
- Create: `arena/hub/state.go`
- Create: `arena/hub/service.go`
- Create: `arena/hub/prestart_test.go`
- Create: `arena/hub/orchestration_test.go`
- Create: `arena/table/commands.go`
- Create: `arena/table/events.go`
- Create: `arena/table/state.go`
- Create: `arena/table/engine.go`
- Create: `arena/table/engine_test.go`
- Create: `arena/table/actor.go`
- Create: `arena/table/actor_test.go`
- Create: `arena/gateway/submit.go`
- Create: `arena/gateway/submit_test.go`
- Create: `arena/session/manager.go`
- Create: `arena/session/manager_test.go`
- Create: `arena/httpapi/server.go`
- Create: `arena/httpapi/lobby_routes.go`
- Create: `arena/httpapi/public_routes.go`
- Create: `arena/httpapi/action_routes.go`
- Create: `arena/httpapi/session_routes.go`
- Create: `arena/httpapi/admin_routes.go`
- Create: `arena/httpapi/server_test.go`
- Create: `arena/projector/lobby.go`
- Create: `arena/projector/standing.go`
- Create: `arena/projector/live_table.go`
- Create: `arena/projector/postgame.go`
- Create: `arena/projector/projector_test.go`
- Create: `arena/recovery/service.go`
- Create: `arena/recovery/service_test.go`
- Create: `arena/replay/replayer.go`
- Create: `arena/replay/replayer_test.go`
- Create: `arena/rating/mapper.go`
- Create: `arena/rating/state.go`
- Create: `arena/rating/writer.go`
- Create: `arena/rating/writer_test.go`
- Create: `arena/integration/runtime_flow_test.go`
- Create: `arena/integration/recovery_flow_test.go`
- Create: `arena/integration/chaos_test.go`
- Create: `deploy/docker-compose.arena.yml`
- Modify: `Makefile`
- Modify: `README.md`
- Modify: `README_ZH.md`
- Modify: `go.mod`
- Modify: `go.sum`

**Responsibilities:**
- `cmd/arenad/main.go`: process entrypoint, config load, app boot, graceful shutdown.
- `arena/app/app.go`: composition root for repository, actors, HTTP server, recovery boot, and shutdown ordering.
- `arena/config/config.go`: env-backed runtime config for Postgres, HTTP listen address, timeouts, blind schedule path, and replay controls.
- `arena/model/*.go`: shared Arena enums, IDs, DTOs, deterministic builders, and serialization helpers.
- `arena/store/repository.go`: authoritative storage interface for waves, tournaments, tables, events, snapshots, projectors, deadlines, and rating outputs.
- `arena/store/postgres/*`: migration runner and concrete Postgres implementation using one shared harness DB.
- `arena/testutil/*`: fake clock, fake repository, deterministic entrant/table fixtures for fast tests.
- `arena/hub/*`: pre-start field lock, seating, round barrier, rebalance, final table, time-cap, completion, DQ handling.
- `arena/table/*`: pure hand engine plus actor wrapper for deadlines, `state_seq`, idempotency, timeout/manual race handling.
- `arena/gateway/submit.go`: request validation pipeline, submission ledger writes, duplicate replay, stale rejection.
- `arena/session/*`: reconnect hydration, session handoff, active-session registry, and read-only gating after elimination or DQ.
- `arena/httpapi/*`: lobby/registration APIs, public read APIs, action write APIs, session/reconnect routes, admin/operator routes, health/readiness endpoints.
- `arena/projector/*`: derived lobby/standing/live-table/postgame read models and rebuild-safe consumers.
- `arena/recovery/*`: startup recovery, expired deadline synthesis, recoverable pause, void escalation.
- `arena/replay/*`: deterministic replay and parity proof generation.
- `arena/rating/*`: completion-to-rating mapping, `confidence_weight`, `no_multiplier`, `mu / sigma / arena_reliability`, public ELO/ladder state, and shared-table writes to `miners` and `arena_result_entries`.
- `arena/integration/*`: full tournament, recovery, and chaos coverage against the real app wiring.
- `deploy/docker-compose.arena.yml`: local Postgres for Arena runtime tests and manual smoke runs.
- `Makefile`: build/test/run targets for `arenad`.
- `README*.md`: developer entrypoints and local run instructions.

### Architectural Decisions to Preserve During Implementation

- Keep the new Go code under top-level `arena/` to match existing repo conventions; do **not** introduce a brand new standalone repo or a deep `internal/` tree unless forced by an access-control problem.
- Keep the Python `mining-service` untouched for MVP; the Go rating writer must write the compatibility rows the Python service already reads.
- Use one shared Postgres truth source with append-only Arena event tables and disposable projectors; do **not** insert Redis/Kafka just to feel distributed.
- Make the hand engine pure and side-effect free; the actor layer is the only place allowed to touch clocks, deadlines, or storage.
- Keep all round-level fairness rules exactly aligned with the frozen spec: no per-round full reshuffle, time-cap only after the current round, DQ only at safe points, and `action_rejected` never increments `state_seq`.

### Task 1: Scaffold `arenad` and Local Dev Boot Path

**Files:**
- Create: `cmd/arenad/main.go`
- Create: `arena/app/app.go`
- Create: `arena/app/app_test.go`
- Create: `arena/config/config.go`
- Create: `arena/config/config_test.go`
- Create: `deploy/docker-compose.arena.yml`
- Modify: `Makefile`

- [ ] **Step 1: Write the failing bootstrap tests**

```go
func TestNewAppRequiresDatabaseURL(t *testing.T) {
	cfg := config.Config{}
	_, err := app.New(cfg)
	if err == nil || !strings.Contains(err.Error(), "database url") {
		t.Fatalf("expected missing database url error, got %v", err)
	}
}

func TestLoadConfigReadsArenaEnv(t *testing.T) {
	t.Setenv("ARENA_DATABASE_URL", "postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable")
	t.Setenv("ARENA_HTTP_ADDR", "127.0.0.1:18117")

	cfg := config.LoadFromEnv()
	if cfg.DatabaseURL == "" || cfg.HTTPAddr != "127.0.0.1:18117" {
		t.Fatalf("unexpected config: %+v", cfg)
	}
}
```

- [ ] **Step 2: Run the bootstrap tests to verify they fail**

Run: `go test ./arena/app ./arena/config -run 'TestNewAppRequiresDatabaseURL|TestLoadConfigReadsArenaEnv' -v`
Expected: FAIL with missing packages/files for `arena/app` and `arena/config`.

- [ ] **Step 3: Write the minimal boot implementation**

```go
func main() {
	cfg := config.MustLoadFromEnv()
	application, err := app.New(cfg)
	if err != nil {
		log.Fatal(err)
	}
	if err := application.Run(context.Background()); err != nil {
		log.Fatal(err)
	}
}
```

Implement:
- `config.Config` with `DatabaseURL`, `HTTPAddr`, `LogLevel`, `ShutdownTimeout`, `MigrationsDir`
- `app.New` that validates required config only
- `app.Run` / `app.Close` skeletons
- `docker-compose.arena.yml` with a local Postgres instance on `55432`
- Makefile targets:
  - `build-arena`
  - `test-arena`
  - `run-arena`
  - `arena-db-up`
  - `arena-db-down`

- [ ] **Step 4: Run the tests and a build**

Run: `go test ./arena/app ./arena/config -v && go build ./cmd/arenad`
Expected: PASS and a successful `arenad` build.

- [ ] **Step 5: Commit**

```bash
git add cmd/arenad/main.go arena/app arena/config deploy/docker-compose.arena.yml Makefile
git commit -m "feat: scaffold arenad bootstrap"
```

### Task 2: Define Arena Models, IDs, and Authoritative SQL Schema

**Files:**
- Create: `arena/model/types.go`
- Create: `arena/model/state.go`
- Create: `arena/model/ids.go`
- Create: `arena/model/types_test.go`
- Create: `arena/store/repository.go`
- Create: `arena/store/postgres/migrate.go`
- Create: `arena/store/postgres/migrate_test.go`
- Create: `arena/store/postgres/schema/001_runtime_core.sql`
- Create: `arena/store/postgres/schema/002_runtime_projectors.sql`
- Create: `arena/store/postgres/schema/003_runtime_rating.sql`
- Modify: `go.mod`
- Modify: `go.sum`

- [ ] **Step 1: Write the failing model and migration tests**

```go
func TestDeterministicArenaIDs(t *testing.T) {
	if model.TableID("tour_1", 2) != model.TableID("tour_1", 2) {
		t.Fatal("expected deterministic table id")
	}
}

func TestMigrateCreatesCoreArenaTables(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	for _, table := range []string{
		"arena_wave",
		"arena_tournament",
		"arena_table",
		"arena_event_log",
		"outbox_event",
		"outbox_dispatch",
		"projector_cursor",
		"dead_letter_event",
		"submission_ledger",
		"arena_action",
		"arena_action_deadline",
		"arena_round_barrier",
		"arena_operator_intervention",
		"arena_rating_input",
	} {
		require.True(t, tableExists(t, db, table), table)
	}
}
```

- [ ] **Step 2: Run the focused tests to verify they fail**

Run: `ARENA_TEST_DATABASE_URL=postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable go test ./arena/model ./arena/store/postgres -run 'TestDeterministicArenaIDs|TestMigrateCreatesCoreArenaTables' -v`
Expected: FAIL because the model package, migration runner, and SQL schema do not exist yet.

- [ ] **Step 3: Write the minimal model and schema implementation**

```go
type TournamentState string

const (
	TournamentStateScheduled TournamentState = "scheduled"
	TournamentStateReady     TournamentState = "ready"
	TournamentStateLiveMTT   TournamentState = "live_multi_table"
	TournamentStateCompleted TournamentState = "completed"
)

func TableID(tournamentID string, tableNo int) string {
	return fmt.Sprintf("tbl:%s:%02d", tournamentID, tableNo)
}
```

Implement:
- all frozen enums from the state-machine spec
- deterministic ID builders for wave / tournament / table / hand / phase / barrier / event
- repository interface boundaries for waves, tournaments, tables, events, snapshots, projectors, rating writes
- SQL migrations for:
  - authoritative tables
  - ingress tables `submission_ledger` and `arena_action`
  - projector tables
  - projector delivery tables `outbox_event`, `outbox_dispatch`, `projector_cursor`, `dead_letter_event`
  - rating/multiplier tables
  - compatibility writes to current shared tables `miners` and `arena_result_entries`
  - snapshot tables:
    - `arena_tournament_snapshot`
    - `arena_table_snapshot`
    - `arena_hand_snapshot`
    - `arena_standing_snapshot`
- required replay-truth fields on authoritative rows:
  - `rng_root_seed`
  - deterministic seed derivation inputs
  - `schema_version`
  - `policy_bundle_version`
  - `state_hash`
  - `payload_hash`
  - `artifact_ref`
  - `state_hash_after`
- `postgres.Migrate` that runs embedded SQL in order and is safe to re-run

- [ ] **Step 4: Run the model and migration tests**

Run: `ARENA_TEST_DATABASE_URL=postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable go test ./arena/model ./arena/store/postgres -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arena/model arena/store/postgres go.mod go.sum
git commit -m "feat: add arena schema and model contracts"
```

### Task 3: Implement Pre-start Hub Flow, Field Lock, and Deterministic Seating

**Files:**
- Create: `arena/testutil/fixtures.go`
- Create: `arena/hub/commands.go`
- Create: `arena/hub/events.go`
- Create: `arena/hub/state.go`
- Create: `arena/hub/service.go`
- Create: `arena/hub/prestart_test.go`

- [ ] **Step 1: Write the failing pre-start hub tests**

```go
func TestRatedShardStartsOnlyAt56To64(t *testing.T) {
	h := newHubForTest(t, 64)
	result := h.LockAndPack()
	require.Equal(t, "rated", result.Tournaments[0].RatedOrPractice)
	require.Len(t, result.Tournaments[0].EntrantIDs, 64)
}

func TestRatedUnderfillDowngrades48To55ToPractice(t *testing.T) {
	h := newHubForTest(t, 52)
	result := h.LockAndPack()
	require.Equal(t, "practice", result.Tournaments[0].RatedOrPractice)
	require.True(t, result.Tournaments[0].NoMultiplier)
}

func TestSeatsPublishedAllowsSingleShardLocalRepublish(t *testing.T) {
	h := newHubForTest(t, 64)
	require.NoError(t, h.PublishSeats())
	require.NoError(t, h.ForceRemoveBeforeStart("miner-07"))
	require.NoError(t, h.RepublishSeats())
	require.ErrorContains(t, h.RepublishSeats(), "republish already used")
}
```

- [ ] **Step 2: Run the pre-start tests to verify they fail**

Run: `go test ./arena/hub -run 'TestRatedShardStartsOnlyAt56To64|TestRatedUnderfillDowngrades48To55ToPractice|TestSeatsPublishedAllowsSingleShardLocalRepublish' -v`
Expected: FAIL because the hub package and pre-start state machine are not implemented.

- [ ] **Step 3: Implement the minimal pre-start hub**

```go
func (s *Service) LockField(ctx context.Context, waveID string) error {
	// snapshot entrants and freeze mutation
}

func (s *Service) AssignShards(ctx context.Context, waveID string) error {
	// rated: 56..64 only; 48..55 downgrade; <48 cancel
}

func (s *Service) GenerateAndPublishSeating(ctx context.Context, tournamentID string) error {
	// constrained-random initial seating; no per-round reshuffle
}
```

Implement:
- `registration_open -> registration_frozen -> field_locked -> seating_generated -> seats_published -> ready`
- deterministic shard packing
- single shard-local republish before `start_armed`
- `arena_reseat_event` authoring for pre-start republish
- hub-side `arena_operator_intervention` creation for forced removal
- durable `arena_tournament_snapshot` writes at:
  - `field_locked`
  - `seating_published`

- [ ] **Step 4: Run the full hub pre-start test file**

Run: `go test ./arena/hub -run 'TestRated|TestSeatsPublished' -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arena/hub arena/testutil/fixtures.go
git commit -m "feat: implement arena prestart hub flow"
```

### Task 4: Build the Pure Table Hand Engine

**Files:**
- Create: `arena/table/commands.go`
- Create: `arena/table/events.go`
- Create: `arena/table/state.go`
- Create: `arena/table/engine.go`
- Create: `arena/table/engine_test.go`

- [ ] **Step 1: Write the failing hand-engine tests**

```go
func TestTimeoutPolicyMapsByPhase(t *testing.T) {
	state := givenTableState("wager", 200)
	next, events, err := table.Apply(state, table.ApplyPhaseTimeout{SeatNo: 3})
	require.NoError(t, err)
	require.Equal(t, table.ActionAutoFold, events[len(events)-1].AutoAction)
	require.Equal(t, next.ActingSeatNo, 4)
}

func TestEliminationResolvedOnlyAtHandClose(t *testing.T) {
	state := givenBustedButOpenHand()
	next, _, err := table.Apply(state, table.CloseHand{})
	require.NoError(t, err)
	require.Equal(t, table.SeatStateEliminated, next.Seats[5].State)
}

func TestNoAllInNoSidePotInvariant(t *testing.T) {
	state := givenShortStackState()
	_, _, err := table.Apply(state, table.SubmitArenaAction{SeatNo: 4, ActionType: "raise", Amount: 999999})
	require.ErrorContains(t, err, "illegal action")
}
```

- [ ] **Step 2: Run the engine tests to verify they fail**

Run: `go test ./arena/table -run 'TestTimeoutPolicyMapsByPhase|TestEliminationResolvedOnlyAtHandClose|TestNoAllInNoSidePotInvariant' -v`
Expected: FAIL because the hand engine does not exist.

- [ ] **Step 3: Implement the minimal pure hand engine**

```go
func Apply(state State, cmd Command) (State, []Event, error) {
	switch c := cmd.(type) {
	case StartHand:
		return applyStartHand(state, c)
	case SubmitArenaAction:
		return applyAction(state, c)
	case ApplyPhaseTimeout:
		return applyTimeout(state, c)
	case CloseHand:
		return applyCloseHand(state)
	default:
		return state, nil, ErrUnknownCommand
	}
}
```

Implement:
- `signal`, `probe`, `wager` phases
- blind/ante deduction
- capped raise reopening
- timeout policy
- per-hand timeout streak accounting hooks
- deterministic elimination tie-break inputs
- no all-in / no side-pot enforcement

- [ ] **Step 4: Run the full table engine test file**

Run: `go test ./arena/table -run 'Test.*' -v`
Expected: PASS for engine tests, with actor tests still absent or failing.

- [ ] **Step 5: Commit**

```bash
git add arena/table/commands.go arena/table/events.go arena/table/state.go arena/table/engine.go arena/table/engine_test.go
git commit -m "feat: add pure arena table engine"
```

### Task 5: Wrap the Engine in a Table Actor with Deadlines and `state_seq`

**Files:**
- Create: `arena/testutil/clock.go`
- Create: `arena/testutil/store.go`
- Create: `arena/table/actor.go`
- Create: `arena/table/actor_test.go`
- Modify: `arena/store/postgres/repository.go`
- Modify: `arena/store/postgres/repository_test.go`

- [ ] **Step 1: Write the failing table-actor tests**

```go
func TestDuplicateRequestReturnsOriginalResult(t *testing.T) {
	actor := newActorForTest(t)
	first := submitAction(t, actor, "req-1", 7)
	second := submitAction(t, actor, "req-1", 7)
	require.Equal(t, first.ResultEventID, second.ResultEventID)
}

func TestRejectedActionDoesNotAdvanceStateSeq(t *testing.T) {
	actor := newActorForTest(t)
	before := actor.State().StateSeq
	_, err := actor.Handle(context.Background(), submitIllegalAction("req-illegal"))
	require.Error(t, err)
	require.Equal(t, before, actor.State().StateSeq)
}

func TestManualActionAndTimeoutRaceOnlyCommitsOneWinner(t *testing.T) {
	actor := newActorForTest(t)
	result := raceManualAndTimeout(t, actor)
	require.True(t, result.OneCommitted)
}

func TestPhaseOpenPersistsDeadlineAndSnapshotAtomically(t *testing.T) {
	actor, repo := newActorWithRepoForTest(t)
	require.NoError(t, actor.OpenPhase(context.Background(), fixtureSignalPhase()))
	require.True(t, repo.HasOpenDeadline("phase-signal-1"))
	require.True(t, repo.HasTableSnapshot("tbl:tour_1:01"))
}
```

- [ ] **Step 2: Run the actor tests to verify they fail**

Run: `go test ./arena/table -run 'TestDuplicateRequestReturnsOriginalResult|TestRejectedActionDoesNotAdvanceStateSeq|TestManualActionAndTimeoutRaceOnlyCommitsOneWinner' -v`
Expected: FAIL because the actor, fake clock, and fake store do not exist yet.

- [ ] **Step 3: Implement the minimal table actor**

```go
type Actor struct {
	mu    sync.Mutex
	state State
	clock Clock
	store store.Repository
}

func (a *Actor) Handle(ctx context.Context, cmd CommandEnvelope) (Result, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	// request_id dedupe, state_seq check, engine apply, deadline update, persist
}
```

Implement:
- serialized command handling
- `request_id` idempotency
- `expected_state_seq` exact match check
- durable deadline open/close writes
- durable `arena_table_snapshot` writes at phase open, hand close, rebalance apply, and final-table seating apply
- durable `arena_hand_snapshot` writes at hand close
- synthetic timeout command support
- timeout streak counted per hand, not per phase
- same-transaction persistence for:
  - event append
  - table snapshot mutation
  - `arena_action_deadline` open/close mutation

- [ ] **Step 4: Run table package tests**

Run: `go test ./arena/table -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arena/testutil/clock.go arena/testutil/store.go arena/table/actor.go arena/table/actor_test.go
git commit -m "feat: add arena table actor and state seq handling"
```

### Task 6: Implement Hub Orchestration for Rounds, Rebalance, Final Table, and Time-Cap

**Files:**
- Modify: `arena/hub/service.go`
- Create: `arena/hub/orchestration_test.go`

- [ ] **Step 1: Write the failing orchestration tests**

```go
func TestRoundBarrierWaitsForAllActiveTables(t *testing.T) {
	h := newLiveHubForTest(t, 24, 3)
	h.MarkHandClosed("tbl:1")
	h.MarkHandClosed("tbl:2")
	require.False(t, h.CanAdvanceRound())
	h.MarkHandClosed("tbl:3")
	require.True(t, h.CanAdvanceRound())
}

func TestFinalTableTakesPrecedenceOverNormalRebalance(t *testing.T) {
	h := newLiveHubForTest(t, 8, 2)
	require.Equal(t, hub.TransitionFinalTable, h.NextBarrierDecision())
}

func TestTimeCapStopsAfterCurrentRoundNotCurrentHand(t *testing.T) {
	h := newLiveHubForTest(t, 17, 2)
	h.ArmTimeCap()
	require.True(t, h.TerminateAfterCurrentRound())
	require.False(t, h.TerminateAfterCurrentHand())
}
```

- [ ] **Step 2: Run the orchestration tests to verify they fail**

Run: `go test ./arena/hub -run 'TestRoundBarrierWaitsForAllActiveTables|TestFinalTableTakesPrecedenceOverNormalRebalance|TestTimeCapStopsAfterCurrentRoundNotCurrentHand' -v`
Expected: FAIL because live orchestration is not implemented.

- [ ] **Step 3: Implement the minimal hub live loop**

```go
func (s *Service) OnTableHandClosed(ctx context.Context, evt table.HandClosed) error {
	// accumulate barrier, apply eliminations, refresh standing, choose next transition
}
```

Implement:
- one-hand-per-active-table-per-round barrier accounting
- break shortest table
- rebalance fairness using blind-distance preference
- `players_remaining <= 8` final table transition
- `P=9..13 => N=2` late-stage exception
- `terminate_after_current_round`
- live DQ safe-point application
- durable hub-level snapshots at:
  - round barrier after standing refresh
  - final table transition completed
  - tournament completed
- durable `arena_standing_snapshot` writes after every authoritative standing refresh

- [ ] **Step 4: Run the full hub test suite**

Run: `go test ./arena/hub -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arena/hub/service.go arena/hub/orchestration_test.go
git commit -m "feat: implement arena round barrier and final table orchestration"
```

### Task 7: Add the Submission Gateway and HTTP API Surface

**Files:**
- Create: `arena/gateway/submit.go`
- Create: `arena/gateway/submit_test.go`
- Create: `arena/session/manager.go`
- Create: `arena/session/manager_test.go`
- Create: `arena/httpapi/server.go`
- Create: `arena/httpapi/lobby_routes.go`
- Create: `arena/httpapi/public_routes.go`
- Create: `arena/httpapi/action_routes.go`
- Create: `arena/httpapi/session_routes.go`
- Create: `arena/httpapi/admin_routes.go`
- Create: `arena/httpapi/server_test.go`
- Modify: `arena/app/app.go`

- [ ] **Step 1: Write the failing gateway and HTTP tests**

```go
func TestDuplicateRequestIDReturnsOriginalResponse(t *testing.T) {
	api := newHTTPServerForTest(t)
	first := postAction(t, api, "req-1", 11)
	second := postAction(t, api, "req-1", 11)
	require.Equal(t, first.ResultEventID, second.ResultEventID)
}

func TestStateSeqMismatchReturns409(t *testing.T) {
	api := newHTTPServerForTest(t)
	resp := postActionWithSeq(t, api, "req-stale", 7, 999)
	require.Equal(t, http.StatusConflict, resp.StatusCode)
}

func TestInvalidSignatureReturns401(t *testing.T) {
	api := newHTTPServerForTest(t)
	resp := postActionWithBadSignature(t, api, "req-bad-sig")
	require.Equal(t, http.StatusUnauthorized, resp.StatusCode)
}

func TestWaveRegistrationLifecycle(t *testing.T) {
	api := newHTTPServerForTest(t)
	requireStatus(t, post(t, api, "/v1/arena/waves/wave_1/register"), http.StatusOK)
	requireStatus(t, deleteReq(t, api, "/v1/arena/waves/wave_1/registration/miner_1"), http.StatusOK)
}

func TestSeatAssignmentEndpointReturnsLatestTableAfterMove(t *testing.T) {
	api := newHTTPServerForTest(t)
	requireStatus(t, get(t, api, "/v1/tournaments/tour_1/seat-assignment/miner_1"), http.StatusOK)
}

func TestReconnectAfterAutoActionGetsHydratedReadOnlyState(t *testing.T) {
	api := newHTTPServerForTest(t)
	requireStatus(t, post(t, api, "/v1/tournaments/tour_1/sessions/reconnect"), http.StatusOK)
}

func TestSessionHandoffReplacesChannelNotSeatAuthority(t *testing.T) {
	manager := newSessionManagerForTest(t)
	first := manager.Attach("miner_1", "session-a")
	second := manager.Attach("miner_1", "session-b")
	require.NotEqual(t, first.SessionID, second.SessionID)
	require.Equal(t, "session-b", manager.Active("miner_1").SessionID)
}

func TestStandingAndLiveTableEndpointsExposeFrozenShape(t *testing.T) {
	api := newHTTPServerForTest(t)
	requireStatus(t, get(t, api, "/v1/tournaments/tour_1/standing"), http.StatusOK)
	requireStatus(t, get(t, api, "/v1/tournaments/tour_1/live-table/tbl_1"), http.StatusOK)
}
```

- [ ] **Step 2: Run the gateway/API tests to verify they fail**

Run: `go test ./arena/gateway ./arena/session ./arena/httpapi -run 'TestDuplicateRequestIDReturnsOriginalResponse|TestStateSeqMismatchReturns409|TestInvalidSignatureReturns401|TestWaveRegistrationLifecycle|TestSeatAssignmentEndpointReturnsLatestTableAfterMove|TestReconnectAfterAutoActionGetsHydratedReadOnlyState|TestSessionHandoffReplacesChannelNotSeatAuthority|TestStandingAndLiveTableEndpointsExposeFrozenShape' -v`
Expected: FAIL because the gateway and HTTP routes do not exist.

- [ ] **Step 3: Implement the minimal gateway and routes**

```go
func (g *Gateway) Submit(ctx context.Context, req SubmitRequest) (SubmitResponse, error) {
	// validate request_id, payload shape, seat existence, expected_state_seq, then hand off
}
```

Implement:
- health and readiness endpoints
- `GET /v1/arena/waves/active`
- `POST /v1/arena/waves/{wave_id}/register`
- `DELETE /v1/arena/waves/{wave_id}/registration/{miner_id}`
- `GET /v1/tournaments/{tournament_id}/standing`
- `GET /v1/tournaments/{tournament_id}/live-table/{table_id}`
- `GET /v1/tournaments/{tournament_id}/seat-assignment/{miner_id}`
- `POST /v1/tournaments/{tournament_id}/sessions/reconnect`
- `POST /v1/tournaments/{tournament_id}/actions`
- admin routes for create/start/recover/void/DQ
- write path:
  - schema validation
  - signature validation
  - request_id lookup
  - existence check
  - submission ledger write
  - authoritative `arena_action` write
  - table actor dispatch
- reconnect path:
  - latest seat assignment lookup
  - active session handoff
  - read-only hydrate after elimination / DQ
  - current table + state_seq hydrate after move-table or FT transition
- contract checks:
  - assert required JSON response shape, not just status code
  - admin routes explicitly own control-plane commands from the spec

- [ ] **Step 4: Run the gateway/API tests**

Run: `go test ./arena/gateway ./arena/session ./arena/httpapi -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arena/gateway arena/session arena/httpapi arena/app/app.go
git commit -m "feat: add arena gateway and http api"
```

### Task 8: Build Standing, Live-Table, and Postgame Projectors

**Files:**
- Create: `arena/projector/lobby.go`
- Create: `arena/projector/standing.go`
- Create: `arena/projector/live_table.go`
- Create: `arena/projector/postgame.go`
- Create: `arena/projector/projector_test.go`

- [ ] **Step 1: Write the failing projector tests**

```go
func TestProjectorsConsumeEachEventOnceByEventID(t *testing.T) {
	p := newProjectorsForTest(t)
	event := fixtureEvent("evt-1")
	require.NoError(t, p.Apply(event))
	require.NoError(t, p.Apply(event))
	require.Equal(t, 1, p.Standing().AppliedCount("evt-1"))
}

func TestPostgameIncludesNoMultiplierReasonAndConfidence(t *testing.T) {
	p := newProjectorsForTest(t)
	require.NoError(t, p.Apply(fixtureCompletedEvent()))
	postgame := p.Postgame("tour_1")
	require.Equal(t, "time_cap_finish", postgame.CompletedReason)
	require.Equal(t, "0.50", postgame.ConfidenceBucket)
}
```

- [ ] **Step 2: Run the projector tests to verify they fail**

Run: `go test ./arena/projector -run 'TestProjectorsConsumeEachEventOnceByEventID|TestPostgameIncludesNoMultiplierReasonAndConfidence' -v`
Expected: FAIL because the projector package does not exist.

- [ ] **Step 3: Implement the minimal projectors**

```go
func (p *StandingProjector) Apply(evt events.Envelope) error {
	if p.cursor.Seen(evt.EventID) {
		return nil
	}
	// mutate read model only
}
```

Implement:
- idempotent `event_id` cursoring
- wave lobby projector for registration-open / waitlist / ready-state views
- standing rank-band updates
- live-table projector
- postgame forensic payload with completion reason, `no_multiplier`, `confidence_weight`, stage reached
- rebuild-safe projector interfaces
- projector delivery plumbing:
  - `outbox_event`
  - `outbox_dispatch`
  - `projector_cursor`
  - `dead_letter_event`

- [ ] **Step 4: Run the projector tests**

Run: `go test ./arena/projector -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arena/projector
git commit -m "feat: add arena read model projectors"
```

### Task 9: Implement Recovery, Replay, Void, and Operator Interventions

**Files:**
- Create: `arena/recovery/service.go`
- Create: `arena/recovery/service_test.go`
- Create: `arena/replay/replayer.go`
- Create: `arena/replay/replayer_test.go`
- Modify: `arena/app/app.go`

- [ ] **Step 1: Write the failing recovery and replay tests**

```go
func TestRecoverySynthesizesExpiredDeadlineTimeout(t *testing.T) {
	app := newRecoverableAppForTest(t)
	crashMidPhase(t, app)
	recovered := restartApp(t, app)
	require.True(t, recovered.SawSyntheticTimeout("deadline-1"))
}

func TestReplayParityMismatchMarksIntegrityFailure(t *testing.T) {
	rep := newReplayerForTest(t)
	result := rep.ReplayCorrupted("tour_1")
	require.NoError(t, result.Err)
	require.False(t, result.ParityOK)
	require.Equal(t, "integrity_failure", result.FinalDisposition)
}
```

- [ ] **Step 2: Run the recovery/replay tests to verify they fail**

Run: `go test ./arena/recovery ./arena/replay -run 'TestRecoverySynthesizesExpiredDeadlineTimeout|TestReplayParityMismatchMarksIntegrityFailure' -v`
Expected: FAIL because recovery and replay packages do not exist.

- [ ] **Step 3: Implement the minimal recovery and replay logic**

```go
func (s *Service) RecoverTournament(ctx context.Context, tournamentID string) error {
	// load snapshot, replay tail, rebuild deadlines, synthesize expired timeouts
}
```

Implement:
- startup scan of live tournaments
- snapshot + tail replay
- expired deadline synthesis
- recoverable pause vs void escalation
- replay parity proof with:
  - final snapshot hash
  - standing snapshot hash
  - per-seat measurement summary
  - `arena_rating_input`
  - `no_multiplier` final flag
  - replay proof hash
- deterministic replay inputs sourced only from durable fields:
  - `rng_root_seed`
  - `policy_bundle_version`
  - event `state_hash_after`
  - row-level `schema_version` / `payload_hash` / `artifact_ref`

- [ ] **Step 4: Run the recovery/replay tests**

Run: `go test ./arena/recovery ./arena/replay -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arena/recovery arena/replay arena/app/app.go
git commit -m "feat: add arena recovery and replay parity checks"
```

### Task 10: Write Rating Inputs and Shared-DB Multiplier Outputs

**Files:**
- Create: `arena/rating/state.go`
- Create: `arena/rating/mapper.go`
- Create: `arena/rating/writer.go`
- Create: `arena/rating/writer_test.go`
- Modify: `arena/store/postgres/repository.go`

- [ ] **Step 1: Write the failing rating tests**

```go
func TestPracticeTournamentDoesNotChangeMultiplier(t *testing.T) {
	writer := newRatingWriterForTest(t)
	out := writer.ApplyCompletedTournament(fixturePracticeCompletion())
	require.True(t, out.NoMultiplier)
	require.Equal(t, 1.0, out.Items[0].MultiplierAfter)
}

func TestFirst15EligibleTournamentsClampMultiplierToOne(t *testing.T) {
	writer := newRatingWriterForTest(t)
	for i := 0; i < 15; i++ {
		_ = writer.ApplyCompletedTournament(fixtureRatedCompletion("miner-1", 0.90))
	}
	last := writer.ApplyCompletedTournament(fixtureRatedCompletion("miner-1", 0.90))
	require.True(t, last.Items[0].MultiplierAfter >= 1.0)
	require.True(t, last.Items[0].MultiplierAfter <= 1.04)
}

func TestCompatibilityWriteFailsFastWhenSharedHarnessTablesMissing(t *testing.T) {
	writer := newRatingWriterAgainstBareArenaSchema(t)
	err := writer.OnTournamentCompleted(context.Background(), fixtureRatedCompletion("miner-1", 0.90))
	require.ErrorContains(t, err, "miners table missing")
}

func TestRatedCompletionUpdatesMuSigmaReliabilityAndPublicELO(t *testing.T) {
	writer := newRatingWriterForTest(t)
	out := writer.ApplyCompletedTournament(fixtureRatedCompletion("miner-1", 0.90))
	require.NotZero(t, out.Items[0].MuAfter)
	require.NotZero(t, out.Items[0].SigmaAfter)
	require.NotZero(t, out.Items[0].ArenaReliabilityAfter)
	require.NotZero(t, out.Items[0].PublicELOAfter)
}

func TestSingleTournamentMultiplierMoveIsCappedAtOneBasisStep(t *testing.T) {
	writer := newRatingWriterForTest(t)
	before := writer.CurrentMultiplier("miner-1")
	out := writer.ApplyCompletedTournament(fixtureRatedCompletion("miner-1", 0.90))
	after := out.Items[0].MultiplierAfter
	require.LessOrEqual(t, math.Abs(after-before), 0.01)
}
```

- [ ] **Step 2: Run the rating tests to verify they fail**

Run: `go test ./arena/rating -run 'TestPracticeTournamentDoesNotChangeMultiplier|TestFirst15EligibleTournamentsClampMultiplierToOne|TestCompatibilityWriteFailsFastWhenSharedHarnessTablesMissing|TestRatedCompletionUpdatesMuSigmaReliabilityAndPublicELO|TestSingleTournamentMultiplierMoveIsCappedAtOneBasisStep' -v`
Expected: FAIL because the rating package does not exist.

- [ ] **Step 3: Implement the minimal rating writer**

```go
func (w *Writer) OnTournamentCompleted(ctx context.Context, completed Completion) error {
	inputs := mapper.BuildInputs(completed)
	return w.repo.WriteRatingAndCompatibilityRows(ctx, inputs)
}
```

Implement:
- `arena_rating_input` mapping from tournament completion
- `confidence_weight` buckets exactly as frozen
- `effective_tournament_score = tournament_score * confidence_weight`
- `no_multiplier` rules
- startup / write-path assertion that shared compatibility tables `miners` and `arena_result_entries` exist before first compatibility write
- write `arena_collusion_metric` / integrity-signal rows needed for stable measurement and no-multiplier reasoning
- rating state updates for:
  - `mu`
  - `sigma`
  - `arena_reliability`
  - `public_elo`
  - public ladder snapshot / rank recompute
- direct writes to:
  - `arena_rating_input`
  - `arena_multiplier_snapshot`
  - `rating_state_current`
  - `rating_snapshot`
  - `public_ladder_snapshot`
  - shared `miners.arena_multiplier`
  - shared `arena_result_entries`

- [ ] **Step 4: Run the rating tests**

Run: `go test ./arena/rating -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arena/rating arena/store/postgres/repository.go
git commit -m "feat: add arena rating writer and compatibility outputs"
```

### Task 11: Add End-to-End, Recovery, and Chaos Integration Coverage

**Files:**
- Create: `arena/integration/runtime_flow_test.go`
- Create: `arena/integration/recovery_flow_test.go`
- Create: `arena/integration/chaos_test.go`

- [ ] **Step 1: Write the failing integration tests**

```go
func TestFullRatedTournamentFlow(t *testing.T) {
	app := newIntegrationApp(t)
	run := seedRatedTournament(t, app, 64)
	playTournamentToCompletion(t, app, run.ID)
	assertCompletedTournament(t, app, run.ID)
}

func TestCrashMidRoundThenRecover(t *testing.T) {
	app := newIntegrationApp(t)
	run := seedRatedTournament(t, app, 64)
	crashDuringWagerPhase(t, app, run.ID)
	restartAndRecover(t, app)
	assertRecoveryParity(t, app, run.ID)
}

func TestDisconnectStormDoesNotBreakBarrier(t *testing.T) {
	app := newIntegrationApp(t)
	run := seedRatedTournament(t, app, 64)
	simulateDisconnectStorm(t, app, run.ID)
	assertBarrierStillMonotonic(t, app, run.ID)
}

func TestVoidFlowProducesNoMultiplierAndNoRatingWrite(t *testing.T) {
	app := newIntegrationApp(t)
	run := seedRatedTournament(t, app, 64)
	forceUnrecoverableCorruption(t, app, run.ID)
	assertVoidedTournament(t, app, run.ID)
}
```

- [ ] **Step 2: Run the integration tests to verify they fail**

Run: `ARENA_TEST_DATABASE_URL=postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable go test ./arena/integration -run 'TestFullRatedTournamentFlow|TestCrashMidRoundThenRecover|TestDisconnectStormDoesNotBreakBarrier|TestVoidFlowProducesNoMultiplierAndNoRatingWrite' -v`
Expected: FAIL because integration harness helpers do not exist yet.

- [ ] **Step 3: Implement the integration harness and minimal assertions**

```go
func newIntegrationApp(t *testing.T) *app.App {
	t.Helper()
	// boot real app against test postgres with deterministic clock
}
```

Implement:
- full tournament happy path
- crash/recovery path
- disconnect storm path
- unrecoverable corruption -> void path
- verification of:
  - exact completion reason
  - replay parity
  - replay proof hash
  - per-seat measurement summary parity
  - deterministic seed reproduction from durable replay fields
  - projector rebuild parity
  - rating input append
  - multiplier-compatibility row write
  - max single-tournament multiplier move `<= 0.01`
  - stable `no_multiplier` reason strings

- [ ] **Step 4: Run all Go Arena tests**

Run: `ARENA_TEST_DATABASE_URL=postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable go test ./arena/... -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add arena/integration
git commit -m "test: add arena end-to-end and chaos coverage"
```

### Task 12: Finalize Developer Docs and Verification Commands

**Files:**
- Modify: `README.md`
- Modify: `README_ZH.md`
- Modify: `Makefile`

- [ ] **Step 1: Write the failing documentation checklist**

Manual checklist:
- `README.md` shows how to boot local Arena Postgres and run `arenad`
- `README_ZH.md` has the same minimal developer path
- `Makefile help` lists Arena targets

- [ ] **Step 2: Update docs and developer commands**

Add:
- Arena local DB start/stop commands
- Arena test command
- Arena binary build/run command
- note that the Go worker writes shared compatibility rows for current miner status surfaces

- [ ] **Step 3: Run the final verification commands**

Run:
- `make arena-db-up`
- `ARENA_TEST_DATABASE_URL=postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable go test ./arena/... -v`
- `go build ./cmd/arenad`
- `make help`

Expected:
- Postgres starts
- all Arena Go tests pass
- `arenad` builds
- Arena targets show in Makefile help

- [ ] **Step 4: Commit**

```bash
git add README.md README_ZH.md Makefile
git commit -m "docs: add arena runtime developer workflow"
```

### Manual Smoke Checklist After Task 12

- [ ] Start local DB: `make arena-db-up`
- [ ] Start runtime: `ARENA_DATABASE_URL=postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable go run ./cmd/arenad`
- [ ] Create a practice wave through the admin route
- [ ] Register 48 deterministic fake entrants through the public wave-registration route
- [ ] Confirm the wave downgrades to practice and starts
- [ ] Force several timeout-only seats and confirm elimination happens only at hand close
- [ ] Force a crash during an open wager phase, restart, and confirm synthetic timeout recovery
- [ ] Finish a rated 64-player tournament and confirm:
  - final table transition occurs at `players_remaining <= 8`
  - completion reason is natural or time-cap after round only
  - `arena_rating_input` rows exist
  - `miners.arena_multiplier` / `arena_result_entries` are updated

### Definition of Done

- Every frozen rule in [docs/ARENA_RUNTIME_STATE_MACHINE_SPEC.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_RUNTIME_STATE_MACHINE_SPEC.md) has a code home and at least one test home.
- No per-round full reshuffle exists anywhere in code.
- `action_rejected` never advances `state_seq`.
- Time-cap only fires after the current round.
- DQ only takes effect at a safe point and marks the tournament `no_multiplier`.
- Replay parity and projector rebuild parity are part of automated tests, not operator folklore.
- The existing Python miner-status path still works because compatibility rows are written directly by the Go worker.

### Risks to Stop On Immediately

- If the team tries to move multiplier logic back into the Python service, stop and reconcile ownership before writing more code.
- If integration tests require introducing Redis or Kafka just to pass, stop and re-check whether the spec actually needs that complexity.
- If the rating writer cannot safely update `miners` and `arena_result_entries` in the shared DB transaction model, stop and write a dedicated bridge plan instead of papering over it.
- If the hand engine starts pulling time, DB, or HTTP dependencies, stop and re-separate the pure engine from actor side effects.

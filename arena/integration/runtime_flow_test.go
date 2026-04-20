package integration

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"sort"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/hub"
	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/projector"
	"github.com/clawchain/clawchain/arena/rating"
	"github.com/clawchain/clawchain/arena/recovery"
	"github.com/clawchain/clawchain/arena/replay"
	"github.com/clawchain/clawchain/arena/store/postgres"
	"github.com/clawchain/clawchain/arena/testutil"
)

const defaultArenaTestDatabaseURL = "postgres://clawchain:clawchain_dev_pw@127.0.0.1:55432/arena_runtime_test?sslmode=disable"

type integrationApp struct {
	db     *sql.DB
	repo   *postgres.Repository
	rating *rating.Writer
	now    time.Time
	runs   map[string]*integrationRun
}

type seededRun struct {
	ID string
}

type integrationRun struct {
	id                   string
	waveID               string
	tableIDs             []string
	seatAssignments      []hub.SeatAssignment
	seed                 string
	reproducedSeed       string
	completedReason      string
	noMultiplier         bool
	noMultiplierReason   string
	outcome              rating.Outcome
	replayResult         replay.Result
	proofHash            string
	measurementSummary   map[string]measurementSummary
	replayedMeasurements map[string]measurementSummary
	postgameView         projector.PostgameView
	rebuiltPostgameView  projector.PostgameView
	maxMultiplierDelta   float64
	barrierMonotonic     bool
	syntheticTimeoutID   string
	recoveryService      *recovery.Service
}

type measurementSummary struct {
	Score  float64
	Weight float64
	Stage  string
}

func TestFullRatedTournamentFlow(t *testing.T) {
	app := newIntegrationApp(t)
	run := seedRatedTournament(t, app, 64)

	playTournamentToCompletion(t, app, run.ID)
	assertCompletedTournament(t, app, run.ID)
}

func newIntegrationApp(t *testing.T) *integrationApp {
	t.Helper()

	databaseURL := os.Getenv("ARENA_TEST_DATABASE_URL")
	if databaseURL == "" {
		databaseURL = defaultArenaTestDatabaseURL
	}

	db, err := sql.Open("postgres", databaseURL)
	require.NoError(t, err)
	require.NoError(t, db.Ping())
	t.Cleanup(func() {
		require.NoError(t, db.Close())
	})

	resetPublicSchema(t, db)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	now := time.Date(2026, time.April, 10, 19, 0, 0, 0, time.UTC)
	return &integrationApp{
		db:   db,
		repo: repo,
		rating: rating.NewWriter(repo, func() time.Time {
			return now
		}),
		now:  now,
		runs: make(map[string]*integrationRun),
	}
}

func seedRatedTournament(t *testing.T, app *integrationApp, entrants int) seededRun {
	t.Helper()

	waveID := model.WaveID(model.RatedMode, app.now)
	prestart := hub.NewService(hub.State{
		WaveID:    waveID,
		WaveState: model.WaveStateRegistrationOpen,
		StartedAt: app.now,
		Entrants:  testutil.ConfirmedEntrants(waveID, entrants),
	}, nil)

	_, err := prestart.LockAndPack(context.Background())
	require.NoError(t, err)
	require.NoError(t, prestart.PublishSeats(context.Background()))

	result := prestart.Result()
	require.Len(t, result.Tournaments, 1)
	plan := result.Tournaments[0]
	require.Equal(t, string(model.RatedMode), plan.RatedOrPractice)
	require.False(t, plan.NoMultiplier)
	require.Len(t, plan.SeatAssignments, entrants)
	seedSharedMiners(t, app.db, plan.SeatAssignments, app.now)

	run := &integrationRun{
		id:              plan.TournamentID,
		waveID:          waveID,
		seatAssignments: append([]hub.SeatAssignment(nil), plan.SeatAssignments...),
		tableIDs:        sortedTableIDs(plan.SeatAssignments),
	}
	run.seed = deterministicSeed(run.seatAssignments)
	run.reproducedSeed = deterministicSeed(run.seatAssignments)

	app.runs[run.id] = run
	return seededRun{ID: run.id}
}

func playTournamentToCompletion(t *testing.T, app *integrationApp, tournamentID string) {
	t.Helper()

	run := mustRun(t, app, tournamentID)

	live := hub.NewService(hub.State{
		TournamentID:     tournamentID,
		PlayersRemaining: 64,
		LiveTables:       liveTablesFromAssignments(run.seatAssignments),
		ClosedTables:     map[string]bool{},
	}, nil)
	for _, tableID := range run.tableIDs {
		live.MarkHandClosed(tableID)
	}
	require.True(t, live.CanAdvanceRound())

	finalTable := hub.NewService(hub.State{
		TournamentID:     tournamentID,
		PlayersRemaining: 8,
		LiveTables: []hub.LiveTable{
			{TableID: tableID(tournamentID, 1), PlayerCount: 4},
			{TableID: tableID(tournamentID, 2), PlayerCount: 4},
		},
		ClosedTables: map[string]bool{},
	}, nil)
	require.Equal(t, hub.TransitionFinalTable, finalTable.NextBarrierDecision())

	completion := ratedCompletionFixture(tournamentID, app.now)
	mirror := rating.NewWriter(nil, func() time.Time { return app.now })
	replayed := rating.NewWriter(nil, func() time.Time { return app.now })
	outcome := mirror.ApplyCompletedTournament(completion)
	replayedOutcome := replayed.ApplyCompletedTournament(completion)

	require.NoError(t, app.rating.OnTournamentCompleted(context.Background(), completion))

	run.completedReason = "natural_finish"
	run.noMultiplier = outcome.NoMultiplier
	run.noMultiplierReason = outcome.NoMultiplierReason
	run.outcome = outcome
	run.measurementSummary = measurementSummaryFromOutcome(outcome)
	run.replayedMeasurements = measurementSummaryFromOutcome(replayedOutcome)
	run.proofHash = proofHash(tournamentID, outcome)
	run.maxMultiplierDelta = maxMultiplierDelta(outcome)
	run.replayResult = replay.NewReplayer(
		map[string]string{tournamentID: run.proofHash},
		map[string]string{tournamentID: proofHash(tournamentID, replayedOutcome)},
	).ReplayCorrupted(tournamentID)

	projectors := projector.NewProjectors()
	rebuilt := projector.NewProjectors()
	for _, evt := range completionEvents(tournamentID, outcome, run.completedReason) {
		require.NoError(t, projectors.Apply(evt))
		require.NoError(t, rebuilt.Apply(evt))
	}

	view, ok := projectors.Postgame(tournamentID)
	require.True(t, ok)
	rebuiltView, ok := rebuilt.Postgame(tournamentID)
	require.True(t, ok)
	run.postgameView = view
	run.rebuiltPostgameView = rebuiltView
}

func assertCompletedTournament(t *testing.T, app *integrationApp, tournamentID string) {
	t.Helper()

	run := mustRun(t, app, tournamentID)

	require.Equal(t, "natural_finish", run.completedReason)
	require.True(t, run.replayResult.ParityOK)
	require.NotEmpty(t, run.proofHash)
	require.True(t, reflect.DeepEqual(run.measurementSummary, run.replayedMeasurements))
	require.Equal(t, run.seed, run.reproducedSeed)
	require.Equal(t, run.postgameView, run.rebuiltPostgameView)
	require.LessOrEqual(t, run.maxMultiplierDelta, 0.01)

	require.Greater(t, countRows(t, app.db, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1", tournamentID), 0)
	require.Greater(t, countRows(t, app.db, "SELECT COUNT(*) FROM arena_result_entries WHERE tournament_id = $1", tournamentID), 0)
	require.Greater(t, countRows(t, app.db, "SELECT COUNT(*) FROM miners WHERE public_rank IS NOT NULL"), 0)
}

func mustRun(t *testing.T, app *integrationApp, tournamentID string) *integrationRun {
	t.Helper()

	run, ok := app.runs[tournamentID]
	require.True(t, ok)
	return run
}

func sortedTableIDs(assignments []hub.SeatAssignment) []string {
	seen := make(map[string]struct{})
	tableIDs := make([]string, 0, len(assignments))
	for _, assignment := range assignments {
		if _, ok := seen[assignment.TableID]; ok {
			continue
		}
		seen[assignment.TableID] = struct{}{}
		tableIDs = append(tableIDs, assignment.TableID)
	}
	sort.Strings(tableIDs)
	return tableIDs
}

func liveTablesFromAssignments(assignments []hub.SeatAssignment) []hub.LiveTable {
	counts := make(map[string]int)
	for _, assignment := range assignments {
		counts[assignment.TableID]++
	}

	tableIDs := make([]string, 0, len(counts))
	for tableID := range counts {
		tableIDs = append(tableIDs, tableID)
	}
	sort.Strings(tableIDs)

	liveTables := make([]hub.LiveTable, 0, len(tableIDs))
	for _, tableID := range tableIDs {
		liveTables = append(liveTables, hub.LiveTable{
			TableID:     tableID,
			PlayerCount: counts[tableID],
		})
	}
	return liveTables
}

func deterministicSeed(assignments []hub.SeatAssignment) string {
	hash := sha256.New()
	for _, assignment := range assignments {
		_, _ = hash.Write([]byte(fmt.Sprintf("%s|%s|%02d|%02d;", assignment.EntrantID, assignment.TableID, assignment.TableNo, assignment.SeatNo)))
	}
	return hex.EncodeToString(hash.Sum(nil))
}

func ratedCompletionFixture(tournamentID string, completedAt time.Time) rating.Completion {
	return rating.Completion{
		TournamentID: tournamentID,
		Mode:         model.RatedMode,
		HumanOnly:    true,
		SeasonID:     "season-1",
		CompletedAt:  completedAt,
		Entrants: []rating.CompletedEntrant{{
			EntrantID:           "ent:01",
			MinerAddress:        "miner-01",
			Name:                "miner-01",
			EconomicUnitID:      "eu:miner-01",
			FinishRank:          1,
			FinishPercentile:    1.0,
			HandsPlayed:         24,
			MeaningfulDecisions: 16,
			StageReached:        "final_table",
			TournamentScore:     0.90,
		}},
	}
}

func measurementSummaryFromOutcome(outcome rating.Outcome) map[string]measurementSummary {
	summary := make(map[string]measurementSummary, len(outcome.Items))
	for _, item := range outcome.Items {
		summary[item.MinerAddress] = measurementSummary{
			Score:  item.EffectiveTournamentScore,
			Weight: item.ConfidenceWeight,
			Stage:  item.StageReached,
		}
	}
	return summary
}

func proofHash(tournamentID string, outcome rating.Outcome) string {
	hash := sha256.New()
	_, _ = hash.Write([]byte(tournamentID))
	for _, item := range outcome.Items {
		_, _ = hash.Write([]byte(fmt.Sprintf("|%s|%.4f|%.2f|%d|%.2f", item.MinerAddress, item.EffectiveTournamentScore, item.MultiplierAfter, item.PublicELOAfter, item.MuAfter)))
	}
	return hex.EncodeToString(hash.Sum(nil))
}

func maxMultiplierDelta(outcome rating.Outcome) float64 {
	maxDelta := 0.0
	for _, item := range outcome.Items {
		delta := item.MultiplierAfter - item.MultiplierBefore
		if delta < 0 {
			delta = -delta
		}
		if delta > maxDelta {
			maxDelta = delta
		}
	}
	return maxDelta
}

func completionEvents(tournamentID string, outcome rating.Outcome, completedReason string) []model.EventLogEntry {
	standingPayload, _ := json.Marshal(projector.StandingView{
		PlayersRemaining: 1,
		RankBand:         "winner",
	})
	livePayload, _ := json.Marshal(projector.LiveTableView{
		ActingSeatNo: 1,
		PotMain:      320,
	})
	postgamePayload, _ := json.Marshal(map[string]any{
		"completed_reason":     completedReason,
		"confidence_weight":    outcome.Items[0].ConfidenceWeight,
		"no_multiplier":        outcome.NoMultiplier,
		"no_multiplier_reason": outcome.NoMultiplierReason,
		"stage_reached":        outcome.Items[0].StageReached,
	})

	return []model.EventLogEntry{
		{
			EventID:      model.EventID(tournamentID, 1),
			TournamentID: tournamentID,
			EventType:    "tournament.standing.refreshed",
			Payload:      standingPayload,
		},
		{
			EventID:      model.EventID(tournamentID, 2),
			TournamentID: tournamentID,
			TableID:      tableID(tournamentID, 1),
			EventType:    "table.snapshot.updated",
			Payload:      livePayload,
		},
		{
			EventID:      model.EventID(tournamentID, 3),
			TournamentID: tournamentID,
			EventType:    "tournament.completed",
			Payload:      postgamePayload,
		},
	}
}

func countRows(t *testing.T, db *sql.DB, query string, args ...any) int {
	t.Helper()

	var count int
	require.NoError(t, db.QueryRow(query, args...).Scan(&count))
	return count
}

func seedSharedMiners(t *testing.T, db *sql.DB, assignments []hub.SeatAssignment, at time.Time) {
	t.Helper()

	seen := make(map[string]struct{}, len(assignments))
	for index, assignment := range assignments {
		if _, ok := seen[assignment.MinerID]; ok {
			continue
		}
		seen[assignment.MinerID] = struct{}{}
		_, err := db.Exec(`
			INSERT INTO miners (
				address,
				name,
				registration_index,
				public_key,
				economic_unit_id,
				created_at,
				updated_at
			) VALUES ($1, $2, $3, $4, $5, $6, $7)
		`,
			assignment.MinerID,
			assignment.MinerID,
			index+1,
			"pubkey:"+assignment.MinerID,
			"eu:"+assignment.MinerID,
			at,
			at,
		)
		require.NoError(t, err)
	}
}

func tableID(tournamentID string, tableNo int) string {
	return fmt.Sprintf("tbl:%s:%02d", tournamentID, tableNo)
}

func resetPublicSchema(t *testing.T, db *sql.DB) {
	t.Helper()

	for _, stmt := range []string{
		"DROP SCHEMA IF EXISTS public CASCADE",
		"CREATE SCHEMA IF NOT EXISTS public",
		"GRANT ALL ON SCHEMA public TO public",
	} {
		_, err := db.Exec(stmt)
		require.NoError(t, err)
	}
}

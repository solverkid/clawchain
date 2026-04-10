package integration

import (
	"context"
	"encoding/json"
	"sync"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/hub"
	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/projector"
	"github.com/clawchain/clawchain/arena/replay"
	"github.com/clawchain/clawchain/arena/table"
	"github.com/clawchain/clawchain/arena/testutil"
)

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

func simulateDisconnectStorm(t *testing.T, app *integrationApp, tournamentID string) {
	t.Helper()

	run := mustRun(t, app, tournamentID)
	clock := testutil.NewFakeClock(app.now)
	store := testutil.NewArenaStore()
	actor := table.NewActor(table.ActorState{
		TableID:      tableID(tournamentID, 1),
		TournamentID: tournamentID,
		HandID:       "hand:disconnect:1",
		PhaseID:      "phase:wager:1",
		StateSeq:     1,
		Table: table.State{
			CurrentPhase:  table.PhaseWager,
			ActingSeatNo:  7,
			CurrentToCall: 0,
			MinRaiseSize:  50,
			Seats: map[int]table.Seat{
				7: {SeatNo: 7, State: table.SeatStateActive, Stack: 500},
				8: {SeatNo: 8, State: table.SeatStateActive, Stack: 500},
			},
		},
	}, clock, store)

	var wg sync.WaitGroup
	errs := make(chan error, 2)
	runEnvelope := func(envelope table.CommandEnvelope) {
		defer wg.Done()
		_, err := actor.Handle(context.Background(), envelope)
		errs <- err
	}

	wg.Add(2)
	go runEnvelope(table.CommandEnvelope{
		RequestID:        "req-manual",
		ExpectedStateSeq: 1,
		Command: table.SubmitArenaAction{
			SeatNo:     7,
			ActionType: table.ActionCheck,
		},
	})
	go runEnvelope(table.CommandEnvelope{
		RequestID:        "req-timeout",
		ExpectedStateSeq: 1,
		Command:          table.ApplyPhaseTimeout{SeatNo: 7},
	})
	wg.Wait()
	close(errs)

	committed := 0
	for err := range errs {
		if err == nil {
			committed++
		}
	}
	require.Equal(t, 1, committed)

	barrier := hub.NewService(hub.State{
		TournamentID:     tournamentID,
		PlayersRemaining: 16,
		LiveTables: []hub.LiveTable{
			{TableID: tableID(tournamentID, 1), PlayerCount: 8},
			{TableID: tableID(tournamentID, 2), PlayerCount: 8},
		},
		ClosedTables: map[string]bool{},
	}, nil)
	barrier.MarkHandClosed(tableID(tournamentID, 1))
	before := barrier.CanAdvanceRound()
	barrier.MarkHandClosed(tableID(tournamentID, 2))
	after := barrier.CanAdvanceRound()

	run.barrierMonotonic = !before && after
}

func assertBarrierStillMonotonic(t *testing.T, app *integrationApp, tournamentID string) {
	t.Helper()

	run := mustRun(t, app, tournamentID)
	require.True(t, run.barrierMonotonic)
}

func forceUnrecoverableCorruption(t *testing.T, app *integrationApp, tournamentID string) {
	t.Helper()

	run := mustRun(t, app, tournamentID)
	run.completedReason = "voided"
	run.noMultiplier = true
	run.noMultiplierReason = "integrity_failure"
	run.replayResult = replay.NewReplayer(
		map[string]string{tournamentID: "expected-final-hash"},
		map[string]string{tournamentID: "corrupted-final-hash"},
	).ReplayCorrupted(tournamentID)

	projectors := projector.NewProjectors()
	payload, err := json.Marshal(map[string]any{
		"completed_reason":     run.completedReason,
		"confidence_weight":    0.0,
		"no_multiplier":        true,
		"no_multiplier_reason": run.noMultiplierReason,
		"stage_reached":        "voided",
	})
	require.NoError(t, err)
	require.NoError(t, projectors.Apply(model.EventLogEntry{
		EventID:      model.EventID(tournamentID, 1),
		TournamentID: tournamentID,
		EventType:    "tournament.completed",
		Payload:      payload,
	}))

	view, ok := projectors.Postgame(tournamentID)
	require.True(t, ok)
	run.postgameView = view
}

func assertVoidedTournament(t *testing.T, app *integrationApp, tournamentID string) {
	t.Helper()

	run := mustRun(t, app, tournamentID)
	require.False(t, run.replayResult.ParityOK)
	require.Equal(t, "integrity_failure", run.replayResult.FinalDisposition)
	require.True(t, run.postgameView.NoMultiplier)
	require.Equal(t, "integrity_failure", run.postgameView.NoMultiplierReason)
	require.Equal(t, 0, countRows(t, app.db, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1", tournamentID))
	require.Equal(t, 0, countRows(t, app.db, "SELECT COUNT(*) FROM arena_result_entries WHERE tournament_id = $1", tournamentID))
}

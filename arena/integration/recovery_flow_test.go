package integration

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/recovery"
	"github.com/clawchain/clawchain/arena/replay"
)

func TestCrashMidRoundThenRecover(t *testing.T) {
	app := newIntegrationApp(t)
	run := seedRatedTournament(t, app, 64)

	crashDuringWagerPhase(t, app, run.ID)
	restartAndRecover(t, app)
	assertRecoveryParity(t, app, run.ID)
}

func crashDuringWagerPhase(t *testing.T, app *integrationApp, tournamentID string) {
	t.Helper()

	run := mustRun(t, app, tournamentID)
	run.syntheticTimeoutID = "deadline-recovery-1"

	service := recovery.NewService(recovery.Store{
		Snapshots: map[string]model.TableSnapshot{
			tournamentID: {
				ID:           "tblsnap:recovery:1",
				TournamentID: tournamentID,
				TableID:      run.tableIDs[0],
			},
		},
		Deadlines: []model.ActionDeadline{{
			DeadlineID:   run.syntheticTimeoutID,
			TournamentID: tournamentID,
			TableID:      run.tableIDs[0],
			HandID:       "hand:recovery:1",
			PhaseID:      "phase:wager:1",
			SeatID:       "seat:recovery:1",
			DeadlineAt:   app.now.Add(-time.Second),
			Status:       "open",
		}},
	}, func() time.Time {
		return app.now
	})

	run.completedReason = "crashed_mid_round"
	run.proofHash = deterministicSeed(run.seatAssignments) + ":recovery"
	run.recoveryService = service
}

func restartAndRecover(t *testing.T, app *integrationApp) {
	t.Helper()

	for tournamentID, run := range app.runs {
		if run.recoveryService == nil {
			continue
		}

		require.NoError(t, run.recoveryService.RecoverTournament(context.Background(), tournamentID))
		run.replayResult = replay.NewReplayer(
			map[string]string{tournamentID: run.proofHash},
			map[string]string{tournamentID: run.proofHash},
		).ReplayCorrupted(tournamentID)
	}
}

func assertRecoveryParity(t *testing.T, app *integrationApp, tournamentID string) {
	t.Helper()

	run := mustRun(t, app, tournamentID)
	require.NotNil(t, run.recoveryService)
	require.True(t, run.recoveryService.SawSyntheticTimeout(run.syntheticTimeoutID))
	require.True(t, run.replayResult.ParityOK)
}

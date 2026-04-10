package model_test

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/model"
)

func TestDeterministicArenaIDs(t *testing.T) {
	start := time.Date(2026, time.April, 10, 9, 30, 0, 0, time.UTC)

	waveID := model.WaveID(model.RatedMode, start)
	require.Equal(t, waveID, model.WaveID(model.RatedMode, start))

	tournamentID := model.TournamentID(waveID, 3)
	require.Equal(t, tournamentID, model.TournamentID(waveID, 3))

	require.Equal(t, model.TableID("tour_1", 2), model.TableID("tour_1", 2))
	require.NotEqual(t, model.TableID("tour_1", 2), model.TableID("tour_1", 3))

	handID := model.HandID(tournamentID, 2, 14)
	require.Equal(t, handID, model.HandID(tournamentID, 2, 14))

	phaseID := model.PhaseID(handID, model.PhaseTypeSignal)
	require.Equal(t, phaseID, model.PhaseID(handID, model.PhaseTypeSignal))

	barrierID := model.BarrierID(tournamentID, 4)
	require.Equal(t, barrierID, model.BarrierID(tournamentID, 4))

	eventID := model.EventID("table:tour_1:02", 11)
	require.Equal(t, eventID, model.EventID("table:tour_1:02", 11))
}

func TestFrozenArenaStatesValidate(t *testing.T) {
	for _, state := range []model.WaveState{
		model.WaveStateScheduled,
		model.WaveStateRegistrationOpen,
		model.WaveStateRegistrationFrozen,
		model.WaveStateFieldLocked,
		model.WaveStateEligibilityResolving,
		model.WaveStateFieldFinalized,
		model.WaveStatePacking,
		model.WaveStateTournamentsCreated,
		model.WaveStateSeatingGenerated,
		model.WaveStateSeatsPublished,
		model.WaveStateStartArmed,
		model.WaveStateInProgress,
		model.WaveStateCompleted,
		model.WaveStateFinalized,
		model.WaveStateCancelled,
		model.WaveStateVoided,
	} {
		require.NoError(t, state.Validate())
	}

	for _, state := range []model.TournamentState{
		model.TournamentStateScheduled,
		model.TournamentStateRegistrationConfirmed,
		model.TournamentStateSeating,
		model.TournamentStateReady,
		model.TournamentStateLiveMultiTable,
		model.TournamentStateRebalancing,
		model.TournamentStateFinalTableTransition,
		model.TournamentStateLiveFinalTable,
		model.TournamentStateCompleted,
		model.TournamentStateRated,
		model.TournamentStateSettled,
		model.TournamentStateCancelled,
		model.TournamentStateVoided,
	} {
		require.NoError(t, state.Validate())
	}

	for _, state := range []model.TableState{
		model.TableStateOpen,
		model.TableStateHandStarting,
		model.TableStateHandLive,
		model.TableStateHandClosing,
		model.TableStateAwaitingBarrier,
		model.TableStatePausedForRebalance,
		model.TableStateClosed,
	} {
		require.NoError(t, state.Validate())
	}

	for _, state := range []model.HandState{
		model.HandStateCreated,
		model.HandStateBlindsPosted,
		model.HandStateSignalOpen,
		model.HandStateSignalClosed,
		model.HandStateProbeOpen,
		model.HandStateProbeClosed,
		model.HandStateWagerOpen,
		model.HandStateWagerClosed,
		model.HandStateShowdownResolved,
		model.HandStateAwardsApplied,
		model.HandStateEliminationResolved,
		model.HandStateClosed,
	} {
		require.NoError(t, state.Validate())
	}

	for _, state := range []model.PhaseState{
		model.PhaseStatePending,
		model.PhaseStateOpen,
		model.PhaseStateClosing,
		model.PhaseStateClosed,
	} {
		require.NoError(t, state.Validate())
	}

	for _, state := range []model.SeatState{
		model.SeatStateActive,
		model.SeatStateSitOut,
		model.SeatStateEliminated,
	} {
		require.NoError(t, state.Validate())
	}

	for _, state := range []model.RegistrationState{
		model.RegistrationStateNotRegistered,
		model.RegistrationStateRegistered,
		model.RegistrationStateWaitlisted,
		model.RegistrationStateConfirmed,
		model.RegistrationStateSeated,
		model.RegistrationStatePlaying,
		model.RegistrationStateEliminated,
		model.RegistrationStateChampion,
		model.RegistrationStateRemovedBeforeStart,
		model.RegistrationStateDisqualified,
	} {
		require.NoError(t, state.Validate())
	}

	require.Error(t, model.WaveState("nope").Validate())
	require.Error(t, model.TournamentState("nope").Validate())
	require.Error(t, model.TableState("nope").Validate())
	require.Error(t, model.HandState("nope").Validate())
	require.Error(t, model.PhaseState("nope").Validate())
	require.Error(t, model.SeatState("nope").Validate())
	require.Error(t, model.RegistrationState("nope").Validate())
}

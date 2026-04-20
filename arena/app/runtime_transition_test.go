package app

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"sort"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/config"
	"github.com/clawchain/clawchain/arena/httpapi"
	"github.com/clawchain/clawchain/arena/hub"
	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/table"
)

func TestAdvanceClosedTablesTriggersFinalTableTransition(t *testing.T) {
	db := openArenaRuntimeTestDB(t)
	resetArenaRuntimeSchema(t, db)
	require.NoError(t, db.Close())

	application, err := New(config.Config{
		DatabaseURL:     arenaRuntimeTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	ctx := context.Background()
	waveID := "wave_final_table_transition_1"
	_, err = application.runtime.CreateWave(ctx, createWaveRequest(waveID))
	require.NoError(t, err)
	for idx := 1; idx <= 16; idx++ {
		require.NoError(t, application.runtime.RegisterMiner(ctx, waveID, minerID(idx)))
	}
	lockResp, err := application.runtime.LockWave(ctx, waveID)
	require.NoError(t, err)
	_, err = application.runtime.PublishSeats(ctx, waveID)
	require.NoError(t, err)

	tournamentRuntime := application.runtime.tournaments[lockResp.TournamentID]
	require.NotNil(t, tournamentRuntime)

	leftTableID := "tbl:" + lockResp.TournamentID + ":01"
	rightTableID := "tbl:" + lockResp.TournamentID + ":02"
	application.runtime.actors[leftTableID] = reducedRecoveredActor(t, application.runtime, leftTableID, []int{1, 2, 3, 4})
	application.runtime.actors[rightTableID] = reducedRecoveredActor(t, application.runtime, rightTableID, []int{1, 2, 3, 4})
	if application.runtime.gateway != nil {
		application.runtime.gateway.RegisterActor(leftTableID, application.runtime.actors[leftTableID])
		application.runtime.gateway.RegisterActor(rightTableID, application.runtime.actors[rightTableID])
	}

	_, _, err = application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, leftTableID)
	require.NoError(t, err)
	state, nextRoundNo, err := application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, rightTableID)
	require.NoError(t, err)
	require.Equal(t, 2, nextRoundNo)
	require.Equal(t, lockResp.TournamentID, state.TournamentID)

	tournament := application.runtime.tournaments[lockResp.TournamentID].tournament
	require.Equal(t, 8, tournament.PlayersRemaining)
	require.Equal(t, 1, tournament.ActiveTableCount)
	require.Equal(t, leftTableID, tournament.FinalTableTableID)
	require.Equal(t, "live_final_table", string(tournament.State))

	finalTableAssignments := 0
	for _, assignment := range application.runtime.tournaments[lockResp.TournamentID].seatAssignments {
		if assignment.TableID == leftTableID && !assignment.ReadOnly {
			finalTableAssignments++
		}
	}
	require.Equal(t, 8, finalTableAssignments)
	require.NotContains(t, application.runtime.tournaments[lockResp.TournamentID].liveTables, rightTableID)
	require.Equal(t, 1, len(activeTournamentActors(application.runtime, lockResp.TournamentID)))
}

func TestAdvanceClosedTablesPreservesReadOnlyHydrateForEliminatedEntrants(t *testing.T) {
	db := openArenaRuntimeTestDB(t)
	resetArenaRuntimeSchema(t, db)
	require.NoError(t, db.Close())

	application, err := New(config.Config{
		DatabaseURL:     arenaRuntimeTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	ctx := context.Background()
	waveID := "wave_clear_eliminated_after_transition_1"
	_, err = application.runtime.CreateWave(ctx, createWaveRequest(waveID))
	require.NoError(t, err)
	for idx := 1; idx <= 16; idx++ {
		require.NoError(t, application.runtime.RegisterMiner(ctx, waveID, minerID(idx)))
	}
	lockResp, err := application.runtime.LockWave(ctx, waveID)
	require.NoError(t, err)
	_, err = application.runtime.PublishSeats(ctx, waveID)
	require.NoError(t, err)

	tournamentRuntime := application.runtime.tournaments[lockResp.TournamentID]
	require.NotNil(t, tournamentRuntime)

	leftTableID := "tbl:" + lockResp.TournamentID + ":01"
	rightTableID := "tbl:" + lockResp.TournamentID + ":02"
	eliminatedOnKeptTable := make(map[string]struct{})
	for minerID, assignment := range tournamentRuntime.seatAssignments {
		if assignment.TableID == leftTableID && assignment.SeatNo > 4 {
			eliminatedOnKeptTable[minerID] = struct{}{}
		}
	}
	require.Len(t, eliminatedOnKeptTable, 4)

	application.runtime.actors[leftTableID] = reducedRecoveredActor(t, application.runtime, leftTableID, []int{1, 2, 3, 4})
	application.runtime.actors[rightTableID] = reducedRecoveredActor(t, application.runtime, rightTableID, []int{1, 2, 3, 4})
	if application.runtime.gateway != nil {
		application.runtime.gateway.RegisterActor(leftTableID, application.runtime.actors[leftTableID])
		application.runtime.gateway.RegisterActor(rightTableID, application.runtime.actors[rightTableID])
	}

	_, _, err = application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, leftTableID)
	require.NoError(t, err)
	_, _, err = application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, rightTableID)
	require.NoError(t, err)

	waveRuntime := application.runtime.waves[waveID]
	assignments := application.runtime.currentAssignmentsForTournamentLocked(waveRuntime, lockResp.TournamentID)
	require.Len(t, assignments, 8)

	for minerID := range eliminatedOnKeptTable {
		entrant := waveRuntime.entrants[minerID]
		require.Empty(t, entrant.TableID)
		require.Empty(t, entrant.SeatID)
		require.Equal(t, model.RegistrationStateEliminated, entrant.RegistrationState)
		assignment, ok := tournamentRuntime.seatAssignments[minerID]
		require.True(t, ok)
		require.Equal(t, leftTableID, assignment.TableID)
		require.True(t, assignment.ReadOnly)
	}
}

func TestRestartRecoversReadOnlyHydrateForEliminatedEntrant(t *testing.T) {
	db := openArenaRuntimeTestDB(t)
	resetArenaRuntimeSchema(t, db)
	require.NoError(t, db.Close())

	cfg := config.Config{
		DatabaseURL:     arenaRuntimeTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	}

	application, err := New(cfg)
	require.NoError(t, err)

	ctx := context.Background()
	waveID := "wave_restart_eliminated_hydrate_1"
	_, err = application.runtime.CreateWave(ctx, createWaveRequest(waveID))
	require.NoError(t, err)
	for idx := 1; idx <= 16; idx++ {
		require.NoError(t, application.runtime.RegisterMiner(ctx, waveID, minerID(idx)))
	}
	lockResp, err := application.runtime.LockWave(ctx, waveID)
	require.NoError(t, err)
	_, err = application.runtime.PublishSeats(ctx, waveID)
	require.NoError(t, err)

	tournamentRuntime := application.runtime.tournaments[lockResp.TournamentID]
	require.NotNil(t, tournamentRuntime)

	leftTableID := "tbl:" + lockResp.TournamentID + ":01"
	rightTableID := "tbl:" + lockResp.TournamentID + ":02"
	var eliminatedMinerID string
	for minerID, assignment := range tournamentRuntime.seatAssignments {
		if assignment.TableID == leftTableID && assignment.SeatNo == 5 {
			eliminatedMinerID = minerID
			break
		}
	}
	require.NotEmpty(t, eliminatedMinerID)

	application.runtime.actors[leftTableID] = reducedRecoveredActor(t, application.runtime, leftTableID, []int{1, 2, 3, 4})
	application.runtime.actors[rightTableID] = reducedRecoveredActor(t, application.runtime, rightTableID, []int{1, 2, 3, 4})
	if application.runtime.gateway != nil {
		application.runtime.gateway.RegisterActor(leftTableID, application.runtime.actors[leftTableID])
		application.runtime.gateway.RegisterActor(rightTableID, application.runtime.actors[rightTableID])
	}

	_, _, err = application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, leftTableID)
	require.NoError(t, err)
	_, _, err = application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, rightTableID)
	require.NoError(t, err)

	require.NoError(t, application.Close(context.Background()))

	restarted, err := New(cfg)
	require.NoError(t, err)
	defer func() {
		require.NoError(t, restarted.Close(context.Background()))
	}()

	assignment, ok := restarted.runtime.SeatAssignment(ctx, lockResp.TournamentID, eliminatedMinerID)
	require.True(t, ok)
	require.Equal(t, leftTableID, assignment.TableID)
	require.Equal(t, 5, assignment.SeatNo)
	require.True(t, assignment.ReadOnly)
}

func TestApplyTransitionPlanCarriesHistoricalStreamSeqForReusedTableID(t *testing.T) {
	db := openArenaRuntimeTestDB(t)
	resetArenaRuntimeSchema(t, db)
	require.NoError(t, db.Close())

	application, err := New(config.Config{
		DatabaseURL:     arenaRuntimeTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	ctx := context.Background()
	waveID := "wave_reuse_table_id_stream_seq_1"
	_, err = application.runtime.CreateWave(ctx, createWaveRequest(waveID))
	require.NoError(t, err)
	for idx := 1; idx <= 16; idx++ {
		require.NoError(t, application.runtime.RegisterMiner(ctx, waveID, minerID(idx)))
	}
	lockResp, err := application.runtime.LockWave(ctx, waveID)
	require.NoError(t, err)
	_, err = application.runtime.PublishSeats(ctx, waveID)
	require.NoError(t, err)

	tournamentRuntime := application.runtime.tournaments[lockResp.TournamentID]
	require.NotNil(t, tournamentRuntime)
	waveRuntime := application.runtime.waves[waveID]
	require.NotNil(t, waveRuntime)

	historicalFinalTableID := "tbl:" + lockResp.TournamentID + ":01"
	initialRightTableID := "tbl:" + lockResp.TournamentID + ":02"
	remappedLeftTableID := "tbl:" + lockResp.TournamentID + ":03"
	remappedRightTableID := "tbl:" + lockResp.TournamentID + ":05"

	leftMinerIDs := minerIDsForTableSeats(tournamentRuntime.seatAssignments, historicalFinalTableID, []int{1, 2, 3, 4})
	rightMinerIDs := minerIDsForTableSeats(tournamentRuntime.seatAssignments, initialRightTableID, []int{1, 2, 3, 4})
	require.Len(t, leftMinerIDs, 4)
	require.Len(t, rightMinerIDs, 4)

	application.runtime.actors[remappedLeftTableID] = remappedReducedRecoveredActor(t, application.runtime, historicalFinalTableID, remappedLeftTableID, []int{1, 2, 3, 4})
	application.runtime.actors[remappedRightTableID] = remappedReducedRecoveredActor(t, application.runtime, initialRightTableID, remappedRightTableID, []int{1, 2, 3, 4})
	delete(application.runtime.actors, historicalFinalTableID)
	delete(application.runtime.actors, initialRightTableID)
	if application.runtime.gateway != nil {
		application.runtime.gateway.RemoveActor(historicalFinalTableID)
		application.runtime.gateway.RemoveActor(initialRightTableID)
		application.runtime.gateway.RegisterActor(remappedLeftTableID, application.runtime.actors[remappedLeftTableID])
		application.runtime.gateway.RegisterActor(remappedRightTableID, application.runtime.actors[remappedRightTableID])
	}

	for idx, minerID := range leftMinerIDs {
		reassignEntrantToTable(waveRuntime, tournamentRuntime, minerID, remappedLeftTableID, idx+1, application.runtime.now())
	}
	for idx, minerID := range rightMinerIDs {
		reassignEntrantToTable(waveRuntime, tournamentRuntime, minerID, remappedRightTableID, idx+1, application.runtime.now())
	}
	tournamentRuntime.tournament.PlayersRemaining = 8
	tournamentRuntime.tournament.ActiveTableCount = 2

	assignments := make([]hub.SeatAssignment, 0, 8)
	for idx, minerID := range append(leftMinerIDs, rightMinerIDs...) {
		assignments = append(assignments, hub.SeatAssignment{
			EntrantID: waveRuntime.entrants[minerID].ID,
			MinerID:   minerID,
			TableID:   historicalFinalTableID,
			TableNo:   1,
			SeatNo:    idx + 1,
		})
	}

	states, err := application.runtime.applyTransitionPlanLocked(ctx, waveRuntime, tournamentRuntime, hub.TransitionPlan{
		Decision:        hub.TransitionFinalTable,
		SeatAssignments: assignments,
	}, 2)
	require.NoError(t, err)

	finalActor := application.runtime.actors[historicalFinalTableID]
	require.NotNil(t, finalActor)
	require.Equal(t, int64(2), finalActor.StreamSeq())
	require.Contains(t, states, historicalFinalTableID)
}

func TestAdvanceClosedTableCompletesTournamentAtSingleSurvivor(t *testing.T) {
	db := openArenaRuntimeTestDB(t)
	resetArenaRuntimeSchema(t, db)
	require.NoError(t, db.Close())

	application, err := New(config.Config{
		DatabaseURL:     arenaRuntimeTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	ctx := context.Background()
	waveID := "wave_complete_single_survivor_1"
	_, err = application.runtime.CreateWave(ctx, createWaveRequest(waveID))
	require.NoError(t, err)
	for idx := 1; idx <= 8; idx++ {
		require.NoError(t, application.runtime.RegisterMiner(ctx, waveID, minerID(idx)))
	}
	lockResp, err := application.runtime.LockWave(ctx, waveID)
	require.NoError(t, err)
	_, err = application.runtime.PublishSeats(ctx, waveID)
	require.NoError(t, err)

	tournamentRuntime := application.runtime.tournaments[lockResp.TournamentID]
	require.NotNil(t, tournamentRuntime)

	tableID := "tbl:" + lockResp.TournamentID + ":01"
	application.runtime.actors[tableID] = reducedRecoveredActor(t, application.runtime, tableID, []int{1})
	if application.runtime.gateway != nil {
		application.runtime.gateway.RegisterActor(tableID, application.runtime.actors[tableID])
	}

	state, nextRoundNo, err := application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, tableID)
	require.NoError(t, err)
	require.Empty(t, state.TableID)
	require.Equal(t, 1, nextRoundNo)

	tournament := application.runtime.tournaments[lockResp.TournamentID].tournament
	require.Equal(t, model.TournamentStateCompleted, tournament.State)
	require.NotNil(t, tournament.CompletedAt)
	require.Equal(t, 1, tournament.CurrentRoundNo)
	require.Equal(t, 1, tournament.PlayersRemaining)
	require.Equal(t, 1, tournament.ActiveTableCount)
	require.Equal(t, tableID, tournament.FinalTableTableID)
	require.Empty(t, activeTournamentActors(application.runtime, lockResp.TournamentID))
	require.Empty(t, application.runtime.tournaments[lockResp.TournamentID].liveTables)

	standing, ok := application.runtime.Standing(ctx, lockResp.TournamentID)
	require.True(t, ok)
	require.Equal(t, "completed", standing["status"])
	require.Equal(t, "natural_finish", standing["completed_reason"])
	require.Equal(t, 1, standing["players_remaining"])
}

func TestAdvanceClosedTablePersistsRoundBarrierProgress(t *testing.T) {
	db := openArenaRuntimeTestDB(t)
	resetArenaRuntimeSchema(t, db)
	require.NoError(t, db.Close())

	application, err := New(config.Config{
		DatabaseURL:     arenaRuntimeTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	ctx := context.Background()
	waveID := "wave_barrier_persist_1"
	_, err = application.runtime.CreateWave(ctx, createWaveRequest(waveID))
	require.NoError(t, err)
	for idx := 1; idx <= 16; idx++ {
		require.NoError(t, application.runtime.RegisterMiner(ctx, waveID, minerID(idx)))
	}
	lockResp, err := application.runtime.LockWave(ctx, waveID)
	require.NoError(t, err)
	_, err = application.runtime.PublishSeats(ctx, waveID)
	require.NoError(t, err)

	tournamentRuntime := application.runtime.tournaments[lockResp.TournamentID]
	require.NotNil(t, tournamentRuntime)

	leftTableID := "tbl:" + lockResp.TournamentID + ":01"
	rightTableID := "tbl:" + lockResp.TournamentID + ":02"
	application.runtime.actors[leftTableID] = reducedRecoveredActor(t, application.runtime, leftTableID, []int{1, 2, 3, 4})
	application.runtime.actors[rightTableID] = reducedRecoveredActor(t, application.runtime, rightTableID, []int{1, 2, 3, 4})

	_, _, err = application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, leftTableID)
	require.NoError(t, err)

	verifyDB := openArenaRuntimeTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()

	var expectedCount, receivedCount int
	var barrierState string
	var payload []byte
	err = verifyDB.QueryRow(`
		SELECT expected_table_count, received_hand_close_count, barrier_state, payload
		  FROM arena_round_barrier
		 WHERE tournament_id = $1 AND round_no = 1
	`, lockResp.TournamentID).Scan(&expectedCount, &receivedCount, &barrierState, &payload)
	require.NoError(t, err)
	require.Equal(t, 2, expectedCount)
	require.Equal(t, 1, receivedCount)
	require.Equal(t, "open", barrierState)
	require.Contains(t, string(payload), leftTableID)
}

func TestRestartRecoversRoundBarrierProgress(t *testing.T) {
	db := openArenaRuntimeTestDB(t)
	resetArenaRuntimeSchema(t, db)
	require.NoError(t, db.Close())

	first, err := New(config.Config{
		DatabaseURL:     arenaRuntimeTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)

	ctx := context.Background()
	waveID := "wave_barrier_recovery_1"
	_, err = first.runtime.CreateWave(ctx, createWaveRequest(waveID))
	require.NoError(t, err)
	for idx := 1; idx <= 16; idx++ {
		require.NoError(t, first.runtime.RegisterMiner(ctx, waveID, minerID(idx)))
	}
	lockResp, err := first.runtime.LockWave(ctx, waveID)
	require.NoError(t, err)
	_, err = first.runtime.PublishSeats(ctx, waveID)
	require.NoError(t, err)

	tournamentRuntime := first.runtime.tournaments[lockResp.TournamentID]
	require.NotNil(t, tournamentRuntime)

	leftTableID := "tbl:" + lockResp.TournamentID + ":01"
	rightTableID := "tbl:" + lockResp.TournamentID + ":02"
	first.runtime.actors[leftTableID] = reducedRecoveredActor(t, first.runtime, leftTableID, []int{1, 2, 3, 4})
	first.runtime.actors[rightTableID] = reducedRecoveredActor(t, first.runtime, rightTableID, []int{1, 2, 3, 4})

	_, _, err = first.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, leftTableID)
	require.NoError(t, err)
	require.NoError(t, first.Close(context.Background()))

	restarted, err := New(config.Config{
		DatabaseURL:     arenaRuntimeTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, restarted.Close(context.Background()))
	}()

	tournamentRuntime = restarted.runtime.tournaments[lockResp.TournamentID]
	require.NotNil(t, tournamentRuntime)
	restarted.runtime.actors[rightTableID] = reducedRecoveredActor(t, restarted.runtime, rightTableID, []int{1, 2, 3, 4})
	if restarted.runtime.gateway != nil {
		restarted.runtime.gateway.RegisterActor(rightTableID, restarted.runtime.actors[rightTableID])
	}

	state, nextRoundNo, err := restarted.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, rightTableID)
	require.NoError(t, err)
	require.Equal(t, 2, nextRoundNo)
	require.Equal(t, lockResp.TournamentID, state.TournamentID)

	tournament := restarted.runtime.tournaments[lockResp.TournamentID].tournament
	require.Equal(t, 2, tournament.CurrentRoundNo)
	require.Equal(t, 1, tournament.CurrentLevelNo)
}

func TestAdvanceClosedTablesCompletesTournamentAtTimeCap(t *testing.T) {
	db := openArenaRuntimeTestDB(t)
	resetArenaRuntimeSchema(t, db)
	require.NoError(t, db.Close())

	application, err := New(config.Config{
		DatabaseURL:     arenaRuntimeTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	ctx := context.Background()
	waveID := "wave_complete_time_cap_1"
	_, err = application.runtime.CreateWave(ctx, createWaveRequest(waveID))
	require.NoError(t, err)
	for idx := 1; idx <= 16; idx++ {
		require.NoError(t, application.runtime.RegisterMiner(ctx, waveID, minerID(idx)))
	}
	lockResp, err := application.runtime.LockWave(ctx, waveID)
	require.NoError(t, err)
	_, err = application.runtime.PublishSeats(ctx, waveID)
	require.NoError(t, err)
	_, err = application.runtime.ArmTimeCap(ctx, lockResp.TournamentID)
	require.NoError(t, err)

	tournamentRuntime := application.runtime.tournaments[lockResp.TournamentID]
	require.NotNil(t, tournamentRuntime)

	leftTableID := "tbl:" + lockResp.TournamentID + ":01"
	rightTableID := "tbl:" + lockResp.TournamentID + ":02"
	application.runtime.actors[leftTableID] = reducedRecoveredActor(t, application.runtime, leftTableID, []int{1, 2, 3, 4})
	application.runtime.actors[rightTableID] = reducedRecoveredActor(t, application.runtime, rightTableID, []int{1, 2, 3, 4})
	if application.runtime.gateway != nil {
		application.runtime.gateway.RegisterActor(leftTableID, application.runtime.actors[leftTableID])
		application.runtime.gateway.RegisterActor(rightTableID, application.runtime.actors[rightTableID])
	}

	_, _, err = application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, leftTableID)
	require.NoError(t, err)
	state, nextRoundNo, err := application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, rightTableID)
	require.NoError(t, err)
	require.Empty(t, state.TableID)
	require.Equal(t, 1, nextRoundNo)

	tournament := application.runtime.tournaments[lockResp.TournamentID].tournament
	require.Equal(t, model.TournamentStateCompleted, tournament.State)
	require.NotNil(t, tournament.CompletedAt)
	require.Equal(t, 1, tournament.CurrentRoundNo)
	require.Equal(t, 8, tournament.PlayersRemaining)
	require.Equal(t, 2, tournament.ActiveTableCount)
	require.Empty(t, tournament.FinalTableTableID)
	require.Empty(t, activeTournamentActors(application.runtime, lockResp.TournamentID))
	require.Empty(t, application.runtime.tournaments[lockResp.TournamentID].liveTables)

	standing, ok := application.runtime.Standing(ctx, lockResp.TournamentID)
	require.True(t, ok)
	require.Equal(t, "completed", standing["status"])
	require.Equal(t, "time_cap", standing["completed_reason"])
	require.Equal(t, 8, standing["players_remaining"])
}

func TestTimeCapMultiSurvivorWritesDeterministicRatingStages(t *testing.T) {
	db := openArenaRuntimeTestDB(t)
	resetArenaRuntimeSchema(t, db)
	require.NoError(t, db.Close())

	application, err := New(config.Config{
		DatabaseURL:     arenaRuntimeTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	ctx := context.Background()
	waveID := "wave_time_cap_rating_stages_1"
	_, err = application.runtime.CreateWave(ctx, createWaveRequest(waveID))
	require.NoError(t, err)
	for idx := 1; idx <= 16; idx++ {
		require.NoError(t, application.runtime.RegisterMiner(ctx, waveID, minerID(idx)))
	}
	lockResp, err := application.runtime.LockWave(ctx, waveID)
	require.NoError(t, err)
	_, err = application.runtime.PublishSeats(ctx, waveID)
	require.NoError(t, err)
	_, err = application.runtime.ArmTimeCap(ctx, lockResp.TournamentID)
	require.NoError(t, err)

	tournamentRuntime := application.runtime.tournaments[lockResp.TournamentID]
	require.NotNil(t, tournamentRuntime)

	leftTableID := "tbl:" + lockResp.TournamentID + ":01"
	rightTableID := "tbl:" + lockResp.TournamentID + ":02"
	application.runtime.actors[leftTableID] = reducedRecoveredActor(t, application.runtime, leftTableID, []int{1, 2, 3, 4})
	application.runtime.actors[rightTableID] = reducedRecoveredActor(t, application.runtime, rightTableID, []int{1, 2, 3, 4})
	if application.runtime.gateway != nil {
		application.runtime.gateway.RegisterActor(leftTableID, application.runtime.actors[leftTableID])
		application.runtime.gateway.RegisterActor(rightTableID, application.runtime.actors[rightTableID])
	}

	_, _, err = application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, leftTableID)
	require.NoError(t, err)
	_, _, err = application.runtime.advanceClosedTableLocked(ctx, tournamentRuntime, rightTableID)
	require.NoError(t, err)

	verifyDB := openArenaRuntimeTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()
	require.Equal(t, 16, countArenaRuntimeRows(t, verifyDB, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1", lockResp.TournamentID))
	require.Equal(t, 16, countArenaRuntimeRows(t, verifyDB, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1 AND finish_rank BETWEEN 1 AND 16", lockResp.TournamentID))
	require.Equal(t, 8, countArenaRuntimeRows(t, verifyDB, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1 AND stage_reached = 'time_cap_finish'", lockResp.TournamentID))
	require.Equal(t, 8, countArenaRuntimeRows(t, verifyDB, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1 AND stage_reached = 'eliminated'", lockResp.TournamentID))
	require.Zero(t, countArenaRuntimeRows(t, verifyDB, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1 AND stage_reached = 'final_table'", lockResp.TournamentID))
}

func reducedRecoveredActor(t *testing.T, runtime *runtimeService, tableID string, activeSeats []int) *table.Actor {
	t.Helper()

	previous := runtime.actors[tableID]
	require.NotNil(t, previous)

	state := previous.State()
	active := make(map[int]struct{}, len(activeSeats))
	for _, seatNo := range activeSeats {
		active[seatNo] = struct{}{}
	}
	for seatNo, seat := range state.Table.Seats {
		if _, ok := active[seatNo]; ok {
			seat.State = table.SeatStateActive
			seat.Stack = 1000
		} else {
			seat.State = table.SeatStateEliminated
			seat.Stack = 0
		}
		seat.Folded = false
		seat.ManualActionThisHand = false
		seat.TimedOutThisHand = false
		state.Table.Seats[seatNo] = seat
	}
	state.Table.HandClosed = true
	state.Table.CurrentPhase = table.PhaseWager
	state.Table.ActingSeatNo = activeSeats[0]
	state.Table.PhaseStartSeatNo = activeSeats[0]

	return table.NewRecoveredActor(state, previous.StreamSeq(), runtimeClock{now: runtime.now}, runtime.repo)
}

func remappedReducedRecoveredActor(t *testing.T, runtime *runtimeService, sourceTableID, targetTableID string, activeSeats []int) *table.Actor {
	t.Helper()

	previous := runtime.actors[sourceTableID]
	require.NotNil(t, previous)

	state := previous.State()
	active := make(map[int]struct{}, len(activeSeats))
	for _, seatNo := range activeSeats {
		active[seatNo] = struct{}{}
	}
	for seatNo, seat := range state.Table.Seats {
		if _, ok := active[seatNo]; ok {
			seat.State = table.SeatStateActive
			seat.Stack = 1000
		} else {
			seat.State = table.SeatStateEliminated
			seat.Stack = 0
		}
		seat.Folded = false
		seat.ManualActionThisHand = false
		seat.TimedOutThisHand = false
		state.Table.Seats[seatNo] = seat
	}
	state.Table.HandClosed = true
	state.Table.CurrentPhase = table.PhaseWager
	state.Table.ActingSeatNo = activeSeats[0]
	state.Table.PhaseStartSeatNo = activeSeats[0]
	state.TableID = targetTableID
	state.HandID = model.HandID(state.TournamentID, tableNoFromTableID(targetTableID), state.Table.HandNumber)

	return table.NewRecoveredActor(state, previous.StreamSeq(), runtimeClock{now: runtime.now}, runtime.repo)
}

func minerIDsForTableSeats(assignments map[string]httpapi.SeatAssignment, tableID string, seatNos []int) []string {
	seatSet := make(map[int]struct{}, len(seatNos))
	for _, seatNo := range seatNos {
		seatSet[seatNo] = struct{}{}
	}

	minerIDs := make([]string, 0, len(seatNos))
	for minerID, assignment := range assignments {
		if assignment.TableID != tableID {
			continue
		}
		if _, ok := seatSet[assignment.SeatNo]; !ok {
			continue
		}
		minerIDs = append(minerIDs, minerID)
	}
	sort.Strings(minerIDs)
	return minerIDs
}

func reassignEntrantToTable(waveRuntime *waveRuntime, tournamentRuntime *tournamentRuntime, minerID, tableID string, seatNo int, now time.Time) {
	entrant := waveRuntime.entrants[minerID]
	entrant.TableID = tableID
	entrant.SeatID = seatID(tableID, seatNo)
	entrant.RegistrationState = model.RegistrationStatePlaying
	entrant.UpdatedAt = now
	waveRuntime.entrants[minerID] = entrant
	tournamentRuntime.seatAssignments[minerID] = httpapi.SeatAssignment{
		TableID:  tableID,
		SeatNo:   seatNo,
		ReadOnly: true,
	}
}

func activeTournamentActors(runtime *runtimeService, tournamentID string) map[string]*table.Actor {
	actors := make(map[string]*table.Actor)
	for tableID, actor := range runtime.actors {
		if actor.State().TournamentID == tournamentID {
			actors[tableID] = actor
		}
	}
	return actors
}

func createWaveRequest(waveID string) httpapi.CreateWaveRequest {
	return httpapi.CreateWaveRequest{
		WaveID:              waveID,
		Mode:                "rated",
		RegistrationOpenAt:  time.Date(2026, time.April, 10, 19, 0, 0, 0, time.UTC),
		RegistrationCloseAt: time.Date(2026, time.April, 10, 19, 30, 0, 0, time.UTC),
		ScheduledStartAt:    time.Date(2026, time.April, 10, 20, 0, 0, 0, time.UTC),
	}
}

func minerID(idx int) string {
	return fmt.Sprintf("miner_%02d", idx)
}

func arenaRuntimeTestDatabaseURL() string {
	if value := os.Getenv("ARENA_TEST_DATABASE_URL"); value != "" {
		return value
	}
	return "postgres://clawchain:clawchain_dev_pw@127.0.0.1:55432/arena_runtime_test?sslmode=disable"
}

func openArenaRuntimeTestDB(t *testing.T) *sql.DB {
	t.Helper()

	db, err := sql.Open("postgres", arenaRuntimeTestDatabaseURL())
	require.NoError(t, err)
	require.NoError(t, db.Ping())
	return db
}

func resetArenaRuntimeSchema(t *testing.T, db *sql.DB) {
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

func countArenaRuntimeRows(t *testing.T, db *sql.DB, query string, args ...any) int {
	t.Helper()

	var count int
	require.NoError(t, db.QueryRow(query, args...).Scan(&count))
	return count
}

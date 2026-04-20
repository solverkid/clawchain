package app_test

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	_ "github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/app"
	"github.com/clawchain/clawchain/arena/bot"
	"github.com/clawchain/clawchain/arena/config"
	"github.com/clawchain/clawchain/arena/replay"
	"github.com/clawchain/clawchain/arena/store/postgres"
	"github.com/clawchain/clawchain/arena/swarm"
)

func TestNewAppRequiresDatabaseURL(t *testing.T) {
	cfg := config.Config{}

	_, err := app.New(cfg)
	if err == nil || !strings.Contains(err.Error(), "database url") {
		t.Fatalf("expected missing database url error, got %v", err)
	}
}

func TestAppWiresAdminLockPublishFlow(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	t.Cleanup(func() {
		require.NoError(t, application.Close(context.Background()))
	})

	handler := application.Handler()

	createWaveResp := httptest.NewRecorder()
	createWaveReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/waves", strings.NewReader(`{
		"wave_id":"wave_admin_1",
		"mode":"rated",
		"registration_open_at":"2026-04-10T19:00:00Z",
		"registration_close_at":"2026-04-10T19:30:00Z",
		"scheduled_start_at":"2026-04-10T20:00:00Z"
	}`))
	handler.ServeHTTP(createWaveResp, createWaveReq)
	require.Equal(t, http.StatusCreated, createWaveResp.Code)

	for i := 1; i <= 56; i++ {
		resp := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodPost, "/v1/arena/waves/wave_admin_1/register", strings.NewReader(fmt.Sprintf(`{"miner_id":"miner_%02d"}`, i)))
		handler.ServeHTTP(resp, req)
		require.Equal(t, http.StatusOK, resp.Code)
	}

	lockResp := httptest.NewRecorder()
	lockReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/waves/wave_admin_1/lock", nil)
	handler.ServeHTTP(lockResp, lockReq)
	require.Equal(t, http.StatusOK, lockResp.Code)

	var lockBody map[string]any
	require.NoError(t, json.Unmarshal(lockResp.Body.Bytes(), &lockBody))
	tournamentID := lockBody["tournament_id"].(string)

	publishResp := httptest.NewRecorder()
	publishReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/waves/wave_admin_1/publish-seats", nil)
	handler.ServeHTTP(publishResp, publishReq)
	require.Equal(t, http.StatusOK, publishResp.Code)

	seatResp := httptest.NewRecorder()
	seatReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/seat-assignment/miner_01", nil)
	handler.ServeHTTP(seatResp, seatReq)
	require.Equal(t, http.StatusOK, seatResp.Code)
	require.Contains(t, seatResp.Body.String(), `"table_id"`)

	verifyDB := openArenaAppTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()
	require.Equal(t, 1, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_wave WHERE wave_id = $1", "wave_admin_1"))
	require.Equal(t, 56, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_entrant WHERE wave_id = $1", "wave_admin_1"))
	require.Equal(t, 1, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_tournament WHERE tournament_id = $1", tournamentID))
}

func TestRunServesHealthUntilContextCancel(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	runDone := make(chan error, 1)
	go func() {
		runDone <- application.Run(ctx)
	}()

	require.Eventually(t, func() bool {
		resp, err := http.Get("http://" + application.HTTPAddr() + "/healthz")
		if err != nil {
			return false
		}
		defer resp.Body.Close()
		return resp.StatusCode == http.StatusOK
	}, 2*time.Second, 25*time.Millisecond)

	cancel()
	require.NoError(t, <-runDone)
}

func TestRestartRecoversPublishedTournamentAndProcessesExpiredDeadline(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	first, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)

	tournamentID := seedPublishedTournament(t, first.Handler(), "wave_restart_1", 56)
	db = openArenaAppTestDB(t)
	_, err = db.Exec(`UPDATE arena_action_deadline SET deadline_at = NOW() - INTERVAL '1 second' WHERE tournament_id = $1`, tournamentID)
	require.NoError(t, err)
	require.NoError(t, db.Close())
	require.NoError(t, first.Close(context.Background()))

	restarted, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, restarted.Close(context.Background()))
	}()

	seatResp := httptest.NewRecorder()
	seatReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/seat-assignment/miner_01", nil)
	restarted.Handler().ServeHTTP(seatResp, seatReq)
	require.Equal(t, http.StatusOK, seatResp.Code)

	require.NoError(t, restarted.ProcessExpiredDeadlines(context.Background()))

	verifyDB := openArenaAppTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()
	require.Greater(t, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_action WHERE tournament_id = $1", tournamentID), 0)
}

func TestProcessExpiredDeadlinesOpensReplacementDeadlineAfterTimeout(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	handler := application.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_timeout_replacement_deadline_1", 8)
	tableID := "tbl:" + tournamentID + ":01"

	liveTable := loadLiveTable(t, handler, tournamentID, tableID)
	initialActingSeatNo := int(liveTable["acting_seat_no"].(float64))
	require.Equal(t, "signal", liveTable["current_phase"])

	db = openArenaAppTestDB(t)
	_, err = db.Exec(`UPDATE arena_action_deadline SET deadline_at = NOW() - INTERVAL '1 second' WHERE tournament_id = $1 AND table_id = $2 AND status = 'open'`, tournamentID, tableID)
	require.NoError(t, err)
	require.NoError(t, db.Close())

	require.NoError(t, application.ProcessExpiredDeadlines(context.Background()))

	liveTable = loadLiveTable(t, handler, tournamentID, tableID)
	require.Equal(t, "signal", liveTable["current_phase"])
	require.NotEqual(t, initialActingSeatNo, int(liveTable["acting_seat_no"].(float64)))

	verifyDB := openArenaAppTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()
	require.Equal(t, 2, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_action_deadline WHERE tournament_id = $1 AND table_id = $2", tournamentID, tableID))
	require.Equal(t, 1, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_action_deadline WHERE tournament_id = $1 AND table_id = $2 AND status = 'open'", tournamentID, tableID))
}

func TestProcessExpiredDeadlinesCanAdvanceRoundOnTimeoutOnlyPath(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	handler := application.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_timeout_round_advance_1", 8)
	tableID := "tbl:" + tournamentID + ":01"

	verifyDB := openArenaAppTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()

	advanced := false
	for step := 0; step < 64; step++ {
		standingResp := httptest.NewRecorder()
		standingReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/standing", nil)
		handler.ServeHTTP(standingResp, standingReq)
		require.Equal(t, http.StatusOK, standingResp.Code)

		var standing map[string]any
		require.NoError(t, json.Unmarshal(standingResp.Body.Bytes(), &standing))
		if int(standing["round_no"].(float64)) >= 2 {
			advanced = true
			break
		}

		_, err = verifyDB.Exec(`UPDATE arena_action_deadline SET deadline_at = NOW() - INTERVAL '1 second' WHERE tournament_id = $1 AND status = 'open'`, tournamentID)
		require.NoError(t, err)
		require.NoError(t, application.ProcessExpiredDeadlines(context.Background()))
	}

	require.True(t, advanced, "timeout-only flow should advance to round 2")
	requireLiveTablePhase(t, handler, tournamentID, tableID, "signal")
}

func TestAdminControlTimeCapForceRemoveAndVoid(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	handler := application.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_admin_control_1", 56)

	forceRemoveResp := httptest.NewRecorder()
	forceRemoveReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/waves/wave_admin_control_1/force-remove", strings.NewReader(`{"miner_id":"miner_56"}`))
	handler.ServeHTTP(forceRemoveResp, forceRemoveReq)
	require.Equal(t, http.StatusOK, forceRemoveResp.Code)
	require.Contains(t, forceRemoveResp.Body.String(), `"republished":true`)

	removedSeatResp := httptest.NewRecorder()
	removedSeatReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/seat-assignment/miner_56", nil)
	handler.ServeHTTP(removedSeatResp, removedSeatReq)
	require.Equal(t, http.StatusNotFound, removedSeatResp.Code)

	timeCapResp := httptest.NewRecorder()
	timeCapReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/tournaments/"+tournamentID+"/time-cap", nil)
	handler.ServeHTTP(timeCapResp, timeCapReq)
	require.Equal(t, http.StatusOK, timeCapResp.Code)
	require.Contains(t, timeCapResp.Body.String(), `"terminate_after_current_round":true`)

	voidResp := httptest.NewRecorder()
	voidReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/tournaments/"+tournamentID+"/void", strings.NewReader(`{"reason":"manual_ops"}`))
	handler.ServeHTTP(voidResp, voidReq)
	require.Equal(t, http.StatusOK, voidResp.Code)

	verifyDB := openArenaAppTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()
	require.Equal(t, 1, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_tournament WHERE tournament_id = $1 AND voided = TRUE AND no_multiplier = TRUE AND tournament_state = 'voided'", tournamentID))
	require.Equal(t, 1, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_entrant WHERE wave_id = $1 AND miner_id = 'miner_56' AND registration_state = 'removed_before_start'", "wave_admin_control_1"))
}

func TestAdminDisqualifyBlocksManualActionsAndAppliesAtRoundBarrier(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	handler := application.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_live_disqualify_1", 8)
	tableID := "tbl:" + tournamentID + ":01"
	liveTable := loadLiveTable(t, handler, tournamentID, tableID)
	disqualifiedSeatNo := int(liveTable["acting_seat_no"].(float64))
	disqualifiedMinerID := lookupMinerForTableSeat(t, handler, tournamentID, tableID, disqualifiedSeatNo, 8)

	disqualifyResp := httptest.NewRecorder()
	disqualifyReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/tournaments/"+tournamentID+"/disqualify", strings.NewReader(fmt.Sprintf(`{
		"miner_id":"%s",
		"reason":"manual_ops"
	}`, disqualifiedMinerID)))
	handler.ServeHTTP(disqualifyResp, disqualifyReq)
	require.Equal(t, http.StatusOK, disqualifyResp.Code, disqualifyResp.Body.String())
	require.Contains(t, disqualifyResp.Body.String(), `"no_multiplier":true`)

	standingResp := httptest.NewRecorder()
	standingReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/standing", nil)
	handler.ServeHTTP(standingResp, standingReq)
	require.Equal(t, http.StatusOK, standingResp.Code)
	require.Contains(t, standingResp.Body.String(), `"no_multiplier":true`)
	require.Contains(t, standingResp.Body.String(), `"no_multiplier_reason":"live_disqualification"`)

	assignment := reconnectSeatAssignment(t, handler, tournamentID, disqualifiedMinerID, "dq-session")
	require.Equal(t, true, assignment["read_only"])

	actionResp := httptest.NewRecorder()
	actionReq := httptest.NewRequest(http.MethodPost, "/v1/tournaments/"+tournamentID+"/actions", strings.NewReader(fmt.Sprintf(`{
		"request_id":"req-dq-%s",
		"table_id":"%s",
		"miner_id":"%s",
		"session_id":"dq-session",
		"seat_no":%d,
		"action_type":"signal_none",
		"expected_state_seq":%d,
		"signature":"sig:%s"
	}`, tournamentID, tableID, disqualifiedMinerID, disqualifiedSeatNo, int(assignment["state_seq"].(float64)), disqualifiedMinerID)))
	handler.ServeHTTP(actionResp, actionReq)
	require.Equal(t, http.StatusConflict, actionResp.Code)
	require.Contains(t, actionResp.Body.String(), "read_only_assignment")

	verifyDB := openArenaAppTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()

	advanced := false
	for step := 0; step < 64; step++ {
		standingResp = httptest.NewRecorder()
		standingReq = httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/standing", nil)
		handler.ServeHTTP(standingResp, standingReq)
		require.Equal(t, http.StatusOK, standingResp.Code)

		var standing map[string]any
		require.NoError(t, json.Unmarshal(standingResp.Body.Bytes(), &standing))
		if int(standing["round_no"].(float64)) >= 2 {
			require.Equal(t, float64(7), standing["players_remaining"])
			require.Equal(t, true, standing["no_multiplier"])
			advanced = true
			break
		}

		_, err = verifyDB.Exec(`UPDATE arena_action_deadline SET deadline_at = NOW() - INTERVAL '1 second' WHERE tournament_id = $1 AND status = 'open'`, tournamentID)
		require.NoError(t, err)
		require.NoError(t, application.ProcessExpiredDeadlines(context.Background()))
	}
	require.True(t, advanced, "live disqualification should apply at next round barrier")

	require.Equal(t, 1, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_operator_intervention WHERE tournament_id = $1 AND miner_id = $2 AND intervention_type = 'disqualify' AND status = 'applied'", tournamentID, disqualifiedMinerID))
	require.Equal(t, 1, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_entrant WHERE tournament_id = $1 AND miner_id = $2 AND registration_state = 'disqualified'", tournamentID, disqualifiedMinerID))
}

func TestRestartRecoversPendingDisqualificationAsReadOnly(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	first, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)

	tournamentID := seedPublishedTournament(t, first.Handler(), "wave_live_disqualify_restart_1", 8)
	tableID := "tbl:" + tournamentID + ":01"
	liveTable := loadLiveTable(t, first.Handler(), tournamentID, tableID)
	disqualifiedSeatNo := int(liveTable["acting_seat_no"].(float64))
	disqualifiedMinerID := lookupMinerForTableSeat(t, first.Handler(), tournamentID, tableID, disqualifiedSeatNo, 8)

	disqualifyResp := httptest.NewRecorder()
	disqualifyReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/tournaments/"+tournamentID+"/disqualify", strings.NewReader(fmt.Sprintf(`{
		"miner_id":"%s",
		"reason":"manual_ops"
	}`, disqualifiedMinerID)))
	first.Handler().ServeHTTP(disqualifyResp, disqualifyReq)
	require.Equal(t, http.StatusOK, disqualifyResp.Code, disqualifyResp.Body.String())
	require.NoError(t, first.Close(context.Background()))

	restarted, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, restarted.Close(context.Background()))
	}()

	assignment := reconnectSeatAssignment(t, restarted.Handler(), tournamentID, disqualifiedMinerID, "dq-restart-session")
	require.Equal(t, true, assignment["read_only"])
	require.Equal(t, tableID, assignment["table_id"])
	require.Equal(t, float64(disqualifiedSeatNo), assignment["seat_no"])

	actionResp := httptest.NewRecorder()
	actionReq := httptest.NewRequest(http.MethodPost, "/v1/tournaments/"+tournamentID+"/actions", strings.NewReader(fmt.Sprintf(`{
		"request_id":"req-dq-restart-%s",
		"table_id":"%s",
		"miner_id":"%s",
		"session_id":"dq-restart-session",
		"seat_no":%d,
		"action_type":"signal_none",
		"expected_state_seq":%d,
		"signature":"sig:%s"
	}`, tournamentID, tableID, disqualifiedMinerID, disqualifiedSeatNo, int(assignment["state_seq"].(float64)), disqualifiedMinerID)))
	restarted.Handler().ServeHTTP(actionResp, actionReq)
	require.Equal(t, http.StatusConflict, actionResp.Code)
	require.Contains(t, actionResp.Body.String(), "read_only_assignment")
}

func TestSeatAssignmentIncludesSeatNumberForClientActions(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	tournamentID := seedPublishedTournament(t, application.Handler(), "wave_client_assignment_1", 56)

	resp := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/seat-assignment/miner_01", nil)
	application.Handler().ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)
	require.Contains(t, resp.Body.String(), `"seat_no":1`)
}

func TestPublishedTournamentStartsWithForcedBlinds(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	tournamentID := seedPublishedTournament(t, application.Handler(), "wave_forced_blinds_1", 8)

	resp := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/live-table/tbl:"+tournamentID+":01", nil)
	application.Handler().ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)

	var body map[string]any
	require.NoError(t, json.Unmarshal(resp.Body.Bytes(), &body))
	require.Equal(t, float64(1), body["level_no"])
	require.Equal(t, float64(25), body["small_blind"])
	require.Equal(t, float64(50), body["big_blind"])
	require.Equal(t, float64(0), body["ante"])
	require.Equal(t, float64(75), body["pot_main"])
	require.Equal(t, float64(50), body["current_to_call"])
	require.Equal(t, float64(100), body["min_raise_size"])

	stacks := bySeatNo(body["visible_stacks"].([]any))
	require.Equal(t, float64(975), stacks[1]["stack"])
	require.Equal(t, float64(950), stacks[2]["stack"])

	actions := bySeatNo(body["seat_public_actions"].([]any))
	require.Equal(t, float64(25), actions[1]["committed_this_hand"])
	require.Equal(t, float64(50), actions[2]["committed_this_hand"])
}

func TestBlindLevelAdvancesEveryFourRoundsAndAddsAnte(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	handler := application.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_blind_levels_1", 8)
	tableID := "tbl:" + tournamentID + ":01"

	for round := 0; round < 4; round++ {
		playCurrentRoundOnTable(t, handler, tournamentID, tableID, 8)
	}

	standingResp := httptest.NewRecorder()
	standingReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/standing", nil)
	handler.ServeHTTP(standingResp, standingReq)
	require.Equal(t, http.StatusOK, standingResp.Code)

	var standing map[string]any
	require.NoError(t, json.Unmarshal(standingResp.Body.Bytes(), &standing))
	require.Equal(t, float64(5), standing["round_no"])
	require.Equal(t, float64(2), standing["level_no"])
	require.Equal(t, float64(8), standing["players_remaining"])

	liveTable := loadLiveTable(t, handler, tournamentID, tableID)
	require.Equal(t, "signal", liveTable["current_phase"])
	require.Equal(t, float64(5), liveTable["hand_number"])
	require.Equal(t, float64(2), liveTable["level_no"])
	require.Equal(t, float64(50), liveTable["small_blind"])
	require.Equal(t, float64(100), liveTable["big_blind"])
	require.Equal(t, float64(10), liveTable["ante"])
	require.Equal(t, float64(230), liveTable["pot_main"])
	require.Equal(t, float64(110), liveTable["current_to_call"])
	require.Equal(t, float64(210), liveTable["min_raise_size"])

	actions := bySeatNo(liveTable["seat_public_actions"].([]any))
	require.Equal(t, float64(60), actions[5]["committed_this_hand"])
	require.Equal(t, float64(110), actions[6]["committed_this_hand"])
}

func TestActionSubmissionAdvancesTurnAndReopensDeadline(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	handler := application.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_client_actions_1", 56)

	assignment := loadSeatAssignment(t, handler, tournamentID, "miner_01")
	tableID := assignment["table_id"].(string)
	liveTable := loadLiveTable(t, handler, tournamentID, tableID)
	actingSeatNo := int(liveTable["acting_seat_no"].(float64))
	actingMinerID := lookupMinerForTableSeat(t, handler, tournamentID, tableID, actingSeatNo, 56)
	actingAssignment := loadSeatAssignment(t, handler, tournamentID, actingMinerID)

	submitRecommendedCurrentSeatActionOnTable(t, handler, tournamentID, tableID, 56)

	liveTable = loadLiveTable(t, handler, tournamentID, tableID)
	nextActingSeatNo := int(liveTable["acting_seat_no"].(float64))
	require.NotZero(t, nextActingSeatNo)
	require.NotEqual(t, actingSeatNo, nextActingSeatNo)

	nextMinerID := lookupMinerForTableSeat(t, handler, tournamentID, tableID, nextActingSeatNo, 56)
	nextAssignment := loadSeatAssignment(t, handler, tournamentID, nextMinerID)
	require.Greater(t, int(nextAssignment["state_seq"].(float64)), int(actingAssignment["state_seq"].(float64)))

	verifyDB := openArenaAppTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()
	require.Equal(t, 2, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_action_deadline WHERE tournament_id = $1 AND table_id = $2", tournamentID, tableID))
	require.Equal(t, 1, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_action_deadline WHERE tournament_id = $1 AND table_id = $2 AND status = 'open'", tournamentID, tableID))
}

func TestSingleTableRoundLifecycleAdvancesAcrossPhasesAndStartsNextRound(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	handler := application.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_single_table_lifecycle_1", 8)

	for step := 0; step < 8; step++ {
		submitCurrentSeatAction(t, handler, tournamentID, ActionFromPhase("signal"))
	}
	requireLiveTablePhase(t, handler, tournamentID, "tbl:"+tournamentID+":01", "probe")

	for step := 0; step < 8; step++ {
		submitCurrentSeatAction(t, handler, tournamentID, ActionFromPhase("probe"))
	}
	requireLiveTablePhase(t, handler, tournamentID, "tbl:"+tournamentID+":01", "wager")

	playCurrentRoundOnTable(t, handler, tournamentID, "tbl:"+tournamentID+":01", 8)

	standingResp := httptest.NewRecorder()
	standingReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/standing", nil)
	handler.ServeHTTP(standingResp, standingReq)
	require.Equal(t, http.StatusOK, standingResp.Code)
	require.Contains(t, standingResp.Body.String(), `"round_no":2`)
	require.Contains(t, standingResp.Body.String(), `"players_remaining":8`)

	requireLiveTablePhase(t, handler, tournamentID, "tbl:"+tournamentID+":01", "signal")
}

func TestMultiTableBarrierStartsNextRoundAfterAllTablesClose(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	handler := application.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_multi_table_rebalance_1", 9)
	tableOneID := "tbl:" + tournamentID + ":01"
	tableTwoID := "tbl:" + tournamentID + ":02"

	playCurrentRoundOnTable(t, handler, tournamentID, tableTwoID, 9)
	playCurrentRoundOnTable(t, handler, tournamentID, tableOneID, 9)

	standingResp := httptest.NewRecorder()
	standingReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/standing", nil)
	handler.ServeHTTP(standingResp, standingReq)
	require.Equal(t, http.StatusOK, standingResp.Code)
	require.Contains(t, standingResp.Body.String(), `"round_no":2`)
	require.Contains(t, standingResp.Body.String(), `"players_remaining":9`)
	require.Contains(t, standingResp.Body.String(), `"state":"live_final_table"`)

	requireLiveTableHasCountAndPhase(t, handler, tournamentID, tableOneID, 9, "signal")

	missingResp := httptest.NewRecorder()
	missingReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/live-table/"+tableTwoID, nil)
	handler.ServeHTTP(missingResp, missingReq)
	require.Equal(t, http.StatusNotFound, missingResp.Code)
}

func TestNaturalFinishUsesAwardedPotToBustLoserAndCompleteTournament(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	handler := application.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_natural_finish_award_1", 2)

	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "signal_none", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "signal_none", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "pass_probe", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "pass_probe", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "all_in", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "call", 0)

	standingResp := httptest.NewRecorder()
	standingReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/standing", nil)
	handler.ServeHTTP(standingResp, standingReq)
	require.Equal(t, http.StatusOK, standingResp.Code)
	var standing map[string]any
	require.NoError(t, json.Unmarshal(standingResp.Body.Bytes(), &standing))
	require.Equal(t, "completed", standing["status"])
	require.Equal(t, "natural_finish", standing["completed_reason"])
	require.Equal(t, float64(1), standing["players_remaining"])
	require.Contains(t, []string{"miner_01", "miner_02"}, standing["winner_miner_id"])
	finalStandings, ok := standing["final_standings"].([]any)
	require.True(t, ok, "completed standing should include final_standings")
	require.Len(t, finalStandings, 2)
	for _, rawEntry := range finalStandings {
		entry, ok := rawEntry.(map[string]any)
		require.True(t, ok)
		require.Contains(t, []float64{1, 2}, entry["finish_rank"])
		require.NotEmpty(t, entry["miner_id"])
		require.NotEmpty(t, entry["stage_reached"])
		require.NotEmpty(t, entry["rank_source"])
		require.Contains(t, entry, "final_stack")
		require.Greater(t, entry["hands_played"].(float64), float64(0))
		require.Greater(t, entry["meaningful_decisions"].(float64), float64(0))
		require.Equal(t, float64(0), entry["timeout_actions"])
		require.Equal(t, float64(0), entry["invalid_actions"])
	}
}

func TestNaturalFinishWritesRatingInputsAndFinishRanks(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	handler := application.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_natural_finish_rating_1", 2)

	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "signal_none", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "signal_none", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "pass_probe", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "pass_probe", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "all_in", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "call", 0)

	verifyDB := openArenaAppTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()

	require.Equal(t, 2, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1", tournamentID))
	require.Equal(t, 2, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_result_entries WHERE tournament_id = $1", tournamentID))
	require.Equal(t, 2, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1 AND hands_played > 0", tournamentID))
	require.Equal(t, 2, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1 AND meaningful_decisions > 0", tournamentID))
	require.Zero(t, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1 AND timeout_actions <> 0", tournamentID))
	require.Zero(t, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1 AND invalid_actions <> 0", tournamentID))
	require.Equal(t, []int{1, 2}, loadArenaAppIntSlice(t, verifyDB, "SELECT finish_rank FROM arena_rating_input WHERE tournament_id = $1 ORDER BY finish_rank", tournamentID))
	require.Equal(t, []int{1, 2}, loadArenaAppIntSlice(t, verifyDB, "SELECT finish_rank FROM arena_entrant WHERE tournament_id = $1 ORDER BY finish_rank", tournamentID))
	require.Equal(t, []string{"completed"}, loadArenaAppStringSlice(t, verifyDB, "SELECT payload->>'stage' FROM arena_tournament_snapshot WHERE tournament_id = $1 ORDER BY stream_seq DESC LIMIT 1", tournamentID))
	require.Zero(t, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_rating_input WHERE tournament_id = $1 AND COALESCE(stage_reached, '') = ''", tournamentID))
	require.Zero(t, countArenaAppRows(t, verifyDB, "SELECT COUNT(*) FROM arena_entrant WHERE tournament_id = $1 AND COALESCE(stage_reached, '') = ''", tournamentID))
}

func TestCompletedTournamentReplayHashSurvivesAppRestart(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	first, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)

	handler := first.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_completed_replay_restart_1", 2)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "signal_none", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "signal_none", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "pass_probe", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "pass_probe", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "all_in", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "call", 0)

	verifyDB := openArenaAppTestDB(t)
	repo, err := postgres.NewRepository(verifyDB)
	require.NoError(t, err)
	beforeHash, err := replay.NewRepositoryReplayer(repo).ComputeFinalHash(context.Background(), tournamentID)
	require.NoError(t, err)
	require.NotEmpty(t, beforeHash)
	require.NoError(t, verifyDB.Close())
	require.NoError(t, first.Close(context.Background()))

	restarted, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, restarted.Close(context.Background()))
	}()

	verifyDB = openArenaAppTestDB(t)
	defer func() {
		require.NoError(t, verifyDB.Close())
	}()
	repo, err = postgres.NewRepository(verifyDB)
	require.NoError(t, err)
	replayer := replay.NewRepositoryReplayer(repo)
	afterHash, err := replayer.ComputeFinalHash(context.Background(), tournamentID)
	require.NoError(t, err)
	require.Equal(t, beforeHash, afterHash)

	result := replayer.ReplayTournament(context.Background(), tournamentID, beforeHash)
	require.NoError(t, result.Err)
	require.True(t, result.ParityOK)
	require.Equal(t, "ok", result.FinalDisposition)
}

func TestLiveTableExposesDecisionViewForActingSeat(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	handler := application.Handler()
	tournamentID := seedPublishedTournament(t, handler, "wave_live_table_decision_view_1", 2)

	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "signal_none", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "signal_none", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "pass_probe", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "pass_probe", 0)
	submitCurrentSeatActionWithAmount(t, handler, tournamentID, "raise", 100)

	liveTableResp := httptest.NewRecorder()
	liveTableReq := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/live-table/tbl:"+tournamentID+":01", nil)
	handler.ServeHTTP(liveTableResp, liveTableReq)
	require.Equal(t, http.StatusOK, liveTableResp.Code)

	var body map[string]any
	require.NoError(t, json.Unmarshal(liveTableResp.Body.Bytes(), &body))
	require.Equal(t, "wager", body["current_phase"])
	require.Equal(t, float64(2), body["acting_seat_no"])
	require.Equal(t, float64(100), body["current_to_call"])
	require.Equal(t, float64(100), body["min_raise_size"])
	require.NotZero(t, int(body["state_seq"].(float64)))
	require.Equal(t, []string{"call", "fold", "raise", "all_in"}, stringSlice(body["legal_actions"].([]any)))

	stacks := bySeatNo(body["visible_stacks"].([]any))
	require.Equal(t, float64(900), stacks[1]["stack"])
	require.Equal(t, float64(950), stacks[2]["stack"])

	actions := bySeatNo(body["seat_public_actions"].([]any))
	require.Equal(t, float64(100), actions[1]["committed_this_hand"])
	require.Equal(t, false, actions[1]["folded"])
	require.Equal(t, false, actions[1]["all_in"])
}

func TestSwarmCoordinatorRunsHeuristicBotsToCompletionOverHTTP(t *testing.T) {
	db := openArenaAppTestDB(t)
	resetArenaAppSchema(t, db)
	require.NoError(t, db.Close())

	application, err := app.New(config.Config{
		DatabaseURL:     arenaAppTestDatabaseURL(),
		HTTPAddr:        "127.0.0.1:0",
		ShutdownTimeout: 2 * time.Second,
	})
	require.NoError(t, err)
	defer func() {
		require.NoError(t, application.Close(context.Background()))
	}()

	server := httptest.NewServer(application.Handler())
	defer server.Close()

	tournamentID := seedPublishedTournament(t, application.Handler(), "wave_http_bot_completion_1", 2)

	runners := make([]swarm.Runner, 0, 2)
	for idx := 1; idx <= 2; idx++ {
		runners = append(runners, bot.NewRunner(bot.RunnerConfig{
			BaseURL:      server.URL,
			TournamentID: tournamentID,
			MinerID:      fmt.Sprintf("miner_%02d", idx),
			Policy:       bot.HeuristicPolicy{},
		}))
	}

	observer := bot.NewClient(server.URL, tournamentID, "miner_01")
	result, err := swarm.NewCoordinator(swarm.CoordinatorConfig{
		Observer:      observer,
		Runners:       runners,
		MaxSteps:      2000,
		MaxIdleCycles: 20,
	}).Run(context.Background())
	require.NoError(t, err)
	require.True(t, result.Completed)
	require.NotEmpty(t, result.Logs)
	require.Equal(t, "completed", result.Standing.Status)
	require.Equal(t, "natural_finish", result.Standing.CompletedReason)
	require.Contains(t, []string{"miner_01", "miner_02"}, result.Standing.WinnerMinerID)
	require.Condition(t, func() bool {
		for _, log := range result.Logs {
			if log.Status == "submitted" {
				return true
			}
		}
		return false
	})
}

func ActionFromPhase(phase string) string {
	switch phase {
	case "signal":
		return "signal_none"
	case "probe":
		return "pass_probe"
	default:
		return "check"
	}
}

func submitCurrentSeatAction(t *testing.T, handler http.Handler, tournamentID, actionType string) {
	t.Helper()

	tableID := "tbl:" + tournamentID + ":01"
	liveTable := loadLiveTable(t, handler, tournamentID, tableID)
	submitCurrentSeatActionOnTableWithAmount(t, handler, tournamentID, tableID, int(liveTable["player_count"].(float64)), actionType, 0)
}

func submitCurrentSeatActionWithAmount(t *testing.T, handler http.Handler, tournamentID, actionType string, amount int64) {
	t.Helper()

	tableID := "tbl:" + tournamentID + ":01"
	liveTable := loadLiveTable(t, handler, tournamentID, tableID)
	submitCurrentSeatActionOnTableWithAmount(t, handler, tournamentID, tableID, int(liveTable["player_count"].(float64)), actionType, amount)
}

func submitCurrentSeatActionOnTable(t *testing.T, handler http.Handler, tournamentID, tableID string, entrantCount int, actionType string) {
	t.Helper()

	submitCurrentSeatActionOnTableWithAmount(t, handler, tournamentID, tableID, entrantCount, actionType, 0)
}

func playCurrentRoundOnTable(t *testing.T, handler http.Handler, tournamentID, tableID string, entrantCount int) {
	t.Helper()

	initialLiveTable, ok := tryLoadLiveTable(t, handler, tournamentID, tableID)
	if !ok {
		return
	}
	initialHandNumber := int(initialLiveTable["hand_number"].(float64))

	for step := 0; step < entrantCount*4; step++ {
		liveTable, ok := tryLoadLiveTable(t, handler, tournamentID, tableID)
		if !ok {
			return
		}
		handNumber := int(liveTable["hand_number"].(float64))
		actingSeatNo := int(liveTable["acting_seat_no"].(float64))
		if handNumber > initialHandNumber || actingSeatNo == 0 {
			return
		}
		submitRecommendedCurrentSeatActionOnTable(t, handler, tournamentID, tableID, entrantCount)
	}

	t.Fatalf("table %s did not complete hand %d", tableID, initialHandNumber)
}

func tryLoadLiveTable(t *testing.T, handler http.Handler, tournamentID, tableID string) (map[string]any, bool) {
	t.Helper()

	resp := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/live-table/"+tableID, nil)
	handler.ServeHTTP(resp, req)
	if resp.Code == http.StatusNotFound {
		return nil, false
	}
	require.Equal(t, http.StatusOK, resp.Code)

	var liveTable map[string]any
	require.NoError(t, json.Unmarshal(resp.Body.Bytes(), &liveTable))
	return liveTable, true
}

func loadLiveTable(t *testing.T, handler http.Handler, tournamentID, tableID string) map[string]any {
	t.Helper()

	liveTable, ok := tryLoadLiveTable(t, handler, tournamentID, tableID)
	require.True(t, ok)
	return liveTable
}

func lookupMinerForTableSeat(t *testing.T, handler http.Handler, tournamentID, tableID string, seatNo, entrantCount int) string {
	t.Helper()

	for idx := 1; idx <= entrantCount; idx++ {
		minerID := fmt.Sprintf("miner_%02d", idx)
		resp := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/seat-assignment/"+minerID, nil)
		handler.ServeHTTP(resp, req)
		if resp.Code != http.StatusOK {
			continue
		}
		var assignment map[string]any
		require.NoError(t, json.Unmarshal(resp.Body.Bytes(), &assignment))
		if assignment["table_id"] == tableID && int(assignment["seat_no"].(float64)) == seatNo {
			return minerID
		}
	}

	t.Fatalf("no miner found for %s seat %d", tableID, seatNo)
	return ""
}

func loadSeatAssignment(t *testing.T, handler http.Handler, tournamentID, minerID string) map[string]any {
	t.Helper()

	resp := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/seat-assignment/"+minerID, nil)
	handler.ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)

	var assignment map[string]any
	require.NoError(t, json.Unmarshal(resp.Body.Bytes(), &assignment))
	return assignment
}

func reconnectSeatAssignment(t *testing.T, handler http.Handler, tournamentID, minerID, sessionID string) map[string]any {
	t.Helper()

	resp := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/tournaments/"+tournamentID+"/sessions/reconnect", strings.NewReader(fmt.Sprintf(`{
		"miner_id":"%s",
		"session_id":"%s"
	}`, minerID, sessionID)))
	handler.ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code, resp.Body.String())

	var assignment map[string]any
	require.NoError(t, json.Unmarshal(resp.Body.Bytes(), &assignment))
	return assignment
}

func submitRecommendedCurrentSeatAction(t *testing.T, handler http.Handler, tournamentID string) {
	t.Helper()

	tableID := "tbl:" + tournamentID + ":01"
	liveTable := loadLiveTable(t, handler, tournamentID, tableID)
	submitRecommendedCurrentSeatActionOnTable(t, handler, tournamentID, tableID, int(liveTable["player_count"].(float64)))
}

func submitRecommendedCurrentSeatActionOnTable(t *testing.T, handler http.Handler, tournamentID, tableID string, entrantCount int) {
	t.Helper()

	liveTable := loadLiveTable(t, handler, tournamentID, tableID)
	actionType, amount := recommendedActionForLiveTable(t, liveTable)
	submitCurrentSeatActionOnTableWithAmount(t, handler, tournamentID, tableID, entrantCount, actionType, amount)
}

func submitCurrentSeatActionOnTableWithAmount(t *testing.T, handler http.Handler, tournamentID, tableID string, entrantCount int, actionType string, amount int64) {
	t.Helper()

	liveTable := loadLiveTable(t, handler, tournamentID, tableID)
	actingSeatNo := int(liveTable["acting_seat_no"].(float64))
	minerID := lookupMinerForTableSeat(t, handler, tournamentID, tableID, actingSeatNo, entrantCount)
	sessionID := "test-session-" + minerID
	assignment := reconnectSeatAssignment(t, handler, tournamentID, minerID, sessionID)

	actionResp := httptest.NewRecorder()
	actionReq := httptest.NewRequest(http.MethodPost, "/v1/tournaments/"+tournamentID+"/actions", strings.NewReader(fmt.Sprintf(`{
		"request_id":"req-%s-%s-%d-%s-%d-%d",
		"table_id":"%s",
		"miner_id":"%s",
		"session_id":"%s",
		"seat_no":%d,
		"action_type":"%s",
		"amount":%d,
		"expected_state_seq":%d,
		"signature":"sig:%s"
	}`, tournamentID, strings.ReplaceAll(tableID, ":", "-"), actingSeatNo, actionType, amount, int(assignment["state_seq"].(float64)), assignment["table_id"], minerID, sessionID, actingSeatNo, actionType, amount, int(assignment["state_seq"].(float64)), minerID)))
	handler.ServeHTTP(actionResp, actionReq)
	require.Equal(t, http.StatusOK, actionResp.Code, actionResp.Body.String())
}

func recommendedActionForLiveTable(t *testing.T, liveTable map[string]any) (string, int64) {
	t.Helper()

	switch liveTable["current_phase"] {
	case "signal":
		return "signal_none", 0
	case "probe":
		return "pass_probe", 0
	case "wager":
		legalActions := stringSlice(liveTable["legal_actions"].([]any))
		switch {
		case containsString(legalActions, "call"):
			return "call", 0
		case containsString(legalActions, "check"):
			return "check", 0
		case containsString(legalActions, "all_in"):
			return "all_in", 0
		case containsString(legalActions, "fold"):
			return "fold", 0
		default:
			t.Fatalf("no supported legal action for live table: %+v", liveTable)
		}
	default:
		t.Fatalf("unsupported phase for recommended action: %+v", liveTable["current_phase"])
	}

	return "", 0
}

func requireLiveTablePhase(t *testing.T, handler http.Handler, tournamentID, tableID, phase string) {
	t.Helper()

	resp := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/live-table/"+tableID, nil)
	handler.ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)
	require.Contains(t, resp.Body.String(), fmt.Sprintf(`"current_phase":"%s"`, phase))
}

func requireLiveTableHasCountAndPhase(t *testing.T, handler http.Handler, tournamentID, tableID string, playerCount int, phase string) {
	t.Helper()

	resp := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/v1/tournaments/"+tournamentID+"/live-table/"+tableID, nil)
	handler.ServeHTTP(resp, req)
	require.Equal(t, http.StatusOK, resp.Code)
	require.Contains(t, resp.Body.String(), fmt.Sprintf(`"player_count":%d`, playerCount))
	require.Contains(t, resp.Body.String(), fmt.Sprintf(`"current_phase":"%s"`, phase))
}

func arenaAppTestDatabaseURL() string {
	if value := os.Getenv("ARENA_TEST_DATABASE_URL"); value != "" {
		return value
	}

	return "postgres://clawchain:clawchain_dev_pw@127.0.0.1:55432/arena_runtime_test?sslmode=disable"
}

func openArenaAppTestDB(t *testing.T) *sql.DB {
	t.Helper()

	db, err := sql.Open("postgres", arenaAppTestDatabaseURL())
	require.NoError(t, err)
	require.NoError(t, db.Ping())
	return db
}

func resetArenaAppSchema(t *testing.T, db *sql.DB) {
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

func countArenaAppRows(t *testing.T, db *sql.DB, query string, args ...any) int {
	t.Helper()

	var count int
	require.NoError(t, db.QueryRow(query, args...).Scan(&count))
	return count
}

func loadArenaAppIntSlice(t *testing.T, db *sql.DB, query string, args ...any) []int {
	t.Helper()

	rows, err := db.Query(query, args...)
	require.NoError(t, err)
	defer func() {
		require.NoError(t, rows.Close())
	}()

	values := make([]int, 0)
	for rows.Next() {
		var value int
		require.NoError(t, rows.Scan(&value))
		values = append(values, value)
	}
	require.NoError(t, rows.Err())
	return values
}

func loadArenaAppStringSlice(t *testing.T, db *sql.DB, query string, args ...any) []string {
	t.Helper()

	rows, err := db.Query(query, args...)
	require.NoError(t, err)
	defer func() {
		require.NoError(t, rows.Close())
	}()

	values := make([]string, 0)
	for rows.Next() {
		var value string
		require.NoError(t, rows.Scan(&value))
		values = append(values, value)
	}
	require.NoError(t, rows.Err())
	return values
}

func stringSlice(values []any) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		out = append(out, value.(string))
	}
	return out
}

func bySeatNo(values []any) map[int]map[string]any {
	out := make(map[int]map[string]any, len(values))
	for _, value := range values {
		item := value.(map[string]any)
		out[int(item["seat_no"].(float64))] = item
	}
	return out
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func seedPublishedTournament(t *testing.T, handler http.Handler, waveID string, entrants int) string {
	t.Helper()

	createWaveResp := httptest.NewRecorder()
	createWaveReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/waves", strings.NewReader(fmt.Sprintf(`{
		"wave_id":"%s",
		"mode":"rated",
		"registration_open_at":"2026-04-10T19:00:00Z",
		"registration_close_at":"2026-04-10T19:30:00Z",
		"scheduled_start_at":"2026-04-10T20:00:00Z"
	}`, waveID)))
	handler.ServeHTTP(createWaveResp, createWaveReq)
	require.Equal(t, http.StatusCreated, createWaveResp.Code)

	for i := 1; i <= entrants; i++ {
		resp := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodPost, "/v1/arena/waves/"+waveID+"/register", strings.NewReader(fmt.Sprintf(`{"miner_id":"miner_%02d"}`, i)))
		handler.ServeHTTP(resp, req)
		require.Equal(t, http.StatusOK, resp.Code)
	}

	lockResp := httptest.NewRecorder()
	lockReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/waves/"+waveID+"/lock", nil)
	handler.ServeHTTP(lockResp, lockReq)
	require.Equal(t, http.StatusOK, lockResp.Code)

	var lockBody map[string]any
	require.NoError(t, json.Unmarshal(lockResp.Body.Bytes(), &lockBody))
	tournamentID := lockBody["tournament_id"].(string)

	publishResp := httptest.NewRecorder()
	publishReq := httptest.NewRequest(http.MethodPost, "/v1/admin/arena/waves/"+waveID+"/publish-seats", nil)
	handler.ServeHTTP(publishResp, publishReq)
	require.Equal(t, http.StatusOK, publishResp.Code)

	return tournamentID
}

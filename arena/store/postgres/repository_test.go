package postgres_test

import (
	"context"
	"database/sql"
	"encoding/json"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/store"
	"github.com/clawchain/clawchain/arena/store/postgres"
)

func TestNewRepositoryRequiresDB(t *testing.T) {
	repo, err := postgres.NewRepository(nil)

	require.Nil(t, repo)
	require.Error(t, err)
	require.ErrorContains(t, err, "db")
}

func TestRepositoryImplementsArenaStoreContract(t *testing.T) {
	var repo *postgres.Repository
	var _ store.Repository = repo
}

func TestRepositoryPersistsAuthoritativeRuntimeRows(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	ctx := context.Background()
	now := time.Date(2026, time.April, 10, 10, 0, 0, 0, time.UTC)
	payload := json.RawMessage(`{"source":"test"}`)

	waveID := model.WaveID(model.RatedMode, now)
	tournamentID := model.TournamentID(waveID, 1)
	tableID := model.TableID(tournamentID, 1)
	handID := model.HandID(tournamentID, 1, 1)
	phaseID := model.PhaseID(handID, model.PhaseTypeSignal)
	barrierID := model.BarrierID(tournamentID, 1)

	require.NoError(t, repo.UpsertWave(ctx, model.Wave{
		ID:                  waveID,
		Mode:                model.RatedMode,
		State:               model.WaveStateRegistrationOpen,
		RegistrationOpenAt:  now,
		RegistrationCloseAt: now.Add(30 * time.Minute),
		ScheduledStartAt:    now.Add(time.Hour),
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "wave-state-hash",
			PayloadHash:         "wave-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertEntrant(ctx, model.Entrant{
		ID:                "ent:1",
		WaveID:            waveID,
		TournamentID:      tournamentID,
		MinerID:           "miner-1",
		SeatAlias:         "alias-1",
		RegistrationState: model.RegistrationStateConfirmed,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "entrant-state-hash",
			PayloadHash:         "entrant-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertWaitlistEntry(ctx, model.WaitlistEntry{
		ID:                "wait:1",
		WaveID:            waveID,
		EntrantID:         "ent:1",
		MinerID:           "miner-1",
		RegistrationState: model.RegistrationStateWaitlisted,
		WaitlistPosition:  1,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "wait-state-hash",
			PayloadHash:         "wait-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertPrestartCheck(ctx, model.PrestartCheck{
		ID:           "pre:1",
		WaveID:       waveID,
		EntrantID:    "ent:1",
		CheckType:    "identity",
		CheckStatus:  "passed",
		CheckedAt:    now,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "pre-state-hash",
			PayloadHash:         "pre-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertTournament(ctx, model.Tournament{
		ID:          tournamentID,
		WaveID:      waveID,
		Mode:        model.RatedMode,
		State:       model.TournamentStateReady,
		RNGRootSeed: "rng-root-seed",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "tournament-state-hash",
			PayloadHash:         "tournament-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertShardAssignment(ctx, model.ShardAssignment{
		ID:           "shard:1",
		WaveID:       waveID,
		TournamentID: tournamentID,
		EntrantID:    "ent:1",
		ShardNo:      1,
		SeatDrawToken: "draw-1",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "shard-state-hash",
			PayloadHash:         "shard-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertLevel(ctx, model.Level{
		ID:           "lvl:1",
		TournamentID: tournamentID,
		LevelNo:      1,
		SmallBlind:   10,
		BigBlind:     20,
		Ante:         2,
		StartsAt:     now,
		EndsAt:       now.Add(10 * time.Minute),
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "level-state-hash",
			PayloadHash:         "level-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertTable(ctx, model.Table{
		ID:           tableID,
		TournamentID: tournamentID,
		State:        model.TableStateOpen,
		TableNo:      1,
		RNGRootSeed:  "rng-root-seed",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "table-state-hash",
			PayloadHash:         "table-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertHand(ctx, model.Hand{
		ID:                handID,
		TableID:           tableID,
		TournamentID:      tournamentID,
		RoundNo:           1,
		LevelNo:           1,
		State:             model.HandStateSignalOpen,
		HandStartedAt:     now,
		ButtonSeatNo:      1,
		ActiveSeatCount:   1,
		RNGRootSeed:       "rng-root-seed",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "hand-state-hash",
			PayloadHash:         "hand-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertPhase(ctx, model.Phase{
		ID:        phaseID,
		HandID:    handID,
		TableID:   tableID,
		State:     model.PhaseStateOpen,
		Type:      model.PhaseTypeSignal,
		OpenedAt:  now,
		DeadlineAt: ptrTime(now.Add(15 * time.Second)),
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "phase-state-hash",
			PayloadHash:         "phase-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertSeat(ctx, model.Seat{
		ID:                     "seat:1",
		TableID:                tableID,
		TournamentID:           tournamentID,
		EntrantID:              "ent:1",
		SeatNo:                 1,
		SeatAlias:              "alias-1",
		MinerID:                "miner-1",
		State:                  model.SeatStateActive,
		Stack:                  1000,
		TournamentSeatDrawToken: "draw-1",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "seat-state-hash",
			PayloadHash:         "seat-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertAliasMap(ctx, model.AliasMap{
		ID:           "alias:1",
		TournamentID: tournamentID,
		TableID:      tableID,
		SeatID:       "seat:1",
		SeatAlias:    "alias-1",
		MinerID:      "miner-1",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "alias-state-hash",
			PayloadHash:         "alias-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.AppendSubmissionLedgerEntries(ctx, []model.SubmissionLedger{{
		RequestID:        "req:1",
		TournamentID:     tournamentID,
		TableID:          tableID,
		HandID:           handID,
		PhaseID:          phaseID,
		SeatID:           "seat:1",
		SeatAlias:        "alias-1",
		MinerID:          "miner-1",
		ExpectedStateSeq: 1,
		ValidationStatus: "accepted",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "ledger-state-hash",
			PayloadHash:         "ledger-payload-hash",
		},
		Payload: payload,
	}}))
	require.NoError(t, repo.AppendActionRecords(ctx, []model.ActionRecord{{
		RequestID:          "req:1",
		TournamentID:       tournamentID,
		TableID:            tableID,
		HandID:             handID,
		PhaseID:            phaseID,
		SeatID:             "seat:1",
		SeatAlias:          "alias-1",
		ActionType:         "check",
		ActionSeq:          1,
		ExpectedStateSeq:   1,
		AcceptedStateSeq:   1,
		ValidationStatus:   "accepted",
		ResultEventID:      model.EventID(tableID, 1),
		ReceivedAt:         now,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "action-state-hash",
			PayloadHash:         "action-payload-hash",
		},
		Payload: payload,
	}}))
	require.NoError(t, repo.UpsertActionDeadline(ctx, model.ActionDeadline{
		DeadlineID:      "ddl:1",
		TournamentID:    tournamentID,
		TableID:         tableID,
		HandID:          handID,
		PhaseID:         phaseID,
		SeatID:          "seat:1",
		DeadlineAt:      now.Add(15 * time.Second),
		Status:          "open",
		OpenedByEventID: model.EventID(tableID, 1),
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "deadline-state-hash",
			PayloadHash:         "deadline-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertRoundBarrier(ctx, model.RoundBarrier{
		ID:                         barrierID,
		TournamentID:               tournamentID,
		RoundNo:                    1,
		ExpectedTableCount:         1,
		ReceivedHandCloseCount:     0,
		BarrierState:               "open",
		TerminateAfterCurrentRound: false,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "barrier-state-hash",
			PayloadHash:         "barrier-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertOperatorIntervention(ctx, model.OperatorIntervention{
		ID:               "ops:1",
		TournamentID:     tournamentID,
		TableID:          tableID,
		SeatID:           "seat:1",
		MinerID:          "miner-1",
		InterventionType: "pause",
		Status:           "requested",
		RequestedBy:      "operator",
		RequestedAt:      now,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "ops-state-hash",
			PayloadHash:         "ops-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.AppendReseatEvents(ctx, []model.ReseatEvent{{
		ID:               "reseat:1",
		TournamentID:     tournamentID,
		FromTableID:      tableID,
		ToTableID:        tableID,
		SeatID:           "seat:1",
		EntrantID:        "ent:1",
		RoundNo:          1,
		CausedByBarrierID: barrierID,
		OccurredAt:       now,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "reseat-state-hash",
			PayloadHash:         "reseat-payload-hash",
		},
		Payload: payload,
	}}))
	require.NoError(t, repo.AppendEliminationEvents(ctx, []model.EliminationEvent{{
		ID:               "elim:1",
		TournamentID:     tournamentID,
		TableID:          tableID,
		HandID:           handID,
		SeatID:           "seat:1",
		EntrantID:        "ent:1",
		FinishRank:       64,
		StageReached:     "signal_open",
		OccurredAt:       now,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "elim-state-hash",
			PayloadHash:         "elim-payload-hash",
		},
		Payload: payload,
	}}))

	for table, expected := range map[string]int{
		"arena_entrant":               1,
		"arena_waitlist":              1,
		"arena_prestart_check":        1,
		"arena_shard_assignment":      1,
		"arena_level":                 1,
		"arena_hand":                  1,
		"arena_phase":                 1,
		"arena_seat":                  1,
		"arena_alias_map":             1,
		"submission_ledger":           1,
		"arena_action":                1,
		"arena_action_deadline":       1,
		"arena_round_barrier":         1,
		"arena_operator_intervention": 1,
		"arena_reseat_event":          1,
		"arena_elimination_event":     1,
	} {
		require.Equalf(t, expected, rowCount(t, db, table), table)
	}
}

func rowCount(t *testing.T, db *sql.DB, table string) int {
	t.Helper()

	var count int
	err := db.QueryRow("SELECT COUNT(*) FROM " + table).Scan(&count)
	require.NoError(t, err)
	return count
}

func ptrTime(value time.Time) *time.Time {
	return &value
}

package postgres_test

import (
	"context"
	"database/sql"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/store"
	"github.com/clawchain/clawchain/arena/store/postgres"
	"github.com/clawchain/clawchain/arena/testutil"
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
		ID:          "pre:1",
		WaveID:      waveID,
		EntrantID:   "ent:1",
		CheckType:   "identity",
		CheckStatus: "passed",
		CheckedAt:   now,
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
		ID:            "shard:1",
		WaveID:        waveID,
		TournamentID:  tournamentID,
		EntrantID:     "ent:1",
		ShardNo:       1,
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
		ID:              handID,
		TableID:         tableID,
		TournamentID:    tournamentID,
		RoundNo:         1,
		LevelNo:         1,
		State:           model.HandStateSignalOpen,
		HandStartedAt:   now,
		ButtonSeatNo:    1,
		ActiveSeatCount: 1,
		RNGRootSeed:     "rng-root-seed",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "hand-state-hash",
			PayloadHash:         "hand-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertPhase(ctx, model.Phase{
		ID:         phaseID,
		HandID:     handID,
		TableID:    tableID,
		State:      model.PhaseStateOpen,
		Type:       model.PhaseTypeSignal,
		OpenedAt:   now,
		DeadlineAt: ptrTime(now.Add(15 * time.Second)),
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "phase-state-hash",
			PayloadHash:         "phase-payload-hash",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertSeat(ctx, model.Seat{
		ID:                      "seat:1",
		TableID:                 tableID,
		TournamentID:            tournamentID,
		EntrantID:               "ent:1",
		SeatNo:                  1,
		SeatAlias:               "alias-1",
		MinerID:                 "miner-1",
		State:                   model.SeatStateActive,
		Stack:                   1000,
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
		RequestID:        "req:1",
		TournamentID:     tournamentID,
		TableID:          tableID,
		HandID:           handID,
		PhaseID:          phaseID,
		SeatID:           "seat:1",
		SeatAlias:        "alias-1",
		ActionType:       "check",
		ActionSeq:        1,
		ExpectedStateSeq: 1,
		AcceptedStateSeq: 1,
		ValidationStatus: "accepted",
		ResultEventID:    model.EventID(tableID, 1),
		ReceivedAt:       now,
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
		ID:                "reseat:1",
		TournamentID:      tournamentID,
		FromTableID:       tableID,
		ToTableID:         tableID,
		SeatID:            "seat:1",
		EntrantID:         "ent:1",
		RoundNo:           1,
		CausedByBarrierID: barrierID,
		OccurredAt:        now,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "reseat-state-hash",
			PayloadHash:         "reseat-payload-hash",
		},
		Payload: payload,
	}}))
	require.NoError(t, repo.AppendEliminationEvents(ctx, []model.EliminationEvent{{
		ID:           "elim:1",
		TournamentID: tournamentID,
		TableID:      tableID,
		HandID:       handID,
		SeatID:       "seat:1",
		EntrantID:    "ent:1",
		FinishRank:   64,
		StageReached: "signal_open",
		OccurredAt:   now,
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

func TestSubmissionLedgerRejectsPayloadConflict(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	ctx := context.Background()
	first := model.SubmissionLedger{
		RequestID:        "req:conflict",
		TournamentID:     "tour:1",
		TableID:          "tbl:1",
		ExpectedStateSeq: 7,
		ValidationStatus: "received",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "submission-state-1",
			PayloadHash:         "payload-hash-1",
		},
		Payload: json.RawMessage(`{"action_type":"check"}`),
	}
	require.NoError(t, repo.AppendSubmissionLedgerEntries(ctx, []model.SubmissionLedger{first}))

	err = repo.AppendSubmissionLedgerEntries(ctx, []model.SubmissionLedger{{
		RequestID:        first.RequestID,
		TournamentID:     first.TournamentID,
		TableID:          first.TableID,
		ExpectedStateSeq: 8,
		ValidationStatus: "received",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "submission-state-2",
			PayloadHash:         "payload-hash-2",
		},
		Payload: json.RawMessage(`{"action_type":"raise","amount":100}`),
	}})
	require.Error(t, err)
	require.ErrorContains(t, err, "request_id payload conflict")

	entry, err := repo.LoadSubmissionLedgerEntry(ctx, first.RequestID)
	require.NoError(t, err)
	require.Equal(t, "payload-hash-1", entry.PayloadHash)
	require.Equal(t, first.ExpectedStateSeq, entry.ExpectedStateSeq)
}

func TestAppendEventsAllowsIdempotentDuplicateEventID(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	ctx := context.Background()
	entry := model.EventLogEntry{
		EventID:        "evt:test:1",
		AggregateType:  "table",
		AggregateID:    "tbl:test:1",
		StreamKey:      "table:tbl:test:1",
		StreamSeq:      7,
		TournamentID:   "tour:test:1",
		TableID:        "tbl:test:1",
		HandID:         "hand:test:1",
		PhaseID:        "phase:test:1",
		RoundNo:        2,
		BarrierID:      "barrier:test:1",
		EventType:      "phase_opened",
		EventVersion:   1,
		StateSeq:       11,
		CausationID:    "cause:test:1",
		CorrelationID:  "corr:test:1",
		Payload:        json.RawMessage(`{"kind":"phase_opened"}`),
		StateHashAfter: "state:test:1",
		RNGRootSeed:    "rng:test:1",
		SeedDerivation: model.SeedDerivationInputs{
			TableID:    "tbl:test:1",
			HandNumber: 3,
			SeatNumber: 4,
			StreamName: "community",
		},
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "policy-v1",
			PayloadHash:         "payload:test:1",
			ArtifactRef:         "art:test:1",
		},
	}

	require.NoError(t, repo.AppendEvents(ctx, []model.EventLogEntry{entry}))
	require.NoError(t, repo.AppendEvents(ctx, []model.EventLogEntry{entry}))
	require.Equal(t, 1, rowCount(t, db, "arena_event_log"))
}

func TestAppendEventsRejectsConflictingDuplicateEventID(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	ctx := context.Background()
	first := model.EventLogEntry{
		EventID:        "evt:test:conflict",
		AggregateType:  "table",
		AggregateID:    "tbl:test:conflict",
		StreamKey:      "table:tbl:test:conflict",
		StreamSeq:      13,
		TournamentID:   "tour:test:conflict",
		TableID:        "tbl:test:conflict",
		HandID:         "hand:test:conflict",
		PhaseID:        "phase:test:conflict",
		RoundNo:        1,
		BarrierID:      "barrier:test:conflict",
		EventType:      "action_applied",
		EventVersion:   1,
		StateSeq:       21,
		CausationID:    "cause:test:conflict",
		CorrelationID:  "corr:test:conflict",
		Payload:        json.RawMessage(`{"kind":"action_applied","action":"check"}`),
		StateHashAfter: "state:test:conflict:1",
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "policy-v1",
			PayloadHash:         "payload:test:conflict:1",
		},
	}
	require.NoError(t, repo.AppendEvents(ctx, []model.EventLogEntry{first}))

	conflicting := first
	conflicting.Payload = json.RawMessage(`{"kind":"action_applied","action":"raise","amount":100}`)
	conflicting.PayloadHash = "payload:test:conflict:2"
	conflicting.StateHashAfter = "state:test:conflict:2"

	err = repo.AppendEvents(ctx, []model.EventLogEntry{conflicting})
	require.Error(t, err)
	require.ErrorContains(t, err, "append arena_event_log evt:test:conflict conflict")
	require.ErrorContains(t, err, "payload_hash mismatch")

	var payloadHash string
	require.NoError(t, db.QueryRowContext(ctx, "SELECT payload_hash FROM arena_event_log WHERE event_id = $1", first.EventID).Scan(&payloadHash))
	require.Equal(t, "payload:test:conflict:1", payloadHash)
	require.Equal(t, 1, rowCount(t, db, "arena_event_log"))
}

func TestRepositoryLoadsActionRecordByRequestID(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	ctx := context.Background()
	now := time.Date(2026, time.April, 10, 10, 0, 0, 0, time.UTC)

	require.NoError(t, repo.AppendActionRecords(ctx, []model.ActionRecord{{
		RequestID:        "req:action",
		TournamentID:     "tour:1",
		TableID:          "tbl:1",
		HandID:           "hand:1",
		PhaseID:          "phase:1",
		SeatID:           "seat:tbl:1:07",
		ActionType:       "check",
		ActionSeq:        1,
		ExpectedStateSeq: 7,
		AcceptedStateSeq: 8,
		ValidationStatus: "accepted",
		ResultEventID:    "event:1",
		ReceivedAt:       now,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "action-state",
			PayloadHash:         "action-payload",
		},
		Payload: json.RawMessage(`{"kind":"actor_action"}`),
	}}))

	action, err := repo.LoadActionRecord(ctx, "req:action")
	require.NoError(t, err)
	require.Equal(t, "event:1", action.ResultEventID)
	require.Equal(t, int64(8), action.AcceptedStateSeq)
	require.Equal(t, "check", action.ActionType)
}

func TestAppendActionRecordsAllowsIdempotentLogicalDuplicate(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	ctx := context.Background()
	receivedAt := time.Date(2026, time.April, 10, 10, 0, 0, 0, time.UTC)
	first := model.ActionRecord{
		RequestID:          "req:action:logical:1",
		TournamentID:       "tour:logical",
		TableID:            "tbl:logical",
		HandID:             "hand:logical",
		PhaseID:            "phase:logical",
		SeatID:             "seat:logical",
		SeatAlias:          "alias:logical",
		ActionType:         "raise",
		ActionAmountBucket: 200,
		ActionSeq:          5,
		ExpectedStateSeq:   9,
		AcceptedStateSeq:   10,
		ValidationStatus:   "accepted",
		ResultEventID:      "evt:logical",
		ReceivedAt:         receivedAt,
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "policy-v1",
			StateHash:           "state:logical",
			PayloadHash:         "payload:logical",
			ArtifactRef:         "art:logical",
		},
		Payload: json.RawMessage(`{"kind":"action_applied","action":"raise","amount":200}`),
	}
	require.NoError(t, repo.AppendActionRecords(ctx, []model.ActionRecord{first}))

	duplicate := first
	duplicate.RequestID = "req:action:logical:2"
	duplicate.ReceivedAt = receivedAt.Add(5 * time.Second)
	duplicate.ProcessedAt = ptrTime(receivedAt.Add(6 * time.Second))
	require.NoError(t, repo.AppendActionRecords(ctx, []model.ActionRecord{duplicate}))
	require.Equal(t, 1, rowCount(t, db, "arena_action"))
}

func TestAppendActionRecordsRejectsConflictingLogicalDuplicate(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	ctx := context.Background()
	first := model.ActionRecord{
		RequestID:          "req:action:conflict:1",
		TournamentID:       "tour:logical-conflict",
		TableID:            "tbl:logical-conflict",
		HandID:             "hand:logical-conflict",
		PhaseID:            "phase:logical-conflict",
		SeatID:             "seat:logical-conflict",
		SeatAlias:          "alias:logical-conflict",
		ActionType:         "call",
		ActionAmountBucket: 50,
		ActionSeq:          8,
		ExpectedStateSeq:   14,
		AcceptedStateSeq:   15,
		ValidationStatus:   "accepted",
		ResultEventID:      "evt:logical-conflict",
		ReceivedAt:         time.Date(2026, time.April, 10, 10, 5, 0, 0, time.UTC),
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "policy-v1",
			StateHash:           "state:logical-conflict:1",
			PayloadHash:         "payload:logical-conflict:1",
		},
		Payload: json.RawMessage(`{"kind":"action_applied","action":"call","amount":50}`),
	}
	require.NoError(t, repo.AppendActionRecords(ctx, []model.ActionRecord{first}))

	conflicting := first
	conflicting.RequestID = "req:action:conflict:2"
	conflicting.PayloadHash = "payload:logical-conflict:2"
	conflicting.StateHash = "state:logical-conflict:2"
	conflicting.Payload = json.RawMessage(`{"kind":"action_applied","action":"raise","amount":200}`)

	err = repo.AppendActionRecords(ctx, []model.ActionRecord{conflicting})
	require.Error(t, err)
	require.ErrorContains(t, err, "append arena_action req:action:conflict:2 conflict")
	require.True(
		t,
		strings.Contains(err.Error(), "state_hash mismatch") || strings.Contains(err.Error(), "payload_hash mismatch"),
		err.Error(),
	)

	var requestID string
	require.NoError(t, db.QueryRowContext(ctx, "SELECT request_id FROM arena_action WHERE hand_id = $1 AND seat_id = $2 AND phase_id = $3 AND action_seq = $4", first.HandID, first.SeatID, first.PhaseID, first.ActionSeq).Scan(&requestID))
	require.Equal(t, first.RequestID, requestID)
	require.Equal(t, 1, rowCount(t, db, "arena_action"))
}

func TestAppendRatingInputsUpdatesMeasurementFieldsOnConflict(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	ctx := context.Background()
	first := model.RatingInput{
		ID:               "ari:tour:measurement:miner-1",
		TournamentID:     "tour:measurement",
		EntrantID:        "entrant-1",
		MinerAddress:     "miner-1",
		Mode:             model.RatedMode,
		HumanOnly:        true,
		FinishRank:       1,
		FinishPercentile: 1,
		StageReached:     "completed",
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "rating-input-state-1",
			PayloadHash:         "rating-input-payload-1",
		},
	}
	require.NoError(t, repo.AppendRatingInputs(ctx, []model.RatingInput{first}))

	updated := first
	updated.HandsPlayed = 3
	updated.MeaningfulDecisions = 7
	updated.AutoActions = 1
	updated.TimeoutActions = 1
	updated.InvalidActions = 2
	updated.TruthMetadata = model.TruthMetadata{
		PolicyBundleVersion: "policy-v1",
		StateHash:           "rating-input-state-2",
		PayloadHash:         "rating-input-payload-2",
	}
	require.NoError(t, repo.AppendRatingInputs(ctx, []model.RatingInput{updated}))

	inputs, err := repo.ListRatingInputs(ctx, "tour:measurement")
	require.NoError(t, err)
	require.Len(t, inputs, 1)
	require.Equal(t, 3, inputs[0].HandsPlayed)
	require.Equal(t, 7, inputs[0].MeaningfulDecisions)
	require.Equal(t, 1, inputs[0].AutoActions)
	require.Equal(t, 1, inputs[0].TimeoutActions)
	require.Equal(t, 2, inputs[0].InvalidActions)
}

func TestListActionMeasurementSummariesAggregatesManualTimeoutAndInvalidActions(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	ctx := context.Background()
	now := time.Date(2026, time.April, 10, 10, 0, 0, 0, time.UTC)
	waveID := "wave:measurement-summary"
	tournamentID := "tour:measurement-summary"
	tableID := "tbl:measurement-summary:01"
	timeoutSeatID := "seat:measurement-summary:01"
	payload := json.RawMessage(`{"source":"measurement_summary_test"}`)

	require.NoError(t, repo.UpsertWave(ctx, model.Wave{
		ID:                  waveID,
		Mode:                model.RatedMode,
		State:               model.WaveStateInProgress,
		RegistrationOpenAt:  now,
		RegistrationCloseAt: now,
		ScheduledStartAt:    now,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "wave-measurement-state",
			PayloadHash:         "wave-measurement-payload",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertTournament(ctx, model.Tournament{
		ID:     tournamentID,
		WaveID: waveID,
		Mode:   model.RatedMode,
		State:  model.TournamentStateLiveMultiTable,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "tournament-measurement-state",
			PayloadHash:         "tournament-measurement-payload",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertTable(ctx, model.Table{
		ID:           tableID,
		TournamentID: tournamentID,
		State:        model.TableStateHandLive,
		TableNo:      1,
		RoundNo:      1,
		StateSeq:     1,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "table-measurement-state",
			PayloadHash:         "table-measurement-payload",
		},
		Payload: payload,
	}))
	require.NoError(t, repo.UpsertSeat(ctx, model.Seat{
		ID:           timeoutSeatID,
		TableID:      tableID,
		TournamentID: tournamentID,
		SeatNo:       1,
		MinerID:      "miner-timeout",
		State:        model.SeatStateActive,
		Stack:        1000,
		TruthMetadata: model.TruthMetadata{
			PolicyBundleVersion: "policy-v1",
			StateHash:           "seat-measurement-state",
			PayloadHash:         "seat-measurement-payload",
		},
		Payload: payload,
	}))

	require.NoError(t, repo.AppendSubmissionLedgerEntries(ctx, []model.SubmissionLedger{
		{
			RequestID:        "req:manual:1",
			TournamentID:     tournamentID,
			TableID:          tableID,
			HandID:           "hand:manual:1",
			PhaseID:          "phase:manual:1",
			SeatID:           "seat:manual:01",
			MinerID:          "miner-manual",
			ExpectedStateSeq: 1,
			ValidationStatus: "applied",
			TruthMetadata: model.TruthMetadata{
				PolicyBundleVersion: "policy-v1",
				StateHash:           "ledger-manual-1-state",
				PayloadHash:         "ledger-manual-1-payload",
			},
			Payload: payload,
		},
		{
			RequestID:        "req:manual:2",
			TournamentID:     tournamentID,
			TableID:          tableID,
			HandID:           "hand:manual:1",
			PhaseID:          "phase:manual:1",
			SeatID:           "seat:manual:01",
			MinerID:          "miner-manual",
			ExpectedStateSeq: 2,
			ValidationStatus: "applied",
			TruthMetadata: model.TruthMetadata{
				PolicyBundleVersion: "policy-v1",
				StateHash:           "ledger-manual-2-state",
				PayloadHash:         "ledger-manual-2-payload",
			},
			Payload: payload,
		},
		{
			RequestID:        "req:invalid:1",
			TournamentID:     tournamentID,
			TableID:          tableID,
			HandID:           "hand:invalid:1",
			PhaseID:          "phase:invalid:1",
			SeatID:           "seat:invalid:01",
			MinerID:          "miner-invalid",
			ExpectedStateSeq: 99,
			ValidationStatus: "received",
			TruthMetadata: model.TruthMetadata{
				PolicyBundleVersion: "policy-v1",
				StateHash:           "ledger-invalid-state",
				PayloadHash:         "ledger-invalid-payload",
			},
			Payload: payload,
		},
	}))
	require.NoError(t, repo.AppendActionRecords(ctx, []model.ActionRecord{
		{
			RequestID:        "req:manual:1",
			TournamentID:     tournamentID,
			TableID:          tableID,
			HandID:           "hand:manual:1",
			PhaseID:          "phase:manual:1",
			SeatID:           "seat:manual:01",
			ActionType:       "check",
			ActionSeq:        1,
			ExpectedStateSeq: 1,
			AcceptedStateSeq: 2,
			ValidationStatus: "accepted",
			ResultEventID:    "event:manual:1",
			ReceivedAt:       now,
			TruthMetadata: model.TruthMetadata{
				PolicyBundleVersion: "policy-v1",
				StateHash:           "action-manual-1-state",
				PayloadHash:         "action-manual-1-payload",
			},
			Payload: payload,
		},
		{
			RequestID:        "req:manual:2",
			TournamentID:     tournamentID,
			TableID:          tableID,
			HandID:           "hand:manual:1",
			PhaseID:          "phase:manual:1",
			SeatID:           "seat:manual:01",
			ActionType:       "raise",
			ActionSeq:        2,
			ExpectedStateSeq: 2,
			AcceptedStateSeq: 3,
			ValidationStatus: "accepted",
			ResultEventID:    "event:manual:2",
			ReceivedAt:       now,
			TruthMetadata: model.TruthMetadata{
				PolicyBundleVersion: "policy-v1",
				StateHash:           "action-manual-2-state",
				PayloadHash:         "action-manual-2-payload",
			},
			Payload: payload,
		},
		{
			RequestID:        "req:timeout:1",
			TournamentID:     tournamentID,
			TableID:          tableID,
			HandID:           "hand:timeout:1",
			PhaseID:          "phase:timeout:1",
			SeatID:           timeoutSeatID,
			ActionType:       "timeout",
			ActionSeq:        1,
			ExpectedStateSeq: 3,
			AcceptedStateSeq: 4,
			ValidationStatus: "accepted",
			ResultEventID:    "event:timeout:1",
			ReceivedAt:       now,
			TruthMetadata: model.TruthMetadata{
				PolicyBundleVersion: "policy-v1",
				StateHash:           "action-timeout-state",
				PayloadHash:         "action-timeout-payload",
			},
			Payload: payload,
		},
	}))

	summaries, err := repo.ListActionMeasurementSummaries(ctx, tournamentID)
	require.NoError(t, err)
	byMiner := make(map[string]model.ActionMeasurementSummary, len(summaries))
	for _, summary := range summaries {
		byMiner[summary.MinerID] = summary
	}
	require.Equal(t, model.ActionMeasurementSummary{
		MinerID:             "miner-manual",
		HandsPlayed:         1,
		MeaningfulDecisions: 2,
	}, byMiner["miner-manual"])
	require.Equal(t, model.ActionMeasurementSummary{
		MinerID:        "miner-timeout",
		HandsPlayed:    1,
		AutoActions:    1,
		TimeoutActions: 1,
	}, byMiner["miner-timeout"])
	require.Equal(t, model.ActionMeasurementSummary{
		MinerID:        "miner-invalid",
		InvalidActions: 1,
	}, byMiner["miner-invalid"])
}

func TestUpsertMinerCompatibilityOnlyTouchesArenaOwnedColumns(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	ctx := context.Background()
	address := "miner-compat"
	createdAt := time.Date(2026, time.April, 10, 9, 0, 0, 0, time.UTC)
	updatedAt := createdAt.Add(2 * time.Hour)
	seedMinerRow(t, db, seededMinerRow{
		Address:               address,
		Name:                  "compat-miner",
		RegistrationIndex:     17,
		Status:                "probation",
		PublicKey:             "pubkey-compat",
		EconomicUnitID:        "eu:compat",
		IPAddress:             "127.0.0.1",
		UserAgentHash:         "ua-hash",
		TotalRewards:          321,
		ForecastCommits:       7,
		ForecastReveals:       6,
		SettledTasks:          5,
		CorrectDirectionCount: 4,
		EdgeScoreTotal:        0.42,
		HeldRewards:           111,
		FastTaskOpportunities: 13,
		FastTaskMisses:        2,
		FastWindowStartAt:     ptrTime(createdAt.Add(-time.Hour)),
		AdmissionState:        "open",
		ModelReliability:      0.98,
		OpsReliability:        0.91,
		ArenaMultiplier:       1.02,
		PublicRank:            nil,
		PublicELO:             1210,
		CreatedAt:             createdAt,
		UpdatedAt:             createdAt,
	})

	publicRank := 3
	require.NoError(t, repo.UpsertMinerCompatibility(ctx, model.MinerCompatibility{
		Address:          address,
		ModelReliability: 1.07,
		ArenaMultiplier:  1.18,
		PublicRank:       &publicRank,
		PublicELO:        1444,
		UpdatedAt:        updatedAt,
	}))

	var (
		name                  string
		registrationIndex     int
		status                string
		publicKey             string
		economicUnitID        string
		ipAddress             sql.NullString
		userAgentHash         sql.NullString
		totalRewards          int64
		forecastCommits       int
		forecastReveals       int
		settledTasks          int
		correctDirectionCount int
		edgeScoreTotal        float64
		heldRewards           int64
		fastTaskOpportunities int
		fastTaskMisses        int
		fastWindowStartAt     sql.NullTime
		admissionState        string
		modelReliability      float64
		opsReliability        float64
		arenaMultiplier       float64
		storedPublicRank      sql.NullInt64
		publicELO             int
		storedCreatedAt       time.Time
		storedUpdatedAt       time.Time
	)
	require.NoError(t, db.QueryRowContext(ctx, `
		SELECT
			name,
			registration_index,
			status,
			public_key,
			economic_unit_id,
			ip_address,
			user_agent_hash,
			total_rewards,
			forecast_commits,
			forecast_reveals,
			settled_tasks,
			correct_direction_count,
			edge_score_total,
			held_rewards,
			fast_task_opportunities,
			fast_task_misses,
			fast_window_start_at,
			admission_state,
			model_reliability,
			ops_reliability,
			arena_multiplier,
			public_rank,
			public_elo,
			created_at,
			updated_at
		FROM miners
		WHERE address = $1
	`, address).Scan(
		&name,
		&registrationIndex,
		&status,
		&publicKey,
		&economicUnitID,
		&ipAddress,
		&userAgentHash,
		&totalRewards,
		&forecastCommits,
		&forecastReveals,
		&settledTasks,
		&correctDirectionCount,
		&edgeScoreTotal,
		&heldRewards,
		&fastTaskOpportunities,
		&fastTaskMisses,
		&fastWindowStartAt,
		&admissionState,
		&modelReliability,
		&opsReliability,
		&arenaMultiplier,
		&storedPublicRank,
		&publicELO,
		&storedCreatedAt,
		&storedUpdatedAt,
	))

	require.Equal(t, "compat-miner", name)
	require.Equal(t, 17, registrationIndex)
	require.Equal(t, "probation", status)
	require.Equal(t, "pubkey-compat", publicKey)
	require.Equal(t, "eu:compat", economicUnitID)
	require.Equal(t, "127.0.0.1", ipAddress.String)
	require.Equal(t, "ua-hash", userAgentHash.String)
	require.EqualValues(t, 321, totalRewards)
	require.Equal(t, 7, forecastCommits)
	require.Equal(t, 6, forecastReveals)
	require.Equal(t, 5, settledTasks)
	require.Equal(t, 4, correctDirectionCount)
	require.Equal(t, 0.42, edgeScoreTotal)
	require.EqualValues(t, 111, heldRewards)
	require.Equal(t, 13, fastTaskOpportunities)
	require.Equal(t, 2, fastTaskMisses)
	require.True(t, fastWindowStartAt.Valid)
	require.Equal(t, createdAt.Add(-time.Hour), fastWindowStartAt.Time.UTC())
	require.Equal(t, "open", admissionState)
	require.Equal(t, 0.98, modelReliability)
	require.Equal(t, 0.91, opsReliability)
	require.Equal(t, 1.18, arenaMultiplier)
	require.False(t, storedPublicRank.Valid)
	require.Equal(t, 1210, publicELO)
	require.Equal(t, createdAt, storedCreatedAt.UTC())
	require.Equal(t, updatedAt, storedUpdatedAt.UTC())
}

func TestUpsertMinerCompatibilityRequiresExistingMiner(t *testing.T) {
	db := openTestDB(t)
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	ctx := context.Background()
	publicRank := 4
	err = repo.UpsertMinerCompatibility(ctx, model.MinerCompatibility{
		Address:          "missing-miner",
		ModelReliability: 1.04,
		ArenaMultiplier:  1.09,
		PublicRank:       &publicRank,
		PublicELO:        1380,
		UpdatedAt:        time.Date(2026, time.April, 10, 11, 0, 0, 0, time.UTC),
	})
	require.Error(t, err)
	require.ErrorContains(t, err, "miner not found")
	require.Equal(t, 0, rowCount(t, db, "miners"))
}

func TestAssertSharedHarnessTablesRespectsCurrentSearchPath(t *testing.T) {
	db := testutil.OpenArenaTestDB(t, "arena_store_search_path_test")
	t.Cleanup(func() {
		require.NoError(t, db.Close())
	})
	testutil.ResetArenaSchema(t, db, "arena_store_search_path_test")
	require.NoError(t, postgres.Migrate(db))

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)
	require.NoError(t, repo.AssertSharedHarnessTables(context.Background()))
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

type seededMinerRow struct {
	Address               string
	Name                  string
	RegistrationIndex     int
	Status                string
	PublicKey             string
	EconomicUnitID        string
	IPAddress             string
	UserAgentHash         string
	TotalRewards          int64
	ForecastCommits       int
	ForecastReveals       int
	SettledTasks          int
	CorrectDirectionCount int
	EdgeScoreTotal        float64
	HeldRewards           int64
	FastTaskOpportunities int
	FastTaskMisses        int
	FastWindowStartAt     *time.Time
	AdmissionState        string
	ModelReliability      float64
	OpsReliability        float64
	ArenaMultiplier       float64
	PublicRank            *int
	PublicELO             int
	CreatedAt             time.Time
	UpdatedAt             time.Time
}

func seedMinerRow(t *testing.T, db *sql.DB, miner seededMinerRow) {
	t.Helper()

	_, err := db.Exec(`
		INSERT INTO miners (
			address,
			name,
			registration_index,
			status,
			public_key,
			economic_unit_id,
			ip_address,
			user_agent_hash,
			total_rewards,
			forecast_commits,
			forecast_reveals,
			settled_tasks,
			correct_direction_count,
			edge_score_total,
			held_rewards,
			fast_task_opportunities,
			fast_task_misses,
			fast_window_start_at,
			admission_state,
			model_reliability,
			ops_reliability,
			arena_multiplier,
			public_rank,
			public_elo,
			created_at,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
			$14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26
		)
	`,
		miner.Address,
		miner.Name,
		miner.RegistrationIndex,
		miner.Status,
		miner.PublicKey,
		miner.EconomicUnitID,
		nullIfEmpty(miner.IPAddress),
		nullIfEmpty(miner.UserAgentHash),
		miner.TotalRewards,
		miner.ForecastCommits,
		miner.ForecastReveals,
		miner.SettledTasks,
		miner.CorrectDirectionCount,
		miner.EdgeScoreTotal,
		miner.HeldRewards,
		miner.FastTaskOpportunities,
		miner.FastTaskMisses,
		miner.FastWindowStartAt,
		miner.AdmissionState,
		miner.ModelReliability,
		miner.OpsReliability,
		miner.ArenaMultiplier,
		miner.PublicRank,
		miner.PublicELO,
		miner.CreatedAt,
		miner.UpdatedAt,
	)
	require.NoError(t, err)
}

func nullIfEmpty(value string) any {
	if value == "" {
		return nil
	}
	return value
}

package gateway

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/table"
	"github.com/clawchain/clawchain/arena/testutil"
)

func TestDuplicateRequestIDReturnsOriginalResponse(t *testing.T) {
	g := newGatewayForTest(t)

	first, err := g.Submit(context.Background(), SubmitRequest{
		RequestID:        "req-1",
		TournamentID:     "tour_1",
		TableID:          "tbl:tour_1:01",
		MinerID:          "miner_1",
		SeatNo:           7,
		ActionType:       string(table.ActionCheck),
		ExpectedStateSeq: 7,
		Signature:        "sig:miner_1",
	})
	require.NoError(t, err)

	second, err := g.Submit(context.Background(), SubmitRequest{
		RequestID:        "req-1",
		TournamentID:     "tour_1",
		TableID:          "tbl:tour_1:01",
		MinerID:          "miner_1",
		SeatNo:           7,
		ActionType:       string(table.ActionCheck),
		ExpectedStateSeq: 7,
		Signature:        "sig:miner_1",
	})
	require.NoError(t, err)
	require.Equal(t, first.ResultEventID, second.ResultEventID)
}

func TestStateSeqMismatchReturnsConflictError(t *testing.T) {
	g := newGatewayForTest(t)

	_, err := g.Submit(context.Background(), SubmitRequest{
		RequestID:        "req-stale",
		TournamentID:     "tour_1",
		TableID:          "tbl:tour_1:01",
		MinerID:          "miner_1",
		SeatNo:           7,
		ActionType:       string(table.ActionCheck),
		ExpectedStateSeq: 999,
		Signature:        "sig:miner_1",
	})
	require.ErrorIs(t, err, ErrStateSeqMismatch)
}

func TestInvalidSignatureReturnsUnauthorizedError(t *testing.T) {
	g := newGatewayForTest(t)

	_, err := g.Submit(context.Background(), SubmitRequest{
		RequestID:        "req-bad-sig",
		TournamentID:     "tour_1",
		TableID:          "tbl:tour_1:01",
		MinerID:          "miner_1",
		SeatNo:           7,
		ActionType:       string(table.ActionCheck),
		ExpectedStateSeq: 7,
		Signature:        "bad-signature",
	})
	require.ErrorIs(t, err, ErrInvalidSignature)
}

func TestDuplicateRequestIDDifferentPayloadReturnsConflict(t *testing.T) {
	g := newGatewayForTest(t)

	req := testSubmitRequest()
	_, err := g.Submit(context.Background(), req)
	require.NoError(t, err)

	req.ActionType = string(table.ActionRaise)
	req.Amount = 100

	_, err = g.Submit(context.Background(), req)
	require.Error(t, err)
	require.ErrorContains(t, err, "request_id payload conflict")
}

func TestRetryReturnsDurableResponseAfterObserverFailure(t *testing.T) {
	store := newDurableGatewayStore()
	clock := testutil.NewFakeClock(time.Date(2026, time.April, 10, 14, 0, 0, 0, time.UTC))
	actor := table.NewActor(table.ActorState{
		TableID:      "tbl:tour_1:01",
		TournamentID: "tour_1",
		HandID:       "hand:tour_1:01:0001",
		PhaseID:      "phase-wager-1",
		StateSeq:     7,
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

	req := testSubmitRequest()
	firstGateway := New(Config{
		Actors: map[string]Actor{
			req.TableID: actor,
		},
		Ledger:   store,
		Observer: observerFunc(func(context.Context, SubmitRequest, table.ActorState) error { return errors.New("observer down") }),
	})

	_, err := firstGateway.Submit(context.Background(), req)
	require.Error(t, err)
	require.ErrorContains(t, err, "observer down")

	ledgerEntry, err := store.LoadSubmissionLedgerEntry(context.Background(), req.RequestID)
	require.NoError(t, err)
	require.Equal(t, req.TableID, ledgerEntry.TableID)

	action, err := store.LoadActionRecord(context.Background(), req.RequestID)
	require.NoError(t, err)
	require.NotEmpty(t, action.ResultEventID)

	recoveredGateway := New(Config{Ledger: store})
	response, err := recoveredGateway.Submit(context.Background(), req)
	require.NoError(t, err)
	require.Equal(t, action.ResultEventID, response.ResultEventID)
	require.Equal(t, action.AcceptedStateSeq, response.StateSeq)
}

func testSubmitRequest() SubmitRequest {
	return SubmitRequest{
		RequestID:        "req-1",
		TournamentID:     "tour_1",
		TableID:          "tbl:tour_1:01",
		MinerID:          "miner_1",
		SeatNo:           7,
		ActionType:       string(table.ActionCheck),
		ExpectedStateSeq: 7,
		Signature:        "sig:miner_1",
	}
}

func newGatewayForTest(t *testing.T) *Gateway {
	t.Helper()

	clock := testutil.NewFakeClock(time.Date(2026, time.April, 10, 14, 0, 0, 0, time.UTC))
	store := testutil.NewArenaStore()
	actor := table.NewActor(table.ActorState{
		TableID:      "tbl:tour_1:01",
		TournamentID: "tour_1",
		HandID:       "hand:tour_1:01:0001",
		PhaseID:      "phase-wager-1",
		StateSeq:     7,
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

	return New(Config{
		Actors: map[string]Actor{
			"tbl:tour_1:01": actor,
		},
	})
}

type observerFunc func(ctx context.Context, req SubmitRequest, state table.ActorState) error

func (f observerFunc) OnSubmitCommitted(ctx context.Context, req SubmitRequest, state table.ActorState) error {
	return f(ctx, req, state)
}

type durableGatewayStore struct {
	mu          sync.Mutex
	submissions map[string]model.SubmissionLedger
	actions     map[string]model.ActionRecord
}

func newDurableGatewayStore() *durableGatewayStore {
	return &durableGatewayStore{
		submissions: make(map[string]model.SubmissionLedger),
		actions:     make(map[string]model.ActionRecord),
	}
}

func (s *durableGatewayStore) AppendSubmissionLedgerEntries(_ context.Context, entries []model.SubmissionLedger) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	for _, entry := range entries {
		if existing, ok := s.submissions[entry.RequestID]; ok && existing.PayloadHash != entry.PayloadHash {
			return fmt.Errorf("request_id payload conflict: %s", entry.RequestID)
		}
		s.submissions[entry.RequestID] = entry
	}

	return nil
}

func (s *durableGatewayStore) LoadSubmissionLedgerEntry(_ context.Context, requestID string) (model.SubmissionLedger, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	entry, ok := s.submissions[requestID]
	if !ok {
		return model.SubmissionLedger{}, sql.ErrNoRows
	}
	return entry, nil
}

func (s *durableGatewayStore) LoadActionRecord(_ context.Context, requestID string) (model.ActionRecord, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	action, ok := s.actions[requestID]
	if !ok {
		return model.ActionRecord{}, sql.ErrNoRows
	}
	return action, nil
}

func (s *durableGatewayStore) AppendEvents(_ context.Context, _ []model.EventLogEntry) error {
	return nil
}

func (s *durableGatewayStore) AppendActionRecords(_ context.Context, actions []model.ActionRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	for _, action := range actions {
		s.actions[action.RequestID] = action
	}

	return nil
}

func (s *durableGatewayStore) SaveTableSnapshot(_ context.Context, _ model.TableSnapshot) error {
	return nil
}

func (s *durableGatewayStore) SaveHandSnapshot(_ context.Context, _ model.HandSnapshot) error {
	return nil
}

func (s *durableGatewayStore) UpsertActionDeadline(_ context.Context, _ model.ActionDeadline) error {
	return nil
}

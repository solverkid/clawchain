package gateway

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

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

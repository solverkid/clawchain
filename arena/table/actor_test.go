package table

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/testutil"
)

func TestDuplicateRequestReturnsOriginalResult(t *testing.T) {
	actor := newActorForTest(t)

	first, err := actor.Handle(context.Background(), CommandEnvelope{
		RequestID:        "req-1",
		ExpectedStateSeq: 1,
		Command: SubmitArenaAction{
			SeatNo:     7,
			ActionType: ActionCheck,
		},
	})
	require.NoError(t, err)

	second, err := actor.Handle(context.Background(), CommandEnvelope{
		RequestID:        "req-1",
		ExpectedStateSeq: 1,
		Command: SubmitArenaAction{
			SeatNo:     7,
			ActionType: ActionCheck,
		},
	})
	require.NoError(t, err)
	require.Equal(t, first.ResultEventID, second.ResultEventID)
	require.Equal(t, first.StateSeq, second.StateSeq)
}

func TestRejectedActionDoesNotAdvanceStateSeq(t *testing.T) {
	actor := newActorForTest(t)
	before := actor.State().StateSeq

	_, err := actor.Handle(context.Background(), CommandEnvelope{
		RequestID:        "req-illegal",
		ExpectedStateSeq: before,
		Command: SubmitArenaAction{
			SeatNo:     7,
			ActionType: ActionRaise,
			Amount:     999999,
		},
	})
	require.Error(t, err)
	require.Equal(t, before, actor.State().StateSeq)
}

func TestManualActionAndTimeoutRaceOnlyCommitsOneWinner(t *testing.T) {
	actor := newActorForTest(t)

	var wg sync.WaitGroup
	results := make(chan error, 2)

	run := func(envelope CommandEnvelope) {
		defer wg.Done()
		_, err := actor.Handle(context.Background(), envelope)
		results <- err
	}

	wg.Add(2)
	go run(CommandEnvelope{
		RequestID:        "req-manual",
		ExpectedStateSeq: 1,
		Command: SubmitArenaAction{
			SeatNo:     7,
			ActionType: ActionCheck,
		},
	})
	go run(CommandEnvelope{
		RequestID:        "req-timeout",
		ExpectedStateSeq: 1,
		Command:          ApplyPhaseTimeout{SeatNo: 7},
	})
	wg.Wait()
	close(results)

	var committed int
	for err := range results {
		if err == nil {
			committed++
		}
	}

	require.Equal(t, 1, committed)
	require.Equal(t, int64(2), actor.State().StateSeq)
}

func TestPhaseOpenPersistsDeadlineAndSnapshotAtomically(t *testing.T) {
	actor, repo := newActorWithRepoForTest(t)

	require.NoError(t, actor.OpenPhase(context.Background(), fixtureSignalPhase()))
	require.True(t, repo.HasOpenDeadline("phase-signal-1"))
	require.True(t, repo.HasTableSnapshot("tbl:tour_1:01"))
}

func newActorForTest(t *testing.T) *Actor {
	t.Helper()

	actor, _ := newActorWithRepoForTest(t)
	return actor
}

func newActorWithRepoForTest(t *testing.T) (*Actor, *testutil.ArenaStore) {
	t.Helper()

	clock := testutil.NewFakeClock(time.Date(2026, time.April, 10, 13, 0, 0, 0, time.UTC))
	repo := testutil.NewArenaStore()

	return NewActor(ActorState{
		TableID:      "tbl:tour_1:01",
		TournamentID: "tour_1",
		HandID:       "hand:tour_1:01:0001",
		PhaseID:      "phase-wager-1",
		StateSeq:     1,
		Table: State{
			CurrentPhase:  PhaseWager,
			ActingSeatNo:  7,
			CurrentToCall: 0,
			MinRaiseSize:  50,
			Seats: map[int]Seat{
				7: {SeatNo: 7, State: SeatStateActive, Stack: 500},
				8: {SeatNo: 8, State: SeatStateActive, Stack: 500},
			},
		},
	}, clock, repo), repo
}

func fixtureSignalPhase() PhaseDefinition {
	return PhaseDefinition{
		ID:         "phase-signal-1",
		HandID:     "hand:tour_1:01:0001",
		Type:       PhaseSignal,
		ActingSeat: 7,
		DeadlineAt: ptrTime(time.Date(2026, time.April, 10, 13, 0, 4, 0, time.UTC)),
	}
}

func ptrTime(value time.Time) *time.Time {
	return &value
}

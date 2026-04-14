package table

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/model"
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

func TestHandlePersistsTableSnapshotAtLatestStreamSeq(t *testing.T) {
	clock := testutil.NewFakeClock(time.Date(2026, time.April, 10, 13, 0, 0, 0, time.UTC))
	store := &recordingActorStore{}
	actor := NewRecoveredActor(ActorState{
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
	}, 291, clock, store)

	_, err := actor.Handle(context.Background(), CommandEnvelope{
		RequestID:        "req-latest-stream-seq",
		ExpectedStateSeq: 1,
		Command: SubmitArenaAction{
			SeatNo:     7,
			ActionType: ActionCheck,
		},
	})
	require.NoError(t, err)
	require.Len(t, store.events, 1)
	require.Len(t, store.tableSnapshots, 1)
	require.Equal(t, int64(292), store.events[0].StreamSeq)
	require.Equal(t, store.events[0].StreamSeq, store.tableSnapshots[0].StreamSeq)
}

func TestHandlePersistsHandSnapshotWhenActionAutoClosesHand(t *testing.T) {
	clock := testutil.NewFakeClock(time.Date(2026, time.April, 10, 13, 0, 0, 0, time.UTC))
	store := &recordingActorStore{}
	actor := NewRecoveredActor(ActorState{
		TableID:      "tbl:tour_1:01",
		TournamentID: "tour_1",
		HandID:       "hand:tour_1:01:0001",
		PhaseID:      "phase-wager-1",
		StateSeq:     1,
		Table: State{
			CurrentPhase:     PhaseWager,
			PhaseStartSeatNo: 7,
			ActingSeatNo:     7,
			CurrentToCall:    0,
			MinRaiseSize:     50,
			Seats: map[int]Seat{
				7: {SeatNo: 7, State: SeatStateActive, Stack: 500},
				8: {SeatNo: 8, State: SeatStateActive, Stack: 500, Folded: true},
			},
		},
	}, 291, clock, store)

	_, err := actor.Handle(context.Background(), CommandEnvelope{
		RequestID:        "req-hand-snapshot-action",
		ExpectedStateSeq: 1,
		Command: SubmitArenaAction{
			SeatNo:     7,
			ActionType: ActionCheck,
		},
	})
	require.NoError(t, err)
	require.Len(t, store.handSnapshots, 1)
	require.True(t, actor.State().Table.HandClosed)
}

func TestHandlePersistsHandSnapshotWhenTimeoutAutoClosesHand(t *testing.T) {
	clock := testutil.NewFakeClock(time.Date(2026, time.April, 10, 13, 0, 0, 0, time.UTC))
	store := &recordingActorStore{}
	actor := NewRecoveredActor(ActorState{
		TableID:      "tbl:tour_1:01",
		TournamentID: "tour_1",
		HandID:       "hand:tour_1:01:0001",
		PhaseID:      "phase-wager-1",
		StateSeq:     1,
		Table: State{
			CurrentPhase:     PhaseWager,
			PhaseStartSeatNo: 7,
			ActingSeatNo:     7,
			CurrentToCall:    100,
			MinRaiseSize:     100,
			Seats: map[int]Seat{
				7: {SeatNo: 7, State: SeatStateActive, Stack: 500},
				8: {SeatNo: 8, State: SeatStateActive, Stack: 500, Folded: true, CommittedThisHand: 100},
			},
		},
	}, 291, clock, store)

	_, err := actor.Handle(context.Background(), CommandEnvelope{
		RequestID:        "req-hand-snapshot-timeout",
		ExpectedStateSeq: 1,
		Command:          ApplyPhaseTimeout{SeatNo: 7},
	})
	require.NoError(t, err)
	require.Len(t, store.handSnapshots, 1)
	require.True(t, actor.State().Table.HandClosed)
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

type recordingActorStore struct {
	events         []model.EventLogEntry
	actionRecords  []model.ActionRecord
	deadlines      []model.ActionDeadline
	tableSnapshots []model.TableSnapshot
	handSnapshots  []model.HandSnapshot
}

func (s *recordingActorStore) AppendEvents(_ context.Context, events []model.EventLogEntry) error {
	s.events = append(s.events, events...)
	return nil
}

func (s *recordingActorStore) AppendActionRecords(_ context.Context, actions []model.ActionRecord) error {
	s.actionRecords = append(s.actionRecords, actions...)
	return nil
}

func (s *recordingActorStore) SaveTableSnapshot(_ context.Context, snapshot model.TableSnapshot) error {
	s.tableSnapshots = append(s.tableSnapshots, snapshot)
	return nil
}

func (s *recordingActorStore) SaveHandSnapshot(_ context.Context, snapshot model.HandSnapshot) error {
	s.handSnapshots = append(s.handSnapshots, snapshot)
	return nil
}

func (s *recordingActorStore) UpsertActionDeadline(_ context.Context, deadline model.ActionDeadline) error {
	s.deadlines = append(s.deadlines, deadline)
	return nil
}

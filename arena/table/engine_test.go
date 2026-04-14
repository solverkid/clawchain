package table

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestTimeoutPolicyMapsByPhase(t *testing.T) {
	testCases := []struct {
		name       string
		state      State
		wantAction ActionType
	}{
		{
			name:       "signal timeout becomes signal none",
			state:      givenTableState(PhaseSignal, 0),
			wantAction: ActionSignalNone,
		},
		{
			name:       "probe timeout becomes pass probe",
			state:      givenTableState(PhaseProbe, 0),
			wantAction: ActionPassProbe,
		},
		{
			name:       "wager timeout facing action becomes auto fold",
			state:      givenTableState(PhaseWager, 200),
			wantAction: ActionAutoFold,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			next, events, err := Apply(tc.state, ApplyPhaseTimeout{SeatNo: 3})
			require.NoError(t, err)
			require.NotEmpty(t, events)
			require.Equal(t, tc.wantAction, events[len(events)-1].AutoAction)
			require.Equal(t, 4, next.ActingSeatNo)
		})
	}
}

func TestEliminationResolvedOnlyAtHandClose(t *testing.T) {
	state := givenBustedButOpenHand()

	require.Equal(t, SeatStateActive, state.Seats[5].State)

	next, _, err := Apply(state, CloseHand{})
	require.NoError(t, err)
	require.Equal(t, SeatStateEliminated, next.Seats[5].State)
}

func TestNoAllInNoSidePotInvariant(t *testing.T) {
	state := givenShortStackState()

	_, _, err := Apply(state, SubmitArenaAction{
		SeatNo:     4,
		ActionType: ActionRaise,
		Amount:     999999,
	})
	require.ErrorContains(t, err, "illegal action")
}

func TestStartHandPostsForcedBlinds(t *testing.T) {
	state := State{
		Seats: map[int]Seat{
			1: {SeatNo: 1, State: SeatStateActive, Stack: 1000},
			2: {SeatNo: 2, State: SeatStateActive, Stack: 1000},
			3: {SeatNo: 3, State: SeatStateActive, Stack: 1000},
			4: {SeatNo: 4, State: SeatStateActive, Stack: 1000},
		},
	}

	next, _, err := Apply(state, StartHand{
		SmallBlind: 25,
		BigBlind:   50,
		MinRaiseTo: 100,
	})
	require.NoError(t, err)
	require.Equal(t, 1, next.HandNumber)
	require.Equal(t, int64(75), next.PotMain)
	require.Equal(t, int64(50), next.CurrentToCall)
	require.Equal(t, int64(100), next.MinRaiseSize)
	require.Equal(t, int64(975), next.Seats[1].Stack)
	require.Equal(t, int64(25), next.Seats[1].CommittedThisHand)
	require.Equal(t, int64(950), next.Seats[2].Stack)
	require.Equal(t, int64(50), next.Seats[2].CommittedThisHand)
	require.Equal(t, int64(1000), next.Seats[3].Stack)
	require.Equal(t, int64(1000), next.Seats[4].Stack)
	require.Equal(t, 3, next.ActingSeatNo)
}

func TestSitOutSeatStillPostsAnteAndBlindOnStartHand(t *testing.T) {
	state := State{
		Seats: map[int]Seat{
			1: {SeatNo: 1, State: SeatStateSitOut, Stack: 1000, TimeoutStreak: 2},
			2: {SeatNo: 2, State: SeatStateActive, Stack: 1000},
			3: {SeatNo: 3, State: SeatStateActive, Stack: 1000},
		},
	}

	next, _, err := Apply(state, StartHand{
		SmallBlind: 25,
		BigBlind:   50,
		Ante:       10,
		MinRaiseTo: 100,
	})
	require.NoError(t, err)
	require.Equal(t, int64(105), next.PotMain)
	require.Equal(t, int64(965), next.Seats[1].Stack)
	require.Equal(t, int64(35), next.Seats[1].CommittedThisHand)
	require.Equal(t, int64(940), next.Seats[2].Stack)
	require.Equal(t, int64(60), next.Seats[2].CommittedThisHand)
	require.Equal(t, int64(990), next.Seats[3].Stack)
	require.Equal(t, int64(10), next.Seats[3].CommittedThisHand)
}

func TestManualActionReactivatesSitOutSeatAtHandClose(t *testing.T) {
	state := State{
		HandNumber:       3,
		CurrentPhase:     PhaseWager,
		PhaseStartSeatNo: 1,
		ActingSeatNo:     1,
		CurrentToCall:    0,
		MinRaiseSize:     50,
		Seats: map[int]Seat{
			1: {SeatNo: 1, State: SeatStateSitOut, Stack: 500, TimeoutStreak: 2},
			2: {SeatNo: 2, State: SeatStateActive, Stack: 500, Folded: true},
		},
	}

	next, events, err := Apply(state, SubmitArenaAction{
		SeatNo:     1,
		ActionType: ActionCheck,
	})
	require.NoError(t, err)
	require.Equal(t, EventHandClosed, events[len(events)-1].Type)
	require.Equal(t, SeatStateActive, next.Seats[1].State)
	require.Equal(t, 0, next.Seats[1].TimeoutStreak)
}

func TestPhaseProgressionMovesSignalProbeWagerAndClosesHand(t *testing.T) {
	state := State{
		CurrentPhase:     PhaseSignal,
		PhaseStartSeatNo: 3,
		ActingSeatNo:     3,
		CurrentToCall:    50,
		MinRaiseSize:     100,
		PotMain:          75,
		Seats: map[int]Seat{
			1: {SeatNo: 1, State: SeatStateActive, Stack: 975, CommittedThisHand: 25},
			2: {SeatNo: 2, State: SeatStateActive, Stack: 950, CommittedThisHand: 50},
			3: {SeatNo: 3, State: SeatStateActive, Stack: 1000},
			4: {SeatNo: 4, State: SeatStateActive, Stack: 1000},
		},
	}

	var err error
	state, _, err = Apply(state, SubmitArenaAction{SeatNo: 3, ActionType: ActionSignalNone})
	require.NoError(t, err)
	require.Equal(t, PhaseSignal, state.CurrentPhase)
	require.Equal(t, 4, state.ActingSeatNo)

	state, _, err = Apply(state, SubmitArenaAction{SeatNo: 4, ActionType: ActionSignalNone})
	require.NoError(t, err)
	require.Equal(t, PhaseSignal, state.CurrentPhase)
	require.Equal(t, 1, state.ActingSeatNo)

	state, _, err = Apply(state, SubmitArenaAction{SeatNo: 1, ActionType: ActionSignalNone})
	require.NoError(t, err)
	require.Equal(t, PhaseSignal, state.CurrentPhase)
	require.Equal(t, 2, state.ActingSeatNo)

	state, _, err = Apply(state, SubmitArenaAction{SeatNo: 2, ActionType: ActionSignalNone})
	require.NoError(t, err)
	require.Equal(t, PhaseProbe, state.CurrentPhase)
	require.Equal(t, 3, state.ActingSeatNo)

	state, _, err = Apply(state, SubmitArenaAction{SeatNo: 3, ActionType: ActionPassProbe})
	require.NoError(t, err)
	state, _, err = Apply(state, SubmitArenaAction{SeatNo: 4, ActionType: ActionPassProbe})
	require.NoError(t, err)
	state, _, err = Apply(state, SubmitArenaAction{SeatNo: 1, ActionType: ActionPassProbe})
	require.NoError(t, err)
	state, _, err = Apply(state, SubmitArenaAction{SeatNo: 2, ActionType: ActionPassProbe})
	require.NoError(t, err)
	require.Equal(t, PhaseWager, state.CurrentPhase)
	require.Equal(t, 3, state.ActingSeatNo)
	require.Equal(t, int64(75), state.PotMain)
	require.Equal(t, int64(50), state.CurrentToCall)

	state, _, err = Apply(state, SubmitArenaAction{SeatNo: 3, ActionType: ActionCall})
	require.NoError(t, err)
	state, _, err = Apply(state, SubmitArenaAction{SeatNo: 4, ActionType: ActionCall})
	require.NoError(t, err)
	state, _, err = Apply(state, SubmitArenaAction{SeatNo: 1, ActionType: ActionCall})
	require.NoError(t, err)
	state, events, err := Apply(state, SubmitArenaAction{SeatNo: 2, ActionType: ActionCheck})
	require.NoError(t, err)
	require.True(t, state.HandClosed)
	require.Equal(t, EventHandClosed, events[len(events)-1].Type)
}

func TestSingleContenderWinsEntirePotAtHandClose(t *testing.T) {
	state := State{
		HandNumber:   1,
		CurrentPhase: PhaseWager,
		PotMain:      300,
		Seats: map[int]Seat{
			1: {SeatNo: 1, State: SeatStateActive, Stack: 800},
			2: {SeatNo: 2, State: SeatStateActive, Stack: 900, Folded: true},
			3: {SeatNo: 3, State: SeatStateActive, Stack: 700, Folded: true},
		},
	}

	next, _, err := Apply(state, CloseHand{})
	require.NoError(t, err)
	require.Equal(t, []int{1}, next.WinnerSeatNos)
	require.Equal(t, int64(1100), next.Seats[1].Stack)
	require.Equal(t, int64(300), next.Seats[1].WonThisHand)
}

func TestHighestShowdownValueWinsPotAtHandClose(t *testing.T) {
	state := State{
		HandNumber:   7,
		CurrentPhase: PhaseWager,
		PotMain:      240,
		Seats: map[int]Seat{
			1: {SeatNo: 1, State: SeatStateActive, Stack: 760, ShowdownValue: 11},
			2: {SeatNo: 2, State: SeatStateActive, Stack: 760, ShowdownValue: 99},
			3: {SeatNo: 3, State: SeatStateActive, Stack: 1000, Folded: true},
		},
	}

	next, _, err := Apply(state, CloseHand{})
	require.NoError(t, err)
	require.Equal(t, []int{2}, next.WinnerSeatNos)
	require.Equal(t, int64(1000), next.Seats[2].Stack)
	require.Equal(t, int64(240), next.Seats[2].WonThisHand)
}

func TestTiedShowdownSplitsPotAndAwardsOddChipBySeatOrder(t *testing.T) {
	state := State{
		HandNumber:   9,
		CurrentPhase: PhaseWager,
		PotMain:      101,
		Seats: map[int]Seat{
			1: {SeatNo: 1, State: SeatStateActive, Stack: 900, ShowdownValue: 77},
			2: {SeatNo: 2, State: SeatStateActive, Stack: 900, ShowdownValue: 77},
		},
	}

	next, _, err := Apply(state, CloseHand{})
	require.NoError(t, err)
	require.Equal(t, []int{1, 2}, next.WinnerSeatNos)
	require.Equal(t, int64(951), next.Seats[1].Stack)
	require.Equal(t, int64(950), next.Seats[2].Stack)
	require.Equal(t, int64(51), next.Seats[1].WonThisHand)
	require.Equal(t, int64(50), next.Seats[2].WonThisHand)
}

func TestAllInConsumesEntireStackAndSkipsFutureTurnSelection(t *testing.T) {
	state := State{
		HandNumber:       3,
		CurrentPhase:     PhaseWager,
		PhaseStartSeatNo: 1,
		ActingSeatNo:     1,
		CurrentToCall:    50,
		MinRaiseSize:     50,
		Seats: map[int]Seat{
			1: {SeatNo: 1, State: SeatStateActive, Stack: 80},
			2: {SeatNo: 2, State: SeatStateActive, Stack: 500},
			3: {SeatNo: 3, State: SeatStateActive, Stack: 500},
		},
	}

	next, events, err := Apply(state, SubmitArenaAction{
		SeatNo:     1,
		ActionType: ActionAllIn,
	})
	require.NoError(t, err)
	require.Equal(t, EventActionApplied, events[0].Type)
	require.True(t, next.Seats[1].AllInThisHand)
	require.Equal(t, int64(0), next.Seats[1].Stack)
	require.Equal(t, int64(80), next.Seats[1].CommittedThisHand)
	require.Equal(t, int64(80), next.CurrentToCall)
	require.Equal(t, 2, next.ActingSeatNo)
}

func TestCallAgainstAllInClosesHandWhenNoFurtherActorsRemain(t *testing.T) {
	state := State{
		HandNumber:       4,
		CurrentPhase:     PhaseWager,
		PhaseStartSeatNo: 1,
		ActingSeatNo:     2,
		CurrentToCall:    100,
		MinRaiseSize:     50,
		PotMain:          100,
		Seats: map[int]Seat{
			1: {SeatNo: 1, State: SeatStateActive, Stack: 0, CommittedThisHand: 100, AllInThisHand: true, ShowdownValue: 80},
			2: {SeatNo: 2, State: SeatStateActive, Stack: 900, ShowdownValue: 99},
		},
	}

	next, events, err := Apply(state, SubmitArenaAction{
		SeatNo:     2,
		ActionType: ActionCall,
	})
	require.NoError(t, err)
	require.True(t, next.HandClosed)
	require.Equal(t, EventHandClosed, events[len(events)-1].Type)
	require.Equal(t, int64(0), next.Seats[1].Stack)
	require.Equal(t, SeatStateEliminated, next.Seats[1].State)
	require.Equal(t, int64(1000), next.Seats[2].Stack)
}

func TestSidePotAwardsOnlyEligibleContenders(t *testing.T) {
	state := State{
		HandNumber:   5,
		CurrentPhase: PhaseWager,
		PotMain:      500,
		Seats: map[int]Seat{
			1: {SeatNo: 1, State: SeatStateActive, Stack: 0, CommittedThisHand: 100, ShowdownValue: 99, AllInThisHand: true},
			2: {SeatNo: 2, State: SeatStateActive, Stack: 0, CommittedThisHand: 200, ShowdownValue: 80, AllInThisHand: true},
			3: {SeatNo: 3, State: SeatStateActive, Stack: 0, CommittedThisHand: 200, ShowdownValue: 70, AllInThisHand: true},
		},
	}

	next, _, err := Apply(state, CloseHand{})
	require.NoError(t, err)
	require.Equal(t, int64(300), next.Seats[1].WonThisHand)
	require.Equal(t, int64(200), next.Seats[2].WonThisHand)
	require.Equal(t, int64(0), next.Seats[3].WonThisHand)
	require.Equal(t, int64(300), next.Seats[1].Stack)
	require.Equal(t, int64(200), next.Seats[2].Stack)
	require.Equal(t, int64(0), next.Seats[3].Stack)
}

func TestUnmatchedOverbetRefundsToFoldedContributor(t *testing.T) {
	state := State{
		HandNumber:   6,
		CurrentPhase: PhaseWager,
		PotMain:      300,
		Seats: map[int]Seat{
			1: {SeatNo: 1, State: SeatStateActive, Stack: 0, CommittedThisHand: 100, ShowdownValue: 90},
			2: {SeatNo: 2, State: SeatStateActive, Stack: 0, CommittedThisHand: 200, Folded: true},
		},
	}

	next, _, err := Apply(state, CloseHand{})
	require.NoError(t, err)
	require.Equal(t, []int{1}, next.WinnerSeatNos)
	require.Equal(t, int64(200), next.Seats[1].WonThisHand)
	require.Equal(t, int64(200), next.Seats[1].Stack)
	require.Equal(t, int64(100), next.Seats[2].WonThisHand)
	require.Equal(t, int64(100), next.Seats[2].Stack)
}

func givenTableState(phase Phase, toCall int64) State {
	return State{
		CurrentPhase:  phase,
		ActingSeatNo:  3,
		CurrentToCall: toCall,
		MinRaiseSize:  50,
		Seats: map[int]Seat{
			3: {SeatNo: 3, State: SeatStateActive, Stack: 1000},
			4: {SeatNo: 4, State: SeatStateActive, Stack: 1000},
			5: {SeatNo: 5, State: SeatStateActive, Stack: 1000},
		},
	}
}

func givenBustedButOpenHand() State {
	state := givenTableState(PhaseWager, 0)
	state.Seats[5] = Seat{
		SeatNo: 5,
		State:  SeatStateActive,
		Stack:  -10,
	}
	state.ActingSeatNo = 3
	return state
}

func givenShortStackState() State {
	state := givenTableState(PhaseWager, 50)
	state.ActingSeatNo = 4
	state.Seats[4] = Seat{
		SeatNo: 4,
		State:  SeatStateActive,
		Stack:  120,
	}
	return state
}

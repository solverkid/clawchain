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

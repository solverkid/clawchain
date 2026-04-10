package table

import (
	"errors"
	"fmt"
	"slices"
)

var (
	ErrUnknownCommand = errors.New("unknown command")
	ErrIllegalAction  = errors.New("illegal action")
)

func Apply(state State, cmd Command) (State, []Event, error) {
	switch c := cmd.(type) {
	case StartHand:
		return applyStartHand(state, c)
	case SubmitArenaAction:
		return applyAction(state, c)
	case ApplyPhaseTimeout:
		return applyTimeout(state, c)
	case CloseHand:
		return applyCloseHand(state)
	default:
		return state, nil, ErrUnknownCommand
	}
}

func applyStartHand(state State, _ StartHand) (State, []Event, error) {
	next := state.clone()
	next.HandClosed = false
	for seatNo, seat := range next.Seats {
		seat.Folded = false
		seat.TimedOutThisHand = false
		seat.ManualActionThisHand = false
		next.Seats[seatNo] = seat
	}
	return next, nil, nil
}

func applyAction(state State, cmd SubmitArenaAction) (State, []Event, error) {
	if cmd.SeatNo != state.ActingSeatNo {
		return state, nil, fmt.Errorf("%w: not acting seat", ErrIllegalAction)
	}

	seat, ok := state.Seats[cmd.SeatNo]
	if !ok || seat.State == SeatStateEliminated {
		return state, nil, fmt.Errorf("%w: seat unavailable", ErrIllegalAction)
	}

	if err := validateAction(state, seat, cmd); err != nil {
		return state, nil, err
	}

	next := state.clone()
	seat = next.Seats[cmd.SeatNo]
	seat.ManualActionThisHand = true
	seat.TimedOutThisHand = false

	switch cmd.ActionType {
	case ActionFold:
		seat.Folded = true
	case ActionCall:
		seat.Stack -= state.CurrentToCall
		next.PotMain += state.CurrentToCall
	case ActionRaise:
		seat.Stack -= cmd.Amount
		next.PotMain += cmd.Amount
		next.CurrentToCall = cmd.Amount
	case ActionCheck, ActionSignalNone, ActionPassProbe:
	}

	next.Seats[cmd.SeatNo] = seat
	next.ActingSeatNo = nextActiveSeat(next, cmd.SeatNo)

	return next, []Event{{
		Type:       EventActionApplied,
		SeatNo:     cmd.SeatNo,
		ActionType: cmd.ActionType,
		Amount:     cmd.Amount,
	}}, nil
}

func applyTimeout(state State, cmd ApplyPhaseTimeout) (State, []Event, error) {
	if cmd.SeatNo != state.ActingSeatNo {
		return state, nil, fmt.Errorf("%w: not acting seat", ErrIllegalAction)
	}

	seat, ok := state.Seats[cmd.SeatNo]
	if !ok || seat.State == SeatStateEliminated {
		return state, nil, fmt.Errorf("%w: seat unavailable", ErrIllegalAction)
	}

	next := state.clone()
	seat = next.Seats[cmd.SeatNo]
	seat.TimedOutThisHand = true

	autoAction := timeoutAction(next)
	switch autoAction {
	case ActionAutoFold:
		seat.Folded = true
	case ActionAutoCheck, ActionSignalNone, ActionPassProbe:
	}

	next.Seats[cmd.SeatNo] = seat
	next.ActingSeatNo = nextActiveSeat(next, cmd.SeatNo)

	return next, []Event{{
		Type:       EventTimeoutApplied,
		SeatNo:     cmd.SeatNo,
		AutoAction: autoAction,
	}}, nil
}

func applyCloseHand(state State) (State, []Event, error) {
	next := state.clone()
	next.HandClosed = true

	for seatNo, seat := range next.Seats {
		switch {
		case seat.ManualActionThisHand:
			seat.TimeoutStreak = 0
		case seat.TimedOutThisHand:
			seat.TimeoutStreak++
			if seat.TimeoutStreak == 1 {
				seat.SitOutWarningCount++
			}
			if seat.TimeoutStreak >= 2 {
				seat.State = SeatStateSitOut
			}
			if seat.TimeoutStreak >= 4 {
				seat.State = SeatStateEliminated
			}
		}

		if seat.Stack <= 0 {
			seat.State = SeatStateEliminated
		}

		seat.TimedOutThisHand = false
		seat.ManualActionThisHand = false
		next.Seats[seatNo] = seat
	}

	return next, []Event{{Type: EventHandClosed}}, nil
}

func validateAction(state State, seat Seat, cmd SubmitArenaAction) error {
	switch state.CurrentPhase {
	case PhaseSignal:
		if cmd.ActionType != ActionSignalNone {
			return fmt.Errorf("%w: invalid signal action", ErrIllegalAction)
		}
	case PhaseProbe:
		if cmd.ActionType != ActionPassProbe {
			return fmt.Errorf("%w: invalid probe action", ErrIllegalAction)
		}
	case PhaseWager:
		switch cmd.ActionType {
		case ActionCheck:
			if state.CurrentToCall != 0 {
				return fmt.Errorf("%w: cannot check facing action", ErrIllegalAction)
			}
		case ActionCall:
			if state.CurrentToCall <= 0 || state.CurrentToCall > seat.Stack {
				return fmt.Errorf("%w: invalid call", ErrIllegalAction)
			}
		case ActionFold:
		case ActionRaise:
			if cmd.Amount <= state.CurrentToCall {
				return fmt.Errorf("%w: raise must exceed to_call", ErrIllegalAction)
			}
			if cmd.Amount < state.MinRaiseSize {
				return fmt.Errorf("%w: raise below minimum", ErrIllegalAction)
			}
			if cmd.Amount >= seat.Stack {
				return fmt.Errorf("%w: no all-in or side-pot support", ErrIllegalAction)
			}
		default:
			return fmt.Errorf("%w: unsupported wager action", ErrIllegalAction)
		}
	default:
		return fmt.Errorf("%w: unknown phase", ErrIllegalAction)
	}

	return nil
}

func timeoutAction(state State) ActionType {
	switch state.CurrentPhase {
	case PhaseSignal:
		return ActionSignalNone
	case PhaseProbe:
		return ActionPassProbe
	case PhaseWager:
		if state.CurrentToCall == 0 {
			return ActionAutoCheck
		}
		return ActionAutoFold
	default:
		return ActionAutoFold
	}
}

func nextActiveSeat(state State, currentSeatNo int) int {
	if len(state.Seats) == 0 {
		return 0
	}

	seatNos := make([]int, 0, len(state.Seats))
	for seatNo := range state.Seats {
		seatNos = append(seatNos, seatNo)
	}
	slices.Sort(seatNos)

	for i, seatNo := range seatNos {
		if seatNo != currentSeatNo {
			continue
		}
		for offset := 1; offset <= len(seatNos); offset++ {
			nextSeatNo := seatNos[(i+offset)%len(seatNos)]
			seat := state.Seats[nextSeatNo]
			if seat.State == SeatStateEliminated || seat.Folded {
				continue
			}
			return nextSeatNo
		}
	}

	return currentSeatNo
}

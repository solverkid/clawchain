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

func applyStartHand(state State, cmd StartHand) (State, []Event, error) {
	next := state.clone()
	next.HandNumber++
	next.HandClosed = false
	next.PotMain = 0
	next.CurrentToCall = 0
	next.PhaseStartSeatNo = 0
	next.ActingSeatNo = 0
	next.WinnerSeatNos = nil
	for seatNo, seat := range next.Seats {
		seat.Folded = false
		seat.AllInThisHand = false
		seat.TimedOutThisHand = false
		seat.ManualActionThisHand = false
		seat.CommittedThisHand = 0
		seat.WonThisHand = 0
		seat.ShowdownValue = deterministicShowdownValue(next.HandNumber, seatNo)
		next.Seats[seatNo] = seat
	}

	activeSeatNos := eligibleSeatNos(next)
	if len(activeSeatNos) == 0 {
		next.ActingSeatNo = 0
		next.MinRaiseSize = cmd.MinRaiseTo
		return next, nil, nil
	}

	if cmd.Ante > 0 {
		for _, seatNo := range activeSeatNos {
			forced := forcedContribution(next.Seats[seatNo], cmd.Ante)
			seat := next.Seats[seatNo]
			seat.Stack -= forced
			seat.CommittedThisHand += forced
			seat.AllInThisHand = seat.Stack == 0 && seat.CommittedThisHand > 0
			next.Seats[seatNo] = seat
			next.PotMain += forced
		}
	}

	sbSeatNo := 0
	bbSeatNo := 0
	if len(activeSeatNos) >= 2 {
		sbIndex := (next.HandNumber - 1) % len(activeSeatNos)
		bbIndex := (sbIndex + 1) % len(activeSeatNos)
		sbSeatNo = activeSeatNos[sbIndex]
		bbSeatNo = activeSeatNos[bbIndex]

		if cmd.SmallBlind > 0 {
			forced := forcedContribution(next.Seats[sbSeatNo], cmd.SmallBlind)
			seat := next.Seats[sbSeatNo]
			seat.Stack -= forced
			seat.CommittedThisHand += forced
			seat.AllInThisHand = seat.Stack == 0 && seat.CommittedThisHand > 0
			next.Seats[sbSeatNo] = seat
			next.PotMain += forced
		}
		if cmd.BigBlind > 0 {
			forced := forcedContribution(next.Seats[bbSeatNo], cmd.BigBlind)
			seat := next.Seats[bbSeatNo]
			seat.Stack -= forced
			seat.CommittedThisHand += forced
			seat.AllInThisHand = seat.Stack == 0 && seat.CommittedThisHand > 0
			next.Seats[bbSeatNo] = seat
			next.PotMain += forced
		}
	}

	for _, seat := range next.Seats {
		if seat.CommittedThisHand > next.CurrentToCall {
			next.CurrentToCall = seat.CommittedThisHand
		}
	}
	next.MinRaiseSize = cmd.MinRaiseTo
	next.ActingSeatNo = firstEligibleSeatFrom(next, nextActiveSeatForStart(activeSeatNos, bbSeatNo))
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
	if seat.State == SeatStateSitOut {
		seat.State = SeatStateActive
	}

	switch cmd.ActionType {
	case ActionFold:
		seat.Folded = true
	case ActionCall:
		callAmount := chipsToCall(state, seat)
		seat.Stack -= callAmount
		seat.CommittedThisHand += callAmount
		next.PotMain += callAmount
	case ActionRaise:
		raiseAmount := cmd.Amount - seat.CommittedThisHand
		seat.Stack -= raiseAmount
		seat.CommittedThisHand = cmd.Amount
		next.PotMain += raiseAmount
		next.CurrentToCall = cmd.Amount
	case ActionAllIn:
		allInAmount := seat.Stack
		seat.Stack = 0
		seat.CommittedThisHand += allInAmount
		seat.AllInThisHand = true
		next.PotMain += allInAmount
		if seat.CommittedThisHand > next.CurrentToCall {
			next.CurrentToCall = seat.CommittedThisHand
		}
	case ActionCheck, ActionSignalNone, ActionPassProbe:
	}

	next.Seats[cmd.SeatNo] = seat
	next.ActingSeatNo = nextActiveSeat(next, cmd.SeatNo)

	events := []Event{{
		Type:       EventActionApplied,
		SeatNo:     cmd.SeatNo,
		ActionType: cmd.ActionType,
		Amount:     cmd.Amount,
	}}
	return advanceAfterTurn(state, next, events)
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

	events := []Event{{
		Type:       EventTimeoutApplied,
		SeatNo:     cmd.SeatNo,
		AutoAction: autoAction,
	}}
	return advanceAfterTurn(state, next, events)
}

func applyCloseHand(state State) (State, []Event, error) {
	next := state.clone()
	next.HandClosed = true
	next.ActingSeatNo = 0
	next.CurrentToCall = 0
	resolvedWinners := resolveWinners(next)
	potWinners := awardPot(&next, resolvedWinners)
	if len(potWinners) > 0 {
		next.WinnerSeatNos = potWinners
	} else {
		next.WinnerSeatNos = resolvedWinners
	}

	for seatNo, seat := range next.Seats {
		switch {
		case seat.ManualActionThisHand:
			seat.TimeoutStreak = 0
			if seat.State == SeatStateSitOut {
				seat.State = SeatStateActive
			}
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
			if chipsToCall(state, seat) != 0 {
				return fmt.Errorf("%w: cannot check facing action", ErrIllegalAction)
			}
		case ActionCall:
			callAmount := chipsToCall(state, seat)
			if callAmount <= 0 || callAmount > seat.Stack {
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
			raiseAmount := cmd.Amount - seat.CommittedThisHand
			if raiseAmount <= 0 {
				return fmt.Errorf("%w: invalid raise size", ErrIllegalAction)
			}
			if raiseAmount >= seat.Stack {
				return fmt.Errorf("%w: no all-in or side-pot support", ErrIllegalAction)
			}
		case ActionAllIn:
			if seat.Stack <= 0 {
				return fmt.Errorf("%w: empty stack", ErrIllegalAction)
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
		seat, ok := state.Seats[state.ActingSeatNo]
		if ok && chipsToCall(state, seat) == 0 {
			return ActionAutoCheck
		}
		return ActionAutoFold
	default:
		return ActionAutoFold
	}
}

func advanceAfterTurn(previous State, next State, events []Event) (State, []Event, error) {
	if next.CurrentPhase == PhaseWager {
		if remainingContenders(next) <= 1 || remainingActors(next) == 0 || noFurtherWagerActionsRequired(previous, next) {
			closed, closeEvents, err := applyCloseHand(next)
			if err != nil {
				return previous, nil, err
			}
			return closed, append(events, closeEvents...), nil
		}
	}

	if !phaseCompleted(previous, next) {
		return next, events, nil
	}

	switch next.CurrentPhase {
	case PhaseSignal:
		next.CurrentPhase = PhaseProbe
		next.ActingSeatNo = firstEligibleSeatFrom(next, previous.PhaseStartSeatNo)
		next.PhaseStartSeatNo = next.ActingSeatNo
		return next, events, nil
	case PhaseProbe:
		next.CurrentPhase = PhaseWager
		next.ActingSeatNo = firstEligibleSeatFrom(next, previous.PhaseStartSeatNo)
		next.PhaseStartSeatNo = next.ActingSeatNo
		return next, events, nil
	case PhaseWager:
		closed, closeEvents, err := applyCloseHand(next)
		if err != nil {
			return previous, nil, err
		}
		return closed, append(events, closeEvents...), nil
	default:
		return next, events, nil
	}
}

func phaseCompleted(previous State, next State) bool {
	if next.ActingSeatNo == 0 {
		return remainingActors(next) == 0
	}
	startSeatNo := previous.PhaseStartSeatNo
	if startSeatNo == 0 {
		startSeatNo = previous.ActingSeatNo
	}
	return next.ActingSeatNo == startSeatNo
}

func firstEligibleSeat(state State) int {
	return firstEligibleSeatFrom(state, 0)
}

func firstEligibleSeatFrom(state State, startSeatNo int) int {
	seatNos := make([]int, 0, len(state.Seats))
	for seatNo, seat := range state.Seats {
		if !canAct(seat) {
			continue
		}
		seatNos = append(seatNos, seatNo)
	}
	if len(seatNos) == 0 {
		return 0
	}
	slices.Sort(seatNos)
	if startSeatNo == 0 {
		return seatNos[0]
	}
	for _, seatNo := range seatNos {
		if seatNo >= startSeatNo {
			return seatNo
		}
	}
	return seatNos[0]
}

func eligibleSeatNos(state State) []int {
	seatNos := make([]int, 0, len(state.Seats))
	for seatNo, seat := range state.Seats {
		if seat.State == SeatStateEliminated {
			continue
		}
		seatNos = append(seatNos, seatNo)
	}
	slices.Sort(seatNos)
	return seatNos
}

func nextActiveSeatForStart(activeSeatNos []int, currentSeatNo int) int {
	if len(activeSeatNos) == 0 {
		return 0
	}
	if currentSeatNo == 0 {
		return activeSeatNos[0]
	}
	for idx, seatNo := range activeSeatNos {
		if seatNo != currentSeatNo {
			continue
		}
		return activeSeatNos[(idx+1)%len(activeSeatNos)]
	}
	return activeSeatNos[0]
}

func forcedContribution(seat Seat, amount int64) int64 {
	if amount <= 0 || seat.Stack <= 0 {
		return 0
	}
	if amount > seat.Stack {
		return seat.Stack
	}
	return amount
}

func remainingContenders(state State) int {
	contenders := 0
	for _, seat := range state.Seats {
		if !isContender(seat) {
			continue
		}
		contenders++
	}
	return contenders
}

func remainingActors(state State) int {
	actors := 0
	for _, seat := range state.Seats {
		if !canAct(seat) {
			continue
		}
		actors++
	}
	return actors
}

func noFurtherWagerActionsRequired(previous State, next State) bool {
	if previous.ActingSeatNo == 0 || next.ActingSeatNo != previous.ActingSeatNo {
		return false
	}
	seat, ok := next.Seats[next.ActingSeatNo]
	if !ok {
		return true
	}
	return chipsToCall(next, seat) == 0
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
		for offset := 1; offset < len(seatNos); offset++ {
			nextSeatNo := seatNos[(i+offset)%len(seatNos)]
			seat := state.Seats[nextSeatNo]
			if !canAct(seat) {
				continue
			}
			return nextSeatNo
		}
	}

	return currentSeatNo
}

func resolveWinners(state State) []int {
	contenders := make([]int, 0, len(state.Seats))
	bestValue := int64(-1)
	for seatNo, seat := range state.Seats {
		if !isContender(seat) {
			continue
		}
		value := showdownValue(state, seatNo, seat)
		if value > bestValue {
			bestValue = value
			contenders = []int{seatNo}
			continue
		}
		if value == bestValue {
			contenders = append(contenders, seatNo)
		}
	}
	slices.Sort(contenders)
	return contenders
}

func awardPot(state *State, winners []int) []int {
	if state == nil || state.PotMain <= 0 || len(winners) == 0 {
		return nil
	}

	if totalCommitted(state) <= 0 {
		distributeChips(state, winners, state.PotMain)
		state.PotMain = 0
		return append([]int(nil), winners...)
	}

	potWinners := make(map[int]struct{})
	prevLevel := int64(0)
	for _, level := range commitmentLevels(state) {
		contributors := contributorsAtOrAbove(state, level)
		if len(contributors) == 0 {
			prevLevel = level
			continue
		}

		layerAmount := (level - prevLevel) * int64(len(contributors))
		prevLevel = level
		if layerAmount <= 0 {
			continue
		}

		if len(contributors) == 1 {
			distributeChips(state, contributors, layerAmount)
			continue
		}

		eligible := eligibleContendersAtOrAbove(state, level)
		if len(eligible) == 0 {
			distributeChips(state, contributors, layerAmount)
			continue
		}

		layerWinners := bestShowdownSeats(state, eligible)
		distributeChips(state, layerWinners, layerAmount)
		for _, seatNo := range layerWinners {
			potWinners[seatNo] = struct{}{}
		}
	}
	state.PotMain = 0
	return sortedSeatNos(potWinners)
}

func chipsToCall(state State, seat Seat) int64 {
	if state.CurrentToCall <= seat.CommittedThisHand {
		return 0
	}
	return state.CurrentToCall - seat.CommittedThisHand
}

func canAct(seat Seat) bool {
	return seat.State != SeatStateEliminated && !seat.Folded && !seat.AllInThisHand
}

func isContender(seat Seat) bool {
	return seat.State != SeatStateEliminated && !seat.Folded
}

func showdownValue(state State, seatNo int, seat Seat) int64 {
	if seat.ShowdownValue != 0 {
		return seat.ShowdownValue
	}
	return deterministicShowdownValue(state.HandNumber, seatNo)
}

func totalCommitted(state *State) int64 {
	var total int64
	for _, seat := range state.Seats {
		total += seat.CommittedThisHand
	}
	return total
}

func commitmentLevels(state *State) []int64 {
	seen := make(map[int64]struct{})
	levels := make([]int64, 0, len(state.Seats))
	for _, seat := range state.Seats {
		if seat.CommittedThisHand <= 0 {
			continue
		}
		if _, ok := seen[seat.CommittedThisHand]; ok {
			continue
		}
		seen[seat.CommittedThisHand] = struct{}{}
		levels = append(levels, seat.CommittedThisHand)
	}
	slices.Sort(levels)
	return levels
}

func contributorsAtOrAbove(state *State, level int64) []int {
	contributors := make([]int, 0, len(state.Seats))
	for seatNo, seat := range state.Seats {
		if seat.CommittedThisHand < level {
			continue
		}
		contributors = append(contributors, seatNo)
	}
	slices.Sort(contributors)
	return contributors
}

func eligibleContendersAtOrAbove(state *State, level int64) []int {
	eligible := make([]int, 0, len(state.Seats))
	for seatNo, seat := range state.Seats {
		if seat.CommittedThisHand < level || !isContender(seat) {
			continue
		}
		eligible = append(eligible, seatNo)
	}
	slices.Sort(eligible)
	return eligible
}

func bestShowdownSeats(state *State, seatNos []int) []int {
	winners := make([]int, 0, len(seatNos))
	bestValue := int64(-1)
	for _, seatNo := range seatNos {
		seat := state.Seats[seatNo]
		value := showdownValue(*state, seatNo, seat)
		if value > bestValue {
			bestValue = value
			winners = []int{seatNo}
			continue
		}
		if value == bestValue {
			winners = append(winners, seatNo)
		}
	}
	slices.Sort(winners)
	return winners
}

func distributeChips(state *State, seatNos []int, amount int64) {
	if amount <= 0 || len(seatNos) == 0 {
		return
	}

	share := amount / int64(len(seatNos))
	remainder := amount % int64(len(seatNos))
	for idx, seatNo := range seatNos {
		seat := state.Seats[seatNo]
		payout := share
		if int64(idx) < remainder {
			payout++
		}
		seat.Stack += payout
		seat.WonThisHand += payout
		if seat.ShowdownValue == 0 {
			seat.ShowdownValue = deterministicShowdownValue(state.HandNumber, seatNo)
		}
		state.Seats[seatNo] = seat
	}
}

func sortedSeatNos(seatSet map[int]struct{}) []int {
	seatNos := make([]int, 0, len(seatSet))
	for seatNo := range seatSet {
		seatNos = append(seatNos, seatNo)
	}
	slices.Sort(seatNos)
	return seatNos
}

func deterministicShowdownValue(handNumber, seatNo int) int64 {
	if handNumber <= 0 {
		handNumber = 1
	}
	return int64(((handNumber * 97) + (seatNo * 31)) % 1000)
}

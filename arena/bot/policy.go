package bot

import (
	"fmt"
	"math/rand"
	"time"
)

type Policy interface {
	Decide(assignment SeatAssignment, view LiveTable) (Decision, bool, error)
}

type HeuristicPolicy struct{}
type RandomPolicy struct {
	Rand *rand.Rand
}

type weightedAction struct {
	Action string
	Weight int
}

func NewRandomPolicy(seed int64) RandomPolicy {
	if seed == 0 {
		seed = time.Now().UnixNano()
	}
	return RandomPolicy{Rand: rand.New(rand.NewSource(seed))}
}

func (HeuristicPolicy) Decide(assignment SeatAssignment, view LiveTable) (Decision, bool, error) {
	if assignment.SeatNo != view.ActingSeatNo {
		return Decision{}, false, nil
	}

	switch view.CurrentPhase {
	case "signal":
		return Decision{ActionType: "signal_none"}, true, nil
	case "probe":
		return Decision{ActionType: "pass_probe"}, true, nil
	case "wager":
		return decideWager(assignment, view), true, nil
	case "":
		return Decision{}, false, nil
	default:
		return Decision{}, false, fmt.Errorf("unsupported live phase %q", view.CurrentPhase)
	}
}

func (p RandomPolicy) Decide(assignment SeatAssignment, view LiveTable) (Decision, bool, error) {
	if assignment.SeatNo != view.ActingSeatNo {
		return Decision{}, false, nil
	}

	switch view.CurrentPhase {
	case "signal":
		return Decision{ActionType: "signal_none"}, true, nil
	case "probe":
		return Decision{ActionType: "pass_probe"}, true, nil
	case "wager":
		return decideRandomWager(p.Rand, assignment, view), true, nil
	case "":
		return Decision{}, false, nil
	default:
		return Decision{}, false, fmt.Errorf("unsupported live phase %q", view.CurrentPhase)
	}
}

func decideWager(assignment SeatAssignment, view LiveTable) Decision {
	legal := make(map[string]bool, len(view.LegalActions))
	for _, action := range view.LegalActions {
		legal[action] = true
	}

	stack := view.StackForSeat(assignment.SeatNo)
	switch {
	case legal["raise"] && view.CurrentToCall == 0 && view.MinRaiseTo > 0:
		return Decision{ActionType: "raise", Amount: view.MinRaiseTo}
	case legal["all_in"] && view.CurrentToCall == 0 && stack > 0:
		return Decision{ActionType: "all_in"}
	case legal["check"]:
		return Decision{ActionType: "check"}
	case legal["call"] && view.CurrentToCall > 0 && (stack == 0 || view.CurrentToCall <= stack/2):
		return Decision{ActionType: "call"}
	case legal["all_in"] && view.CurrentToCall >= stack && stack > 0:
		return Decision{ActionType: "all_in"}
	case legal["call"]:
		return Decision{ActionType: "call"}
	case legal["fold"]:
		return Decision{ActionType: "fold"}
	case legal["all_in"]:
		return Decision{ActionType: "all_in"}
	default:
		return Decision{ActionType: "check"}
	}
}

func decideRandomWager(rng *rand.Rand, assignment SeatAssignment, view LiveTable) Decision {
	legal := make(map[string]bool, len(view.LegalActions))
	for _, action := range view.LegalActions {
		legal[action] = true
	}

	stack := view.StackForSeat(assignment.SeatNo)
	options := weightedWagerActions(view, stack, legal)
	if len(options) == 0 {
		return decideWager(assignment, view)
	}

	switch chooseWeightedAction(rng, options) {
	case "raise":
		if amount := randomRaiseAmount(rng, view); amount > 0 {
			return Decision{ActionType: "raise", Amount: amount}
		}
	case "all_in":
		if legal["all_in"] {
			return Decision{ActionType: "all_in"}
		}
	case "call":
		if legal["call"] {
			return Decision{ActionType: "call"}
		}
	case "fold":
		if legal["fold"] {
			return Decision{ActionType: "fold"}
		}
	case "check":
		if legal["check"] {
			return Decision{ActionType: "check"}
		}
	}

	return decideWager(assignment, view)
}

func weightedWagerActions(view LiveTable, stack int64, legal map[string]bool) []weightedAction {
	canRaise := legal["raise"] && view.MinRaiseTo > 0 && view.MaxRaiseTo >= view.MinRaiseTo
	canAllIn := legal["all_in"] && stack > 0

	var options []weightedAction
	add := func(action string, weight int) {
		if weight > 0 {
			options = append(options, weightedAction{Action: action, Weight: weight})
		}
	}

	if view.CurrentToCall == 0 {
		add("check", boolWeight(legal["check"], 80))
		add("raise", boolWeight(canRaise, 12))
		add("all_in", boolWeight(canAllIn, 3))
		add("call", boolWeight(legal["call"], 5))
		if !legal["check"] {
			add("fold", boolWeight(legal["fold"], 20))
		}
	} else if view.CurrentToCall >= stack && stack > 0 {
		add("all_in", boolWeight(canAllIn, 60))
		add("fold", boolWeight(legal["fold"], 40))
		add("call", boolWeight(legal["call"], 10))
	} else {
		add("call", boolWeight(legal["call"], 55))
		add("fold", boolWeight(legal["fold"], 30))
		add("raise", boolWeight(canRaise, 10))
		add("all_in", boolWeight(canAllIn, 5))
		add("check", boolWeight(legal["check"], 5))
	}

	if len(options) > 0 {
		return options
	}

	for _, action := range view.LegalActions {
		options = append(options, weightedAction{Action: action, Weight: 1})
	}
	return options
}

func chooseWeightedAction(rng *rand.Rand, options []weightedAction) string {
	if len(options) == 0 {
		return ""
	}

	total := 0
	for _, option := range options {
		total += option.Weight
	}
	if total <= 0 {
		return options[0].Action
	}

	target := randomIntn(rng, total)
	running := 0
	for _, option := range options {
		running += option.Weight
		if target < running {
			return option.Action
		}
	}
	return options[len(options)-1].Action
}

func randomRaiseAmount(rng *rand.Rand, view LiveTable) int64 {
	if view.MinRaiseTo <= 0 || view.MaxRaiseTo < view.MinRaiseTo {
		return 0
	}

	maxRaiseTo := view.MaxRaiseTo
	if view.MinRaiseSize > 0 {
		capped := view.MinRaiseTo + view.MinRaiseSize*2
		if capped < maxRaiseTo {
			maxRaiseTo = capped
		}
	}
	if maxRaiseTo == view.MinRaiseTo {
		return view.MinRaiseTo
	}

	return view.MinRaiseTo + int64(randomInt63n(rng, maxRaiseTo-view.MinRaiseTo+1))
}

func randomIntn(rng *rand.Rand, n int) int {
	if rng != nil {
		return rng.Intn(n)
	}
	return rand.New(rand.NewSource(time.Now().UnixNano())).Intn(n)
}

func randomInt63n(rng *rand.Rand, n int64) int64 {
	if rng != nil {
		return rng.Int63n(n)
	}
	return rand.New(rand.NewSource(time.Now().UnixNano())).Int63n(n)
}

func boolWeight(enabled bool, weight int) int {
	if enabled {
		return weight
	}
	return 0
}

func (v LiveTable) StackForSeat(seatNo int) int64 {
	for _, seat := range v.VisibleStacks {
		if seat.SeatNo == seatNo {
			return seat.Stack
		}
	}
	return 0
}

package table

type Phase string

const (
	PhaseSignal Phase = "signal"
	PhaseProbe  Phase = "probe"
	PhaseWager  Phase = "wager"
)

type ActionType string

const (
	ActionSignalNone ActionType = "signal_none"
	ActionPassProbe  ActionType = "pass_probe"
	ActionCheck      ActionType = "check"
	ActionCall       ActionType = "call"
	ActionFold       ActionType = "fold"
	ActionRaise      ActionType = "raise"
	ActionAllIn      ActionType = "all_in"
	ActionAutoCheck  ActionType = "auto_check"
	ActionAutoFold   ActionType = "auto_fold"
)

type EventType string

const (
	EventActionApplied  EventType = "action_applied"
	EventTimeoutApplied EventType = "timeout_applied"
	EventHandClosed     EventType = "hand_closed"
)

type Event struct {
	Type       EventType
	SeatNo     int
	ActionType ActionType
	AutoAction ActionType
	Amount     int64
}

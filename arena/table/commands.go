package table

type Command interface {
	isCommand()
}

type StartHand struct{}

func (StartHand) isCommand() {}

type SubmitArenaAction struct {
	SeatNo     int
	ActionType ActionType
	Amount     int64
}

func (SubmitArenaAction) isCommand() {}

type ApplyPhaseTimeout struct {
	SeatNo int
}

func (ApplyPhaseTimeout) isCommand() {}

type CloseHand struct{}

func (CloseHand) isCommand() {}

package table

type Command interface {
	isCommand()
}

type StartHand struct {
	SmallBlind int64
	BigBlind   int64
	Ante       int64
	MinRaiseTo int64
}

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

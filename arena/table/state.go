package table

type SeatState string

const (
	SeatStateActive     SeatState = "active"
	SeatStateSitOut     SeatState = "sit_out"
	SeatStateEliminated SeatState = "eliminated"
)

type Seat struct {
	SeatNo               int
	State                SeatState
	Stack                int64
	Folded               bool
	TimedOutThisHand     bool
	ManualActionThisHand bool
	TimeoutStreak        int
	SitOutWarningCount   int
}

type State struct {
	CurrentPhase  Phase
	ActingSeatNo  int
	CurrentToCall int64
	MinRaiseSize  int64
	PotMain       int64
	HandClosed    bool
	Seats         map[int]Seat
}

func (s State) clone() State {
	next := s
	next.Seats = make(map[int]Seat, len(s.Seats))
	for seatNo, seat := range s.Seats {
		next.Seats[seatNo] = seat
	}
	return next
}

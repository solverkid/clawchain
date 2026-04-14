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
	CommittedThisHand    int64
	WonThisHand          int64
	ShowdownValue        int64
	Folded               bool
	AllInThisHand        bool
	TimedOutThisHand     bool
	ManualActionThisHand bool
	TimeoutStreak        int
	SitOutWarningCount   int
}

type State struct {
	CurrentPhase     Phase
	PhaseStartSeatNo int
	ActingSeatNo     int
	CurrentToCall    int64
	MinRaiseSize     int64
	PotMain          int64
	HandNumber       int
	HandClosed       bool
	WinnerSeatNos    []int
	Seats            map[int]Seat
}

func (s State) clone() State {
	next := s
	next.WinnerSeatNos = append([]int(nil), s.WinnerSeatNos...)
	next.Seats = make(map[int]Seat, len(s.Seats))
	for seatNo, seat := range s.Seats {
		next.Seats[seatNo] = seat
	}
	return next
}

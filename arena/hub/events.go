package hub

type PackResult struct {
	Tournaments []TournamentPlan
}

type TournamentPlan struct {
	TournamentID       string
	RatedOrPractice    string
	NoMultiplier       bool
	EntrantIDs         []string
	SeatAssignments    []SeatAssignment
	RepublishCount     int
	SeatsWerePublished bool
}

type SeatAssignment struct {
	EntrantID string
	MinerID   string
	TableID   string
	TableNo   int
	SeatNo    int
}

type TransitionPlan struct {
	Decision        TransitionDecision
	SeatAssignments []SeatAssignment
}

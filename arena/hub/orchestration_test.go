package hub

import "fmt"
import "testing"

import "github.com/stretchr/testify/require"

func TestRoundBarrierWaitsForAllActiveTables(t *testing.T) {
	h := newLiveHubForTest(t, 24, 3)

	h.MarkHandClosed("tbl:tour_live:01")
	h.MarkHandClosed("tbl:tour_live:02")
	require.False(t, h.CanAdvanceRound())

	h.MarkHandClosed("tbl:tour_live:03")
	require.True(t, h.CanAdvanceRound())
}

func TestFinalTableTakesPrecedenceOverNormalRebalance(t *testing.T) {
	h := newLiveHubForTest(t, 8, 2)

	require.Equal(t, TransitionFinalTable, h.NextBarrierDecision())
}

func TestTimeCapStopsAfterCurrentRoundNotCurrentHand(t *testing.T) {
	h := newLiveHubForTest(t, 17, 2)

	h.ArmTimeCap()
	require.True(t, h.TerminateAfterCurrentRound())
	require.False(t, h.TerminateAfterCurrentHand())
}

func TestRebalancePlanMovesSinglePlayerToShortestTable(t *testing.T) {
	h := NewService(State{
		TournamentID:     "tour_live",
		PlayersRemaining: 16,
		LiveTables: []LiveTable{
			{TableID: tableID("tour_live", 1), PlayerCount: 9},
			{TableID: tableID("tour_live", 2), PlayerCount: 7},
		},
		Tournaments: []TournamentPlan{{
			TournamentID: "tour_live",
			SeatAssignments: []SeatAssignment{
				{EntrantID: "e01", MinerID: "m01", TableID: tableID("tour_live", 1), TableNo: 1, SeatNo: 1},
				{EntrantID: "e02", MinerID: "m02", TableID: tableID("tour_live", 1), TableNo: 1, SeatNo: 2},
				{EntrantID: "e03", MinerID: "m03", TableID: tableID("tour_live", 1), TableNo: 1, SeatNo: 3},
				{EntrantID: "e04", MinerID: "m04", TableID: tableID("tour_live", 1), TableNo: 1, SeatNo: 4},
				{EntrantID: "e05", MinerID: "m05", TableID: tableID("tour_live", 1), TableNo: 1, SeatNo: 5},
				{EntrantID: "e06", MinerID: "m06", TableID: tableID("tour_live", 1), TableNo: 1, SeatNo: 6},
				{EntrantID: "e07", MinerID: "m07", TableID: tableID("tour_live", 1), TableNo: 1, SeatNo: 7},
				{EntrantID: "e08", MinerID: "m08", TableID: tableID("tour_live", 1), TableNo: 1, SeatNo: 8},
				{EntrantID: "e09", MinerID: "m09", TableID: tableID("tour_live", 1), TableNo: 1, SeatNo: 9},
				{EntrantID: "e10", MinerID: "m10", TableID: tableID("tour_live", 2), TableNo: 2, SeatNo: 1},
				{EntrantID: "e11", MinerID: "m11", TableID: tableID("tour_live", 2), TableNo: 2, SeatNo: 2},
				{EntrantID: "e12", MinerID: "m12", TableID: tableID("tour_live", 2), TableNo: 2, SeatNo: 3},
				{EntrantID: "e13", MinerID: "m13", TableID: tableID("tour_live", 2), TableNo: 2, SeatNo: 4},
				{EntrantID: "e14", MinerID: "m14", TableID: tableID("tour_live", 2), TableNo: 2, SeatNo: 5},
				{EntrantID: "e15", MinerID: "m15", TableID: tableID("tour_live", 2), TableNo: 2, SeatNo: 6},
				{EntrantID: "e16", MinerID: "m16", TableID: tableID("tour_live", 2), TableNo: 2, SeatNo: 7},
			},
		}},
	}, nil)

	plan := h.BuildTransitionPlan()
	require.Equal(t, TransitionRebalance, plan.Decision)
	require.Len(t, plan.SeatAssignments, 16)
	require.Equal(t, 8, countAssignmentsOnTable(plan.SeatAssignments, tableID("tour_live", 1)))
	require.Equal(t, 8, countAssignmentsOnTable(plan.SeatAssignments, tableID("tour_live", 2)))
}

func TestBreakTablePlanDropsShortestTable(t *testing.T) {
	h := NewService(State{
		TournamentID:     "tour_live",
		PlayersRemaining: 35,
		LiveTables: []LiveTable{
			{TableID: tableID("tour_live", 1), PlayerCount: 8},
			{TableID: tableID("tour_live", 2), PlayerCount: 8},
			{TableID: tableID("tour_live", 3), PlayerCount: 8},
			{TableID: tableID("tour_live", 4), PlayerCount: 8},
			{TableID: tableID("tour_live", 5), PlayerCount: 3},
		},
		Tournaments: []TournamentPlan{{
			TournamentID:    "tour_live",
			SeatAssignments: makeAssignmentsForCounts("tour_live", []int{8, 8, 8, 8, 3}),
		}},
	}, nil)

	plan := h.BuildTransitionPlan()
	require.Equal(t, TransitionBreakTable, plan.Decision)
	require.Len(t, uniqueTables(plan.SeatAssignments), 4)
	require.Zero(t, countAssignmentsOnTable(plan.SeatAssignments, tableID("tour_live", 5)))
	require.Equal(t, 9, countAssignmentsOnTable(plan.SeatAssignments, tableID("tour_live", 1)))
	require.Equal(t, 9, countAssignmentsOnTable(plan.SeatAssignments, tableID("tour_live", 2)))
	require.Equal(t, 9, countAssignmentsOnTable(plan.SeatAssignments, tableID("tour_live", 3)))
	require.Equal(t, 8, countAssignmentsOnTable(plan.SeatAssignments, tableID("tour_live", 4)))
}

func TestFinalTablePlanConvergesToSingleTable(t *testing.T) {
	h := NewService(State{
		TournamentID:     "tour_live",
		PlayersRemaining: 8,
		LiveTables: []LiveTable{
			{TableID: tableID("tour_live", 1), PlayerCount: 4},
			{TableID: tableID("tour_live", 2), PlayerCount: 4},
		},
		Tournaments: []TournamentPlan{{
			TournamentID:    "tour_live",
			SeatAssignments: makeAssignmentsForCounts("tour_live", []int{4, 4}),
		}},
	}, nil)

	plan := h.BuildTransitionPlan()
	require.Equal(t, TransitionFinalTable, plan.Decision)
	require.Len(t, uniqueTables(plan.SeatAssignments), 1)
	require.Equal(t, 8, countAssignmentsOnTable(plan.SeatAssignments, tableID("tour_live", 1)))
}

func TestNineHandedFieldAlsoConvergesToFinalTable(t *testing.T) {
	h := NewService(State{
		TournamentID:     "tour_live",
		PlayersRemaining: 9,
		LiveTables: []LiveTable{
			{TableID: tableID("tour_live", 1), PlayerCount: 5},
			{TableID: tableID("tour_live", 2), PlayerCount: 4},
		},
		Tournaments: []TournamentPlan{{
			TournamentID:    "tour_live",
			SeatAssignments: makeAssignmentsForCounts("tour_live", []int{5, 4}),
		}},
	}, nil)

	plan := h.BuildTransitionPlan()
	require.Equal(t, TransitionFinalTable, plan.Decision)
	require.Len(t, uniqueTables(plan.SeatAssignments), 1)
	require.Equal(t, 9, countAssignmentsOnTable(plan.SeatAssignments, tableID("tour_live", 1)))
}

func TestTargetTableCountKeepsNineteenPlayersThreeHanded(t *testing.T) {
	require.Equal(t, 3, targetTableCount(19))
	require.Equal(t, 3, targetTableCount(20))
}

func newLiveHubForTest(t *testing.T, playersRemaining, activeTables int) *Service {
	t.Helper()

	liveTables := make([]LiveTable, 0, activeTables)
	for i := 1; i <= activeTables; i++ {
		liveTables = append(liveTables, LiveTable{
			TableID:     tableID("tour_live", i),
			PlayerCount: playersRemaining / activeTables,
		})
	}

	return NewService(State{
		TournamentID:     "tour_live",
		PlayersRemaining: playersRemaining,
		LiveTables:       liveTables,
		ClosedTables:     map[string]bool{},
	}, nil)
}

func countAssignmentsOnTable(assignments []SeatAssignment, tableID string) int {
	count := 0
	for _, assignment := range assignments {
		if assignment.TableID == tableID {
			count++
		}
	}
	return count
}

func uniqueTables(assignments []SeatAssignment) map[string]struct{} {
	tables := make(map[string]struct{})
	for _, assignment := range assignments {
		tables[assignment.TableID] = struct{}{}
	}
	return tables
}

func makeAssignmentsForCounts(tournamentID string, counts []int) []SeatAssignment {
	assignments := make([]SeatAssignment, 0)
	entrantSeq := 1
	for tableNo, count := range counts {
		for seatNo := 1; seatNo <= count; seatNo++ {
			assignments = append(assignments, SeatAssignment{
				EntrantID: "e" + twoDigits(entrantSeq),
				MinerID:   "m" + twoDigits(entrantSeq),
				TableID:   tableID(tournamentID, tableNo+1),
				TableNo:   tableNo + 1,
				SeatNo:    seatNo,
			})
			entrantSeq++
		}
	}
	return assignments
}

func twoDigits(value int) string {
	return fmt.Sprintf("%02d", value)
}

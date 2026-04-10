package hub

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

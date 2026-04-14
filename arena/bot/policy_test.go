package bot

import (
	"math/rand"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestRandomPolicyReturnsOnlyLegalAction(t *testing.T) {
	policy := RandomPolicy{Rand: rand.New(rand.NewSource(7))}

	decision, ok, err := policy.Decide(
		SeatAssignment{SeatNo: 3},
		LiveTable{
			ActingSeatNo: 3,
			CurrentPhase: "wager",
			LegalActions: []string{"check"},
			VisibleStacks: []VisibleStack{
				{SeatNo: 3, Stack: 1000},
			},
		},
	)
	require.NoError(t, err)
	require.True(t, ok)
	require.Equal(t, Decision{ActionType: "check"}, decision)
}

func TestRandomPolicyRaiseStaysWithinBounds(t *testing.T) {
	policy := RandomPolicy{Rand: rand.New(rand.NewSource(11))}

	decision, ok, err := policy.Decide(
		SeatAssignment{SeatNo: 4},
		LiveTable{
			ActingSeatNo:  4,
			CurrentPhase:  "wager",
			CurrentToCall: 50,
			MinRaiseTo:    150,
			MaxRaiseTo:    400,
			LegalActions:  []string{"raise"},
			VisibleStacks: []VisibleStack{
				{SeatNo: 4, Stack: 1000},
			},
		},
	)
	require.NoError(t, err)
	require.True(t, ok)
	require.Equal(t, "raise", decision.ActionType)
	require.GreaterOrEqual(t, decision.Amount, int64(150))
	require.LessOrEqual(t, decision.Amount, int64(400))
}

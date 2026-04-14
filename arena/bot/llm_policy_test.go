package bot

import (
	"context"
	"encoding/json"
	"errors"
	"testing"

	"github.com/stretchr/testify/require"
)

type stubChatClient struct {
	output string
	err    error
	calls  int
}

func (s *stubChatClient) Complete(context.Context, string, string) (string, error) {
	s.calls++
	if s.err != nil {
		return "", s.err
	}
	return s.output, nil
}

type stubPolicy struct {
	decision Decision
	ok       bool
	err      error
	calls    int
}

func (s *stubPolicy) Decide(SeatAssignment, LiveTable) (Decision, bool, error) {
	s.calls++
	return s.decision, s.ok, s.err
}

func TestLLMPolicyParsesStrictJSONDecision(t *testing.T) {
	chat := &stubChatClient{
		output: "```json\n{\"action_type\":\"raise\",\"amount\":150,\"reason\":\"pressure weak range\"}\n```",
	}
	fallback := &stubPolicy{}
	policy := NewLLMPolicy(chat, fallback)

	decision, ok, err := policy.Decide(
		SeatAssignment{SeatNo: 2},
		LiveTable{
			ActingSeatNo:  2,
			CurrentPhase:  "wager",
			CurrentToCall: 100,
			MinRaiseTo:    150,
			MaxRaiseTo:    999,
			LegalActions:  []string{"call", "fold", "raise", "all_in"},
			VisibleStacks: []VisibleStack{
				{SeatNo: 1, Stack: 900},
				{SeatNo: 2, Stack: 1000},
			},
		},
	)
	require.NoError(t, err)
	require.True(t, ok)
	require.Equal(t, Decision{ActionType: "raise", Amount: 150, Reason: "pressure weak range"}, decision)
	require.Equal(t, 1, chat.calls)
	require.Equal(t, 0, fallback.calls)
}

func TestLLMPolicyFallsBackWhenModelReturnsIllegalAction(t *testing.T) {
	chat := &stubChatClient{
		output: "{\"action_type\":\"dance\",\"amount\":0,\"reason\":\"hallucinated\"}",
	}
	fallback := &stubPolicy{
		decision: Decision{ActionType: "call"},
		ok:       true,
	}
	policy := NewLLMPolicy(chat, fallback)

	decision, ok, err := policy.Decide(
		SeatAssignment{SeatNo: 2},
		LiveTable{
			ActingSeatNo:  2,
			CurrentPhase:  "wager",
			CurrentToCall: 100,
			LegalActions:  []string{"call", "fold", "all_in"},
			VisibleStacks: []VisibleStack{
				{SeatNo: 2, Stack: 1000},
			},
		},
	)
	require.NoError(t, err)
	require.True(t, ok)
	require.Equal(t, Decision{ActionType: "call"}, decision)
	require.Equal(t, 1, chat.calls)
	require.Equal(t, 1, fallback.calls)
}

func TestLLMPolicyFallsBackWhenClientFails(t *testing.T) {
	chat := &stubChatClient{err: errors.New("upstream failed")}
	fallback := &stubPolicy{
		decision: Decision{ActionType: "all_in"},
		ok:       true,
	}
	policy := NewLLMPolicy(chat, fallback)

	decision, ok, err := policy.Decide(
		SeatAssignment{SeatNo: 1},
		LiveTable{
			ActingSeatNo: 1,
			CurrentPhase: "wager",
			LegalActions: []string{"all_in", "fold"},
			VisibleStacks: []VisibleStack{
				{SeatNo: 1, Stack: 80},
			},
		},
	)
	require.NoError(t, err)
	require.True(t, ok)
	require.Equal(t, Decision{ActionType: "all_in"}, decision)
	require.Equal(t, 1, fallback.calls)
}

func TestLLMUserPromptIncludesBlindLevelContext(t *testing.T) {
	raw := llmUserPrompt(
		SeatAssignment{TableID: "tbl:test:01", SeatNo: 3, StateSeq: 17},
		LiveTable{
			ActingSeatNo:  3,
			LevelNo:       2,
			SmallBlind:    50,
			BigBlind:      100,
			Ante:          10,
			CurrentPhase:  "wager",
			CurrentToCall: 110,
			MinRaiseTo:    210,
			MaxRaiseTo:    999,
			LegalActions:  []string{"call", "fold", "raise", "all_in"},
		},
	)

	var payload map[string]any
	require.NoError(t, json.Unmarshal([]byte(raw), &payload))
	require.Equal(t, float64(2), payload["level_no"])
	require.Equal(t, float64(50), payload["small_blind"])
	require.Equal(t, float64(100), payload["big_blind"])
	require.Equal(t, float64(10), payload["ante"])
	require.Equal(t, float64(110), payload["current_to_call"])
	require.Equal(t, float64(210), payload["min_raise_to"])
}

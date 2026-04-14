package bot

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
)

type LLMPolicy struct {
	chat     ChatClient
	fallback Policy
}

type llmDecisionPayload struct {
	ActionType string `json:"action_type"`
	Amount     int64  `json:"amount"`
	Reason     string `json:"reason"`
}

func NewLLMPolicy(chat ChatClient, fallback Policy) *LLMPolicy {
	if fallback == nil {
		fallback = HeuristicPolicy{}
	}
	return &LLMPolicy{
		chat:     chat,
		fallback: fallback,
	}
}

func (p *LLMPolicy) Decide(assignment SeatAssignment, view LiveTable) (Decision, bool, error) {
	if assignment.SeatNo != view.ActingSeatNo {
		return Decision{}, false, nil
	}
	if p.chat == nil {
		return p.fallback.Decide(assignment, view)
	}

	raw, err := p.chat.Complete(context.Background(), llmSystemPrompt(), llmUserPrompt(assignment, view))
	if err != nil {
		return p.fallback.Decide(assignment, view)
	}

	decision, err := parseLLMDecision(raw, view)
	if err != nil {
		return p.fallback.Decide(assignment, view)
	}
	return decision, true, nil
}

func llmSystemPrompt() string {
	return "You are a tournament bot. Return exactly one JSON object with action_type, amount, and reason. Do not include markdown or extra text."
}

func llmUserPrompt(assignment SeatAssignment, view LiveTable) string {
	payload := map[string]any{
		"seat_no":             assignment.SeatNo,
		"table_id":            assignment.TableID,
		"state_seq":           assignment.StateSeq,
		"level_no":            view.LevelNo,
		"small_blind":         view.SmallBlind,
		"big_blind":           view.BigBlind,
		"ante":                view.Ante,
		"current_phase":       view.CurrentPhase,
		"acting_seat_no":      view.ActingSeatNo,
		"current_to_call":     view.CurrentToCall,
		"min_raise_to":        view.MinRaiseTo,
		"max_raise_to":        view.MaxRaiseTo,
		"legal_actions":       view.LegalActions,
		"visible_stacks":      view.VisibleStacks,
		"seat_public_actions": view.SeatPublicActions,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Sprintf("{\"seat_no\":%d,\"current_phase\":%q}", assignment.SeatNo, view.CurrentPhase)
	}
	return string(body)
}

func parseLLMDecision(raw string, view LiveTable) (Decision, error) {
	jsonText, err := extractJSONObject(raw)
	if err != nil {
		return Decision{}, err
	}

	var payload llmDecisionPayload
	if err := json.Unmarshal([]byte(jsonText), &payload); err != nil {
		return Decision{}, err
	}
	if err := validateLLMDecision(payload, view); err != nil {
		return Decision{}, err
	}

	decision := Decision{
		ActionType: payload.ActionType,
		Reason:     strings.TrimSpace(payload.Reason),
	}
	if payload.ActionType == "raise" {
		decision.Amount = payload.Amount
	}
	return decision, nil
}

func extractJSONObject(raw string) (string, error) {
	start := strings.Index(raw, "{")
	end := strings.LastIndex(raw, "}")
	if start < 0 || end < start {
		return "", fmt.Errorf("llm response missing json object")
	}
	return raw[start : end+1], nil
}

func validateLLMDecision(payload llmDecisionPayload, view LiveTable) error {
	if payload.ActionType == "" {
		return fmt.Errorf("llm response missing action_type")
	}

	legal := make(map[string]bool, len(view.LegalActions))
	for _, action := range view.LegalActions {
		legal[action] = true
	}
	if !legal[payload.ActionType] {
		return fmt.Errorf("illegal action %q", payload.ActionType)
	}

	if payload.ActionType != "raise" {
		return nil
	}
	if payload.Amount <= 0 {
		return fmt.Errorf("raise amount must be positive")
	}
	if view.MinRaiseTo > 0 && payload.Amount < view.MinRaiseTo {
		return fmt.Errorf("raise amount %d below minimum %d", payload.Amount, view.MinRaiseTo)
	}
	if view.MaxRaiseTo > 0 && payload.Amount > view.MaxRaiseTo {
		return fmt.Errorf("raise amount %d above maximum %d", payload.Amount, view.MaxRaiseTo)
	}
	return nil
}

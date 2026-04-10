package projector

import (
	"encoding/json"
	"fmt"

	"github.com/clawchain/clawchain/arena/model"
)

type PostgameView struct {
	CompletedReason    string `json:"completed_reason"`
	ConfidenceBucket   string `json:"confidence_bucket"`
	NoMultiplier       bool   `json:"no_multiplier"`
	NoMultiplierReason string `json:"no_multiplier_reason"`
	StageReached       string `json:"stage_reached"`
}

type PostgameProjector struct {
	seen  map[string]struct{}
	views map[string]PostgameView
}

func NewPostgameProjector() *PostgameProjector {
	return &PostgameProjector{
		seen:  make(map[string]struct{}),
		views: make(map[string]PostgameView),
	}
}

func (p *PostgameProjector) Apply(evt model.EventLogEntry) error {
	if evt.EventType != "tournament.completed" {
		return nil
	}
	if _, ok := p.seen[evt.EventID]; ok {
		return nil
	}

	var payload struct {
		CompletedReason    string  `json:"completed_reason"`
		ConfidenceWeight   float64 `json:"confidence_weight"`
		NoMultiplier       bool    `json:"no_multiplier"`
		NoMultiplierReason string  `json:"no_multiplier_reason"`
		StageReached       string  `json:"stage_reached"`
	}
	if err := json.Unmarshal(evt.Payload, &payload); err != nil {
		return err
	}

	p.seen[evt.EventID] = struct{}{}
	p.views[evt.TournamentID] = PostgameView{
		CompletedReason:    payload.CompletedReason,
		ConfidenceBucket:   fmt.Sprintf("%.2f", payload.ConfidenceWeight),
		NoMultiplier:       payload.NoMultiplier,
		NoMultiplierReason: payload.NoMultiplierReason,
		StageReached:       payload.StageReached,
	}
	return nil
}

func (p *PostgameProjector) View(tournamentID string) (PostgameView, bool) {
	view, ok := p.views[tournamentID]
	return view, ok
}

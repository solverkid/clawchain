package projector

import (
	"encoding/json"

	"github.com/clawchain/clawchain/arena/model"
)

type StandingView struct {
	PlayersRemaining int    `json:"players_remaining"`
	RankBand         string `json:"rank_band"`
}

type StandingProjector struct {
	seen         map[string]struct{}
	appliedCount map[string]int
	views        map[string]StandingView
}

func NewStandingProjector() *StandingProjector {
	return &StandingProjector{
		seen:         make(map[string]struct{}),
		appliedCount: make(map[string]int),
		views:        make(map[string]StandingView),
	}
}

func (p *StandingProjector) Apply(evt model.EventLogEntry) error {
	if evt.EventType != "tournament.standing.refreshed" {
		return nil
	}
	if _, ok := p.seen[evt.EventID]; ok {
		return nil
	}

	var payload StandingView
	if err := json.Unmarshal(evt.Payload, &payload); err != nil {
		return err
	}

	p.seen[evt.EventID] = struct{}{}
	p.appliedCount[evt.EventID]++
	p.views[evt.TournamentID] = payload
	return nil
}

func (p *StandingProjector) AppliedCount(eventID string) int {
	return p.appliedCount[eventID]
}

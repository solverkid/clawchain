package projector

import (
	"encoding/json"

	"github.com/clawchain/clawchain/arena/model"
)

type LiveTableView struct {
	ActingSeatNo int   `json:"acting_seat_no"`
	PotMain      int64 `json:"pot_main"`
}

type LiveTableProjector struct {
	seen  map[string]struct{}
	views map[string]map[string]LiveTableView
}

func NewLiveTableProjector() *LiveTableProjector {
	return &LiveTableProjector{
		seen:  make(map[string]struct{}),
		views: make(map[string]map[string]LiveTableView),
	}
}

func (p *LiveTableProjector) Apply(evt model.EventLogEntry) error {
	if evt.EventType != "table.snapshot.updated" {
		return nil
	}
	if _, ok := p.seen[evt.EventID]; ok {
		return nil
	}

	var payload LiveTableView
	if err := json.Unmarshal(evt.Payload, &payload); err != nil {
		return err
	}

	if p.views[evt.TournamentID] == nil {
		p.views[evt.TournamentID] = make(map[string]LiveTableView)
	}
	p.seen[evt.EventID] = struct{}{}
	p.views[evt.TournamentID][evt.TableID] = payload
	return nil
}

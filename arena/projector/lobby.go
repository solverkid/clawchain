package projector

import "github.com/clawchain/clawchain/arena/model"

type Projectors struct {
	lobby    *LobbyProjector
	standing *StandingProjector
	live     *LiveTableProjector
	postgame *PostgameProjector
}

func NewProjectors() *Projectors {
	return &Projectors{
		lobby:    NewLobbyProjector(),
		standing: NewStandingProjector(),
		live:     NewLiveTableProjector(),
		postgame: NewPostgameProjector(),
	}
}

func (p *Projectors) Apply(evt model.EventLogEntry) error {
	if err := p.lobby.Apply(evt); err != nil {
		return err
	}
	if err := p.standing.Apply(evt); err != nil {
		return err
	}
	if err := p.live.Apply(evt); err != nil {
		return err
	}
	if err := p.postgame.Apply(evt); err != nil {
		return err
	}
	return nil
}

func (p *Projectors) Standing() *StandingProjector {
	return p.standing
}

func (p *Projectors) Postgame(tournamentID string) (PostgameView, bool) {
	return p.postgame.View(tournamentID)
}

type LobbyProjector struct {
	seen map[string]struct{}
}

func NewLobbyProjector() *LobbyProjector {
	return &LobbyProjector{seen: make(map[string]struct{})}
}

func (p *LobbyProjector) Apply(evt model.EventLogEntry) error {
	if _, ok := p.seen[evt.EventID]; ok {
		return nil
	}
	p.seen[evt.EventID] = struct{}{}
	return nil
}

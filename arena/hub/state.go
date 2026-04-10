package hub

import (
	"slices"
	"time"

	"github.com/clawchain/clawchain/arena/model"
)

type State struct {
	WaveID            string
	WaveState         model.WaveState
	StartedAt         time.Time
	Entrants          []model.Entrant
	Tournaments       []TournamentPlan
	republishUsed     bool
	pendingRepublish  bool
	snapshotStreamSeq int64
}

func (s State) result() PackResult {
	tournaments := make([]TournamentPlan, 0, len(s.Tournaments))
	for _, tournament := range s.Tournaments {
		copyPlan := tournament
		copyPlan.EntrantIDs = slices.Clone(tournament.EntrantIDs)
		copyPlan.SeatAssignments = slices.Clone(tournament.SeatAssignments)
		tournaments = append(tournaments, copyPlan)
	}

	return PackResult{Tournaments: tournaments}
}

func (s State) activeEntrants() []model.Entrant {
	entrants := make([]model.Entrant, 0, len(s.Entrants))
	for _, entrant := range s.Entrants {
		if entrant.RegistrationState == model.RegistrationStateRemovedBeforeStart {
			continue
		}
		entrants = append(entrants, entrant)
	}

	slices.SortFunc(entrants, func(a, b model.Entrant) int {
		if a.MinerID != b.MinerID {
			if a.MinerID < b.MinerID {
				return -1
			}
			return 1
		}
		if a.ID < b.ID {
			return -1
		}
		if a.ID > b.ID {
			return 1
		}
		return 0
	})

	return entrants
}

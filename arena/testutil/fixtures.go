package testutil

import (
	"fmt"
	"time"

	"github.com/clawchain/clawchain/arena/model"
)

func ConfirmedEntrants(waveID string, count int) []model.Entrant {
	entrants := make([]model.Entrant, 0, count)
	createdAt := time.Date(2026, time.April, 10, 9, 0, 0, 0, time.UTC)

	for i := 1; i <= count; i++ {
		entrants = append(entrants, model.Entrant{
			ID:                fmt.Sprintf("ent:%02d", i),
			WaveID:            waveID,
			MinerID:           fmt.Sprintf("miner-%02d", i),
			SeatAlias:         fmt.Sprintf("alias-%02d", i),
			RegistrationState: model.RegistrationStateConfirmed,
			TruthMetadata: model.TruthMetadata{
				PolicyBundleVersion: "policy-v1",
				StateHash:           fmt.Sprintf("entrant-state-%02d", i),
				PayloadHash:         fmt.Sprintf("entrant-payload-%02d", i),
			},
			CreatedAt: createdAt,
			UpdatedAt: createdAt,
		})
	}

	return entrants
}

package recovery

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/model"
)

func TestRecoverySynthesizesExpiredDeadlineTimeout(t *testing.T) {
	service := newRecoverableServiceForTest()

	require.NoError(t, service.RecoverTournament(context.Background(), "tour_1"))
	require.True(t, service.SawSyntheticTimeout("deadline-1"))
}

func newRecoverableServiceForTest() *Service {
	now := time.Date(2026, time.April, 10, 16, 0, 0, 0, time.UTC)

	return NewService(Store{
		Snapshots: map[string]model.TableSnapshot{
			"tour_1": {
				ID:           "tblsnap:tour_1:1",
				TournamentID: "tour_1",
				TableID:      "tbl:tour_1:01",
			},
		},
		Deadlines: []model.ActionDeadline{{
			DeadlineID:   "deadline-1",
			TournamentID: "tour_1",
			TableID:      "tbl:tour_1:01",
			HandID:       "hand:tour_1:01:0001",
			PhaseID:      "phase-signal-1",
			SeatID:       "seat:tbl:tour_1:01:07",
			DeadlineAt:   now.Add(-time.Second),
			Status:       "open",
		}},
	}, func() time.Time { return now })
}

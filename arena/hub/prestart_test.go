package hub

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/testutil"
)

func TestRatedShardStartsOnlyAt56To64(t *testing.T) {
	h, _ := newHubForTest(t, 64)

	result, err := h.LockAndPack(context.Background())
	require.NoError(t, err)
	require.Len(t, result.Tournaments, 1)
	require.Equal(t, string(model.RatedMode), result.Tournaments[0].RatedOrPractice)
	require.False(t, result.Tournaments[0].NoMultiplier)
	require.Len(t, result.Tournaments[0].EntrantIDs, 64)
}

func TestRatedUnderfillDowngrades48To55ToPractice(t *testing.T) {
	h, _ := newHubForTest(t, 52)

	result, err := h.LockAndPack(context.Background())
	require.NoError(t, err)
	require.Len(t, result.Tournaments, 1)
	require.Equal(t, string(model.PracticeMode), result.Tournaments[0].RatedOrPractice)
	require.True(t, result.Tournaments[0].NoMultiplier)
	require.Len(t, result.Tournaments[0].EntrantIDs, 52)
}

func TestSeatsPublishedAllowsSingleShardLocalRepublish(t *testing.T) {
	h, recorder := newHubForTest(t, 64)

	_, err := h.LockAndPack(context.Background())
	require.NoError(t, err)
	require.NoError(t, h.PublishSeats(context.Background()))
	require.NoError(t, h.ForceRemoveBeforeStart(context.Background(), "miner-07"))
	require.NoError(t, h.RepublishSeats(context.Background()))
	require.ErrorContains(t, h.RepublishSeats(context.Background()), "republish already used")

	result := h.Result()
	require.Len(t, result.Tournaments, 1)
	require.Len(t, result.Tournaments[0].EntrantIDs, 63)
	require.Len(t, recorder.interventions, 1)
	require.NotEmpty(t, recorder.reseats)
	require.GreaterOrEqual(t, len(recorder.snapshots), 2)
}

func TestInitialSeatAssignmentsBalanceUnderfilledField(t *testing.T) {
	h, _ := newHubForTest(t, 43)

	result, err := h.LockAndPack(context.Background())
	require.NoError(t, err)
	require.Len(t, result.Tournaments, 1)
	assignments := result.Tournaments[0].SeatAssignments

	require.Len(t, uniqueTables(assignments), 5)
	require.Equal(t, 9, countAssignmentsOnTable(assignments, tableID(result.Tournaments[0].TournamentID, 1)))
	require.Equal(t, 9, countAssignmentsOnTable(assignments, tableID(result.Tournaments[0].TournamentID, 2)))
	require.Equal(t, 9, countAssignmentsOnTable(assignments, tableID(result.Tournaments[0].TournamentID, 3)))
	require.Equal(t, 8, countAssignmentsOnTable(assignments, tableID(result.Tournaments[0].TournamentID, 4)))
	require.Equal(t, 8, countAssignmentsOnTable(assignments, tableID(result.Tournaments[0].TournamentID, 5)))
}

func TestInitialSeatAssignmentsUseShuffledDrawNotSequentialMinerOrder(t *testing.T) {
	h, _ := newHubForTest(t, 16)

	result, err := h.LockAndPack(context.Background())
	require.NoError(t, err)
	require.Len(t, result.Tournaments, 1)

	firstTable := make([]string, 0, 8)
	for _, assignment := range result.Tournaments[0].SeatAssignments {
		if assignment.TableNo != 1 {
			continue
		}
		firstTable = append(firstTable, assignment.MinerID)
	}
	require.NotEqual(t, []string{
		"miner-01", "miner-02", "miner-03", "miner-04",
		"miner-05", "miner-06", "miner-07", "miner-08",
	}, firstTable)
}

func newHubForTest(t *testing.T, entrants int) (*Service, *recordingStore) {
	t.Helper()

	start := time.Date(2026, time.April, 10, 12, 0, 0, 0, time.UTC)
	waveID := model.WaveID(model.RatedMode, start)
	recorder := &recordingStore{}

	return NewService(State{
		WaveID:    waveID,
		WaveState: model.WaveStateRegistrationOpen,
		Entrants:  testutil.ConfirmedEntrants(waveID, entrants),
		StartedAt: start,
	}, recorder), recorder
}

type recordingStore struct {
	snapshots     []model.TournamentSnapshot
	interventions []model.OperatorIntervention
	reseats       []model.ReseatEvent
}

func (r *recordingStore) SaveTournamentSnapshot(_ context.Context, snapshot model.TournamentSnapshot) error {
	r.snapshots = append(r.snapshots, snapshot)
	return nil
}

func (r *recordingStore) UpsertOperatorIntervention(_ context.Context, intervention model.OperatorIntervention) error {
	r.interventions = append(r.interventions, intervention)
	return nil
}

func (r *recordingStore) AppendReseatEvents(_ context.Context, events []model.ReseatEvent) error {
	r.reseats = append(r.reseats, events...)
	return nil
}

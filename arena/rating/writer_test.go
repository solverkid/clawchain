package rating

import (
	"context"
	"database/sql"
	"math"
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/store/postgres"
)

const defaultArenaTestDatabaseURL = "postgres://clawchain:clawchain_dev_pw@127.0.0.1:55432/arena_runtime_test?sslmode=disable"

func TestPracticeTournamentDoesNotChangeMultiplier(t *testing.T) {
	writer := newRatingWriterForTest(t)

	out := writer.ApplyCompletedTournament(fixturePracticeCompletion())

	require.True(t, out.NoMultiplier)
	require.Equal(t, 1.0, out.Items[0].MultiplierAfter)
}

func TestFirst15EligibleTournamentsClampMultiplierToOne(t *testing.T) {
	writer := newRatingWriterForTest(t)

	for i := 0; i < 15; i++ {
		_ = writer.ApplyCompletedTournament(fixtureRatedCompletion("miner-1", 0.90))
	}

	last := writer.ApplyCompletedTournament(fixtureRatedCompletion("miner-1", 0.90))
	require.True(t, last.Items[0].MultiplierAfter >= 1.0)
	require.True(t, last.Items[0].MultiplierAfter <= 1.04)
}

func TestCompatibilityWriteFailsFastWhenSharedHarnessTablesMissing(t *testing.T) {
	writer := newRatingWriterAgainstBareArenaSchema(t)

	err := writer.OnTournamentCompleted(context.Background(), fixtureRatedCompletion("miner-1", 0.90))

	require.ErrorContains(t, err, "miners table missing")
}

func TestRatedCompletionUpdatesMuSigmaReliabilityAndPublicELO(t *testing.T) {
	writer := newRatingWriterForTest(t)

	out := writer.ApplyCompletedTournament(fixtureRatedCompletion("miner-1", 0.90))

	require.NotZero(t, out.Items[0].MuAfter)
	require.NotZero(t, out.Items[0].SigmaAfter)
	require.NotZero(t, out.Items[0].ArenaReliabilityAfter)
	require.NotZero(t, out.Items[0].PublicELOAfter)
}

func TestSingleTournamentMultiplierMoveIsCappedAtOneBasisStep(t *testing.T) {
	writer := newRatingWriterForTest(t)

	before := writer.CurrentMultiplier("miner-1")
	out := writer.ApplyCompletedTournament(fixtureRatedCompletion("miner-1", 0.90))
	after := out.Items[0].MultiplierAfter

	require.LessOrEqual(t, math.Abs(after-before), 0.01)
}

func TestBootstrapRestoresMultiplierAndEligibleTournamentCount(t *testing.T) {
	repo := newMemoryRepository()
	repo.runtimeStates = []model.RatingRuntimeState{{
		MinerAddress:            "miner-1",
		Mu:                      28.0,
		Sigma:                   7.0,
		ArenaReliability:        1.2,
		PublicELO:               1260,
		PublicRank:              4,
		Multiplier:              1.23,
		EligibleTournamentCount: 16,
	}}

	writer := NewWriter(repo, func() time.Time {
		return time.Date(2026, time.April, 10, 18, 0, 0, 0, time.UTC)
	})

	require.NoError(t, writer.Bootstrap(context.Background()))
	require.Equal(t, 1.23, writer.CurrentMultiplier("miner-1"))

	out := writer.ApplyCompletedTournament(fixtureRatedCompletion("miner-1", 0.90))
	require.Equal(t, 1.24, out.Items[0].MultiplierAfter)
	require.InDelta(t, 28.0+((0.90-0.5)*4), out.Items[0].MuAfter, 0.001)
}

func newRatingWriterForTest(t *testing.T) *Writer {
	t.Helper()

	return NewWriter(newMemoryRepository(), func() time.Time {
		return time.Date(2026, time.April, 10, 18, 0, 0, 0, time.UTC)
	})
}

func newRatingWriterAgainstBareArenaSchema(t *testing.T) *Writer {
	t.Helper()

	databaseURL := os.Getenv("ARENA_TEST_DATABASE_URL")
	if databaseURL == "" {
		databaseURL = defaultArenaTestDatabaseURL
	}

	db, err := sql.Open("postgres", databaseURL)
	require.NoError(t, err)

	t.Cleanup(func() {
		require.NoError(t, db.Close())
	})

	require.NoError(t, db.Ping())
	resetPublicSchema(t, db)

	repo, err := postgres.NewRepository(db)
	require.NoError(t, err)

	return NewWriter(repo, func() time.Time {
		return time.Date(2026, time.April, 10, 18, 0, 0, 0, time.UTC)
	})
}

func resetPublicSchema(t *testing.T, db *sql.DB) {
	t.Helper()

	for _, stmt := range []string{
		"DROP SCHEMA IF EXISTS public CASCADE",
		"CREATE SCHEMA IF NOT EXISTS public",
		"GRANT ALL ON SCHEMA public TO public",
	} {
		_, err := db.Exec(stmt)
		require.NoError(t, err)
	}
}

func fixturePracticeCompletion() Completion {
	return Completion{
		TournamentID: "tour_practice",
		Mode:         model.PracticeMode,
		HumanOnly:    true,
		SeasonID:     "season-1",
		CompletedAt:  time.Date(2026, time.April, 10, 18, 0, 0, 0, time.UTC),
		Entrants: []CompletedEntrant{{
			EntrantID:           "ent:practice:1",
			MinerAddress:        "miner-practice-1",
			Name:                "practice-1",
			EconomicUnitID:      "econ-practice-1",
			FinishRank:          1,
			FinishPercentile:    1.0,
			HandsPlayed:         12,
			MeaningfulDecisions: 8,
			StageReached:        "practice_finish",
			TournamentScore:     0.80,
		}},
	}
}

func fixtureRatedCompletion(minerAddress string, score float64) Completion {
	return Completion{
		TournamentID: "tour_rated",
		Mode:         model.RatedMode,
		HumanOnly:    true,
		SeasonID:     "season-1",
		CompletedAt:  time.Date(2026, time.April, 10, 18, 0, 0, 0, time.UTC),
		Entrants: []CompletedEntrant{{
			EntrantID:           "ent:rated:1",
			MinerAddress:        minerAddress,
			Name:                minerAddress,
			EconomicUnitID:      "econ-" + minerAddress,
			FinishRank:          1,
			FinishPercentile:    1.0,
			HandsPlayed:         24,
			MeaningfulDecisions: 16,
			StageReached:        "final_table",
			TournamentScore:     score,
		}},
	}
}

type memoryRepository struct {
	runtimeStates []model.RatingRuntimeState
}

func newMemoryRepository() *memoryRepository {
	return &memoryRepository{}
}

func (r *memoryRepository) AppendRatingInputs(context.Context, []model.RatingInput) error {
	return nil
}

func (r *memoryRepository) AppendCollusionMetrics(context.Context, []model.CollusionMetric) error {
	return nil
}

func (r *memoryRepository) UpsertRatingState(context.Context, model.RatingState) error {
	return nil
}

func (r *memoryRepository) SaveRatingSnapshot(context.Context, model.RatingSnapshot) error {
	return nil
}

func (r *memoryRepository) SavePublicLadderSnapshot(context.Context, model.PublicLadderSnapshot) error {
	return nil
}

func (r *memoryRepository) SaveMultiplierSnapshot(context.Context, model.MultiplierSnapshot) error {
	return nil
}

func (r *memoryRepository) UpsertMinerCompatibility(context.Context, model.MinerCompatibility) error {
	return nil
}

func (r *memoryRepository) UpsertArenaResultEntry(context.Context, model.ArenaResultEntry) error {
	return nil
}

func (r *memoryRepository) AssertSharedHarnessTables(context.Context) error {
	return nil
}

func (r *memoryRepository) LoadPersistedMinerStates(context.Context) ([]model.RatingRuntimeState, error) {
	return append([]model.RatingRuntimeState(nil), r.runtimeStates...), nil
}

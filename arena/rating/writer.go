package rating

import (
	"context"
	"errors"
	"fmt"
	"math"
	"sort"
	"time"

	"github.com/clawchain/clawchain/arena/model"
)

type repository interface {
	AppendRatingInputs(ctx context.Context, inputs []model.RatingInput) error
	AppendCollusionMetrics(ctx context.Context, metrics []model.CollusionMetric) error
	UpsertRatingState(ctx context.Context, state model.RatingState) error
	SaveRatingSnapshot(ctx context.Context, snapshot model.RatingSnapshot) error
	SavePublicLadderSnapshot(ctx context.Context, snapshot model.PublicLadderSnapshot) error
	SaveMultiplierSnapshot(ctx context.Context, snapshot model.MultiplierSnapshot) error
	UpsertMinerCompatibility(ctx context.Context, miner model.MinerCompatibility) error
	UpsertArenaResultEntry(ctx context.Context, entry model.ArenaResultEntry) error
	AssertSharedHarnessTables(ctx context.Context) error
}

type Writer struct {
	repo   repository
	now    func() time.Time
	states map[string]minerState
}

func NewWriter(repo repository, now func() time.Time) *Writer {
	if now == nil {
		now = time.Now().UTC
	}

	return &Writer{
		repo:   repo,
		now:    now,
		states: make(map[string]minerState),
	}
}

func (w *Writer) CurrentMultiplier(minerAddress string) float64 {
	return w.currentState(minerAddress).Multiplier
}

func (w *Writer) ApplyCompletedTournament(completion Completion) Outcome {
	appliedAt := defaultCompletionTime(completion.CompletedAt, w.now())
	weights := make([]float64, len(completion.Entrants))
	noMultiplier, noMultiplierReason := resolveTournamentMultiplierGate(completion, weights)

	outcome := Outcome{
		NoMultiplier:       noMultiplier,
		NoMultiplierReason: noMultiplierReason,
		Items:              make([]OutcomeItem, 0, len(completion.Entrants)),
	}

	for idx, entrant := range completion.Entrants {
		state := w.currentState(entrant.MinerAddress)
		weight := weights[idx]
		effectiveScore := entrant.TournamentScore * weight
		ratingEligible := completion.Mode == model.RatedMode && completion.HumanOnly && !outcome.NoMultiplier && weight > 0

		next := state
		if ratingEligible {
			next.Mu = state.Mu + ((effectiveScore - 0.5) * 4)
			next.Sigma = clampFloat(state.Sigma-(0.25*weight), 1.0, defaultSigma)
			next.ArenaReliability = clampFloat(state.ArenaReliability+(0.10*weight), 0.25, 2.0)
			next.PublicELO = state.PublicELO + int(math.Round((effectiveScore-0.5)*40))
		}

		eligibleForMultiplier := ratingEligible
		if eligibleForMultiplier {
			next.EligibleTournamentCount++
			if next.EligibleTournamentCount <= warmupClampEligibleCount {
				next.Multiplier = defaultMultiplier
			} else {
				delta := clampFloat((effectiveScore-0.5)/40.0, -maxMultiplierStep, maxMultiplierStep)
				next.Multiplier = clampFloat(round2(state.Multiplier+delta), 0.5, 2.0)
			}
		}

		conservativeSkill := next.Mu - (3 * next.Sigma)
		item := OutcomeItem{
			EntrantID:                entrant.EntrantID,
			MinerAddress:             entrant.MinerAddress,
			Name:                     defaultString(entrant.Name, entrant.MinerAddress),
			EconomicUnitID:           entrant.EconomicUnitID,
			FinishRank:               entrant.FinishRank,
			FinishPercentile:         entrant.FinishPercentile,
			HandsPlayed:              entrant.HandsPlayed,
			MeaningfulDecisions:      entrant.MeaningfulDecisions,
			AutoActions:              entrant.AutoActions,
			TimeoutActions:           entrant.TimeoutActions,
			InvalidActions:           entrant.InvalidActions,
			StageReached:             entrant.StageReached,
			StackPathSummary:         normalizeJSON(entrant.StackPathSummary),
			ScoreComponents:          normalizeJSON(entrant.ScoreComponents),
			Penalties:                normalizeJSON(entrant.Penalties),
			TournamentScore:          entrant.TournamentScore,
			EffectiveTournamentScore: effectiveScore,
			ConfidenceWeight:         weight,
			FieldStrengthAdjustment:  entrant.FieldStrengthAdjustment,
			BotAdjustment:            entrant.BotAdjustment,
			TimeCapAdjustment:        entrant.TimeCapAdjustment,
			EligibleForMultiplier:    eligibleForMultiplier,
			MuAfter:                  next.Mu,
			SigmaAfter:               next.Sigma,
			ArenaReliabilityAfter:    next.ArenaReliability,
			PublicELOAfter:           next.PublicELO,
			MultiplierBefore:         state.Multiplier,
			MultiplierAfter:          next.Multiplier,
			ConservativeSkill:        &conservativeSkill,
			Payload:                  normalizeJSON(entrant.Payload),
		}

		w.states[entrant.MinerAddress] = next
		outcome.Items = append(outcome.Items, item)
	}

	w.recomputePublicRanks()
	outcome.Items = w.attachPublicRanks(outcome.Items)
	outcome.buildPersistenceModels(completion, appliedAt)

	return outcome
}

func (w *Writer) OnTournamentCompleted(ctx context.Context, completion Completion) error {
	if w.repo == nil {
		return errors.New("rating repository is required")
	}

	if err := w.repo.AssertSharedHarnessTables(ctx); err != nil {
		return err
	}

	outcome := w.ApplyCompletedTournament(completion)

	if len(outcome.inputs) > 0 {
		if err := w.repo.AppendRatingInputs(ctx, outcome.inputs); err != nil {
			return fmt.Errorf("append rating inputs: %w", err)
		}
	}
	if len(outcome.collusionMetrics) > 0 {
		if err := w.repo.AppendCollusionMetrics(ctx, outcome.collusionMetrics); err != nil {
			return fmt.Errorf("append collusion metrics: %w", err)
		}
	}
	for _, state := range outcome.ratingStates {
		if err := w.repo.UpsertRatingState(ctx, state); err != nil {
			return fmt.Errorf("upsert rating state %s: %w", state.MinerAddress, err)
		}
	}
	for _, snapshot := range outcome.ratingSnapshots {
		if err := w.repo.SaveRatingSnapshot(ctx, snapshot); err != nil {
			return fmt.Errorf("save rating snapshot %s: %w", snapshot.ID, err)
		}
	}
	for _, snapshot := range outcome.ladderSnapshots {
		if err := w.repo.SavePublicLadderSnapshot(ctx, snapshot); err != nil {
			return fmt.Errorf("save public ladder snapshot %s: %w", snapshot.ID, err)
		}
	}
	for _, snapshot := range outcome.multiplierSnapshots {
		if err := w.repo.SaveMultiplierSnapshot(ctx, snapshot); err != nil {
			return fmt.Errorf("save multiplier snapshot %s: %w", snapshot.ID, err)
		}
	}
	for _, miner := range outcome.minerCompatibility {
		if err := w.repo.UpsertMinerCompatibility(ctx, miner); err != nil {
			return fmt.Errorf("upsert miner compatibility %s: %w", miner.Address, err)
		}
	}
	for _, entry := range outcome.resultEntries {
		if err := w.repo.UpsertArenaResultEntry(ctx, entry); err != nil {
			return fmt.Errorf("upsert arena result entry %s: %w", entry.ID, err)
		}
	}

	return nil
}

func (w *Writer) currentState(minerAddress string) minerState {
	state, ok := w.states[minerAddress]
	if !ok {
		return defaultMinerState()
	}
	return state
}

func (w *Writer) recomputePublicRanks() {
	type entry struct {
		address string
		state   minerState
	}

	ranked := make([]entry, 0, len(w.states))
	for address, state := range w.states {
		ranked = append(ranked, entry{address: address, state: state})
	}

	sort.Slice(ranked, func(i, j int) bool {
		if ranked[i].state.PublicELO == ranked[j].state.PublicELO {
			return ranked[i].address < ranked[j].address
		}
		return ranked[i].state.PublicELO > ranked[j].state.PublicELO
	})

	for idx, entry := range ranked {
		state := w.states[entry.address]
		state.PublicRank = idx + 1
		w.states[entry.address] = state
	}
}

func (w *Writer) attachPublicRanks(items []OutcomeItem) []OutcomeItem {
	for idx := range items {
		state := w.currentState(items[idx].MinerAddress)
		items[idx].PublicRankAfter = state.PublicRank
	}
	return items
}

func (o *Outcome) buildPersistenceModels(completion Completion, appliedAt time.Time) {
	for _, item := range o.Items {
		o.inputs = append(o.inputs, buildRatingInput(completion, item, appliedAt))
		o.collusionMetrics = append(o.collusionMetrics, buildCollusionMetrics(completion, item, appliedAt, o.NoMultiplier, o.NoMultiplierReason)...)
		o.ratingStates = append(o.ratingStates, buildRatingState(item, appliedAt))
		o.ratingSnapshots = append(o.ratingSnapshots, buildRatingSnapshot(completion, item, appliedAt))
		o.ladderSnapshots = append(o.ladderSnapshots, buildPublicLadderSnapshot(completion, item, appliedAt))
		o.multiplierSnapshots = append(o.multiplierSnapshots, buildMultiplierSnapshot(completion, item, appliedAt))
		o.minerCompatibility = append(o.minerCompatibility, buildMinerCompatibility(item, appliedAt))
		o.resultEntries = append(o.resultEntries, buildArenaResultEntry(completion, item, appliedAt))
	}
}

func resolveTournamentMultiplierGate(completion Completion, weights []float64) (bool, string) {
	if completion.NoMultiplier {
		return true, defaultString(completion.NoMultiplierReason, noMultiplierReasonExplicit)
	}
	if completion.Mode != model.RatedMode {
		return true, noMultiplierReasonPractice
	}
	if !completion.HumanOnly {
		return true, noMultiplierReasonNonHumanOnly
	}

	for idx, entrant := range completion.Entrants {
		weights[idx] = resolveConfidenceWeight(completion, entrant)
		if weights[idx] == 0 {
			return true, noMultiplierReasonZeroConfidence
		}
	}

	return false, ""
}

func resolveConfidenceWeight(completion Completion, entrant CompletedEntrant) float64 {
	if entrant.ConfidenceWeight > 0 {
		return bucketConfidenceWeight(entrant.ConfidenceWeight)
	}
	if completion.ConfidenceWeight > 0 {
		return bucketConfidenceWeight(completion.ConfidenceWeight)
	}
	if completion.Mode != model.RatedMode {
		return 0
	}
	if entrant.HandsPlayed >= 20 && entrant.MeaningfulDecisions >= 12 && entrant.TimeoutActions == 0 && entrant.InvalidActions == 0 {
		return 1.0
	}
	if entrant.HandsPlayed >= 12 && entrant.MeaningfulDecisions >= 8 {
		return 0.75
	}
	if entrant.HandsPlayed >= 8 && entrant.MeaningfulDecisions >= 5 {
		return 0.50
	}
	if entrant.HandsPlayed > 0 {
		return 0.25
	}
	return 0
}

func defaultCompletionTime(completedAt time.Time, now time.Time) time.Time {
	if completedAt.IsZero() {
		return now.UTC()
	}
	return completedAt.UTC()
}

func defaultString(value, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

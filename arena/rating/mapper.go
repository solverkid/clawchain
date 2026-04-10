package rating

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/clawchain/clawchain/arena/model"
)

func buildRatingInput(completion Completion, item OutcomeItem, at time.Time) model.RatingInput {
	inputID := fmt.Sprintf("ari:%s:%s", completion.TournamentID, item.MinerAddress)

	return model.RatingInput{
		ID:                      inputID,
		TournamentID:            completion.TournamentID,
		EntrantID:               item.EntrantID,
		MinerAddress:            item.MinerAddress,
		Mode:                    completion.Mode,
		HumanOnly:               completion.HumanOnly,
		FinishRank:              item.FinishRank,
		FinishPercentile:        item.FinishPercentile,
		HandsPlayed:             item.HandsPlayed,
		MeaningfulDecisions:     item.MeaningfulDecisions,
		AutoActions:             item.AutoActions,
		TimeoutActions:          item.TimeoutActions,
		InvalidActions:          item.InvalidActions,
		StageReached:            item.StageReached,
		StackPathSummary:        normalizeJSON(item.StackPathSummary),
		ScoreComponents:         normalizeJSON(item.ScoreComponents),
		Penalties:               normalizeJSON(item.Penalties),
		TournamentScore:         item.TournamentScore,
		ConfidenceWeight:        item.ConfidenceWeight,
		FieldStrengthAdjustment: item.FieldStrengthAdjustment,
		BotAdjustment:           item.BotAdjustment,
		TimeCapAdjustment:       item.TimeCapAdjustment,
		Payload: normalizeJSON(marshalJSON(map[string]any{
			"effective_tournament_score": item.EffectiveTournamentScore,
			"eligible_for_multiplier":    item.EligibleForMultiplier,
		})),
		TruthMetadata: truthMetadata(inputID),
		CreatedAt:     at,
	}
}

func buildCollusionMetrics(completion Completion, item OutcomeItem, at time.Time, noMultiplier bool, noMultiplierReason string) []model.CollusionMetric {
	basePayload := marshalJSON(map[string]any{
		"no_multiplier":        noMultiplier,
		"no_multiplier_reason": noMultiplierReason,
		"stage_reached":        item.StageReached,
	})

	return []model.CollusionMetric{
		{
			ID:            fmt.Sprintf("acm:%s:%s:%s", completion.TournamentID, item.MinerAddress, collusionMetricConfidenceWeight),
			TournamentID:  completion.TournamentID,
			MinerAddress:  item.MinerAddress,
			MetricName:    collusionMetricConfidenceWeight,
			MetricValue:   item.ConfidenceWeight,
			Payload:       basePayload,
			TruthMetadata: truthMetadata(fmt.Sprintf("acm:%s:%s:%s", completion.TournamentID, item.MinerAddress, collusionMetricConfidenceWeight)),
			CreatedAt:     at,
		},
		{
			ID:            fmt.Sprintf("acm:%s:%s:%s", completion.TournamentID, item.MinerAddress, collusionMetricEffectiveTournament),
			TournamentID:  completion.TournamentID,
			MinerAddress:  item.MinerAddress,
			MetricName:    collusionMetricEffectiveTournament,
			MetricValue:   item.EffectiveTournamentScore,
			Payload:       basePayload,
			TruthMetadata: truthMetadata(fmt.Sprintf("acm:%s:%s:%s", completion.TournamentID, item.MinerAddress, collusionMetricEffectiveTournament)),
			CreatedAt:     at,
		},
	}
}

func buildRatingState(item OutcomeItem, at time.Time) model.RatingState {
	payload := marshalJSON(map[string]any{
		"public_rank": item.PublicRankAfter,
	})

	return model.RatingState{
		MinerAddress:     item.MinerAddress,
		Mu:               item.MuAfter,
		Sigma:            item.SigmaAfter,
		ArenaReliability: item.ArenaReliabilityAfter,
		PublicELO:        item.PublicELOAfter,
		Payload:          payload,
		TruthMetadata:    truthMetadata(item.MinerAddress),
		UpdatedAt:        at,
	}
}

func buildRatingSnapshot(completion Completion, item OutcomeItem, at time.Time) model.RatingSnapshot {
	snapshotID := fmt.Sprintf("ratingsnap:%s:%s", completion.TournamentID, item.MinerAddress)

	return model.RatingSnapshot{
		ID:               snapshotID,
		MinerAddress:     item.MinerAddress,
		Mu:               item.MuAfter,
		Sigma:            item.SigmaAfter,
		ArenaReliability: item.ArenaReliabilityAfter,
		PublicELO:        item.PublicELOAfter,
		Payload:          marshalJSON(map[string]any{"public_rank": item.PublicRankAfter}),
		TruthMetadata:    truthMetadata(snapshotID),
		CreatedAt:        at,
	}
}

func buildPublicLadderSnapshot(completion Completion, item OutcomeItem, at time.Time) model.PublicLadderSnapshot {
	snapshotID := fmt.Sprintf("ladder:%s:%s", completion.TournamentID, item.MinerAddress)

	return model.PublicLadderSnapshot{
		ID:            snapshotID,
		SeasonID:      defaultSeasonID(completion.SeasonID),
		MinerAddress:  item.MinerAddress,
		PublicRank:    item.PublicRankAfter,
		PublicELO:     item.PublicELOAfter,
		Payload:       marshalJSON(map[string]any{"tournament_id": completion.TournamentID}),
		TruthMetadata: truthMetadata(snapshotID),
		CreatedAt:     at,
	}
}

func buildMultiplierSnapshot(completion Completion, item OutcomeItem, at time.Time) model.MultiplierSnapshot {
	snapshotID := fmt.Sprintf("mult:%s:%s", completion.TournamentID, item.MinerAddress)

	return model.MultiplierSnapshot{
		ID:                    snapshotID,
		TournamentID:          completion.TournamentID,
		MinerAddress:          item.MinerAddress,
		EligibleForMultiplier: item.EligibleForMultiplier,
		TournamentScore:       item.TournamentScore,
		ConfidenceWeight:      item.ConfidenceWeight,
		MultiplierBefore:      item.MultiplierBefore,
		MultiplierAfter:       item.MultiplierAfter,
		Payload: marshalJSON(map[string]any{
			"effective_tournament_score": item.EffectiveTournamentScore,
		}),
		TruthMetadata: truthMetadata(snapshotID),
		CreatedAt:     at,
	}
}

func buildMinerCompatibility(item OutcomeItem, at time.Time) model.MinerCompatibility {
	publicRank := item.PublicRankAfter

	return model.MinerCompatibility{
		Address:          item.MinerAddress,
		Name:             item.Name,
		Status:           "active",
		EconomicUnitID:   item.EconomicUnitID,
		AdmissionState:   "probation",
		ModelReliability: item.ArenaReliabilityAfter,
		OpsReliability:   defaultArenaReliability,
		ArenaMultiplier:  item.MultiplierAfter,
		PublicRank:       &publicRank,
		PublicELO:        item.PublicELOAfter,
		UpdatedAt:        at,
	}
}

func buildArenaResultEntry(completion Completion, item OutcomeItem, at time.Time) model.ArenaResultEntry {
	entryID := fmt.Sprintf("are:%s:%s", completion.TournamentID, item.MinerAddress)

	return model.ArenaResultEntry{
		ID:                    entryID,
		TournamentID:          completion.TournamentID,
		MinerAddress:          item.MinerAddress,
		Mode:                  completion.Mode,
		HumanOnly:             completion.HumanOnly,
		EligibleForMultiplier: item.EligibleForMultiplier,
		ArenaScore:            item.EffectiveTournamentScore,
		ConservativeSkill:     item.ConservativeSkill,
		MultiplierAfter:       item.MultiplierAfter,
		CreatedAt:             at,
		UpdatedAt:             at,
	}
}

func truthMetadata(id string) model.TruthMetadata {
	return model.TruthMetadata{
		SchemaVersion:       1,
		PolicyBundleVersion: "v1",
		StateHash:           id,
		PayloadHash:         id,
	}
}

func marshalJSON(payload any) json.RawMessage {
	raw, err := json.Marshal(payload)
	if err != nil {
		return json.RawMessage(`{}`)
	}
	return raw
}

func normalizeJSON(payload json.RawMessage) json.RawMessage {
	if len(payload) == 0 {
		return json.RawMessage(`{}`)
	}
	return payload
}

func defaultSeasonID(seasonID string) string {
	if seasonID == "" {
		return "arena-v1"
	}
	return seasonID
}

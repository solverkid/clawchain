package rating

import (
	"encoding/json"
	"math"
	"time"

	"github.com/clawchain/clawchain/arena/model"
)

const (
	defaultMu               = 25.0
	defaultSigma            = 8.333333
	defaultArenaReliability = 1.0
	defaultPublicELO        = 1200
	defaultMultiplier       = 1.0

	warmupClampEligibleCount = 15
	maxMultiplierStep        = 0.01
)

const (
	noMultiplierReasonExplicit         = "explicit_hold"
	noMultiplierReasonPractice         = "practice_tournament"
	noMultiplierReasonNonHumanOnly     = "non_human_only"
	noMultiplierReasonZeroConfidence   = "zero_confidence_weight"
	collusionMetricConfidenceWeight    = "confidence_weight"
	collusionMetricEffectiveTournament = "effective_tournament_score"
)

type Completion struct {
	TournamentID       string
	Mode               model.ArenaMode
	HumanOnly          bool
	NoMultiplier       bool
	NoMultiplierReason string
	SeasonID           string
	ConfidenceWeight   float64
	CompletedAt        time.Time
	Entrants           []CompletedEntrant
}

type CompletedEntrant struct {
	EntrantID               string
	MinerAddress            string
	Name                    string
	EconomicUnitID          string
	FinishRank              int
	FinishPercentile        float64
	HandsPlayed             int
	MeaningfulDecisions     int
	AutoActions             int
	TimeoutActions          int
	InvalidActions          int
	StageReached            string
	StackPathSummary        json.RawMessage
	ScoreComponents         json.RawMessage
	Penalties               json.RawMessage
	TournamentScore         float64
	ConfidenceWeight        float64
	FieldStrengthAdjustment float64
	BotAdjustment           float64
	TimeCapAdjustment       float64
	Payload                 json.RawMessage
}

type Outcome struct {
	NoMultiplier       bool
	NoMultiplierReason string
	Items              []OutcomeItem

	inputs              []model.RatingInput
	collusionMetrics    []model.CollusionMetric
	ratingStates        []model.RatingState
	ratingSnapshots     []model.RatingSnapshot
	ladderSnapshots     []model.PublicLadderSnapshot
	multiplierSnapshots []model.MultiplierSnapshot
	minerCompatibility  []model.MinerCompatibility
	resultEntries       []model.ArenaResultEntry
}

type OutcomeItem struct {
	EntrantID                string
	MinerAddress             string
	Name                     string
	EconomicUnitID           string
	FinishRank               int
	FinishPercentile         float64
	HandsPlayed              int
	MeaningfulDecisions      int
	AutoActions              int
	TimeoutActions           int
	InvalidActions           int
	StageReached             string
	StackPathSummary         json.RawMessage
	ScoreComponents          json.RawMessage
	Penalties                json.RawMessage
	TournamentScore          float64
	EffectiveTournamentScore float64
	ConfidenceWeight         float64
	FieldStrengthAdjustment  float64
	BotAdjustment            float64
	TimeCapAdjustment        float64
	EligibleForMultiplier    bool
	MuAfter                  float64
	SigmaAfter               float64
	ArenaReliabilityAfter    float64
	PublicELOAfter           int
	PublicRankAfter          int
	MultiplierBefore         float64
	MultiplierAfter          float64
	ConservativeSkill        *float64
	Payload                  json.RawMessage
}

type minerState struct {
	Mu                      float64
	Sigma                   float64
	ArenaReliability        float64
	PublicELO               int
	PublicRank              int
	Multiplier              float64
	EligibleTournamentCount int
}

func defaultMinerState() minerState {
	return minerState{
		Mu:               defaultMu,
		Sigma:            defaultSigma,
		ArenaReliability: defaultArenaReliability,
		PublicELO:        defaultPublicELO,
		Multiplier:       defaultMultiplier,
	}
}

func bucketConfidenceWeight(weight float64) float64 {
	if weight <= 0 {
		return 0
	}

	buckets := []float64{0.25, 0.50, 0.75, 1.00}
	best := buckets[0]
	bestDiff := math.Abs(weight - best)

	for _, candidate := range buckets[1:] {
		diff := math.Abs(weight - candidate)
		if diff < bestDiff {
			best = candidate
			bestDiff = diff
		}
	}

	return best
}

func clampFloat(value, minValue, maxValue float64) float64 {
	if value < minValue {
		return minValue
	}
	if value > maxValue {
		return maxValue
	}
	return value
}

func round2(value float64) float64 {
	return math.Round(value*100) / 100
}

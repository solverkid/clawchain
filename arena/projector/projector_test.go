package projector

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/arena/model"
)

func TestProjectorsConsumeEachEventOnceByEventID(t *testing.T) {
	p := NewProjectors()
	event := fixtureStandingEvent("evt-1")

	require.NoError(t, p.Apply(event))
	require.NoError(t, p.Apply(event))
	require.Equal(t, 1, p.Standing().AppliedCount("evt-1"))
}

func TestPostgameIncludesNoMultiplierReasonAndConfidence(t *testing.T) {
	p := NewProjectors()

	require.NoError(t, p.Apply(fixtureCompletedEvent()))
	postgame, ok := p.Postgame("tour_1")
	require.True(t, ok)
	require.Equal(t, "time_cap_finish", postgame.CompletedReason)
	require.Equal(t, "0.50", postgame.ConfidenceBucket)
	require.True(t, postgame.NoMultiplier)
}

func fixtureStandingEvent(eventID string) model.EventLogEntry {
	payload, _ := json.Marshal(map[string]any{
		"players_remaining": 17,
		"rank_band":         "top_16",
	})

	return model.EventLogEntry{
		EventID:       eventID,
		TournamentID:  "tour_1",
		EventType:     "tournament.standing.refreshed",
		OccurredAt:    time.Date(2026, time.April, 10, 15, 0, 0, 0, time.UTC),
		TruthMetadata: model.TruthMetadata{PayloadHash: eventID, StateHash: eventID, PolicyBundleVersion: "policy-v1"},
		Payload:       payload,
	}
}

func fixtureCompletedEvent() model.EventLogEntry {
	payload, _ := json.Marshal(map[string]any{
		"completed_reason":     "time_cap_finish",
		"confidence_weight":    0.5,
		"no_multiplier":        true,
		"no_multiplier_reason": "time_cap_finish",
		"stage_reached":        "final_table",
	})

	return model.EventLogEntry{
		EventID:       "evt-complete-1",
		TournamentID:  "tour_1",
		EventType:     "tournament.completed",
		OccurredAt:    time.Date(2026, time.April, 10, 15, 30, 0, 0, time.UTC),
		TruthMetadata: model.TruthMetadata{PayloadHash: "evt-complete-1", StateHash: "evt-complete-1", PolicyBundleVersion: "policy-v1"},
		Payload:       payload,
	}
}

package bot

import "testing"

func TestActionRequestIDIncludesTournamentID(t *testing.T) {
	first := actionRequestID("tour:alpha:01", "miner_01", 1, 7)
	second := actionRequestID("tour:beta:01", "miner_01", 1, 7)

	if first == second {
		t.Fatalf("expected different request ids across tournaments, got %q", first)
	}
}

func TestActionRequestIDIsStableWithinTournament(t *testing.T) {
	got := actionRequestID("tour:stable:01", "miner_01", 12, 44)
	want := "arena-bot-tour:stable:01-miner_01-000012-44"
	if got != want {
		t.Fatalf("unexpected request id: got %q want %q", got, want)
	}
}

package model

import (
	"slices"
	"strings"
	"testing"

	"github.com/clawchain/clawchain/pokermtt/fixture"
)

func TestContractDonorRuntimePaths(t *testing.T) {
	expectedAllowed := []string{
		"/v1/mtt/start",
		"/v1/mtt/getMTTRoomByID",
		"/v1/mtt/reentryMTTGame",
		"/v1/mtt/cancel",
		"/v1/join_game",
		"/v1/ws",
	}
	if got := DonorAllowedRuntimePaths(); !slices.Equal(got, expectedAllowed) {
		t.Fatalf("allowed donor runtime paths mismatch: got %v want %v", got, expectedAllowed)
	}
	if slices.Contains(DonorAllowedRuntimePaths(), DonorStopMTTPath) {
		t.Fatalf("donor Stop path must not be an allowed runtime path")
	}
	if !IsForbiddenDonorRuntimePath("/v1/mtt/Stop") {
		t.Fatalf("donor Stop path must be forbidden")
	}
	if IsForbiddenDonorRuntimePath("/v1/mtt/cancel") {
		t.Fatalf("donor cancel path must remain allowed")
	}
}

func TestContractRedisRankingKeys(t *testing.T) {
	contractFixture := fixture.DefaultContractFixture()
	if got := RankingUserInfoKey(GameTypeMTT, contractFixture.SourceMTTID); got != "rankingUserInfo:mtt:local-mtt-001" {
		t.Fatalf("snapshot key mismatch: %s", got)
	}
	if got := RankingAliveScoreKey(GameTypeMTT, contractFixture.SourceMTTID); got != "rankingNotDiedScore:mtt:local-mtt-001" {
		t.Fatalf("alive score key mismatch: %s", got)
	}
	if got := RankingDiedInfoKey(GameTypeMTT, contractFixture.SourceMTTID); got != "rankingUserDiedInfo:mtt:local-mtt-001" {
		t.Fatalf("died info key mismatch: %s", got)
	}
}

func TestContractLocalAuthTokenShape(t *testing.T) {
	contractFixture := fixture.DefaultContractFixture()
	got := LocalAuthBearerToken(contractFixture.DonorUserID)
	want := "Bearer local-user:7"
	if got != want {
		t.Fatalf("local auth bearer token mismatch: got %q want %q", got, want)
	}
	if !strings.HasPrefix(got, LocalAuthBearerPrefix+LocalAuthTokenPrefix) {
		t.Fatalf("local auth bearer token must preserve donor mock token shape: %q", got)
	}
}

func TestContractFixtureCanonicalIDs(t *testing.T) {
	contractFixture := fixture.DefaultContractFixture()
	if strings.Contains(strings.ToLower(contractFixture.TournamentID), "arena") {
		t.Fatalf("poker mtt tournament fixture must not use arena naming: %q", contractFixture.TournamentID)
	}
	if contractFixture.SourceMTTID == "" || contractFixture.DonorUserID == "" || contractFixture.MinerAddress == "" || contractFixture.TableID == "" {
		t.Fatalf("fixture must include donor and ClawChain identity anchors: %+v", contractFixture)
	}
	if got := contractFixture.HandID(); got != "poker-mtt-local-001:table-001:1" {
		t.Fatalf("hand id mismatch: %q", got)
	}
}

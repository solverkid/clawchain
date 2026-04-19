package ranking_test

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"testing"

	"github.com/clawchain/clawchain/pokermtt/model"
	"github.com/clawchain/clawchain/pokermtt/ranking"
	"github.com/stretchr/testify/require"
)

func TestRedisStoreReadsDonorRankingKeys(t *testing.T) {
	ctx := context.Background()
	redis := newFakeRedis()
	redis.hashes[model.RankingUserInfoKey(model.GameTypeMTT, "mtt-1")] = map[string]string{
		"7:1": mustJSON(t, map[string]any{
			"userID":       "7",
			"entryNumber":  1,
			"minerAddress": "claw1miner7",
			"endChip":      4500,
		}),
	}
	redis.zsets[model.RankingAliveScoreKey(model.GameTypeMTT, "mtt-1")] = []ranking.ZMember{
		{Member: "7:1", Score: 4500},
	}
	redis.lists[model.RankingDiedInfoKey(model.GameTypeMTT, "mtt-1")] = []string{
		mustJSON(t, map[string]any{"userID": "8", "entryNumber": 1, "rank": 1}),
	}

	store := ranking.RedisStore{
		Client:   redis,
		GameType: model.GameTypeMTT,
	}
	snapshot, err := store.ReadLiveSnapshot(ctx, "mtt-1")
	require.NoError(t, err)

	require.Equal(t, "mtt-1", snapshot.TournamentID)
	require.Equal(t, model.GameTypeMTT, snapshot.GameType)
	require.Equal(t, ranking.RedisKeys{
		UserInfo:   model.RankingUserInfoKey(model.GameTypeMTT, "mtt-1"),
		AliveScore: model.RankingAliveScoreKey(model.GameTypeMTT, "mtt-1"),
		DiedInfo:   model.RankingDiedInfoKey(model.GameTypeMTT, "mtt-1"),
	}, snapshot.Keys)
	require.Equal(t, []string{
		model.RankingUserInfoKey(model.GameTypeMTT, "mtt-1"),
		model.RankingAliveScoreKey(model.GameTypeMTT, "mtt-1"),
		model.RankingDiedInfoKey(model.GameTypeMTT, "mtt-1"),
	}, redis.calls)
	require.Equal(t, "7", mustDecode(t, snapshot.UserInfo["7:1"])["userID"])
	require.Equal(t, []ranking.ZMember{{Member: "7:1", Score: 4500}}, snapshot.Alive)
	require.Len(t, snapshot.Died, 1)
}

func TestRedisStoreReadStableSnapshotRejectsDrift(t *testing.T) {
	client := &driftingRedisClient{}
	store := ranking.RedisStore{Client: client, GameType: model.GameTypeMTT}

	_, err := store.ReadStableLiveSnapshot(
		context.Background(),
		"mtt-drift",
		ranking.StableSnapshotPolicy{MaxAttempts: 2},
	)

	require.Error(t, err)
	require.Contains(t, err.Error(), "unstable poker mtt live ranking snapshot")
}

func TestRedisStoreReadStableFinalizationInputIncludesRegistrationSource(t *testing.T) {
	ctx := context.Background()
	redis := newFakeRedis()
	redis.hashes[model.RankingUserInfoKey(model.GameTypeMTT, "mtt-finalization-input")] = map[string]string{
		"7:1": mustJSON(t, map[string]any{
			"userID":       "7",
			"entryNumber":  1,
			"minerAddress": "claw1miner7",
			"endChip":      4500,
		}),
	}
	redis.zsets[model.RankingAliveScoreKey(model.GameTypeMTT, "mtt-finalization-input")] = []ranking.ZMember{
		{Member: "7:1", Score: 4500},
	}
	registrationSource := fakeRegistrationSource{
		snapshot: ranking.RegistrationSnapshot{
			TournamentID: "mtt-finalization-input",
			UserInfo: map[string]string{
				"8:1": mustJSON(t, map[string]any{
					"userID":        "8",
					"entryNumber":   1,
					"minerAddress":  "claw1miner8",
					"standUpStatus": "no_show",
					"startChip":     3000,
					"endChip":       3000,
				}),
			},
		},
	}
	store := ranking.RedisStore{
		Client:             redis,
		GameType:           model.GameTypeMTT,
		RegistrationSource: &registrationSource,
	}

	live, registration, err := store.ReadStableFinalizationInput(
		ctx,
		"mtt-finalization-input",
		ranking.StableSnapshotPolicy{MaxAttempts: 2},
	)
	require.NoError(t, err)
	require.Equal(t, "7", mustDecode(t, live.UserInfo["7:1"])["userID"])
	require.Equal(t, "8", mustDecode(t, registration.UserInfo["8:1"])["userID"])
	require.Equal(t, []string{
		model.RankingUserInfoKey(model.GameTypeMTT, "mtt-finalization-input"),
		model.RankingAliveScoreKey(model.GameTypeMTT, "mtt-finalization-input"),
		model.RankingDiedInfoKey(model.GameTypeMTT, "mtt-finalization-input"),
		model.RankingUserInfoKey(model.GameTypeMTT, "mtt-finalization-input"),
		model.RankingAliveScoreKey(model.GameTypeMTT, "mtt-finalization-input"),
		model.RankingDiedInfoKey(model.GameTypeMTT, "mtt-finalization-input"),
	}, redis.calls)
	require.Equal(t, []string{"mtt-finalization-input"}, registrationSource.calls)
}

func TestFinalizerCanonicalizesLiveSnapshotEdges(t *testing.T) {
	snapshot := ranking.LiveSnapshot{
		TournamentID: "mtt-edges",
		SourceMTTID:  "donor-mtt-edges",
		GameType:     model.GameTypeMTT,
		Keys: ranking.RedisKeys{
			UserInfo:   model.RankingUserInfoKey(model.GameTypeMTT, "mtt-edges"),
			AliveScore: model.RankingAliveScoreKey(model.GameTypeMTT, "mtt-edges"),
			DiedInfo:   model.RankingDiedInfoKey(model.GameTypeMTT, "mtt-edges"),
		},
		UserInfo: map[string]string{
			"7:2": mustJSON(t, map[string]any{
				"userID":       "7",
				"entryNumber":  2,
				"playerName":   "seven",
				"minerAddress": "claw1miner7",
				"startChip":    3000,
				"endChip":      9000,
				"roomID":       "room-1",
			}),
			"8:1": mustJSON(t, map[string]any{
				"userID":       "8",
				"entryNumber":  1,
				"minerAddress": "claw1miner8",
				"startChip":    3000,
				"endChip":      0,
			}),
			"10:1": mustJSON(t, map[string]any{
				"userID":       "10",
				"entryNumber":  1,
				"minerAddress": "claw1miner10",
				"startChip":    3000,
				"endChip":      0,
			}),
			"11:1": mustJSON(t, map[string]any{
				"userID":        "11",
				"entryNumber":   1,
				"minerAddress":  "claw1miner11",
				"standUpStatus": "no_show",
				"startChip":     3000,
				"endChip":       3000,
			}),
		},
		Alive: []ranking.ZMember{
			{Member: "7:2", Score: 9000},
			{Member: "9:1", Score: 7000},
		},
		Died: []string{
			mustJSON(t, map[string]any{
				"userID":       "8",
				"entryNumber":  1,
				"rank":         4,
				"minerAddress": "claw1miner8",
				"endChip":      0,
			}),
			mustJSON(t, map[string]any{
				"userID":       "10",
				"entryNumber":  1,
				"rank":         "-",
				"minerAddress": "claw1miner10",
				"endChip":      0,
			}),
		},
	}
	finalizer := ranking.Finalizer{PolicyBundleVersion: "poker-mtt-phase1-test"}

	first, err := finalizer.Finalize(snapshot)
	require.NoError(t, err)
	second, err := finalizer.Finalize(snapshot)
	require.NoError(t, err)
	require.Equal(t, first.Root, second.Root)
	require.Equal(t, first.SnapshotHash, second.SnapshotHash)
	require.NotEmpty(t, first.Root)
	require.NotEmpty(t, first.SnapshotID)
	require.Len(t, first.Rows, 5)

	rows := rowsByMember(first.Rows)
	require.Equal(t, ranking.RankStateRanked, rows["7:2"].RankState)
	require.Equal(t, 1, rankValue(t, rows["7:2"]))
	require.Equal(t, float64(9000), rows["7:2"].Chip)
	require.Equal(t, float64(6000), rows["7:2"].ChipDelta)
	require.True(t, rows["7:2"].SnapshotFound)
	require.Equal(t, "claw1miner7", rows["7:2"].MinerAddress)

	require.Equal(t, ranking.RankStateRanked, rows["9:1"].RankState)
	require.Equal(t, 2, rankValue(t, rows["9:1"]))
	require.False(t, rows["9:1"].SnapshotFound)
	require.Equal(t, "9", rows["9:1"].SourceUserID)
	require.Equal(t, 1, rows["9:1"].EntryNumber)

	require.Equal(t, ranking.RankStateRanked, rows["8:1"].RankState)
	require.Equal(t, 3, rankValue(t, rows["8:1"]))
	require.True(t, rows["8:1"].SourceRankNumeric)

	require.Equal(t, ranking.RankStateUnresolvedSnapshot, rows["10:1"].RankState)
	require.Nil(t, rows["10:1"].Rank)
	require.Equal(t, 4, displayRankValue(t, rows["10:1"]))
	require.Equal(t, "-", rows["10:1"].SourceRank)
	require.False(t, rows["10:1"].SourceRankNumeric)

	require.Equal(t, ranking.RankStateWaitingNoShow, rows["11:1"].RankState)
	require.Nil(t, rows["11:1"].Rank)
	require.True(t, rows["11:1"].WaitingOrNoShow)
	require.Equal(t, "no_show", rows["11:1"].StandUpStatus)
}

func TestFinalizerAssignsUniquePayoutRanksForTiedDiedDisplayRank(t *testing.T) {
	snapshot := ranking.LiveSnapshot{
		TournamentID: "mtt-tied-died",
		GameType:     model.GameTypeMTT,
		UserInfo: map[string]string{
			"1:1": mustJSON(t, map[string]any{
				"userID":       "1",
				"entryNumber":  1,
				"minerAddress": "claw1miner1",
				"startChip":    3000,
				"endChip":      9000,
			}),
			"2:1": mustJSON(t, map[string]any{
				"userID":       "2",
				"entryNumber":  1,
				"minerAddress": "claw1miner2",
				"startChip":    2200,
				"endChip":      0,
			}),
			"3:1": mustJSON(t, map[string]any{
				"userID":       "3",
				"entryNumber":  1,
				"minerAddress": "claw1miner3",
				"startChip":    1900,
				"endChip":      0,
			}),
			"4:1": mustJSON(t, map[string]any{
				"userID":       "4",
				"entryNumber":  1,
				"minerAddress": "claw1miner4",
				"startChip":    500,
				"endChip":      0,
			}),
		},
		Alive: []ranking.ZMember{{Member: "1:1", Score: 9000}},
		Died: []string{
			mustJSON(t, map[string]any{
				"userID":       "3",
				"entryNumber":  1,
				"rank":         3,
				"minerAddress": "claw1miner3",
				"startChip":    1900,
				"endChip":      0,
			}),
			mustJSON(t, map[string]any{
				"userID":       "2",
				"entryNumber":  1,
				"rank":         3,
				"minerAddress": "claw1miner2",
				"startChip":    2200,
				"endChip":      0,
			}),
			mustJSON(t, map[string]any{
				"userID":       "4",
				"entryNumber":  1,
				"rank":         1,
				"minerAddress": "claw1miner4",
				"startChip":    500,
				"endChip":      0,
			}),
		},
	}

	finalized, err := (ranking.Finalizer{PolicyBundleVersion: "poker-mtt-payout-rank-test"}).Finalize(snapshot)
	require.NoError(t, err)

	rows := rowsByMember(finalized.Rows)
	require.Equal(t, 1, rankValue(t, rows["1:1"]))
	require.Equal(t, 1, displayRankValue(t, rows["1:1"]))
	require.Equal(t, 2, rankValue(t, rows["2:1"]))
	require.Equal(t, 3, rankValue(t, rows["3:1"]))
	require.Equal(t, 4, rankValue(t, rows["4:1"]))
	require.Equal(t, 2, displayRankValue(t, rows["2:1"]))
	require.Equal(t, 2, displayRankValue(t, rows["3:1"]))
	require.Equal(t, 4, displayRankValue(t, rows["4:1"]))
	require.Equal(t, "source_rank_display_then_start_chip_desc_member_id", rows["2:1"].RankTiebreaker)
	require.Equal(t, "source_rank_display_then_start_chip_desc_member_id", rows["3:1"].RankTiebreaker)
	require.Equal(t, []string{"1:1", "2:1", "3:1", "4:1"}, memberIDs(finalized.Rows))

	ranks := make([]int, 0, len(finalized.Rows))
	for _, row := range finalized.Rows {
		if row.RankState == ranking.RankStateRanked {
			ranks = append(ranks, rankValue(t, row))
		}
	}
	sort.Ints(ranks)
	require.Equal(t, []int{1, 2, 3, 4}, ranks)
}

func TestFinalizerCollapsesDuplicateReentriesByEconomicUnit(t *testing.T) {
	snapshot := ranking.LiveSnapshot{
		TournamentID: "mtt-reentry",
		GameType:     model.GameTypeMTT,
		UserInfo: map[string]string{
			"42:1": mustJSON(t, map[string]any{
				"userID":       "42",
				"entryNumber":  1,
				"minerAddress": "claw1miner42",
				"startChip":    3000,
				"endChip":      0,
			}),
			"42:2": mustJSON(t, map[string]any{
				"userID":       "42",
				"entryNumber":  2,
				"minerAddress": "claw1miner42",
				"startChip":    3000,
				"endChip":      11000,
			}),
		},
		Alive: []ranking.ZMember{
			{Member: "42:2", Score: 11000},
		},
		Died: []string{
			mustJSON(t, map[string]any{
				"userID":       "42",
				"entryNumber":  1,
				"rank":         1,
				"minerAddress": "claw1miner42",
				"endChip":      0,
			}),
		},
	}

	finalized, err := (ranking.Finalizer{PolicyBundleVersion: "poker-mtt-phase1-test"}).Finalize(snapshot)
	require.NoError(t, err)

	rows := rowsByMember(finalized.Rows)
	require.Equal(t, "claw1miner42", rows["42:2"].EconomicUnitID)
	require.Equal(t, "claw1miner42", rows["42:1"].EconomicUnitID)
	require.Equal(t, 2, rows["42:2"].ReentryCount)
	require.Equal(t, 2, rows["42:1"].ReentryCount)
	require.Equal(t, ranking.RankStateRanked, rows["42:2"].RankState)
	require.Equal(t, ranking.RankStateDuplicateEntryCollapsed, rows["42:1"].RankState)
	require.Equal(t, 1, rankValue(t, rows["42:2"]))
	require.Nil(t, rows["42:1"].Rank)
	require.Equal(t, 2, displayRankValue(t, rows["42:1"]))
}

func TestFinalizerMergesRegistrationNoShowAbsentFromRedis(t *testing.T) {
	snapshot := ranking.LiveSnapshot{
		TournamentID: "mtt-registration-no-show",
		GameType:     model.GameTypeMTT,
		UserInfo: map[string]string{
			"7:1": mustJSON(t, map[string]any{
				"userID":       "7",
				"entryNumber":  1,
				"minerAddress": "claw1miner7",
				"startChip":    3000,
				"endChip":      6000,
			}),
		},
		Alive: []ranking.ZMember{{Member: "7:1", Score: 6000}},
	}
	registration := ranking.RegistrationSnapshot{
		TournamentID: "mtt-registration-no-show",
		UserInfo: map[string]string{
			"8:1": mustJSON(t, map[string]any{
				"userID":         "8",
				"entryNumber":    1,
				"minerAddress":   "claw1miner8",
				"economicUnitID": "eu:8",
				"playerName":     "miner 8",
				"standUpStatus":  "no_show",
				"startChip":      3000,
				"endChip":        3000,
			}),
		},
	}

	finalized, err := (ranking.Finalizer{PolicyBundleVersion: "poker-mtt-phase3-test"}).
		FinalizeWithRegistration(snapshot, registration)
	require.NoError(t, err)

	rows := rowsByMember(finalized.Rows)
	require.Len(t, rows, 2)
	require.Equal(t, ranking.RankStateWaitingNoShow, rows["8:1"].RankState)
	require.Equal(t, ranking.StandingStatusPending, rows["8:1"].Status)
	require.False(t, rows["8:1"].SnapshotFound)
	require.True(t, rows["8:1"].WaitingOrNoShow)
	require.Equal(t, "claw1miner8", rows["8:1"].MinerAddress)
	require.Equal(t, "eu:8", rows["8:1"].EconomicUnitID)
	require.Nil(t, rows["8:1"].Rank)
}

func TestFinalizerMergesRegistrationWaitingUserAbsentFromRedis(t *testing.T) {
	snapshot := ranking.LiveSnapshot{
		TournamentID: "mtt-registration-waiting",
		GameType:     model.GameTypeMTT,
		UserInfo: map[string]string{
			"7:1": mustJSON(t, map[string]any{
				"userID":       "7",
				"entryNumber":  1,
				"minerAddress": "claw1miner7",
				"startChip":    3000,
				"endChip":      3000,
			}),
		},
		Alive: []ranking.ZMember{{Member: "7:1", Score: 3000}},
	}
	registration := ranking.RegistrationSnapshot{
		TournamentID: "mtt-registration-waiting",
		UserInfo: map[string]string{
			"9:1": mustJSON(t, map[string]any{
				"userID":       "9",
				"entryNumber":  1,
				"minerAddress": "claw1miner9",
				"status":       "WAITING",
				"startChip":    3000,
				"endChip":      3000,
			}),
		},
	}

	finalized, err := (ranking.Finalizer{PolicyBundleVersion: "poker-mtt-phase3-test"}).
		FinalizeWithRegistration(snapshot, registration)
	require.NoError(t, err)

	rows := rowsByMember(finalized.Rows)
	require.Equal(t, ranking.RankStateWaitingNoShow, rows["9:1"].RankState)
	require.False(t, rows["9:1"].SnapshotFound)
	require.True(t, rows["9:1"].WaitingOrNoShow)
	require.Equal(t, "WAITING", rows["9:1"].StandUpStatus)
}

func TestFinalizerRequiresTerminalStateOrQuietBarrierWhenConfigured(t *testing.T) {
	snapshot := ranking.LiveSnapshot{
		TournamentID: "mtt-barrier",
		RuntimeState: "running",
		UserInfo: map[string]string{
			"7:1": mustJSON(t, map[string]any{
				"userID":       "7",
				"entryNumber":  1,
				"minerAddress": "claw1miner7",
				"startChip":    3000,
				"endChip":      3000,
			}),
		},
		Alive: []ranking.ZMember{{Member: "7:1", Score: 3000}},
	}

	_, err := (ranking.Finalizer{
		PolicyBundleVersion:    "poker-mtt-phase3-test",
		RequireTerminalOrQuiet: true,
	}).Finalize(snapshot)
	require.ErrorIs(t, err, ranking.ErrFinalizationBarrier)

	snapshot.QuietPeriodSatisfied = true
	finalized, err := (ranking.Finalizer{
		PolicyBundleVersion:    "poker-mtt-phase3-test",
		RequireTerminalOrQuiet: true,
	}).Finalize(snapshot)
	require.NoError(t, err)
	require.Len(t, finalized.Rows, 1)
}

func TestFinalizerRejectsEntrantCountAndChipDriftWhenConfigured(t *testing.T) {
	snapshot := ranking.LiveSnapshot{
		TournamentID: "mtt-invariants",
		RuntimeState: "finished",
		UserInfo:     map[string]string{},
		Alive:        []ranking.ZMember{{Member: "7:1", Score: 9000}},
	}

	_, err := (ranking.Finalizer{
		PolicyBundleVersion: "poker-mtt-phase3-test",
		ExpectedEntrants:    2,
	}).Finalize(snapshot)
	require.ErrorIs(t, err, ranking.ErrFinalizationBarrier)
	require.Contains(t, err.Error(), "entrant count")

	_, err = (ranking.Finalizer{
		PolicyBundleVersion:     "poker-mtt-phase3-test",
		ExpectedTotalChip:       6000,
		TotalChipDriftTolerance: 0,
	}).Finalize(snapshot)
	require.ErrorIs(t, err, ranking.ErrFinalizationBarrier)
	require.Contains(t, err.Error(), "total chip drift")
}

func TestFinalizerRejectsAliveDiedWaitingCountDriftWhenConfigured(t *testing.T) {
	expectedAlive := 0
	snapshot := ranking.LiveSnapshot{
		TournamentID: "mtt-status-counts",
		RuntimeState: "finished",
		UserInfo: map[string]string{
			"7:1": mustJSON(t, map[string]any{
				"userID":       "7",
				"entryNumber":  1,
				"minerAddress": "claw1miner7",
				"startChip":    3000,
				"endChip":      3000,
			}),
		},
		Alive: []ranking.ZMember{{Member: "7:1", Score: 3000}},
	}

	_, err := (ranking.Finalizer{
		PolicyBundleVersion: "poker-mtt-phase3-test",
		ExpectedAlive:       &expectedAlive,
	}).Finalize(snapshot)
	require.ErrorIs(t, err, ranking.ErrFinalizationBarrier)
	require.Contains(t, err.Error(), "alive count")
}

func TestFinalizerCanonicalizesEqualAliveScoreTiesByMemberID(t *testing.T) {
	userInfo := map[string]string{
		"7:1": mustJSON(t, map[string]any{
			"userID":       "7",
			"entryNumber":  1,
			"minerAddress": "claw1miner7",
			"endChip":      5000,
		}),
		"8:1": mustJSON(t, map[string]any{
			"userID":       "8",
			"entryNumber":  1,
			"minerAddress": "claw1miner8",
			"endChip":      5000,
		}),
	}
	left := ranking.LiveSnapshot{
		TournamentID: "mtt-equal-ties",
		GameType:     model.GameTypeMTT,
		UserInfo:     userInfo,
		Alive: []ranking.ZMember{
			{Member: "8:1", Score: 5000},
			{Member: "7:1", Score: 5000},
		},
	}
	right := ranking.LiveSnapshot{
		TournamentID: "mtt-equal-ties",
		GameType:     model.GameTypeMTT,
		UserInfo:     userInfo,
		Alive: []ranking.ZMember{
			{Member: "7:1", Score: 5000},
			{Member: "8:1", Score: 5000},
		},
	}

	finalizer := ranking.Finalizer{PolicyBundleVersion: "poker-mtt-phase2-test"}
	leftFinal, err := finalizer.Finalize(left)
	require.NoError(t, err)
	rightFinal, err := finalizer.Finalize(right)
	require.NoError(t, err)

	require.Equal(t, leftFinal.Root, rightFinal.Root)
	require.Equal(t, leftFinal.SnapshotHash, rightFinal.SnapshotHash)
	require.Equal(t, 1, rankValue(t, rowsByMember(leftFinal.Rows)["7:1"]))
	require.Equal(t, 2, rankValue(t, rowsByMember(leftFinal.Rows)["8:1"]))
}

func TestFinalizerCanonicalHashIgnoresSnapshotJSONKeyOrder(t *testing.T) {
	left := ranking.LiveSnapshot{
		TournamentID: "mtt-canonical-json",
		GameType:     model.GameTypeMTT,
		UserInfo: map[string]string{
			"7:1": `{"userID":"7","entryNumber":1,"minerAddress":"claw1miner7","endChip":5000}`,
		},
		Alive: []ranking.ZMember{{Member: "7:1", Score: 5000}},
	}
	right := ranking.LiveSnapshot{
		TournamentID: "mtt-canonical-json",
		GameType:     model.GameTypeMTT,
		UserInfo: map[string]string{
			"7:1": `{"endChip":5000,"minerAddress":"claw1miner7","entryNumber":1,"userID":"7"}`,
		},
		Alive: []ranking.ZMember{{Member: "7:1", Score: 5000}},
	}

	finalizer := ranking.Finalizer{PolicyBundleVersion: "poker-mtt-phase1-test"}
	leftFinal, err := finalizer.Finalize(left)
	require.NoError(t, err)
	rightFinal, err := finalizer.Finalize(right)
	require.NoError(t, err)

	require.Equal(t, leftFinal.SnapshotHash, rightFinal.SnapshotHash)
	require.Equal(t, leftFinal.Root, rightFinal.Root)
}

func TestFinalizerCanonicalHashIgnoresRoutingRoomID(t *testing.T) {
	left := ranking.LiveSnapshot{
		TournamentID: "mtt-routing-room",
		GameType:     model.GameTypeMTT,
		UserInfo: map[string]string{
			"7:1": `{"userID":"7","entryNumber":1,"minerAddress":"claw1miner7","endChip":5000,"roomID":"room-a"}`,
		},
		Alive: []ranking.ZMember{{Member: "7:1", Score: 5000}},
	}
	right := ranking.LiveSnapshot{
		TournamentID: "mtt-routing-room",
		GameType:     model.GameTypeMTT,
		UserInfo: map[string]string{
			"7:1": `{"userID":"7","entryNumber":1,"minerAddress":"claw1miner7","endChip":5000,"roomID":"room-b"}`,
		},
		Alive: []ranking.ZMember{{Member: "7:1", Score: 5000}},
	}

	finalizer := ranking.Finalizer{PolicyBundleVersion: "poker-mtt-phase1-test"}
	leftFinal, err := finalizer.Finalize(left)
	require.NoError(t, err)
	rightFinal, err := finalizer.Finalize(right)
	require.NoError(t, err)

	require.NotEqual(t, rowsByMember(leftFinal.Rows)["7:1"].RoomID, rowsByMember(rightFinal.Rows)["7:1"].RoomID)
	require.Equal(t, leftFinal.Root, rightFinal.Root)
}

func TestFinalizerStableRootForTenThousandEntrants(t *testing.T) {
	const entrants = 10000
	snapshot := ranking.LiveSnapshot{
		TournamentID: "mtt-10k",
		GameType:     model.GameTypeMTT,
		UserInfo:     make(map[string]string, entrants),
		Alive:        make([]ranking.ZMember, 0, 3),
		Died:         make([]string, 0, entrants-3),
	}
	for i := 0; i < entrants; i++ {
		memberID := fmt.Sprintf("%d:1", i)
		snapshot.UserInfo[memberID] = mustJSON(t, map[string]any{
			"userID":       fmt.Sprint(i),
			"entryNumber":  1,
			"minerAddress": fmt.Sprintf("claw1miner%05d", i),
			"startChip":    3000,
			"endChip":      0,
		})
	}
	for i := 0; i < 3; i++ {
		memberID := fmt.Sprintf("%d:1", i)
		snapshot.Alive = append(snapshot.Alive, ranking.ZMember{
			Member: memberID,
			Score:  float64(10000 - i),
		})
	}
	for i := 3; i < entrants; i++ {
		snapshot.Died = append(snapshot.Died, mustJSON(t, map[string]any{
			"userID":       fmt.Sprint(i),
			"entryNumber":  1,
			"rank":         i,
			"minerAddress": fmt.Sprintf("claw1miner%05d", i),
			"endChip":      0,
		}))
	}

	first, err := (ranking.Finalizer{PolicyBundleVersion: "poker-mtt-phase1-test"}).Finalize(snapshot)
	require.NoError(t, err)
	second, err := (ranking.Finalizer{PolicyBundleVersion: "poker-mtt-phase1-test"}).Finalize(snapshot)
	require.NoError(t, err)

	require.Len(t, first.Rows, entrants)
	require.LessOrEqual(t, cap(first.Rows), entrants)
	require.Equal(t, first.Root, second.Root)
	require.Equal(t, first.SnapshotHash, second.SnapshotHash)
	require.Equal(t, 1, rankValue(t, first.Rows[0]))
	require.Equal(t, entrants, rankValue(t, first.Rows[entrants-1]))
}

type fakeRedis struct {
	hashes map[string]map[string]string
	zsets  map[string][]ranking.ZMember
	lists  map[string][]string
	calls  []string
}

type driftingRedisClient struct {
	hgetCalls int
}

type fakeRegistrationSource struct {
	snapshot ranking.RegistrationSnapshot
	calls    []string
}

func (s *fakeRegistrationSource) ReadRegistrationSnapshot(ctx context.Context, tournamentID string) (ranking.RegistrationSnapshot, error) {
	if err := ctx.Err(); err != nil {
		return ranking.RegistrationSnapshot{}, err
	}
	s.calls = append(s.calls, tournamentID)
	return s.snapshot, nil
}

func (r *driftingRedisClient) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	r.hgetCalls++
	return map[string]string{
		"7:1": fmt.Sprintf(
			`{"userID":"7","entryNumber":1,"minerAddress":"claw1miner7","endChip":%d}`,
			4500+r.hgetCalls,
		),
	}, nil
}

func (r *driftingRedisClient) ZRevRangeWithScores(ctx context.Context, key string, start int64, stop int64) ([]ranking.ZMember, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return []ranking.ZMember{{Member: "7:1", Score: 4500}}, nil
}

func (r *driftingRedisClient) LRange(ctx context.Context, key string, start int64, stop int64) ([]string, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return nil, nil
}

func newFakeRedis() *fakeRedis {
	return &fakeRedis{
		hashes: make(map[string]map[string]string),
		zsets:  make(map[string][]ranking.ZMember),
		lists:  make(map[string][]string),
	}
}

func (r *fakeRedis) HGetAll(ctx context.Context, key string) (map[string]string, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	r.calls = append(r.calls, key)
	values := make(map[string]string, len(r.hashes[key]))
	for member, value := range r.hashes[key] {
		values[member] = value
	}
	return values, nil
}

func (r *fakeRedis) ZRevRangeWithScores(ctx context.Context, key string, start int64, stop int64) ([]ranking.ZMember, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if start != 0 || stop != -1 {
		panic(fmt.Sprintf("unexpected zrange bounds: %d %d", start, stop))
	}
	r.calls = append(r.calls, key)
	values := append([]ranking.ZMember(nil), r.zsets[key]...)
	return values, nil
}

func (r *fakeRedis) LRange(ctx context.Context, key string, start int64, stop int64) ([]string, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if start != 0 || stop != -1 {
		panic(fmt.Sprintf("unexpected lrange bounds: %d %d", start, stop))
	}
	r.calls = append(r.calls, key)
	values := append([]string(nil), r.lists[key]...)
	return values, nil
}

func mustJSON(t *testing.T, value any) string {
	t.Helper()
	payload, err := json.Marshal(value)
	require.NoError(t, err)
	return string(payload)
}

func mustDecode(t *testing.T, payload string) map[string]any {
	t.Helper()
	var decoded map[string]any
	require.NoError(t, json.Unmarshal([]byte(payload), &decoded))
	return decoded
}

func rowsByMember(rows []ranking.FinalRankingRow) map[string]ranking.FinalRankingRow {
	out := make(map[string]ranking.FinalRankingRow, len(rows))
	for _, row := range rows {
		out[row.MemberID] = row
	}
	keys := make([]string, 0, len(out))
	for key := range out {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return out
}

func memberIDs(rows []ranking.FinalRankingRow) []string {
	memberIDs := make([]string, 0, len(rows))
	for _, row := range rows {
		memberIDs = append(memberIDs, row.MemberID)
	}
	return memberIDs
}

func rankValue(t *testing.T, row ranking.FinalRankingRow) int {
	t.Helper()
	require.NotNil(t, row.Rank)
	return *row.Rank
}

func displayRankValue(t *testing.T, row ranking.FinalRankingRow) int {
	t.Helper()
	require.NotNil(t, row.DisplayRank)
	return *row.DisplayRank
}

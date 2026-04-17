package ranking

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/clawchain/clawchain/pokermtt/model"
)

var ErrInvalidRedisStore = errors.New("invalid poker mtt ranking redis store")
var ErrUnstableLiveSnapshot = errors.New("unstable poker mtt live ranking snapshot")

type StableSnapshotPolicy struct {
	MaxAttempts int
}

type RedisClient interface {
	HGetAll(ctx context.Context, key string) (map[string]string, error)
	ZRevRangeWithScores(ctx context.Context, key string, start int64, stop int64) ([]ZMember, error)
	LRange(ctx context.Context, key string, start int64, stop int64) ([]string, error)
}

type RegistrationSource interface {
	ReadRegistrationSnapshot(ctx context.Context, tournamentID string) (RegistrationSnapshot, error)
}

type RedisStore struct {
	Client             RedisClient
	GameType           string
	RegistrationSource RegistrationSource
}

func (s RedisStore) ReadLiveSnapshot(ctx context.Context, tournamentID string) (LiveSnapshot, error) {
	tournamentID = strings.TrimSpace(tournamentID)
	if s.Client == nil || tournamentID == "" {
		return LiveSnapshot{}, ErrInvalidRedisStore
	}
	gameType := strings.TrimSpace(s.GameType)
	if gameType == "" {
		gameType = model.GameTypeMTT
	}

	keys := RedisKeys{
		UserInfo:   model.RankingUserInfoKey(gameType, tournamentID),
		AliveScore: model.RankingAliveScoreKey(gameType, tournamentID),
		DiedInfo:   model.RankingDiedInfoKey(gameType, tournamentID),
	}

	userInfo, err := s.Client.HGetAll(ctx, keys.UserInfo)
	if err != nil {
		return LiveSnapshot{}, err
	}
	alive, err := s.Client.ZRevRangeWithScores(ctx, keys.AliveScore, 0, -1)
	if err != nil {
		return LiveSnapshot{}, err
	}
	died, err := s.Client.LRange(ctx, keys.DiedInfo, 0, -1)
	if err != nil {
		return LiveSnapshot{}, err
	}

	return LiveSnapshot{
		TournamentID: tournamentID,
		SourceMTTID:  tournamentID,
		GameType:     gameType,
		Keys:         keys,
		UserInfo:     copyStringMap(userInfo),
		Alive:        append([]ZMember(nil), alive...),
		Died:         append([]string(nil), died...),
	}, nil
}

func (s RedisStore) ReadStableLiveSnapshot(ctx context.Context, tournamentID string, policy StableSnapshotPolicy) (LiveSnapshot, error) {
	maxAttempts := policy.MaxAttempts
	if maxAttempts <= 0 {
		maxAttempts = 2
	}
	for attempt := 0; attempt < maxAttempts; attempt++ {
		first, err := s.ReadLiveSnapshot(ctx, tournamentID)
		if err != nil {
			return LiveSnapshot{}, err
		}
		firstHash, err := hashLiveSnapshot(first)
		if err != nil {
			return LiveSnapshot{}, err
		}
		second, err := s.ReadLiveSnapshot(ctx, tournamentID)
		if err != nil {
			return LiveSnapshot{}, err
		}
		secondHash, err := hashLiveSnapshot(second)
		if err != nil {
			return LiveSnapshot{}, err
		}
		if firstHash == secondHash {
			return second, nil
		}
	}
	return LiveSnapshot{}, fmt.Errorf("%w after %d attempts", ErrUnstableLiveSnapshot, maxAttempts)
}

func (s RedisStore) ReadStableFinalizationInput(
	ctx context.Context,
	tournamentID string,
	policy StableSnapshotPolicy,
) (LiveSnapshot, RegistrationSnapshot, error) {
	live, err := s.ReadStableLiveSnapshot(ctx, tournamentID, policy)
	if err != nil {
		return LiveSnapshot{}, RegistrationSnapshot{}, err
	}
	if s.RegistrationSource == nil {
		return live, RegistrationSnapshot{TournamentID: live.TournamentID, SourceMTTID: live.SourceMTTID}, nil
	}
	registration, err := s.RegistrationSource.ReadRegistrationSnapshot(ctx, tournamentID)
	if err != nil {
		return LiveSnapshot{}, RegistrationSnapshot{}, err
	}
	if registration.TournamentID == "" {
		registration.TournamentID = live.TournamentID
	}
	if registration.SourceMTTID == "" {
		registration.SourceMTTID = live.SourceMTTID
	}
	return live, registration, nil
}

func hashLiveSnapshot(snapshot LiveSnapshot) (string, error) {
	payload, err := json.Marshal(snapshot)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

func copyStringMap(values map[string]string) map[string]string {
	out := make(map[string]string, len(values))
	for key, value := range values {
		out[key] = value
	}
	return out
}

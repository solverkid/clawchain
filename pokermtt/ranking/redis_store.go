package ranking

import (
	"context"
	"errors"
	"strings"

	"github.com/clawchain/clawchain/pokermtt/model"
)

var ErrInvalidRedisStore = errors.New("invalid poker mtt ranking redis store")

type RedisClient interface {
	HGetAll(ctx context.Context, key string) (map[string]string, error)
	ZRevRangeWithScores(ctx context.Context, key string, start int64, stop int64) ([]ZMember, error)
	LRange(ctx context.Context, key string, start int64, stop int64) ([]string, error)
}

type RedisStore struct {
	Client   RedisClient
	GameType string
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

func copyStringMap(values map[string]string) map[string]string {
	out := make(map[string]string, len(values))
	for key, value := range values {
		out[key] = value
	}
	return out
}

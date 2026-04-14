package model

import "fmt"

const (
	GameTypeMTT = "mtt"

	DonorStartMTTPath       = "/v1/mtt/start"
	DonorGetMTTRoomByIDPath = "/v1/mtt/getMTTRoomByID"
	DonorReentryMTTGamePath = "/v1/mtt/reentryMTTGame"
	DonorCancelMTTPath      = "/v1/mtt/cancel"
	DonorJoinGamePath       = "/v1/join_game"
	DonorWebSocketPath      = "/v1/ws"
	DonorStopMTTPath        = "/v1/mtt/Stop"

	MockUserIDHeader       = "Mock-Userid"
	LocalAuthTokenPrefix   = "local-user:"
	LocalAuthBearerPrefix  = "Bearer "
	RedisRankingUserInfo   = "rankingUserInfo"
	RedisRankingAliveScore = "rankingNotDiedScore"
	RedisRankingDiedInfo   = "rankingUserDiedInfo"
)

var donorAllowedRuntimePaths = []string{
	DonorStartMTTPath,
	DonorGetMTTRoomByIDPath,
	DonorReentryMTTGamePath,
	DonorCancelMTTPath,
	DonorJoinGamePath,
	DonorWebSocketPath,
}

var donorForbiddenRuntimePaths = []string{
	DonorStopMTTPath,
}

func DonorAllowedRuntimePaths() []string {
	return append([]string(nil), donorAllowedRuntimePaths...)
}

func DonorForbiddenRuntimePaths() []string {
	return append([]string(nil), donorForbiddenRuntimePaths...)
}

func IsForbiddenDonorRuntimePath(path string) bool {
	for _, forbiddenPath := range donorForbiddenRuntimePaths {
		if path == forbiddenPath {
			return true
		}
	}
	return false
}

func LocalAuthBearerToken(userID string) string {
	return LocalAuthBearerPrefix + LocalAuthTokenPrefix + userID
}

func RankingUserInfoKey(gameType string, tournamentID string) string {
	return redisRankingKey(RedisRankingUserInfo, gameType, tournamentID)
}

func RankingAliveScoreKey(gameType string, tournamentID string) string {
	return redisRankingKey(RedisRankingAliveScore, gameType, tournamentID)
}

func RankingDiedInfoKey(gameType string, tournamentID string) string {
	return redisRankingKey(RedisRankingDiedInfo, gameType, tournamentID)
}

func redisRankingKey(prefix string, gameType string, tournamentID string) string {
	return fmt.Sprintf("%s:%s:%s", prefix, gameType, tournamentID)
}

package types

import "context"

// QueryServer 查询接口
type QueryServer interface {
	Score(context.Context, *QueryScoreRequest) (*QueryScoreResponse, error)
	Leaderboard(context.Context, *QueryLeaderboardRequest) (*QueryLeaderboardResponse, error)
}

// QueryScoreRequest 查询单个矿工声誉
type QueryScoreRequest struct {
	MinerAddress string `json:"miner_address"`
}

// QueryScoreResponse 单个矿工声誉响应
type QueryScoreResponse struct {
	Score ReputationScore `json:"score"`
}

// QueryLeaderboardRequest 排行榜请求
type QueryLeaderboardRequest struct {
	Limit uint32 `json:"limit"`
}

// QueryLeaderboardResponse 排行榜响应
type QueryLeaderboardResponse struct {
	Scores []ReputationScore `json:"scores"`
}

// RegisterQueryServer 简化注册（无 protobuf 时的占位）
func RegisterQueryServer(s interface{}, srv QueryServer) {
	_ = s
	_ = srv
}

package types

import (
	"context"
)

// MsgServer 消息处理接口
type MsgServer interface {
	SubmitCommit(context.Context, *MsgSubmitCommit) (*MsgSubmitCommitResponse, error)
	SubmitReveal(context.Context, *MsgSubmitReveal) (*MsgSubmitRevealResponse, error)
}

// QueryServer 查询接口
type QueryServer interface {
	GetPendingChallenges(context.Context, *QueryPendingChallengesRequest) (*QueryPendingChallengesResponse, error)
	GetChallenge(context.Context, *QueryChallengeRequest) (*QueryChallengeResponse, error)
}

// 消息响应
type MsgSubmitCommitResponse struct{}
type MsgSubmitRevealResponse struct{}

// 查询请求和响应
type QueryPendingChallengesRequest struct {
	MinerAddress string `json:"miner_address"`
}

type QueryPendingChallengesResponse struct {
	Challenges []Challenge `json:"challenges"`
}

type QueryChallengeRequest struct {
	ChallengeId string `json:"challenge_id"`
}

type QueryChallengeResponse struct {
	Challenge Challenge `json:"challenge"`
}

// 事件类型
const (
	EventTypeCommitSubmitted = "commit_submitted"
	EventTypeRevealSubmitted = "reveal_submitted"
)

// 事件属性
const (
	AttributeKeyChallengeID = "challenge_id"
	AttributeKeyMiner       = "miner"
	AttributeKeyCommitHash  = "commit_hash"
	AttributeKeyAnswer      = "answer"
)

// RegisterMsgServer 简化注册（无 protobuf 时的占位）
func RegisterMsgServer(s interface{}, srv MsgServer) {
	_ = s
	_ = srv
}

// RegisterQueryServer 简化注册（无 protobuf 时的占位）
func RegisterQueryServer(s interface{}, srv QueryServer) {
	_ = s
	_ = srv
}

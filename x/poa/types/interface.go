package types

import (
	"context"
)

// MsgServer 消息处理接口
type MsgServer interface {
	RegisterMiner(context.Context, *MsgRegisterMiner) (*MsgRegisterMinerResponse, error)
	StakeMiner(context.Context, *MsgStakeMiner) (*MsgStakeMinerResponse, error)
	UnstakeMiner(context.Context, *MsgUnstakeMiner) (*MsgUnstakeMinerResponse, error)
}

// QueryServer 查询接口
type QueryServer interface {
	GetMiner(context.Context, *QueryMinerRequest) (*QueryMinerResponse, error)
	GetActiveMiners(context.Context, *QueryActiveMinersRequest) (*QueryActiveMinersResponse, error)
}

// 消息响应
type MsgRegisterMinerResponse struct{}
type MsgStakeMinerResponse struct{}
type MsgUnstakeMinerResponse struct{}

// 查询请求和响应
type QueryMinerRequest struct {
	MinerAddress string `json:"miner_address"`
}

type QueryMinerResponse struct {
	Miner Miner `json:"miner"`
}

type QueryActiveMinersRequest struct{}

type QueryActiveMinersResponse struct {
	Miners []Miner `json:"miners"`
}

// 事件类型
const (
	EventTypeMinerRegistered = "miner_registered"
	EventTypeMinerStaked     = "miner_staked"
	EventTypeMinerUnstaked   = "miner_unstaked"
)

// 事件属性
const (
	AttributeKeyMiner  = "miner"
	AttributeKeyStake  = "stake"
	AttributeKeyAmount = "amount"
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

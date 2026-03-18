package types

import "cosmossdk.io/errors"

var (
	// ErrMinerAlreadyRegistered 矿工已注册
	ErrMinerAlreadyRegistered = errors.Register(ModuleName, 1, "miner already registered")
	// ErrMinerAlreadyExists 矿工已存在（创世状态验证用）
	ErrMinerAlreadyExists = errors.Register(ModuleName, 2, "miner already exists")
	// ErrMinerNotFound 矿工未找到
	ErrMinerNotFound = errors.Register(ModuleName, 3, "miner not found")
	// ErrInsufficientStake 质押金额不足
	ErrInsufficientStake = errors.Register(ModuleName, 4, "insufficient stake amount, minimum is 100 CLAW")
	// ErrInvalidStakeAmount 无效质押金额
	ErrInvalidStakeAmount = errors.Register(ModuleName, 5, "invalid stake amount")
	// ErrMinerNotActive 矿工未激活
	ErrMinerNotActive = errors.Register(ModuleName, 6, "miner is not active")
	// ErrMinerSuspended 矿工被暂停
	ErrMinerSuspended = errors.Register(ModuleName, 7, "miner is suspended due to low reputation")
	// ErrUnstakeInProgress 已在解质押中
	ErrUnstakeInProgress = errors.Register(ModuleName, 8, "unstake already in progress")
	// ErrMaxMinersPerIP 同一 IP 矿工数超限
	ErrMaxMinersPerIP = errors.Register(ModuleName, 9, "exceeded maximum miners per IP")
	// ErrInvalidParams 参数验证错误
	ErrInvalidParams = errors.Register(ModuleName, 10, "invalid params")
	// ErrInvalidStake 无效的质押操作
	ErrInvalidStake = errors.Register(ModuleName, 11, "invalid stake operation")
)

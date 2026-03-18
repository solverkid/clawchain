package types

import (
	sdk "github.com/cosmos/cosmos-sdk/types"
)

const (
	TypeMsgRegisterMiner = "register_miner"
	TypeMsgStakeMiner    = "stake_miner"
	TypeMsgUnstakeMiner  = "unstake_miner"
)

// MsgRegisterMiner 注册矿工消息
type MsgRegisterMiner struct {
	MinerAddress string `json:"miner_address"`
	StakeAmount  uint64 `json:"stake_amount,string"` // 初始质押金额（可选）
}

func (msg MsgRegisterMiner) ValidateBasic() error {
	_, err := sdk.AccAddressFromBech32(msg.MinerAddress)
	if err != nil {
		return err
	}
	return nil
}

func (msg MsgRegisterMiner) GetSigners() []sdk.AccAddress {
	addr, _ := sdk.AccAddressFromBech32(msg.MinerAddress)
	return []sdk.AccAddress{addr}
}

// MsgStakeMiner 矿工质押消息
type MsgStakeMiner struct {
	MinerAddress string `json:"miner_address"`
	Amount       uint64 `json:"amount,string"`
}

func (msg MsgStakeMiner) ValidateBasic() error {
	_, err := sdk.AccAddressFromBech32(msg.MinerAddress)
	if err != nil {
		return err
	}
	if msg.Amount == 0 {
		return ErrInvalidStake
	}
	return nil
}

func (msg MsgStakeMiner) GetSigners() []sdk.AccAddress {
	addr, _ := sdk.AccAddressFromBech32(msg.MinerAddress)
	return []sdk.AccAddress{addr}
}

// MsgUnstakeMiner 矿工解质押消息
type MsgUnstakeMiner struct {
	MinerAddress string `json:"miner_address"`
	Amount       uint64 `json:"amount,string"`
}

func (msg MsgUnstakeMiner) ValidateBasic() error {
	_, err := sdk.AccAddressFromBech32(msg.MinerAddress)
	if err != nil {
		return err
	}
	if msg.Amount == 0 {
		return ErrInvalidStake
	}
	return nil
}

func (msg MsgUnstakeMiner) GetSigners() []sdk.AccAddress {
	addr, _ := sdk.AccAddressFromBech32(msg.MinerAddress)
	return []sdk.AccAddress{addr}
}

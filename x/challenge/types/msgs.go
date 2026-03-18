package types

import (
	sdk "github.com/cosmos/cosmos-sdk/types"
)

const (
	TypeMsgSubmitCommit = "submit_commit"
	TypeMsgSubmitReveal = "submit_reveal"
)

// MsgSubmitCommit 提交挑战答案的承诺（哈希）
type MsgSubmitCommit struct {
	MinerAddress string `json:"miner_address"`
	ChallengeId  string `json:"challenge_id"`
	CommitHash   string `json:"commit_hash"` // SHA256(answer + salt)
}

func (msg MsgSubmitCommit) ValidateBasic() error {
	_, err := sdk.AccAddressFromBech32(msg.MinerAddress)
	if err != nil {
		return err
	}
	if msg.ChallengeId == "" || msg.CommitHash == "" {
		return ErrInvalidChallenge
	}
	return nil
}

func (msg MsgSubmitCommit) GetSigners() []sdk.AccAddress {
	addr, _ := sdk.AccAddressFromBech32(msg.MinerAddress)
	return []sdk.AccAddress{addr}
}

// MsgSubmitReveal 揭示挑战答案
type MsgSubmitReveal struct {
	MinerAddress string `json:"miner_address"`
	ChallengeId  string `json:"challenge_id"`
	Answer       string `json:"answer"`
	Salt         string `json:"salt"`
}

func (msg MsgSubmitReveal) ValidateBasic() error {
	_, err := sdk.AccAddressFromBech32(msg.MinerAddress)
	if err != nil {
		return err
	}
	if msg.ChallengeId == "" || msg.Answer == "" {
		return ErrInvalidChallenge
	}
	return nil
}

func (msg MsgSubmitReveal) GetSigners() []sdk.AccAddress {
	addr, _ := sdk.AccAddressFromBech32(msg.MinerAddress)
	return []sdk.AccAddress{addr}
}

package types

import (
	"strings"

	sdk "github.com/cosmos/cosmos-sdk/types"
)

var allowedAnchorSchemaVersions = map[string]struct{}{
	"settlement.v1":               {},
	"clawchain.anchor_payload.v1": {},
}

func (msg *MsgAnchorSettlementBatch) ValidateBasic() error {
	if _, err := sdk.AccAddressFromBech32(msg.Submitter); err != nil {
		return err
	}
	if msg.SettlementBatchId == "" || msg.AnchorJobId == "" {
		return ErrInvalidSettlementBatch
	}
	if msg.SchemaVersion == "" || msg.CanonicalRoot == "" || msg.AnchorPayloadHash == "" {
		return ErrInvalidSettlementBatch
	}
	if _, ok := allowedAnchorSchemaVersions[msg.SchemaVersion]; !ok {
		return ErrInvalidSettlementBatch
	}
	if !strings.HasPrefix(msg.CanonicalRoot, "sha256:") || len(msg.CanonicalRoot) <= len("sha256:") {
		return ErrInvalidSettlementBatch
	}
	if !strings.HasPrefix(msg.AnchorPayloadHash, "sha256:") || len(msg.AnchorPayloadHash) <= len("sha256:") {
		return ErrInvalidSettlementBatch
	}
	return nil
}

func (msg *MsgAnchorSettlementBatch) GetSigners() []sdk.AccAddress {
	addr, _ := sdk.AccAddressFromBech32(msg.Submitter)
	return []sdk.AccAddress{addr}
}

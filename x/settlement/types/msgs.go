package types

import (
	"strings"
	"time"

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
	if msg.SettlementBatchId == "" || msg.AnchorJobId == "" || msg.Lane == "" {
		return ErrInvalidSettlementBatch
	}
	if msg.SchemaVersion == "" || msg.PolicyBundleVersion == "" || msg.WindowEndAt == "" {
		return ErrInvalidSettlementBatch
	}
	if _, ok := allowedAnchorSchemaVersions[msg.SchemaVersion]; !ok {
		return ErrInvalidSettlementBatch
	}
	if _, err := time.Parse(time.RFC3339, msg.WindowEndAt); err != nil {
		return ErrInvalidSettlementBatch
	}
	for _, hashRef := range []string{
		msg.CanonicalRoot,
		msg.AnchorPayloadHash,
		msg.RewardWindowIdsRoot,
		msg.TaskRunIdsRoot,
		msg.MinerRewardRowsRoot,
	} {
		if !isSHA256Ref(hashRef) {
			return ErrInvalidSettlementBatch
		}
	}
	return nil
}

func isSHA256Ref(value string) bool {
	return strings.HasPrefix(value, "sha256:") && len(value) > len("sha256:")
}

func (msg *MsgAnchorSettlementBatch) GetSigners() []sdk.AccAddress {
	addr, _ := sdk.AccAddressFromBech32(msg.Submitter)
	return []sdk.AccAddress{addr}
}

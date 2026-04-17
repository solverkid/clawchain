package types_test

import (
	"bytes"
	"strings"
	"testing"

	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/stretchr/testify/require"

	"github.com/clawchain/clawchain/x/settlement/types"
)

func TestMsgAnchorSettlementBatchValidateBasic(t *testing.T) {
	msg := &types.MsgAnchorSettlementBatch{
		Submitter:           sdk.AccAddress(bytes.Repeat([]byte{0x01}, 20)).String(),
		SettlementBatchId:   "sb_2026_04_10_0001",
		AnchorJobId:         "anchor_job_01",
		Lane:                "fast",
		SchemaVersion:       "settlement.v1",
		PolicyBundleVersion: "policy.v1",
		CanonicalRoot:       "sha256:" + strings.Repeat("a", 64),
		AnchorPayloadHash:   "sha256:" + strings.Repeat("b", 64),
		RewardWindowIdsRoot: "sha256:" + strings.Repeat("c", 64),
		TaskRunIdsRoot:      "sha256:" + strings.Repeat("d", 64),
		MinerRewardRowsRoot: "sha256:" + strings.Repeat("e", 64),
		WindowEndAt:         "2026-04-10T03:15:00Z",
		TotalRewardAmount:   12345,
	}

	require.NoError(t, msg.ValidateBasic())

	invalid := *msg
	invalid.Submitter = "bad-address"
	require.Error(t, invalid.ValidateBasic())

	missingRoot := *msg
	missingRoot.CanonicalRoot = ""
	require.Error(t, missingRoot.ValidateBasic())

	invalidSchema := *msg
	invalidSchema.SchemaVersion = "bad-schema"
	require.Error(t, invalidSchema.ValidateBasic())

	missingLane := *msg
	missingLane.Lane = ""
	require.Error(t, missingLane.ValidateBasic())

	missingPolicy := *msg
	missingPolicy.PolicyBundleVersion = ""
	require.Error(t, missingPolicy.ValidateBasic())

	missingRewardWindowRoot := *msg
	missingRewardWindowRoot.RewardWindowIdsRoot = ""
	require.Error(t, missingRewardWindowRoot.ValidateBasic())

	missingMinerRoot := *msg
	missingMinerRoot.MinerRewardRowsRoot = ""
	require.Error(t, missingMinerRoot.ValidateBasic())

	missingWindowEnd := *msg
	missingWindowEnd.WindowEndAt = ""
	require.Error(t, missingWindowEnd.ValidateBasic())
}

func TestAnchorSettlementBatchRejectsMalformedSha256Roots(t *testing.T) {
	msg := &types.MsgAnchorSettlementBatch{
		Submitter:           sdk.AccAddress(bytes.Repeat([]byte{0x01}, 20)).String(),
		SettlementBatchId:   "sb_2026_04_10_0001",
		AnchorJobId:         "anchor_job_01",
		Lane:                "fast",
		SchemaVersion:       "settlement.v1",
		PolicyBundleVersion: "policy.v1",
		CanonicalRoot:       "sha256:x",
		AnchorPayloadHash:   "sha256:" + strings.Repeat("b", 64),
		RewardWindowIdsRoot: "sha256:" + strings.Repeat("c", 64),
		TaskRunIdsRoot:      "sha256:" + strings.Repeat("d", 64),
		MinerRewardRowsRoot: "sha256:" + strings.Repeat("e", 64),
		WindowEndAt:         "2026-04-10T03:15:00Z",
		TotalRewardAmount:   12345,
	}

	err := msg.ValidateBasic()

	require.Error(t, err)
	require.Contains(t, err.Error(), "invalid settlement batch")
}

package cli

import (
	"strconv"

	"github.com/spf13/cobra"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/client/flags"
	"github.com/cosmos/cosmos-sdk/client/tx"

	"github.com/clawchain/clawchain/x/settlement/types"
)

const (
	flagLane                = "lane"
	flagSchemaVersion       = "schema-version"
	flagPolicyBundleVersion = "policy-bundle-version"
	flagRewardWindowIDsRoot = "reward-window-ids-root"
	flagTaskRunIDsRoot      = "task-run-ids-root"
	flagMinerRewardRowsRoot = "miner-reward-rows-root"
	flagWindowEndAt         = "window-end-at"
	flagTotalRewardAmount   = "total-reward-amount"
)

func NewTxCmd() *cobra.Command {
	txCmd := &cobra.Command{
		Use:                        types.ModuleName,
		Short:                      "Settlement transaction subcommands",
		DisableFlagParsing:         true,
		SuggestionsMinimumDistance: 2,
		RunE:                       client.ValidateCmd,
	}

	txCmd.AddCommand(
		NewAnchorSettlementBatchTxCmd(),
	)

	return txCmd
}

func NewAnchorSettlementBatchTxCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "anchor-batch [from_key_or_address] [settlement_batch_id] [anchor_job_id] [canonical_root] [anchor_payload_hash]",
		Short: "Anchor a settlement batch root onchain",
		Args:  cobra.ExactArgs(5),
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := cmd.Flags().Set(flags.FlagFrom, args[0]); err != nil {
				return err
			}

			clientCtx, err := client.GetClientTxContext(cmd)
			if err != nil {
				return err
			}

			totalRewardAmount, err := cmd.Flags().GetUint64(flagTotalRewardAmount)
			if err != nil {
				return err
			}
			msg := &types.MsgAnchorSettlementBatch{
				Submitter:           clientCtx.GetFromAddress().String(),
				SettlementBatchId:   args[1],
				AnchorJobId:         args[2],
				CanonicalRoot:       args[3],
				AnchorPayloadHash:   args[4],
				Lane:                mustGetString(cmd, flagLane),
				SchemaVersion:       mustGetString(cmd, flagSchemaVersion),
				PolicyBundleVersion: mustGetString(cmd, flagPolicyBundleVersion),
				RewardWindowIdsRoot: mustGetString(cmd, flagRewardWindowIDsRoot),
				TaskRunIdsRoot:      mustGetString(cmd, flagTaskRunIDsRoot),
				MinerRewardRowsRoot: mustGetString(cmd, flagMinerRewardRowsRoot),
				WindowEndAt:         mustGetString(cmd, flagWindowEndAt),
				TotalRewardAmount:   totalRewardAmount,
			}

			return tx.GenerateOrBroadcastTxCLI(clientCtx, cmd.Flags(), msg)
		},
	}

	cmd.Flags().String(flagLane, "", "Settlement lane label")
	cmd.Flags().String(flagSchemaVersion, "", "Settlement schema version")
	cmd.Flags().String(flagPolicyBundleVersion, "", "Policy bundle version")
	cmd.Flags().String(flagRewardWindowIDsRoot, "", "Reward window ids root")
	cmd.Flags().String(flagTaskRunIDsRoot, "", "Task run ids root")
	cmd.Flags().String(flagMinerRewardRowsRoot, "", "Miner reward rows root")
	cmd.Flags().String(flagWindowEndAt, "", "Window end time RFC3339")
	cmd.Flags().Uint64(flagTotalRewardAmount, 0, "Total reward amount in base units")
	flags.AddTxFlagsToCmd(cmd)

	return cmd
}

func mustGetString(cmd *cobra.Command, flag string) string {
	value, err := cmd.Flags().GetString(flag)
	if err != nil {
		panic("unexpected string flag read failure for " + flag + ": " + strconv.Quote(err.Error()))
	}
	return value
}

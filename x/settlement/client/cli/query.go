package cli

import (
	"encoding/json"

	"github.com/spf13/cobra"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/client/flags"

	"github.com/clawchain/clawchain/x/settlement/types"
)

func NewQueryCmd() *cobra.Command {
	queryCmd := &cobra.Command{
		Use:                        types.ModuleName,
		Short:                      "Settlement query subcommands",
		DisableFlagParsing:         true,
		SuggestionsMinimumDistance: 2,
		RunE:                       client.ValidateCmd,
	}
	queryCmd.AddCommand(NewSettlementAnchorQueryCmd())
	return queryCmd
}

func NewSettlementAnchorQueryCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "settlement-anchor [settlement_batch_id]",
		Short: "Query a settlement anchor by settlement batch id",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			clientCtx, err := client.GetClientQueryContext(cmd)
			if err != nil {
				return err
			}
			resp, err := types.NewQueryClient(clientCtx).SettlementAnchor(
				cmd.Context(),
				&types.QuerySettlementAnchorRequest{SettlementBatchID: args[0]},
			)
			if err != nil {
				return err
			}
			payload, err := json.Marshal(resp)
			if err != nil {
				return err
			}
			return clientCtx.PrintRaw(payload)
		},
	}
	flags.AddQueryFlagsToCmd(cmd)
	return cmd
}

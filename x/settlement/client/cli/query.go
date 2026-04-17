package cli

import (
	"fmt"

	"github.com/spf13/cobra"

	"github.com/cosmos/cosmos-sdk/client"

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
	return &cobra.Command{
		Use:   "settlement-anchor [settlement_batch_id]",
		Short: "Query a settlement anchor by settlement batch id",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if _, err := client.GetClientQueryContext(cmd); err != nil {
				return err
			}
			return fmt.Errorf("settlement anchor query client is not wired in this lightweight module build: %s", args[0])
		},
	}
}

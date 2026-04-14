package main

import (
	"context"
	"os"

	"cosmossdk.io/log"
	dbm "github.com/cosmos/cosmos-db"
	"io"

	cmtcfg "github.com/cometbft/cometbft/config"
	"github.com/spf13/cobra"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/client/config"
	"github.com/cosmos/cosmos-sdk/client/keys"
	"github.com/cosmos/cosmos-sdk/codec/address"
	"github.com/cosmos/cosmos-sdk/server"
	serverconfig "github.com/cosmos/cosmos-sdk/server/config"
	servertypes "github.com/cosmos/cosmos-sdk/server/types"
	"github.com/cosmos/cosmos-sdk/types/module"
	authcmdcli "github.com/cosmos/cosmos-sdk/x/auth/client/cli"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	bankcli "github.com/cosmos/cosmos-sdk/x/bank/client/cli"
	genutilcli "github.com/cosmos/cosmos-sdk/x/genutil/client/cli"

	"github.com/clawchain/clawchain/app"
)

func main() {
	app.SetConfig()
	rootCmd := NewRootCmd()
	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

func NewRootCmd() *cobra.Command {
	encodingConfig := app.MakeEncodingConfig()

	initClientCtx := client.Context{}.
		WithCodec(encodingConfig.Codec).
		WithInterfaceRegistry(encodingConfig.InterfaceRegistry).
		WithTxConfig(encodingConfig.TxConfig).
		WithLegacyAmino(encodingConfig.Amino).
		WithInput(os.Stdin).
		WithAccountRetriever(authtypes.AccountRetriever{}).
		WithHomeDir(app.DefaultNodeHome).
		WithViper("")

	preRunHandler := makePreRunHandler(initClientCtx)

	rootCmd := &cobra.Command{
		Use:               "clawchaind",
		Short:             "ClawChain - Proof of Availability AI Agent Blockchain",
		PersistentPreRunE: preRunHandler,
	}
	rootCmd.SetContext(context.WithValue(context.Background(), server.ServerContextKey, server.NewDefaultContext()))
	_ = client.SetCmdClientContext(rootCmd, initClientCtx)

	initRootCmd(rootCmd, encodingConfig, app.ModuleBasics, preRunHandler)
	return rootCmd
}

func makePreRunHandler(initClientCtx client.Context) func(cmd *cobra.Command, args []string) error {
	return func(cmd *cobra.Command, _ []string) error {
		cmd.SetOut(cmd.OutOrStdout())
		cmd.SetErr(cmd.ErrOrStderr())

		clientCtx, err := client.ReadPersistentCommandFlags(initClientCtx, cmd.Flags())
		if err != nil {
			return err
		}

		clientCtx, err = config.ReadFromClientConfig(clientCtx)
		if err != nil {
			return err
		}

		if err := client.SetCmdClientContextHandler(clientCtx, cmd); err != nil {
			return err
		}

		customAppTemplate, customAppConfig := initAppConfig()
		customCMTConfig := initCometBFTConfig()

		return server.InterceptConfigsPreRunHandler(cmd, customAppTemplate, customAppConfig, customCMTConfig)
	}
}

// initCometBFTConfig returns default CometBFT config
func initCometBFTConfig() *cmtcfg.Config {
	cfg := cmtcfg.DefaultConfig()
	return cfg
}

// initAppConfig returns custom app config template and config.
// Key: must return a struct with `mapstructure:",squash"` embedding
// so that viper can properly unmarshal all fields.
func initAppConfig() (string, interface{}) {
	type CustomAppConfig struct {
		serverconfig.Config `mapstructure:",squash"`
	}

	srvCfg := serverconfig.DefaultConfig()
	srvCfg.MinGasPrices = "0uclaw"

	customAppConfig := CustomAppConfig{
		Config: *srvCfg,
	}

	return serverconfig.DefaultConfigTemplate, customAppConfig
}

func initRootCmd(
	rootCmd *cobra.Command,
	encodingConfig app.EncodingConfig,
	basicManager module.BasicManager,
	preRunHandler func(cmd *cobra.Command, args []string) error,
) {
	rootCmd.AddCommand(
		genutilcli.InitCmd(app.AllModuleBasics(), app.DefaultNodeHome),
		genutilcli.Commands(encodingConfig.TxConfig, app.AllModuleBasics(), app.DefaultNodeHome),
		keys.Commands(),
	)

	// Use AddCommands (which internally calls StartCmd)
	server.AddCommands(rootCmd, app.DefaultNodeHome, newApp, appExport, addModuleInitFlags)

	// query/tx subcommands
	queryCmd := &cobra.Command{
		Use:               "query",
		Aliases:           []string{"q"},
		Short:             "Querying subcommands",
		RunE:              client.ValidateCmd,
		PersistentPreRunE: preRunHandler,
	}
	txCmd := &cobra.Command{
		Use:               "tx",
		Short:             "Transactions subcommands",
		RunE:              client.ValidateCmd,
		PersistentPreRunE: preRunHandler,
	}
	basicManager.AddQueryCommands(queryCmd)
	basicManager.AddTxCommands(txCmd)
	txCmd.AddCommand(
		authcmdcli.GetSignCommand(),
		authcmdcli.GetBroadcastCommand(),
	)
	replaceBankTxCommand(txCmd)
	rootCmd.AddCommand(queryCmd, txCmd)
}

func replaceBankTxCommand(txCmd *cobra.Command) {
	for _, cmd := range txCmd.Commands() {
		if cmd.Name() == "bank" {
			txCmd.RemoveCommand(cmd)
			break
		}
	}
	txCmd.AddCommand(bankcli.NewTxCmd(address.NewBech32Codec(app.AccountAddressPrefix)))
}

func newApp(logger log.Logger, db dbm.DB, traceStore io.Writer, appOpts servertypes.AppOptions) servertypes.Application {
	// Key fix: use DefaultBaseappOptions which handles min gas prices, pruning, etc.
	baseappOptions := server.DefaultBaseappOptions(appOpts)
	return app.NewClawChainApp(logger, db, traceStore, true, appOpts, baseappOptions...)
}

func appExport(
	logger log.Logger, db dbm.DB, traceStore io.Writer,
	height int64, forZeroHeight bool, jailAllowedAddrs []string,
	appOpts servertypes.AppOptions, modulesToExport []string,
) (servertypes.ExportedApp, error) {
	clawApp := app.NewClawChainApp(logger, db, traceStore, height == -1, appOpts)
	if height != -1 {
		if err := clawApp.LoadHeight(height); err != nil {
			return servertypes.ExportedApp{}, err
		}
	}
	return clawApp.ExportAppStateAndValidators(forZeroHeight, jailAllowedAddrs, modulesToExport)
}

func addModuleInitFlags(startCmd *cobra.Command) {
	// Add module-specific init flags here if needed
}

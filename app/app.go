package app

import (
	"encoding/json"
	"io"

	abci "github.com/cometbft/cometbft/abci/types"
	dbm "github.com/cosmos/cosmos-db"
	"cosmossdk.io/log"
	storetypes "cosmossdk.io/store/types"

	"github.com/cosmos/cosmos-sdk/baseapp"
	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/codec"
	"github.com/cosmos/cosmos-sdk/codec/address"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/runtime"
	"github.com/cosmos/cosmos-sdk/server/api"
	serverconfig "github.com/cosmos/cosmos-sdk/server/config"
	servertypes "github.com/cosmos/cosmos-sdk/server/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/module"
	"github.com/cosmos/cosmos-sdk/x/auth"
	authkeeper "github.com/cosmos/cosmos-sdk/x/auth/keeper"
	authtypes "github.com/cosmos/cosmos-sdk/x/auth/types"
	"github.com/cosmos/cosmos-sdk/x/bank"
	bankkeeper "github.com/cosmos/cosmos-sdk/x/bank/keeper"
	banktypes "github.com/cosmos/cosmos-sdk/x/bank/types"
	"github.com/cosmos/cosmos-sdk/x/consensus"
	consensuskeeper "github.com/cosmos/cosmos-sdk/x/consensus/keeper"
	consensustypes "github.com/cosmos/cosmos-sdk/x/consensus/types"
	distr "github.com/cosmos/cosmos-sdk/x/distribution"
	distrkeeper "github.com/cosmos/cosmos-sdk/x/distribution/keeper"
	distrtypes "github.com/cosmos/cosmos-sdk/x/distribution/types"
	"github.com/cosmos/cosmos-sdk/x/genutil"
	genutiltypes "github.com/cosmos/cosmos-sdk/x/genutil/types"
	"github.com/cosmos/cosmos-sdk/x/mint"
	mintkeeper "github.com/cosmos/cosmos-sdk/x/mint/keeper"
	minttypes "github.com/cosmos/cosmos-sdk/x/mint/types"
	"github.com/cosmos/cosmos-sdk/x/staking"
	stakingkeeper "github.com/cosmos/cosmos-sdk/x/staking/keeper"
	stakingtypes "github.com/cosmos/cosmos-sdk/x/staking/types"

	poakeeper "github.com/clawchain/clawchain/x/poa/keeper"
	poamodule "github.com/clawchain/clawchain/x/poa/module"
	poatypes "github.com/clawchain/clawchain/x/poa/types"
	challengekeeper "github.com/clawchain/clawchain/x/challenge/keeper"
	challengemodule "github.com/clawchain/clawchain/x/challenge/module"
	challengetypes "github.com/clawchain/clawchain/x/challenge/types"
	reputationkeeper "github.com/clawchain/clawchain/x/reputation/keeper"
	reputationmodule "github.com/clawchain/clawchain/x/reputation/module"
	reputationtypes "github.com/clawchain/clawchain/x/reputation/types"
)

var (
	// ModuleBasics 定义链的基础模块（不含需要 codec 的 CLI 模块）
	// staking/distr/mint 需要 codec 才能注册 CLI，用 GetModuleBasics() 获取完整版本
	// ModuleBasics 定义链的基础模块（不包含需要 codec 的 staking/distr/mint）
	// consensus.AppModuleBasic 不需要 codec，可以包含
	// staking/distr/mint 的 AppModuleBasic 需要 codec 才能调用 GetTxCmd，所以不放这里
	// 它们的接口已在 encoding.go 中通过 registerExtraModuleInterfaces 注册
	// 运行时它们在 ModuleManager 中完整初始化
	// CLI 安全的模块（不含staking/distr/mint/consensus，它们的GetTxCmd需要keeper会panic）
	ModuleBasics = module.NewBasicManager(
		auth.AppModuleBasic{},
		bank.AppModuleBasic{},
		genutil.NewAppModuleBasic(genutiltypes.DefaultMessageValidator),
		poamodule.AppModuleBasic{},
		challengemodule.AppModuleBasic{},
		reputationmodule.AppModuleBasic{},
	)

	// module account permissions
	maccPerms = map[string][]string{
		authtypes.FeeCollectorName:     nil,
		distrtypes.ModuleName:          nil,
		minttypes.ModuleName:           {authtypes.Minter},
		stakingtypes.BondedPoolName:    {authtypes.Burner, authtypes.Staking},
		stakingtypes.NotBondedPoolName: {authtypes.Burner, authtypes.Staking},
		poatypes.ModuleName:            {authtypes.Minter, authtypes.Burner},
	}
)

// ClawChainApp 主应用结构
type ClawChainApp struct {
	*baseapp.BaseApp

	cdc               codec.Codec
	legacyAmino       *codec.LegacyAmino
	appCodec          codec.Codec
	txConfig          client.TxConfig
	interfaceRegistry codectypes.InterfaceRegistry

	// keys 所有模块的 store keys
	keys    map[string]*storetypes.KVStoreKey
	tkeys   map[string]*storetypes.TransientStoreKey
	memKeys map[string]*storetypes.MemoryStoreKey

	// keepers
	AccountKeeper    authkeeper.AccountKeeper
	BankKeeper       bankkeeper.BaseKeeper
	ConsensusKeeper  consensuskeeper.Keeper
	StakingKeeper    *stakingkeeper.Keeper
	DistrKeeper      distrkeeper.Keeper
	MintKeeper       mintkeeper.Keeper
	PoAKeeper        poakeeper.Keeper
	ChallengeKeeper  challengekeeper.Keeper
	ReputationKeeper reputationkeeper.Keeper

	// module manager
	ModuleManager *module.Manager
}

// NewClawChainApp 创建新的 ClawChainApp
func NewClawChainApp(
	logger log.Logger,
	db dbm.DB,
	traceStore io.Writer,
	loadLatest bool,
	appOpts servertypes.AppOptions,
	baseAppOptions ...func(*baseapp.BaseApp),
) *ClawChainApp {
	encodingConfig := MakeEncodingConfig()
	appCodec := encodingConfig.Codec
	legacyAmino := encodingConfig.Amino
	interfaceRegistry := encodingConfig.InterfaceRegistry
	txConfig := encodingConfig.TxConfig

	bApp := baseapp.NewBaseApp(AppName, logger, db, txConfig.TxDecoder(), baseAppOptions...)
	bApp.SetCommitMultiStoreTracer(traceStore)
	bApp.SetVersion("0.1.0")
	bApp.SetInterfaceRegistry(interfaceRegistry)
	bApp.SetTxEncoder(txConfig.TxEncoder())

	keys := storetypes.NewKVStoreKeys(
		authtypes.StoreKey,
		banktypes.StoreKey,
		consensustypes.StoreKey,
		stakingtypes.StoreKey,
		distrtypes.StoreKey,
		minttypes.StoreKey,
		poatypes.StoreKey,
		challengetypes.StoreKey,
		reputationtypes.StoreKey,
	)
	tkeys := storetypes.NewTransientStoreKeys()
	memKeys := storetypes.NewMemoryStoreKeys()

	app := &ClawChainApp{
		BaseApp:           bApp,
		cdc:               appCodec,
		legacyAmino:       legacyAmino,
		appCodec:          appCodec,
		txConfig:          txConfig,
		interfaceRegistry: interfaceRegistry,
		keys:              keys,
		tkeys:             tkeys,
		memKeys:           memKeys,
	}

	// init keepers
	app.AccountKeeper = authkeeper.NewAccountKeeper(
		appCodec,
		runtime.NewKVStoreService(keys[authtypes.StoreKey]),
		authtypes.ProtoBaseAccount,
		maccPerms,
		address.NewBech32Codec(AccountAddressPrefix),
		AccountAddressPrefix,
		authtypes.NewModuleAddress("gov").String(),
	)

	app.BankKeeper = bankkeeper.NewBaseKeeper(
		appCodec,
		runtime.NewKVStoreService(keys[banktypes.StoreKey]),
		app.AccountKeeper,
		BlockedModuleAccountAddrs(),
		authtypes.NewModuleAddress("gov").String(),
		logger,
	)

	app.ConsensusKeeper = consensuskeeper.NewKeeper(
		appCodec,
		runtime.NewKVStoreService(keys[consensustypes.StoreKey]),
		authtypes.NewModuleAddress("gov").String(),
		runtime.EventService{},
	)
	// 关键：设置 consensus params store，否则 replay 时报错
	bApp.SetParamStore(app.ConsensusKeeper.ParamsStore)

	app.StakingKeeper = stakingkeeper.NewKeeper(
		appCodec,
		runtime.NewKVStoreService(keys[stakingtypes.StoreKey]),
		app.AccountKeeper,
		app.BankKeeper,
		authtypes.NewModuleAddress("gov").String(),
		address.NewBech32Codec(AccountAddressPrefix+"valoper"),
		address.NewBech32Codec(AccountAddressPrefix+"valcons"),
	)

	app.DistrKeeper = distrkeeper.NewKeeper(
		appCodec,
		runtime.NewKVStoreService(keys[distrtypes.StoreKey]),
		app.AccountKeeper,
		app.BankKeeper,
		app.StakingKeeper,
		authtypes.FeeCollectorName,
		authtypes.NewModuleAddress("gov").String(),
	)

	app.MintKeeper = mintkeeper.NewKeeper(
		appCodec,
		runtime.NewKVStoreService(keys[minttypes.StoreKey]),
		app.StakingKeeper,
		app.AccountKeeper,
		app.BankKeeper,
		authtypes.FeeCollectorName,
		authtypes.NewModuleAddress("gov").String(),
	)

	app.PoAKeeper = poakeeper.NewKeeper(
		appCodec,
		keys[poatypes.StoreKey],
	)

	app.ChallengeKeeper = challengekeeper.NewKeeper(
		appCodec,
		keys[challengetypes.StoreKey],
	)

	app.ReputationKeeper = reputationkeeper.NewKeeper(
		appCodec,
		keys[reputationtypes.StoreKey],
	)

	// set BaseApp CMS
	app.MountKVStores(keys)
	app.MountTransientStores(tkeys)
	app.MountMemoryStores(memKeys)

	// set BaseApp init/begin/end blockers
	app.SetInitChainer(app.InitChainer)
	app.SetBeginBlocker(app.BeginBlocker)
	app.SetEndBlocker(app.EndBlocker)

	// create module manager
	app.ModuleManager = module.NewManager(
		auth.NewAppModule(appCodec, app.AccountKeeper, nil, nil),
		bank.NewAppModule(appCodec, app.BankKeeper, app.AccountKeeper, nil),
		consensus.NewAppModule(appCodec, app.ConsensusKeeper),
		staking.NewAppModule(appCodec, app.StakingKeeper, app.AccountKeeper, app.BankKeeper, nil),
		distr.NewAppModule(appCodec, app.DistrKeeper, app.AccountKeeper, app.BankKeeper, app.StakingKeeper, nil),
		mint.NewAppModule(appCodec, app.MintKeeper, app.AccountKeeper, nil, nil),
		genutil.NewAppModule(app.AccountKeeper, app.StakingKeeper, app, encodingConfig.TxConfig),
		poamodule.NewAppModule(app.PoAKeeper),
		challengemodule.NewAppModule(app.ChallengeKeeper),
		reputationmodule.NewAppModule(app.ReputationKeeper),
	)

	// set order for init genesis — staking before genutil (genutil processes gentxs)
	app.ModuleManager.SetOrderInitGenesis(
		authtypes.ModuleName,
		banktypes.ModuleName,
		distrtypes.ModuleName,
		stakingtypes.ModuleName,
		minttypes.ModuleName,
		genutiltypes.ModuleName,
		consensustypes.ModuleName,
		poatypes.ModuleName,
		challengetypes.ModuleName,
		reputationtypes.ModuleName,
	)

	// set order for begin/end block
	app.ModuleManager.SetOrderBeginBlockers(
		minttypes.ModuleName,
		distrtypes.ModuleName,
		stakingtypes.ModuleName,
		consensustypes.ModuleName,
		poatypes.ModuleName,
		challengetypes.ModuleName,
		reputationtypes.ModuleName,
	)

	app.ModuleManager.SetOrderEndBlockers(
		stakingtypes.ModuleName,
		consensustypes.ModuleName,
		poatypes.ModuleName,
		challengetypes.ModuleName,
		reputationtypes.ModuleName,
	)

	// register module services
	app.ModuleManager.RegisterServices(module.NewConfigurator(app.appCodec, app.MsgServiceRouter(), app.GRPCQueryRouter()))

	if loadLatest {
		if err := app.LoadLatestVersion(); err != nil {
			panic(err)
		}
	}

	return app
}

// Name 返回应用名称
func (app *ClawChainApp) Name() string { return AppName }

// LegacyAmino 返回 legacy amino codec
func (app *ClawChainApp) LegacyAmino() *codec.LegacyAmino {
	return app.legacyAmino
}

// AppCodec 返回 app codec
func (app *ClawChainApp) AppCodec() codec.Codec {
	return app.appCodec
}

// InterfaceRegistry 返回接口注册表
func (app *ClawChainApp) InterfaceRegistry() codectypes.InterfaceRegistry {
	return app.interfaceRegistry
}

// TxConfig 返回 tx config
func (app *ClawChainApp) TxConfig() client.TxConfig {
	return app.txConfig
}

// InitChainer 初始化链
func (app *ClawChainApp) InitChainer(ctx sdk.Context, req *abci.RequestInitChain) (*abci.ResponseInitChain, error) {
	var genesisState GenesisState
	if err := json.Unmarshal(req.AppStateBytes, &genesisState); err != nil {
		return nil, err
	}
	return app.ModuleManager.InitGenesis(ctx, app.appCodec, genesisState)
}

// BeginBlocker 区块开始处理
func (app *ClawChainApp) BeginBlocker(ctx sdk.Context) (sdk.BeginBlock, error) {
	return app.ModuleManager.BeginBlock(ctx)
}

// EndBlocker 区块结束处理
func (app *ClawChainApp) EndBlocker(ctx sdk.Context) (sdk.EndBlock, error) {
	return app.ModuleManager.EndBlock(ctx)
}

// LoadHeight 加载指定高度
func (app *ClawChainApp) LoadHeight(height int64) error {
	return app.LoadVersion(height)
}

// BlockedModuleAccountAddrs 返回被阻止的模块账户地址
func BlockedModuleAccountAddrs() map[string]bool {
	modAccAddrs := make(map[string]bool)
	for acc := range maccPerms {
		modAccAddrs[authtypes.NewModuleAddress(acc).String()] = true
	}
	return modAccAddrs
}

// RegisterAPIRoutes 注册 API 路由
func (app *ClawChainApp) RegisterAPIRoutes(apiSvr *api.Server, apiConfig serverconfig.APIConfig) {
	// Register gRPC Gateway routes
}

// RegisterTxService 注册 tx 服务
func (app *ClawChainApp) RegisterTxService(clientCtx client.Context) {
	// Tx service registered via gRPC
}

// RegisterTendermintService 注册 Tendermint 服务
func (app *ClawChainApp) RegisterTendermintService(clientCtx client.Context) {
	// Tendermint service registered via gRPC
}

// RegisterNodeService 注册 Node 服务
func (app *ClawChainApp) RegisterNodeService(clientCtx client.Context, cfg serverconfig.Config) {
	// Register Node gRPC service
}

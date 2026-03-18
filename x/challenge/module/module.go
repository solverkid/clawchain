package module

import (
	"context"
	"encoding/json"

	gwruntime "github.com/grpc-ecosystem/grpc-gateway/runtime"

	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/codec"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/cosmos/cosmos-sdk/types/module"

	"github.com/clawchain/clawchain/x/challenge/keeper"
	"github.com/clawchain/clawchain/x/challenge/types"
)

var (
	_ module.AppModuleBasic = AppModuleBasic{}
	_ module.HasGenesis     = AppModule{}
	_ module.AppModule      = AppModule{}
)

// AppModuleBasic implements module.AppModuleBasic
type AppModuleBasic struct{}

func (AppModuleBasic) Name() string { return types.ModuleName }

func (AppModuleBasic) RegisterLegacyAminoCodec(_ *codec.LegacyAmino) {}

func (AppModuleBasic) RegisterInterfaces(_ codectypes.InterfaceRegistry) {}

func (AppModuleBasic) RegisterGRPCGatewayRoutes(_ client.Context, _ *gwruntime.ServeMux) {}

func (AppModuleBasic) DefaultGenesis(_ codec.JSONCodec) json.RawMessage {
	gs := types.DefaultGenesis()
	bz, _ := json.Marshal(gs)
	return bz
}

func (AppModuleBasic) ValidateGenesis(_ codec.JSONCodec, _ client.TxEncodingConfig, bz json.RawMessage) error {
	var gs types.GenesisState
	if err := json.Unmarshal(bz, &gs); err != nil {
		return err
	}
	return gs.Validate()
}

// AppModule implements module.AppModule
type AppModule struct {
	AppModuleBasic
	keeper keeper.Keeper
}

func NewAppModule(k keeper.Keeper) AppModule {
	return AppModule{keeper: k}
}

func (am AppModule) RegisterServices(cfg module.Configurator) {
	types.RegisterMsgServer(cfg.MsgServer(), keeper.NewMsgServerImpl(am.keeper))
	types.RegisterQueryServer(cfg.QueryServer(), keeper.NewQueryServerImpl(am.keeper))
}

func (am AppModule) InitGenesis(ctx sdk.Context, _ codec.JSONCodec, data json.RawMessage) {
	var gs types.GenesisState
	json.Unmarshal(data, &gs)
	am.keeper.InitGenesis(ctx, gs)
}

func (am AppModule) ExportGenesis(ctx sdk.Context, _ codec.JSONCodec) json.RawMessage {
	gs := am.keeper.ExportGenesis(ctx)
	bz, _ := json.Marshal(gs)
	return bz
}

func (am AppModule) ConsensusVersion() uint64 { return 1 }

func (am AppModule) BeginBlock(goCtx context.Context) error {
	ctx := sdk.UnwrapSDKContext(goCtx)
	// 每 10 个区块生成一次公开挑战（任何矿工都可以参与）
	if ctx.BlockHeight()%10 == 0 && ctx.BlockHeight() > 0 {
		epoch := uint64(ctx.BlockHeight() / 10)
		am.keeper.GeneratePublicChallenge(ctx, epoch)
	}
	return nil
}

func (am AppModule) EndBlock(goCtx context.Context) error {
	ctx := sdk.UnwrapSDKContext(goCtx)
	// 处理待结算的奖励（转账）
	if err := am.keeper.ProcessPendingRewards(ctx); err != nil {
		am.keeper.Logger(ctx).Error("处理待结算奖励失败", "error", err)
	}
	return nil
}

func (am AppModule) IsOnePerModuleType() {}
func (am AppModule) IsAppModule()        {}

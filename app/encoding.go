package app

import (
	txsigning "cosmossdk.io/x/tx/signing"
	"github.com/cosmos/cosmos-sdk/client"
	"github.com/cosmos/cosmos-sdk/codec"
	"github.com/cosmos/cosmos-sdk/codec/address"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	"github.com/cosmos/cosmos-sdk/std"
	"github.com/cosmos/cosmos-sdk/types/module"
	"github.com/cosmos/cosmos-sdk/x/auth/tx"
	"github.com/cosmos/cosmos-sdk/x/consensus"
	distr "github.com/cosmos/cosmos-sdk/x/distribution"
	"github.com/cosmos/cosmos-sdk/x/mint"
	"github.com/cosmos/cosmos-sdk/x/staking"
	gogoproto "github.com/cosmos/gogoproto/proto"
)

type EncodingConfig struct {
	InterfaceRegistry codectypes.InterfaceRegistry
	Codec             codec.Codec
	TxConfig          client.TxConfig
	Amino             *codec.LegacyAmino
}

var extraBasics = module.NewBasicManager(
	consensus.AppModuleBasic{},
	staking.AppModuleBasic{},
	distr.AppModuleBasic{},
	mint.AppModuleBasic{},
)

func MakeEncodingConfig() EncodingConfig {
	amino := codec.NewLegacyAmino()

	// 创建带有 address codec 的 InterfaceRegistry（修复 gentx address codec 问题）
	interfaceRegistry, err := codectypes.NewInterfaceRegistryWithOptions(codectypes.InterfaceRegistryOptions{
		ProtoFiles: gogoproto.HybridResolver,
		SigningOptions: txsigning.Options{
			AddressCodec:          address.NewBech32Codec(AccountAddressPrefix),
			ValidatorAddressCodec: address.NewBech32Codec(AccountAddressPrefix + "valoper"),
		},
	})
	if err != nil {
		panic(err)
	}

	cdc := codec.NewProtoCodec(interfaceRegistry)
	txCfg := tx.NewTxConfig(cdc, tx.DefaultSignModes)

	std.RegisterLegacyAminoCodec(amino)
	std.RegisterInterfaces(interfaceRegistry)

	ModuleBasics.RegisterLegacyAminoCodec(amino)
	ModuleBasics.RegisterInterfaces(interfaceRegistry)

	extraBasics.RegisterLegacyAminoCodec(amino)
	extraBasics.RegisterInterfaces(interfaceRegistry)

	return EncodingConfig{
		InterfaceRegistry: interfaceRegistry,
		Codec:             cdc,
		TxConfig:          txCfg,
		Amino:             amino,
	}
}

func AllModuleBasics() module.BasicManager {
	all := make(module.BasicManager)
	for k, v := range ModuleBasics {
		all[k] = v
	}
	for k, v := range extraBasics {
		all[k] = v
	}
	return all
}

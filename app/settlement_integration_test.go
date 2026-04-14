package app

import (
	"io"
	"testing"

	"cosmossdk.io/log"
	dbm "github.com/cosmos/cosmos-db"
	codectypes "github.com/cosmos/cosmos-sdk/codec/types"
	sdk "github.com/cosmos/cosmos-sdk/types"
	"github.com/stretchr/testify/require"

	settlementtypes "github.com/clawchain/clawchain/x/settlement/types"
)

func TestMakeEncodingConfigRegistersSettlementMsg(t *testing.T) {
	encCfg := MakeEncodingConfig()

	anyValue, err := codectypes.NewAnyWithValue(&settlementtypes.MsgAnchorSettlementBatch{})
	require.NoError(t, err)
	require.Equal(t, "/clawchain.settlement.v1.MsgAnchorSettlementBatch", anyValue.TypeUrl)

	var unpacked sdk.Msg
	err = encCfg.Codec.UnpackAny(anyValue, &unpacked)
	require.NoError(t, err)

	_, ok := unpacked.(*settlementtypes.MsgAnchorSettlementBatch)
	require.True(t, ok)
}

func TestNewDefaultGenesisStateIncludesSettlementModule(t *testing.T) {
	genesis := NewDefaultGenesisState()
	_, ok := genesis[settlementtypes.ModuleName]
	require.True(t, ok)
}

func TestNewClawChainAppIncludesSettlementModule(t *testing.T) {
	if sdk.GetConfig().GetBech32AccountAddrPrefix() != AccountAddressPrefix {
		SetConfig()
	}
	require.NotPanics(t, func() {
		_ = NewClawChainApp(log.NewNopLogger(), dbm.NewMemDB(), io.Discard, false, nil)
	})
}

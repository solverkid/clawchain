package keeper

import (
	"encoding/json"

	"cosmossdk.io/log"
	storetypes "cosmossdk.io/store/types"
	"github.com/cosmos/cosmos-sdk/codec"
	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/clawchain/clawchain/x/settlement/types"
)

type Keeper struct {
	cdc      codec.BinaryCodec
	storeKey storetypes.StoreKey
}

func NewKeeper(cdc codec.BinaryCodec, storeKey storetypes.StoreKey) Keeper {
	return Keeper{
		cdc:      cdc,
		storeKey: storeKey,
	}
}

func (k Keeper) Logger(ctx sdk.Context) log.Logger {
	return ctx.Logger().With("module", "x/"+types.ModuleName)
}

func (k Keeper) HasSettlementAnchor(ctx sdk.Context, settlementBatchID string) bool {
	store := ctx.KVStore(k.storeKey)
	return store.Has(types.GetSettlementAnchorKey(settlementBatchID))
}

func (k Keeper) SetSettlementAnchor(ctx sdk.Context, anchor types.SettlementAnchor) error {
	store := ctx.KVStore(k.storeKey)
	bz, err := json.Marshal(anchor)
	if err != nil {
		return err
	}
	store.Set(types.GetSettlementAnchorKey(anchor.SettlementBatchID), bz)
	return nil
}

func (k Keeper) GetSettlementAnchor(ctx sdk.Context, settlementBatchID string) (*types.SettlementAnchor, bool) {
	store := ctx.KVStore(k.storeKey)
	bz := store.Get(types.GetSettlementAnchorKey(settlementBatchID))
	if bz == nil {
		return nil, false
	}

	var anchor types.SettlementAnchor
	if err := json.Unmarshal(bz, &anchor); err != nil {
		return nil, false
	}
	return &anchor, true
}

func (k Keeper) InitGenesis(ctx sdk.Context, gs types.GenesisState) {
	for _, anchor := range gs.Anchors {
		_ = k.SetSettlementAnchor(ctx, anchor)
	}
}

func (k Keeper) ExportGenesis(ctx sdk.Context) *types.GenesisState {
	store := ctx.KVStore(k.storeKey)
	iter := storetypes.KVStorePrefixIterator(store, types.SettlementAnchorKeyPrefix)
	defer iter.Close()

	anchors := make([]types.SettlementAnchor, 0)
	for ; iter.Valid(); iter.Next() {
		var anchor types.SettlementAnchor
		if err := json.Unmarshal(iter.Value(), &anchor); err != nil {
			continue
		}
		anchors = append(anchors, anchor)
	}

	return &types.GenesisState{Anchors: anchors}
}

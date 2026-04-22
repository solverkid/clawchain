package keeper

import (
	"encoding/json"
	"slices"
	"strconv"

	storetypes "cosmossdk.io/store/types"
	sdk "github.com/cosmos/cosmos-sdk/types"

	"github.com/clawchain/clawchain/x/reputation/types"
)

// SettlementAnchorReader 限制 reputation delta 只能绑定已锚定的 settlement batch。
type SettlementAnchorReader interface {
	HasSettlementAnchor(ctx sdk.Context, settlementBatchID string) bool
}

func (k *Keeper) SetSettlementAnchorReader(reader SettlementAnchorReader) {
	k.settlementAnchorReader = reader
}

// GetMinerScore 返回 challenge keeper 需要的分数视图。
func (k Keeper) GetMinerScore(ctx sdk.Context, addr string) (int32, bool) {
	score, found := k.GetScore(ctx, addr)
	if !found {
		return 0, false
	}
	return score.Score, true
}

func (k Keeper) SetAuthorizedDeltaController(ctx sdk.Context, controller string) error {
	if _, err := sdk.AccAddressFromBech32(controller); err != nil {
		return err
	}
	store := ctx.KVStore(k.storeKey)
	store.Set(types.GetAuthorizedDeltaControllerKey(controller), []byte{0x01})
	return nil
}

func (k Keeper) IsAuthorizedDeltaController(ctx sdk.Context, controller string) bool {
	store := ctx.KVStore(k.storeKey)
	return store.Has(types.GetAuthorizedDeltaControllerKey(controller))
}

func (k Keeper) GetAuthorizedDeltaControllers(ctx sdk.Context) []string {
	store := ctx.KVStore(k.storeKey)
	iter := storetypes.KVStorePrefixIterator(store, types.AuthorizedDeltaControllerPrefix)
	defer iter.Close()

	controllers := make([]string, 0)
	for ; iter.Valid(); iter.Next() {
		controller := string(iter.Key()[len(types.AuthorizedDeltaControllerPrefix):])
		controllers = append(controllers, controller)
	}
	slices.Sort(controllers)
	return controllers
}

func (k Keeper) GetAppliedReputationDelta(ctx sdk.Context, deltaID string) (types.AppliedReputationDelta, bool) {
	store := ctx.KVStore(k.storeKey)
	bz := store.Get(types.GetAppliedReputationDeltaKey(deltaID))
	if bz == nil {
		return types.AppliedReputationDelta{}, false
	}

	var receipt types.AppliedReputationDelta
	if err := json.Unmarshal(bz, &receipt); err != nil {
		return types.AppliedReputationDelta{}, false
	}
	return receipt, true
}

func (k Keeper) SetAppliedReputationDelta(ctx sdk.Context, receipt types.AppliedReputationDelta) error {
	bz, err := json.Marshal(receipt)
	if err != nil {
		return err
	}
	store := ctx.KVStore(k.storeKey)
	store.Set(types.GetAppliedReputationDeltaKey(receipt.Delta.DeltaID), bz)
	return nil
}

func (k Keeper) GetAllAppliedReputationDeltas(ctx sdk.Context) []types.AppliedReputationDelta {
	store := ctx.KVStore(k.storeKey)
	iter := storetypes.KVStorePrefixIterator(store, types.AppliedReputationDeltaPrefix)
	defer iter.Close()

	receipts := make([]types.AppliedReputationDelta, 0)
	for ; iter.Valid(); iter.Next() {
		var receipt types.AppliedReputationDelta
		if err := json.Unmarshal(iter.Value(), &receipt); err != nil {
			continue
		}
		receipts = append(receipts, receipt)
	}
	slices.SortFunc(receipts, func(a, b types.AppliedReputationDelta) int {
		switch {
		case a.Delta.DeltaID < b.Delta.DeltaID:
			return -1
		case a.Delta.DeltaID > b.Delta.DeltaID:
			return 1
		default:
			return 0
		}
	})
	return receipts
}

// ApplyReputationDelta 只接受授权 controller 的 append-only 窗口级 delta。
func (k Keeper) ApplyReputationDelta(
	ctx sdk.Context,
	controller string,
	delta types.ReputationDelta,
) (types.AppliedReputationDelta, error) {
	if !k.IsAuthorizedDeltaController(ctx, controller) {
		return types.AppliedReputationDelta{}, types.ErrUnauthorizedDeltaController.Wrapf("%s", controller)
	}
	if err := delta.Validate(); err != nil {
		return types.AppliedReputationDelta{}, err
	}
	if k.settlementAnchorReader == nil || !k.settlementAnchorReader.HasSettlementAnchor(ctx, delta.SettlementBatchID) {
		return types.AppliedReputationDelta{}, types.ErrSettlementAnchorRequired.Wrapf("%s", delta.SettlementBatchID)
	}

	payloadHash, err := delta.PayloadHash()
	if err != nil {
		return types.AppliedReputationDelta{}, err
	}
	if existing, found := k.GetAppliedReputationDelta(ctx, delta.DeltaID); found {
		if existing.PayloadHash != payloadHash {
			return types.AppliedReputationDelta{}, types.ErrReputationDeltaConflict.Wrapf(
				"delta_id %s already applied with different payload",
				delta.DeltaID,
			)
		}
		return existing, nil
	}

	oldScore, found := k.GetMinerScore(ctx, delta.MinerAddress)
	if !found {
		k.InitMiner(ctx, delta.MinerAddress)
		oldScore, _ = k.GetMinerScore(ctx, delta.MinerAddress)
	}

	k.UpdateScore(ctx, delta.MinerAddress, delta.Delta, delta.Reason)
	newScore, _ := k.GetMinerScore(ctx, delta.MinerAddress)

	receipt := types.AppliedReputationDelta{
		Delta:           delta,
		Controller:      controller,
		PayloadHash:     payloadHash,
		OldScore:        oldScore,
		NewScore:        newScore,
		AppliedAtHeight: ctx.BlockHeight(),
		AppliedAtUnix:   ctx.BlockTime().Unix(),
	}
	if err := k.SetAppliedReputationDelta(ctx, receipt); err != nil {
		return types.AppliedReputationDelta{}, err
	}

	ctx.EventManager().EmitEvent(sdk.NewEvent(
		types.EventTypeReputationDeltaApplied,
		sdk.NewAttribute(types.AttributeKeyDeltaID, delta.DeltaID),
		sdk.NewAttribute(types.AttributeKeyController, controller),
		sdk.NewAttribute(types.AttributeKeyMiner, delta.MinerAddress),
		sdk.NewAttribute(types.AttributeKeySettlementBatchID, delta.SettlementBatchID),
		sdk.NewAttribute(types.AttributeKeyRewardWindowID, delta.RewardWindowID),
		sdk.NewAttribute(types.AttributeKeyOldScore, strconv.FormatInt(int64(oldScore), 10)),
		sdk.NewAttribute(types.AttributeKeyNewScore, strconv.FormatInt(int64(newScore), 10)),
		sdk.NewAttribute(types.AttributeKeyPayloadHash, payloadHash),
	))

	return receipt, nil
}

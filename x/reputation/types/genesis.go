package types

import (
	"slices"

	sdk "github.com/cosmos/cosmos-sdk/types"
)

// GenesisState 声誉模块创世状态
type GenesisState struct {
	Scores                     []ReputationScore        `json:"scores"`
	AuthorizedDeltaControllers []string                 `json:"authorized_delta_controllers"`
	AppliedDeltas              []AppliedReputationDelta `json:"applied_deltas"`
}

// DefaultGenesis 默认创世
func DefaultGenesis() *GenesisState {
	return &GenesisState{
		Scores:                     []ReputationScore{},
		AuthorizedDeltaControllers: []string{},
		AppliedDeltas:              []AppliedReputationDelta{},
	}
}

// Validate 验证
func (gs GenesisState) Validate() error {
	seenControllers := make(map[string]struct{}, len(gs.AuthorizedDeltaControllers))
	for _, controller := range gs.AuthorizedDeltaControllers {
		if _, err := sdk.AccAddressFromBech32(controller); err != nil {
			return err
		}
		if _, exists := seenControllers[controller]; exists {
			return ErrUnauthorizedDeltaController.Wrapf("duplicate authorized controller %s", controller)
		}
		seenControllers[controller] = struct{}{}
	}

	seenDeltaIDs := make(map[string]struct{}, len(gs.AppliedDeltas))
	for _, receipt := range gs.AppliedDeltas {
		if err := receipt.Validate(); err != nil {
			return err
		}
		deltaID := receipt.Delta.DeltaID
		if _, exists := seenDeltaIDs[deltaID]; exists {
			return ErrReputationDeltaConflict.Wrapf("duplicate applied delta %s", deltaID)
		}
		seenDeltaIDs[deltaID] = struct{}{}
	}

	slices.Sort(gs.AuthorizedDeltaControllers)
	return nil
}

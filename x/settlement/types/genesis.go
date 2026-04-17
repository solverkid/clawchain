package types

import sdk "github.com/cosmos/cosmos-sdk/types"

type GenesisState struct {
	Anchors              []SettlementAnchor `json:"anchors"`
	AuthorizedSubmitters []string           `json:"authorized_submitters"`
}

func DefaultGenesis() *GenesisState {
	return &GenesisState{
		Anchors:              []SettlementAnchor{},
		AuthorizedSubmitters: []string{},
	}
}

func (gs GenesisState) Validate() error {
	seen := make(map[string]struct{}, len(gs.AuthorizedSubmitters))
	for _, submitter := range gs.AuthorizedSubmitters {
		if _, err := sdk.AccAddressFromBech32(submitter); err != nil {
			return err
		}
		if _, ok := seen[submitter]; ok {
			return ErrUnauthorizedSubmitter.Wrapf("duplicate authorized submitter %s", submitter)
		}
		seen[submitter] = struct{}{}
	}
	return nil
}

package types

type GenesisState struct {
	Anchors []SettlementAnchor `json:"anchors"`
}

func DefaultGenesis() *GenesisState {
	return &GenesisState{
		Anchors: []SettlementAnchor{},
	}
}

func (gs GenesisState) Validate() error {
	return nil
}

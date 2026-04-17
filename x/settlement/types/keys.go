package types

const (
	ModuleName = "settlement"
	StoreKey   = ModuleName
	RouterKey  = ModuleName
)

var (
	SettlementAnchorKeyPrefix          = []byte{0x01}
	AuthorizedAnchorSubmitterKeyPrefix = []byte{0x02}
)

func GetSettlementAnchorKey(settlementBatchID string) []byte {
	return append(append([]byte{}, SettlementAnchorKeyPrefix...), []byte(settlementBatchID)...)
}

func GetAuthorizedAnchorSubmitterKey(submitter string) []byte {
	return append(append([]byte{}, AuthorizedAnchorSubmitterKeyPrefix...), []byte(submitter)...)
}

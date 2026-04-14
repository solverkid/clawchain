package types

const (
	ModuleName = "settlement"
	StoreKey   = ModuleName
	RouterKey  = ModuleName
)

var (
	SettlementAnchorKeyPrefix = []byte{0x01}
)

func GetSettlementAnchorKey(settlementBatchID string) []byte {
	return append(SettlementAnchorKeyPrefix, []byte(settlementBatchID)...)
}

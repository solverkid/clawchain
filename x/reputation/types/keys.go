package types

const (
	ModuleName = "reputation"
	StoreKey   = ModuleName
	RouterKey  = ModuleName
)

var (
	ScoreKeyPrefix  = []byte{0x01}
	StreakKeyPrefix  = []byte{0x02} // 连续签到信息前缀（备用，目前内嵌在 Score 里）
)

func GetScoreKey(addr string) []byte {
	return append(ScoreKeyPrefix, []byte(addr)...)
}

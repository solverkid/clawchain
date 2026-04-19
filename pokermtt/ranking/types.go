package ranking

type RedisKeys struct {
	UserInfo   string `json:"user_info"`
	AliveScore string `json:"alive_score"`
	DiedInfo   string `json:"died_info"`
}

type ZMember struct {
	Member string  `json:"member"`
	Score  float64 `json:"score"`
}

type LiveSnapshot struct {
	TournamentID         string            `json:"tournament_id"`
	SourceMTTID          string            `json:"source_mtt_id"`
	GameType             string            `json:"game_type"`
	RuntimeState         string            `json:"runtime_state,omitempty"`
	QuietPeriodSatisfied bool              `json:"quiet_period_satisfied,omitempty"`
	Keys                 RedisKeys         `json:"keys"`
	UserInfo             map[string]string `json:"user_info"`
	Alive                []ZMember         `json:"alive"`
	Died                 []string          `json:"died"`
}

type RegistrationSnapshot struct {
	TournamentID string            `json:"tournament_id"`
	SourceMTTID  string            `json:"source_mtt_id"`
	UserInfo     map[string]string `json:"user_info"`
}

type RankState string

const (
	RankStateRanked                  RankState = "ranked"
	RankStateWaitingNoShow           RankState = "waiting_no_show"
	RankStateUnresolvedSnapshot      RankState = "unresolved_snapshot"
	RankStateVoided                  RankState = "voided"
	RankStateDuplicateEntryCollapsed RankState = "duplicate_entry_collapsed"
)

type StandingStatus string

const (
	StandingStatusAlive   StandingStatus = "alive"
	StandingStatusDied    StandingStatus = "died"
	StandingStatusPending StandingStatus = "pending"
)

type Finalization struct {
	TournamentID        string            `json:"tournament_id"`
	SourceMTTID         string            `json:"source_mtt_id"`
	SnapshotID          string            `json:"standing_snapshot_id"`
	SnapshotHash        string            `json:"standing_snapshot_hash"`
	Root                string            `json:"root"`
	PolicyBundleVersion string            `json:"policy_bundle_version"`
	Rows                []FinalRankingRow `json:"rows"`
}

type FinalRankingRow struct {
	ID                   string         `json:"id"`
	TournamentID         string         `json:"tournament_id"`
	SourceMTTID          string         `json:"source_mtt_id"`
	SourceUserID         string         `json:"source_user_id"`
	MinerAddress         string         `json:"miner_address"`
	EconomicUnitID       string         `json:"economic_unit_id"`
	MemberID             string         `json:"member_id"`
	EntryNumber          int            `json:"entry_number"`
	ReentryCount         int            `json:"reentry_count"`
	Rank                 *int           `json:"rank"`
	DisplayRank          *int           `json:"display_rank,omitempty"`
	RankState            RankState      `json:"rank_state"`
	RankBasis            string         `json:"rank_basis,omitempty"`
	RankTiebreaker       string         `json:"rank_tiebreaker,omitempty"`
	Chip                 float64        `json:"chip"`
	ChipDelta            float64        `json:"chip_delta"`
	DiedTime             string         `json:"died_time"`
	WaitingOrNoShow      bool           `json:"waiting_or_no_show"`
	Bounty               float64        `json:"bounty"`
	DefeatNum            int            `json:"defeat_num"`
	FieldSizePolicy      string         `json:"field_size_policy"`
	StandingSnapshotID   string         `json:"standing_snapshot_id"`
	StandingSnapshotHash string         `json:"standing_snapshot_hash"`
	EvidenceRoot         string         `json:"evidence_root"`
	EvidenceState        string         `json:"evidence_state"`
	PolicyBundleVersion  string         `json:"policy_bundle_version"`
	SnapshotFound        bool           `json:"snapshot_found"`
	Status               StandingStatus `json:"status"`
	PlayerName           string         `json:"player_name"`
	RoomID               string         `json:"room_id"`
	StartChip            float64        `json:"start_chip"`
	StandUpStatus        string         `json:"stand_up_status"`
	SourceRank           string         `json:"source_rank"`
	SourceRankNumeric    bool           `json:"source_rank_numeric"`
	ZSetScore            *float64       `json:"zset_score"`
}

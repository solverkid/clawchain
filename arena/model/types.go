package model

import (
	"encoding/json"
	"time"
)

type TruthMetadata struct {
	SchemaVersion       int
	PolicyBundleVersion string
	StateHash           string
	PayloadHash         string
	ArtifactRef         string
}

type SeedDerivationInputs struct {
	TableID    string
	HandNumber int
	SeatNumber int
	StreamName string
}

type Wave struct {
	ID                  string
	Mode                ArenaMode
	State               WaveState
	RegistrationOpenAt  time.Time
	RegistrationCloseAt time.Time
	ScheduledStartAt    time.Time
	TargetShardSize     int
	SoftMinEntrants     int
	SoftMaxEntrants     int
	HardMaxEntrants     int
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Tournament struct {
	ID                    string
	WaveID                string
	Mode                  ArenaMode
	State                 TournamentState
	Exhibition            bool
	NoMultiplier          bool
	Cancelled             bool
	Voided                bool
	HumanOnly             bool
	IntegrityHold         bool
	SeatingRepublishCount int
	CurrentRoundNo        int
	CurrentLevelNo        int
	PlayersRegistered     int
	PlayersConfirmed      int
	PlayersRemaining      int
	ActiveTableCount      int
	FinalTableTableID     string
	RNGRootSeed           string
	TimeCapAt             *time.Time
	CompletedAt           *time.Time
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Entrant struct {
	ID                string
	WaveID            string
	TournamentID      string
	MinerID           string
	EconomicUnitID    string
	SeatAlias         string
	RegistrationState RegistrationState
	TableID           string
	SeatID            string
	FinishRank        int
	StageReached      string
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type WaitlistEntry struct {
	ID                string
	WaveID            string
	EntrantID         string
	MinerID           string
	RegistrationState RegistrationState
	WaitlistPosition  int
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type PrestartCheck struct {
	ID          string
	WaveID      string
	EntrantID   string
	CheckType   string
	CheckStatus string
	ReasonCode  string
	CheckedAt   time.Time
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type ShardAssignment struct {
	ID              string
	WaveID          string
	TournamentID    string
	EntrantID       string
	ShardNo         int
	TableNo         int
	SeatDrawToken   string
	AssignmentState string
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Level struct {
	ID           string
	TournamentID string
	LevelNo      int
	SmallBlind   int64
	BigBlind     int64
	Ante         int64
	StartsAt     time.Time
	EndsAt       time.Time
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Table struct {
	ID                 string
	TournamentID       string
	State              TableState
	TableNo            int
	RoundNo            int
	CurrentHandID      string
	ButtonSeatNo       int
	ActingSeatNo       int
	CurrentToCall      int64
	MinRaiseSize       int64
	PotMain            int64
	StateSeq           int64
	LevelNo            int
	IsFinalTable       bool
	PausedForRebalance bool
	RNGRootSeed        string
	SeedDerivation     SeedDerivationInputs
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Hand struct {
	ID                    string
	TableID               string
	TournamentID          string
	RoundNo               int
	LevelNo               int
	State                 HandState
	HandStartedAt         time.Time
	HandClosedAt          *time.Time
	ButtonSeatNo          int
	ActiveSeatCount       int
	PotMain               int64
	WinnerCount           int
	TimeCapForcedLastHand bool
	RNGRootSeed           string
	SeedDerivation        SeedDerivationInputs
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Phase struct {
	ID             string
	HandID         string
	TableID        string
	Type           PhaseType
	State          PhaseState
	OpenedAt       time.Time
	DeadlineAt     *time.Time
	ClosedAt       *time.Time
	RNGRootSeed    string
	SeedDerivation SeedDerivationInputs
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type Seat struct {
	ID                      string
	TableID                 string
	TournamentID            string
	EntrantID               string
	SeatNo                  int
	SeatAlias               string
	MinerID                 string
	State                   SeatState
	Stack                   int64
	TimeoutStreak           int
	SitOutWarningCount      int
	LastForcedBlindRound    int
	LastManualActionAt      *time.Time
	TournamentSeatDrawToken string
	AdminStatusOverlay      string
	RemovedReason           string
	RNGRootSeed             string
	SeedDerivation          SeedDerivationInputs
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type AliasMap struct {
	ID           string
	TournamentID string
	TableID      string
	SeatID       string
	EntrantID    string
	SeatAlias    string
	MinerID      string
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
	UpdatedAt time.Time
}

type EventLogEntry struct {
	EventID        string
	AggregateType  string
	AggregateID    string
	StreamKey      string
	StreamSeq      int64
	TournamentID   string
	TableID        string
	HandID         string
	PhaseID        string
	RoundNo        int
	BarrierID      string
	EventType      string
	EventVersion   int
	StateSeq       int64
	CausationID    string
	CorrelationID  string
	OccurredAt     time.Time
	Payload        json.RawMessage
	PayloadURI     string
	StateHashAfter string
	RNGRootSeed    string
	SeedDerivation SeedDerivationInputs
	TruthMetadata
}

type SubmissionLedger struct {
	RequestID          string
	TournamentID       string
	TableID            string
	HandID             string
	PhaseID            string
	SeatID             string
	SeatAlias          string
	MinerID            string
	ExpectedStateSeq   int64
	ValidationStatus   string
	Payload            json.RawMessage
	PayloadArtifactRef string
	TruthMetadata
	CreatedAt time.Time
	UpdatedAt time.Time
}

type ActionRecord struct {
	RequestID            string
	TournamentID         string
	TableID              string
	HandID               string
	PhaseID              string
	SeatID               string
	SeatAlias            string
	ActionType           string
	ActionAmountBucket   int64
	ActionSeq            int
	ExpectedStateSeq     int64
	AcceptedStateSeq     int64
	ValidationStatus     string
	ResultEventID        string
	ReceivedAt           time.Time
	ProcessedAt          *time.Time
	ErrorCode            string
	DuplicateOfRequestID string
	Payload              json.RawMessage
	TruthMetadata
}

type ActionMeasurementSummary struct {
	MinerID             string
	HandsPlayed         int
	MeaningfulDecisions int
	AutoActions         int
	TimeoutActions      int
	InvalidActions      int
}

type ActionDeadline struct {
	DeadlineID        string
	TournamentID      string
	TableID           string
	HandID            string
	PhaseID           string
	SeatID            string
	DeadlineAt        time.Time
	Status            string
	OpenedByEventID   string
	ResolvedByEventID string
	Payload           json.RawMessage
	TruthMetadata
	CreatedAt time.Time
	UpdatedAt time.Time
}

type ReseatEvent struct {
	ID                string
	TournamentID      string
	FromTableID       string
	ToTableID         string
	SeatID            string
	EntrantID         string
	RoundNo           int
	CausedByBarrierID string
	OccurredAt        time.Time
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
}

type EliminationEvent struct {
	ID           string
	TournamentID string
	TableID      string
	HandID       string
	SeatID       string
	EntrantID    string
	FinishRank   int
	StageReached string
	OccurredAt   time.Time
	TruthMetadata
	Payload   json.RawMessage
	CreatedAt time.Time
}

type RoundBarrier struct {
	ID                         string
	TournamentID               string
	RoundNo                    int
	ExpectedTableCount         int
	ReceivedHandCloseCount     int
	BarrierState               string
	PendingReseatPlanRef       string
	PendingLevelNo             int
	TerminateAfterCurrentRound bool
	Payload                    json.RawMessage
	TruthMetadata
	CreatedAt time.Time
	UpdatedAt time.Time
}

type OperatorIntervention struct {
	ID                   string
	TournamentID         string
	TableID              string
	SeatID               string
	MinerID              string
	InterventionType     string
	Status               string
	RequestedBy          string
	RequestedAt          time.Time
	EffectiveAtSafePoint bool
	ReasonCode           string
	ReasonDetail         string
	CreatedEventID       string
	ResolvedEventID      string
	Payload              json.RawMessage
	TruthMetadata
	CreatedAt time.Time
	UpdatedAt time.Time
}

type TournamentSnapshot struct {
	ID             string
	TournamentID   string
	StreamKey      string
	StreamSeq      int64
	StateSeq       int64
	RNGRootSeed    string
	SeedDerivation SeedDerivationInputs
	Payload        json.RawMessage
	TruthMetadata
	CreatedAt time.Time
}

type TableSnapshot struct {
	ID             string
	TournamentID   string
	TableID        string
	StreamKey      string
	StreamSeq      int64
	StateSeq       int64
	RNGRootSeed    string
	SeedDerivation SeedDerivationInputs
	Payload        json.RawMessage
	TruthMetadata
	CreatedAt time.Time
}

type HandSnapshot struct {
	ID             string
	TournamentID   string
	TableID        string
	HandID         string
	StreamKey      string
	StreamSeq      int64
	StateSeq       int64
	RNGRootSeed    string
	SeedDerivation SeedDerivationInputs
	Payload        json.RawMessage
	TruthMetadata
	CreatedAt time.Time
}

type StandingSnapshot struct {
	ID           string
	TournamentID string
	StreamKey    string
	StreamSeq    int64
	StateSeq     int64
	Payload      json.RawMessage
	TruthMetadata
	CreatedAt time.Time
}

type OutboxEvent struct {
	ID             string
	AggregateType  string
	AggregateID    string
	StreamKey      string
	Lane           string
	SeasonID       string
	RewardWindowID string
	EventType      string
	EventVersion   int
	OccurredAt     time.Time
	CausationID    string
	CorrelationID  string
	Producer       string
	Visibility     string
	Payload        json.RawMessage
	PayloadURI     string
	TruthMetadata
}

type OutboxDispatch struct {
	ID            string
	OutboxEventID string
	ConsumerName  string
	AttemptCount  int
	Status        string
	NextAttemptAt *time.Time
	DispatchedAt  *time.Time
	ErrorMessage  string
	CreatedAt     time.Time
	UpdatedAt     time.Time
}

type ProjectorCursor struct {
	ProjectorName string
	LastEventID   string
	LastStreamKey string
	LastStreamSeq int64
	UpdatedAt     time.Time
}

type DeadLetterEvent struct {
	ID            string
	OutboxEventID string
	ProjectorName string
	ErrorMessage  string
	OccurredAt    time.Time
	Payload       json.RawMessage
	TruthMetadata
	CreatedAt time.Time
}

type RatingInput struct {
	ID                      string
	TournamentID            string
	EntrantID               string
	MinerAddress            string
	Mode                    ArenaMode
	HumanOnly               bool
	FinishRank              int
	FinishPercentile        float64
	HandsPlayed             int
	MeaningfulDecisions     int
	AutoActions             int
	TimeoutActions          int
	InvalidActions          int
	StageReached            string
	StackPathSummary        json.RawMessage
	ScoreComponents         json.RawMessage
	Penalties               json.RawMessage
	TournamentScore         float64
	ConfidenceWeight        float64
	FieldStrengthAdjustment float64
	BotAdjustment           float64
	TimeCapAdjustment       float64
	Payload                 json.RawMessage
	TruthMetadata
	CreatedAt time.Time
}

type CollusionMetric struct {
	ID           string
	TournamentID string
	MinerAddress string
	MetricName   string
	MetricValue  float64
	Payload      json.RawMessage
	TruthMetadata
	CreatedAt time.Time
}

type RatingState struct {
	MinerAddress     string
	Mu               float64
	Sigma            float64
	ArenaReliability float64
	PublicELO        int
	Payload          json.RawMessage
	TruthMetadata
	UpdatedAt time.Time
}

type RatingRuntimeState struct {
	MinerAddress            string
	Mu                      float64
	Sigma                   float64
	ArenaReliability        float64
	PublicELO               int
	PublicRank              int
	Multiplier              float64
	EligibleTournamentCount int
}

type RatingSnapshot struct {
	ID               string
	MinerAddress     string
	Mu               float64
	Sigma            float64
	ArenaReliability float64
	PublicELO        int
	Payload          json.RawMessage
	TruthMetadata
	CreatedAt time.Time
}

type PublicLadderSnapshot struct {
	ID           string
	SeasonID     string
	MinerAddress string
	PublicRank   int
	PublicELO    int
	Payload      json.RawMessage
	TruthMetadata
	CreatedAt time.Time
}

type MultiplierSnapshot struct {
	ID                    string
	TournamentID          string
	MinerAddress          string
	EligibleForMultiplier bool
	TournamentScore       float64
	ConfidenceWeight      float64
	MultiplierBefore      float64
	MultiplierAfter       float64
	Payload               json.RawMessage
	TruthMetadata
	CreatedAt time.Time
}

type MinerCompatibility struct {
	Address               string
	Name                  string
	RegistrationIndex     int
	Status                string
	PublicKey             string
	EconomicUnitID        string
	IPAddress             string
	UserAgentHash         string
	TotalRewards          int64
	ForecastCommits       int
	ForecastReveals       int
	SettledTasks          int
	CorrectDirectionCount int
	EdgeScoreTotal        float64
	HeldRewards           int64
	FastTaskOpportunities int
	FastTaskMisses        int
	FastWindowStartAt     *time.Time
	AdmissionState        string
	ModelReliability      float64
	OpsReliability        float64
	ArenaMultiplier       float64
	PublicRank            *int
	PublicELO             int
	CreatedAt             time.Time
	UpdatedAt             time.Time
}

type ArenaResultEntry struct {
	ID                    string
	TournamentID          string
	MinerAddress          string
	Mode                  ArenaMode
	HumanOnly             bool
	EligibleForMultiplier bool
	ArenaScore            float64
	ConservativeSkill     *float64
	MultiplierAfter       float64
	CreatedAt             time.Time
	UpdatedAt             time.Time
}

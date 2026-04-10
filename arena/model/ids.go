package model

import (
	"fmt"
	"time"
)

const waveTimestampLayout = "20060102T150405Z"

func WaveID(mode ArenaMode, scheduledStart time.Time) string {
	return fmt.Sprintf("wav:%s:%s", mode, scheduledStart.UTC().Format(waveTimestampLayout))
}

func TournamentID(waveID string, shardNo int) string {
	return fmt.Sprintf("tour:%s:%02d", waveID, shardNo)
}

func TableID(tournamentID string, tableNo int) string {
	return fmt.Sprintf("tbl:%s:%02d", tournamentID, tableNo)
}

func HandID(tournamentID string, tableNo, handNo int) string {
	return fmt.Sprintf("hand:%s:%02d:%04d", tournamentID, tableNo, handNo)
}

func PhaseID(handID string, phaseType PhaseType) string {
	return fmt.Sprintf("phase:%s:%s", handID, phaseType)
}

func BarrierID(tournamentID string, roundNo int) string {
	return fmt.Sprintf("bar:%s:%03d", tournamentID, roundNo)
}

func EventID(streamKey string, streamSeq int64) string {
	return fmt.Sprintf("evt:%s:%012d", streamKey, streamSeq)
}

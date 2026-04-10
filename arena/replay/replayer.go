package replay

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"

	"github.com/clawchain/clawchain/arena/model"
)

type Result struct {
	Err              error
	ParityOK         bool
	FinalDisposition string
}

type Replayer struct {
	expectedFinalHashes map[string]string
	computedFinalHashes map[string]string
	loader              repositoryLoader
}

func NewReplayer(expectedFinalHashes, computedFinalHashes map[string]string) *Replayer {
	return &Replayer{
		expectedFinalHashes: expectedFinalHashes,
		computedFinalHashes: computedFinalHashes,
	}
}

type repositoryLoader interface {
	LoadLatestTournamentSnapshot(ctx context.Context, tournamentID string) (model.TournamentSnapshot, error)
	LoadLatestTableSnapshots(ctx context.Context, tournamentID string) ([]model.TableSnapshot, error)
	ListRatingInputs(ctx context.Context, tournamentID string) ([]model.RatingInput, error)
}

func NewRepositoryReplayer(loader repositoryLoader) *Replayer {
	return &Replayer{loader: loader}
}

func (r *Replayer) ReplayCorrupted(tournamentID string) Result {
	expected := r.expectedFinalHashes[tournamentID]
	computed := r.computedFinalHashes[tournamentID]

	if expected == computed {
		return Result{
			ParityOK:         true,
			FinalDisposition: "ok",
		}
	}

	return Result{
		ParityOK:         false,
		FinalDisposition: "integrity_failure",
	}
}

func (r *Replayer) ComputeFinalHash(ctx context.Context, tournamentID string) (string, error) {
	if r.loader == nil {
		if computed, ok := r.computedFinalHashes[tournamentID]; ok {
			return computed, nil
		}
		return "", errors.New("repository loader is required")
	}

	tournamentSnapshot, err := r.loader.LoadLatestTournamentSnapshot(ctx, tournamentID)
	if err != nil {
		return "", err
	}
	tableSnapshots, err := r.loader.LoadLatestTableSnapshots(ctx, tournamentID)
	if err != nil {
		return "", err
	}
	ratingInputs, err := r.loader.ListRatingInputs(ctx, tournamentID)
	if err != nil {
		return "", err
	}

	sort.Slice(tableSnapshots, func(i, j int) bool {
		if tableSnapshots[i].TableID != tableSnapshots[j].TableID {
			return tableSnapshots[i].TableID < tableSnapshots[j].TableID
		}
		if tableSnapshots[i].StreamSeq != tableSnapshots[j].StreamSeq {
			return tableSnapshots[i].StreamSeq < tableSnapshots[j].StreamSeq
		}
		return tableSnapshots[i].ID < tableSnapshots[j].ID
	})
	sort.Slice(ratingInputs, func(i, j int) bool {
		if ratingInputs[i].MinerAddress != ratingInputs[j].MinerAddress {
			return ratingInputs[i].MinerAddress < ratingInputs[j].MinerAddress
		}
		if ratingInputs[i].EntrantID != ratingInputs[j].EntrantID {
			return ratingInputs[i].EntrantID < ratingInputs[j].EntrantID
		}
		return ratingInputs[i].ID < ratingInputs[j].ID
	})

	type tournamentPart struct {
		ID          string `json:"id"`
		StreamSeq   int64  `json:"stream_seq"`
		StateSeq    int64  `json:"state_seq"`
		StateHash   string `json:"state_hash"`
		PayloadHash string `json:"payload_hash"`
		Payload     string `json:"payload"`
	}
	type tablePart struct {
		TableID     string `json:"table_id"`
		StreamSeq   int64  `json:"stream_seq"`
		StateSeq    int64  `json:"state_seq"`
		StateHash   string `json:"state_hash"`
		PayloadHash string `json:"payload_hash"`
		Payload     string `json:"payload"`
	}
	type ratingPart struct {
		ID              string  `json:"id"`
		EntrantID       string  `json:"entrant_id"`
		MinerAddress    string  `json:"miner_address"`
		FinishRank      int     `json:"finish_rank"`
		TournamentScore float64 `json:"tournament_score"`
		StateHash       string  `json:"state_hash"`
		PayloadHash     string  `json:"payload_hash"`
	}

	parts := struct {
		Tournament tournamentPart `json:"tournament"`
		Tables     []tablePart    `json:"tables"`
		Ratings    []ratingPart   `json:"ratings"`
	}{
		Tournament: tournamentPart{
			ID:          tournamentSnapshot.ID,
			StreamSeq:   tournamentSnapshot.StreamSeq,
			StateSeq:    tournamentSnapshot.StateSeq,
			StateHash:   tournamentSnapshot.StateHash,
			PayloadHash: tournamentSnapshot.PayloadHash,
			Payload:     string(tournamentSnapshot.Payload),
		},
		Tables:  make([]tablePart, 0, len(tableSnapshots)),
		Ratings: make([]ratingPart, 0, len(ratingInputs)),
	}

	for _, snapshot := range tableSnapshots {
		parts.Tables = append(parts.Tables, tablePart{
			TableID:     snapshot.TableID,
			StreamSeq:   snapshot.StreamSeq,
			StateSeq:    snapshot.StateSeq,
			StateHash:   snapshot.StateHash,
			PayloadHash: snapshot.PayloadHash,
			Payload:     string(snapshot.Payload),
		})
	}
	for _, input := range ratingInputs {
		parts.Ratings = append(parts.Ratings, ratingPart{
			ID:              input.ID,
			EntrantID:       input.EntrantID,
			MinerAddress:    input.MinerAddress,
			FinishRank:      input.FinishRank,
			TournamentScore: input.TournamentScore,
			StateHash:       input.StateHash,
			PayloadHash:     input.PayloadHash,
		})
	}

	payload, err := json.Marshal(parts)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:]), nil
}

func (r *Replayer) ReplayTournament(ctx context.Context, tournamentID, expectedHash string) Result {
	computed, err := r.ComputeFinalHash(ctx, tournamentID)
	if err != nil {
		return Result{
			Err:              err,
			ParityOK:         false,
			FinalDisposition: "integrity_failure",
		}
	}
	if computed == expectedHash {
		return Result{
			ParityOK:         true,
			FinalDisposition: "ok",
		}
	}
	return Result{
		ParityOK:         false,
		FinalDisposition: "integrity_failure",
	}
}

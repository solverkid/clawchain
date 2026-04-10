package gateway

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"

	"github.com/clawchain/clawchain/arena/table"
)

var (
	ErrInvalidSignature = errors.New("invalid signature")
	ErrStateSeqMismatch = errors.New("state_seq_mismatch")
	ErrUnknownTable     = errors.New("unknown table")
	ErrBadRequest       = errors.New("bad request")
)

type Actor interface {
	Handle(ctx context.Context, envelope table.CommandEnvelope) (table.Result, error)
}

type Config struct {
	Actors map[string]Actor
}

type SubmitRequest struct {
	RequestID        string `json:"request_id"`
	TournamentID     string `json:"tournament_id"`
	TableID          string `json:"table_id"`
	MinerID          string `json:"miner_id"`
	SeatNo           int    `json:"seat_no"`
	ActionType       string `json:"action_type"`
	Amount           int64  `json:"amount"`
	ExpectedStateSeq int64  `json:"expected_state_seq"`
	Signature        string `json:"signature"`
}

type SubmitResponse struct {
	ResultEventID string `json:"result_event_id"`
	StateSeq      int64  `json:"state_seq"`
}

type Gateway struct {
	mu        sync.Mutex
	actors    map[string]Actor
	responses map[string]SubmitResponse
	ledger    map[string]SubmitRequest
}

func New(cfg Config) *Gateway {
	actors := cfg.Actors
	if actors == nil {
		actors = map[string]Actor{}
	}

	return &Gateway{
		actors:    actors,
		responses: make(map[string]SubmitResponse),
		ledger:    make(map[string]SubmitRequest),
	}
}

func (g *Gateway) Submit(ctx context.Context, req SubmitRequest) (SubmitResponse, error) {
	if ctx == nil {
		return SubmitResponse{}, ErrBadRequest
	}

	g.mu.Lock()
	if response, ok := g.responses[req.RequestID]; ok {
		g.mu.Unlock()
		return response, nil
	}
	g.mu.Unlock()

	if !validSignature(req.MinerID, req.Signature) {
		return SubmitResponse{}, ErrInvalidSignature
	}

	actor, ok := g.actors[req.TableID]
	if !ok {
		return SubmitResponse{}, ErrUnknownTable
	}

	command, err := toCommand(req)
	if err != nil {
		return SubmitResponse{}, err
	}

	result, err := actor.Handle(ctx, table.CommandEnvelope{
		RequestID:        req.RequestID,
		ExpectedStateSeq: req.ExpectedStateSeq,
		Command:          command,
	})
	if err != nil {
		if errors.Is(err, table.ErrStateSeqMismatch) {
			return SubmitResponse{}, ErrStateSeqMismatch
		}
		return SubmitResponse{}, err
	}

	response := SubmitResponse{
		ResultEventID: result.ResultEventID,
		StateSeq:      result.StateSeq,
	}

	g.mu.Lock()
	defer g.mu.Unlock()
	g.ledger[req.RequestID] = req
	g.responses[req.RequestID] = response

	return response, nil
}

func validSignature(minerID, signature string) bool {
	return signature == fmt.Sprintf("sig:%s", minerID)
}

func toCommand(req SubmitRequest) (table.Command, error) {
	actionType := table.ActionType(strings.TrimSpace(req.ActionType))
	if actionType == "" {
		return nil, ErrBadRequest
	}

	return table.SubmitArenaAction{
		SeatNo:     req.SeatNo,
		ActionType: actionType,
		Amount:     req.Amount,
	}, nil
}

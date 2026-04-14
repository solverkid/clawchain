package gateway

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"

	"github.com/clawchain/clawchain/arena/model"
	"github.com/clawchain/clawchain/arena/table"
)

var (
	ErrInvalidSignature       = errors.New("invalid signature")
	ErrStateSeqMismatch       = errors.New("state_seq_mismatch")
	ErrUnknownTable           = errors.New("unknown table")
	ErrBadRequest             = errors.New("bad request")
	ErrRequestPayloadConflict = errors.New("request_id payload conflict")
)

type Actor interface {
	Handle(ctx context.Context, envelope table.CommandEnvelope) (table.Result, error)
	State() table.ActorState
}

type Observer interface {
	OnSubmitCommitted(ctx context.Context, req SubmitRequest, state table.ActorState) error
}

type Ledger interface {
	AppendSubmissionLedgerEntries(ctx context.Context, entries []model.SubmissionLedger) error
	LoadSubmissionLedgerEntry(ctx context.Context, requestID string) (model.SubmissionLedger, error)
	LoadActionRecord(ctx context.Context, requestID string) (model.ActionRecord, error)
}

type Config struct {
	Actors   map[string]Actor
	Ledger   Ledger
	Observer Observer
}

type SubmitRequest struct {
	RequestID        string `json:"request_id"`
	TournamentID     string `json:"tournament_id"`
	TableID          string `json:"table_id"`
	MinerID          string `json:"miner_id"`
	SessionID        string `json:"session_id,omitempty"`
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
	inFlight  map[string]inFlightRequest
	durable   Ledger
	observer  Observer
}

type inFlightRequest struct {
	payloadHash string
	done        chan struct{}
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
		inFlight:  make(map[string]inFlightRequest),
		durable:   cfg.Ledger,
		observer:  cfg.Observer,
	}
}

func (g *Gateway) Submit(ctx context.Context, req SubmitRequest) (SubmitResponse, error) {
	if ctx == nil {
		return SubmitResponse{}, ErrBadRequest
	}
	if !validSignature(req.MinerID, req.Signature) {
		return SubmitResponse{}, ErrInvalidSignature
	}

	payloadHash := submissionPayloadHash(req)
	for {
		response, wait, actor, observer, err := g.beginSubmit(req, payloadHash)
		if err != nil {
			return SubmitResponse{}, err
		}
		if response.ResultEventID != "" {
			return response, nil
		}
		if wait != nil {
			select {
			case <-ctx.Done():
				return SubmitResponse{}, ctx.Err()
			case <-wait:
				continue
			}
		}
		return g.submitOwned(ctx, req, payloadHash, actor, observer)
	}
}

func (g *Gateway) beginSubmit(req SubmitRequest, payloadHash string) (SubmitResponse, chan struct{}, Actor, Observer, error) {
	g.mu.Lock()
	defer g.mu.Unlock()

	if existing, ok := g.ledger[req.RequestID]; ok && submissionPayloadHash(existing) != payloadHash {
		return SubmitResponse{}, nil, nil, nil, ErrRequestPayloadConflict
	}
	if response, ok := g.responses[req.RequestID]; ok {
		return response, nil, nil, nil, nil
	}
	if inFlight, ok := g.inFlight[req.RequestID]; ok {
		if inFlight.payloadHash != payloadHash {
			return SubmitResponse{}, nil, nil, nil, ErrRequestPayloadConflict
		}
		return SubmitResponse{}, inFlight.done, nil, nil, nil
	}

	actor := g.actors[req.TableID]
	observer := g.observer
	g.inFlight[req.RequestID] = inFlightRequest{
		payloadHash: payloadHash,
		done:        make(chan struct{}),
	}
	return SubmitResponse{}, nil, actor, observer, nil
}

func (g *Gateway) submitOwned(ctx context.Context, req SubmitRequest, payloadHash string, actor Actor, observer Observer) (response SubmitResponse, err error) {
	cacheRequest := false
	cacheResponse := false
	defer func() {
		g.finishSubmit(req, response, cacheRequest, cacheResponse)
	}()

	command, err := toCommand(req)
	if err != nil {
		return SubmitResponse{}, err
	}

	entry, entryFound, err := g.loadLedgerEntry(ctx, req.RequestID)
	if err != nil {
		return SubmitResponse{}, err
	}
	if entryFound && entry.PayloadHash != payloadHash {
		return SubmitResponse{}, ErrRequestPayloadConflict
	}
	if entryFound {
		action, found, err := g.loadActionRecord(ctx, req.RequestID)
		if err != nil {
			return SubmitResponse{}, err
		}
		if found {
			response = SubmitResponse{
				ResultEventID: action.ResultEventID,
				StateSeq:      action.AcceptedStateSeq,
			}
			cacheRequest = true
			cacheResponse = true
			if err := g.finalizeDurableReplay(ctx, req, payloadHash, actor, observer); err != nil {
				cacheResponse = false
				return SubmitResponse{}, err
			}
			return response, nil
		}
	}
	if actor == nil {
		return SubmitResponse{}, ErrUnknownTable
	}

	if err := g.recordSubmission(ctx, req, payloadHash, actor, "received"); err != nil {
		return SubmitResponse{}, err
	}
	cacheRequest = true

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

	response = SubmitResponse{
		ResultEventID: result.ResultEventID,
		StateSeq:      result.StateSeq,
	}
	if err := g.recordSubmission(ctx, req, payloadHash, actor, "committed"); err != nil {
		return SubmitResponse{}, err
	}

	if observer != nil {
		if err := observer.OnSubmitCommitted(ctx, req, actor.State()); err != nil {
			return SubmitResponse{}, err
		}
	}
	if err := g.recordSubmission(ctx, req, payloadHash, actor, "applied"); err != nil {
		return SubmitResponse{}, err
	}
	cacheResponse = true

	return response, nil
}

func (g *Gateway) RegisterActor(tableID string, actor Actor) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.actors[tableID] = actor
}

func (g *Gateway) RemoveActor(tableID string) {
	g.mu.Lock()
	defer g.mu.Unlock()
	delete(g.actors, tableID)
}

func (g *Gateway) SetObserver(observer Observer) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.observer = observer
}

func (g *Gateway) loadLedgerEntry(ctx context.Context, requestID string) (model.SubmissionLedger, bool, error) {
	if g.durable == nil {
		return model.SubmissionLedger{}, false, nil
	}
	entry, err := g.durable.LoadSubmissionLedgerEntry(ctx, requestID)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return model.SubmissionLedger{}, false, nil
		}
		return model.SubmissionLedger{}, false, err
	}
	return entry, true, nil
}

func (g *Gateway) loadActionRecord(ctx context.Context, requestID string) (model.ActionRecord, bool, error) {
	if g.durable == nil {
		return model.ActionRecord{}, false, nil
	}
	action, err := g.durable.LoadActionRecord(ctx, requestID)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return model.ActionRecord{}, false, nil
		}
		return model.ActionRecord{}, false, err
	}
	return action, true, nil
}

func (g *Gateway) finalizeDurableReplay(ctx context.Context, req SubmitRequest, payloadHash string, actor Actor, observer Observer) error {
	if observer != nil && actor != nil {
		if err := observer.OnSubmitCommitted(ctx, req, actor.State()); err != nil {
			return err
		}
	}
	if observer == nil || actor != nil {
		return g.recordSubmission(ctx, req, payloadHash, actor, "applied")
	}
	return nil
}

func (g *Gateway) recordSubmission(ctx context.Context, req SubmitRequest, payloadHash string, actor Actor, status string) error {
	if g.durable == nil {
		return nil
	}

	handID := ""
	phaseID := ""
	if actor != nil {
		state := actor.State()
		handID = state.HandID
		phaseID = state.PhaseID
	}
	entry := model.SubmissionLedger{
		RequestID:        req.RequestID,
		TournamentID:     req.TournamentID,
		TableID:          req.TableID,
		HandID:           handID,
		PhaseID:          phaseID,
		SeatID:           seatIDForRequest(req),
		MinerID:          req.MinerID,
		ExpectedStateSeq: req.ExpectedStateSeq,
		ValidationStatus: status,
		Payload:          mustJSON(req),
		TruthMetadata: model.TruthMetadata{
			SchemaVersion:       1,
			PolicyBundleVersion: "policy-v1",
			StateHash:           fmt.Sprintf("submission-state:%s:%d", req.RequestID, req.ExpectedStateSeq),
			PayloadHash:         payloadHash,
		},
	}
	if err := g.durable.AppendSubmissionLedgerEntries(ctx, []model.SubmissionLedger{entry}); err != nil {
		if isRequestPayloadConflict(err) {
			return ErrRequestPayloadConflict
		}
		return err
	}
	return nil
}

func (g *Gateway) finishSubmit(req SubmitRequest, response SubmitResponse, cacheRequest bool, cacheResponse bool) {
	g.mu.Lock()
	defer g.mu.Unlock()

	if cacheRequest {
		g.ledger[req.RequestID] = req
	}
	if cacheResponse {
		g.responses[req.RequestID] = response
	}
	if inFlight, ok := g.inFlight[req.RequestID]; ok {
		close(inFlight.done)
		delete(g.inFlight, req.RequestID)
	}
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

func seatIDForRequest(req SubmitRequest) string {
	if req.SeatNo <= 0 {
		return fmt.Sprintf("system:%s", req.TableID)
	}
	return fmt.Sprintf("seat:%s:%02d", req.TableID, req.SeatNo)
}

func submissionPayloadHash(req SubmitRequest) string {
	payload, err := json.Marshal(struct {
		TournamentID     string `json:"tournament_id"`
		TableID          string `json:"table_id"`
		MinerID          string `json:"miner_id"`
		SeatNo           int    `json:"seat_no"`
		ActionType       string `json:"action_type"`
		Amount           int64  `json:"amount"`
		ExpectedStateSeq int64  `json:"expected_state_seq"`
	}{
		TournamentID:     req.TournamentID,
		TableID:          req.TableID,
		MinerID:          req.MinerID,
		SeatNo:           req.SeatNo,
		ActionType:       req.ActionType,
		Amount:           req.Amount,
		ExpectedStateSeq: req.ExpectedStateSeq,
	})
	if err != nil {
		return ""
	}
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:])
}

func mustJSON(v any) json.RawMessage {
	payload, err := json.Marshal(v)
	if err != nil {
		return json.RawMessage(`{}`)
	}
	return payload
}

func isRequestPayloadConflict(err error) bool {
	return err != nil && strings.Contains(strings.ToLower(err.Error()), "request_id payload conflict")
}

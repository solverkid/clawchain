// Package mining implements the miner's main loop.
// Polls for challenges, solves them, and submits commit-reveal via chain tx.
package mining

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"log/slog"
	"time"

	"github.com/clawchain/clawminer/client"
	"github.com/clawchain/clawminer/config"
	"github.com/clawchain/clawminer/solver"
)

// MiningLoop is the main mining loop.
type MiningLoop struct {
	cfg         *config.Config
	chainClient *client.ChainClient
	solver      *solver.Solver
	minerAddr   string
	logger      *slog.Logger
	lastHeight  int64
}

// NewMiningLoop creates a new mining loop.
func NewMiningLoop(
	cfg *config.Config,
	chainClient *client.ChainClient,
	slv *solver.Solver,
	minerAddr string,
	logger *slog.Logger,
) *MiningLoop {
	return &MiningLoop{
		cfg:         cfg,
		chainClient: chainClient,
		solver:      slv,
		minerAddr:   minerAddr,
		logger:      logger,
	}
}

type commitInfo struct {
	ChallengeID string
	Answer      string
	Salt        string
	CommitHash  string
	CommitTxID  string
	CommitTime  time.Time
}

// Run starts the mining loop (blocks until context is cancelled).
func (m *MiningLoop) Run(ctx context.Context) error {
	m.logger.Info("⛏️  Mining loop started",
		"miner", m.minerAddr,
		"node", m.cfg.NodeRPC,
		"chain_id", m.cfg.ChainID,
	)

	pendingReveals := make(map[string]*commitInfo)
	ticker := time.NewTicker(6 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			m.logger.Info("Mining loop stopped", "reason", ctx.Err())
			return nil
		case <-ticker.C:
			m.tick(ctx, pendingReveals)
		}
	}
}

func (m *MiningLoop) tick(ctx context.Context, pendingReveals map[string]*commitInfo) {
	height, err := m.chainClient.GetLatestBlock(ctx)
	if err != nil {
		m.logger.Error("get block height failed", "error", err)
		return
	}

	if height <= m.lastHeight {
		return
	}
	m.lastHeight = height

	// Process pending reveals
	m.processReveals(ctx, pendingReveals)

	// Query pending challenges
	challenges, err := m.chainClient.GetPendingChallenges(ctx, m.minerAddr)
	if err != nil {
		m.logger.Error("query challenges failed", "error", err)
		return
	}

	if len(challenges) == 0 {
		return
	}

	m.logger.Info("📋 Got challenges", "count", len(challenges), "height", height)

	for _, ch := range challenges {
		if _, exists := pendingReveals[ch.ID]; exists {
			continue
		}
		m.processChallenge(ctx, ch, pendingReveals)
	}
}

func (m *MiningLoop) processChallenge(ctx context.Context, ch solver.Challenge, pendingReveals map[string]*commitInfo) {
	m.logger.Info("🔧 Solving challenge", "id", ch.ID, "type", ch.Type)

	answer, err := m.solver.Solve(ctx, ch)
	if err != nil {
		m.logger.Error("solve failed", "id", ch.ID, "error", err)
		return
	}

	salt, err := generateSalt()
	if err != nil {
		m.logger.Error("generate salt failed", "error", err)
		return
	}

	commitHash := client.ComputeCommitHash(answer, salt)

	m.logger.Info("📤 Submitting commit", "id", ch.ID)

	txHash, err := m.chainClient.SubmitCommit(ctx, m.minerAddr, ch.ID, commitHash)
	if err != nil {
		m.logger.Error("commit failed", "id", ch.ID, "error", err)
		return
	}

	pendingReveals[ch.ID] = &commitInfo{
		ChallengeID: ch.ID,
		Answer:      answer,
		Salt:        salt,
		CommitHash:  commitHash,
		CommitTxID:  txHash,
		CommitTime:  time.Now(),
	}

	m.logger.Info("✅ Commit accepted", "id", ch.ID, "tx", txHash[:16]+"...")
}

func (m *MiningLoop) processReveals(ctx context.Context, pendingReveals map[string]*commitInfo) {
	for id, info := range pendingReveals {
		if time.Since(info.CommitTime) < 10*time.Second {
			continue
		}

		m.logger.Info("📤 Submitting reveal", "id", id)

		txHash, err := m.chainClient.SubmitReveal(ctx, m.minerAddr, id, info.Answer, info.Salt)
		if err != nil {
			m.logger.Error("reveal failed", "id", id, "error", err)
			if time.Since(info.CommitTime) > 5*time.Minute {
				m.logger.Warn("reveal timed out, dropping", "id", id)
				delete(pendingReveals, id)
			}
			continue
		}

		m.logger.Info("✅ Reveal accepted", "id", id, "tx", txHash[:16]+"...")
		delete(pendingReveals, id)
	}
}

func generateSalt() (string, error) {
	salt := make([]byte, 32)
	if _, err := rand.Read(salt); err != nil {
		return "", err
	}
	return hex.EncodeToString(salt), nil
}

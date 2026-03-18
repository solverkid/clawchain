// Package mining 实现矿工挖矿主循环。
// 循环监听新区块、接收挑战、求解并提交 commit-reveal 答案。
package mining

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log/slog"
	"time"

	"github.com/clawchain/clawminer/client"
	"github.com/clawchain/clawminer/config"
	"github.com/clawchain/clawminer/solver"
)

// MiningLoop 挖矿主循环
type MiningLoop struct {
	cfg         *config.Config
	chainClient *client.ChainClient
	solver      *solver.Solver
	minerAddr   string // 矿工地址
	logger      *slog.Logger
	lastHeight  int64 // 上次处理的区块高度
}

// NewMiningLoop 创建挖矿主循环
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

// commitInfo 保存 commit 信息，用于后续 reveal
type commitInfo struct {
	ChallengeID string
	Answer      string
	Salt        string
	CommitHash  string
	CommitTxID  string
	CommitTime  time.Time
}

// Run 启动挖矿主循环（阻塞运行，直到 context 取消）
func (m *MiningLoop) Run(ctx context.Context) error {
	m.logger.Info("⛏️  挖矿循环启动",
		"miner", m.minerAddr,
		"node", m.cfg.NodeRPC,
		"chain_id", m.cfg.ChainID,
	)

	// 待 reveal 的 commits 队列
	pendingReveals := make(map[string]*commitInfo)

	// 出块间隔轮询（约 5 秒一个块）
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			m.logger.Info("挖矿循环停止", "reason", ctx.Err())
			return nil
		case <-ticker.C:
			m.tick(ctx, pendingReveals)
		}
	}
}

// tick 每个区块周期执行一次
func (m *MiningLoop) tick(ctx context.Context, pendingReveals map[string]*commitInfo) {
	// 1. 获取最新区块高度
	height, err := m.chainClient.GetLatestBlock(ctx)
	if err != nil {
		m.logger.Error("获取区块高度失败", "error", err)
		return
	}

	// 跳过已处理的高度
	if height <= m.lastHeight {
		return
	}
	m.logger.Debug("新区块", "height", height)
	m.lastHeight = height

	// 2. 尝试 reveal 已经 commit 的挑战
	m.processReveals(ctx, pendingReveals)

	// 3. 查询分配给自己的待处理挑战
	challenges, err := m.chainClient.GetPendingChallenges(ctx, m.minerAddr)
	if err != nil {
		m.logger.Error("查询挑战失败", "error", err)
		return
	}

	if len(challenges) == 0 {
		return
	}

	m.logger.Info("收到挑战", "count", len(challenges), "height", height)

	// 4. 逐个处理挑战
	for _, ch := range challenges {
		// 跳过已经 commit 过的
		if _, exists := pendingReveals[ch.ID]; exists {
			continue
		}

		m.processChallenge(ctx, ch, pendingReveals)
	}
}

// processChallenge 处理单个挑战：求解 → commit
func (m *MiningLoop) processChallenge(
	ctx context.Context,
	ch solver.Challenge,
	pendingReveals map[string]*commitInfo,
) {
	m.logger.Info("处理挑战",
		"id", ch.ID,
		"type", ch.Type,
		"prompt_len", len(ch.Prompt),
	)

	// 4a. 用 solver 求解
	answer, err := m.solver.Solve(ctx, ch)
	if err != nil {
		m.logger.Error("求解挑战失败", "id", ch.ID, "error", err)
		return
	}

	// 4b. 生成安全随机 salt
	salt, err := generateSalt()
	if err != nil {
		m.logger.Error("生成 salt 失败", "error", err)
		return
	}

	// 4c. 计算 commit hash = SHA256(answer + salt)
	commitHash := computeCommitHash(answer, salt)

	m.logger.Info("提交 commit",
		"challenge_id", ch.ID,
		"commit_hash", commitHash,
	)

	// 4d. 提交 commit 交易
	txHash, err := m.chainClient.SubmitCommit(ctx, m.minerAddr, ch.ID, commitHash)
	if err != nil {
		m.logger.Error("提交 commit 失败", "challenge_id", ch.ID, "error", err)
		return
	}

	// 4e. 保存 commit 信息，等待 reveal
	pendingReveals[ch.ID] = &commitInfo{
		ChallengeID: ch.ID,
		Answer:      answer,
		Salt:        salt,
		CommitHash:  commitHash,
		CommitTxID:  txHash,
		CommitTime:  time.Now(),
	}

	m.logger.Info("commit 成功，等待 reveal 窗口",
		"challenge_id", ch.ID,
		"tx_hash", txHash,
	)
}

// processReveals 处理待 reveal 的 commits
func (m *MiningLoop) processReveals(ctx context.Context, pendingReveals map[string]*commitInfo) {
	for id, info := range pendingReveals {
		// commit 后等待至少 1 个区块再 reveal（简化的 reveal 窗口逻辑）
		if time.Since(info.CommitTime) < 10*time.Second {
			continue
		}

		m.logger.Info("提交 reveal",
			"challenge_id", id,
			"answer_len", len(info.Answer),
		)

		txHash, err := m.chainClient.SubmitReveal(ctx, m.minerAddr, id, info.Answer, info.Salt)
		if err != nil {
			m.logger.Error("提交 reveal 失败", "challenge_id", id, "error", err)
			// 超时则放弃
			if time.Since(info.CommitTime) > 5*time.Minute {
				m.logger.Warn("reveal 超时，放弃", "challenge_id", id)
				delete(pendingReveals, id)
			}
			continue
		}

		m.logger.Info("✅ reveal 成功",
			"challenge_id", id,
			"tx_hash", txHash,
		)
		delete(pendingReveals, id)
	}
}

// generateSalt 生成 32 字节的安全随机 salt（hex 编码）
func generateSalt() (string, error) {
	salt := make([]byte, 32)
	if _, err := rand.Read(salt); err != nil {
		return "", fmt.Errorf("生成随机 salt 失败: %w", err)
	}
	return hex.EncodeToString(salt), nil
}

// computeCommitHash 计算 commit 哈希：SHA256(answer + salt)
func computeCommitHash(answer, salt string) string {
	h := sha256.New()
	h.Write([]byte(answer + salt))
	return hex.EncodeToString(h.Sum(nil))
}

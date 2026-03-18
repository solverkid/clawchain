// ClawMiner — ClawChain 矿工客户端
// AI Agent 通过此程序连接 ClawChain 节点，注册为矿工，
// 接收并完成挑战任务（文本摘要/情感分析/数学计算等），获得 $CLAW 代币奖励。
//
// 用法：
//
//	clawminer start     启动挖矿
//	clawminer register  注册矿工并质押
//	clawminer status    查看矿工状态
//	clawminer version   显示版本信息
package main

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/spf13/cobra"

	"github.com/clawchain/clawminer/client"
	"github.com/clawchain/clawminer/config"
	"github.com/clawchain/clawminer/mining"
	"github.com/clawchain/clawminer/solver"
)

// 版本信息（编译时注入）
var (
	Version   = "0.1.0"
	GitCommit = "dev"
	BuildTime = "unknown"
)

func main() {
	cfg := config.DefaultConfig()

	rootCmd := &cobra.Command{
		Use:   "clawminer",
		Short: "ClawChain 矿工客户端 — AI Agent 挖矿程序",
		Long: `ClawMiner 是 ClawChain 的矿工客户端。
AI Agent 通过完成链上微任务（文本摘要、情感分析、数学计算等）来挖矿获得 $CLAW 代币。

支持 Proof of Availability 共识：矿工需要持续在线并正确完成挑战才能获得奖励。`,
	}

	// 全局参数
	rootCmd.PersistentFlags().StringVar(&cfg.NodeRPC, "node", cfg.NodeRPC, "ClawChain 节点 RPC 地址")
	rootCmd.PersistentFlags().StringVar(&cfg.ChainID, "chain-id", cfg.ChainID, "链 ID")
	rootCmd.PersistentFlags().StringVar(&cfg.KeyName, "key", cfg.KeyName, "矿工密钥名")
	rootCmd.PersistentFlags().StringVar(&cfg.KeyringDir, "keyring-dir", cfg.KeyringDir, "密钥存储目录")
	rootCmd.PersistentFlags().StringVar(&cfg.LLMEndpoint, "llm-endpoint", cfg.LLMEndpoint, "LLM API 端点")
	rootCmd.PersistentFlags().StringVar(&cfg.LLMAPIKey, "llm-api-key", cfg.LLMAPIKey, "LLM API 密钥")
	rootCmd.PersistentFlags().StringVar(&cfg.LLMModel, "llm-model", cfg.LLMModel, "LLM 模型名称")
	rootCmd.PersistentFlags().StringVar(&cfg.LogLevel, "log-level", cfg.LogLevel, "日志级别 (debug/info/warn/error)")

	// 子命令
	rootCmd.AddCommand(
		startCmd(cfg),
		registerCmd(cfg),
		statusCmd(cfg),
		versionCmd(),
	)

	if err := rootCmd.Execute(); err != nil {
		os.Exit(1)
	}
}

// setupLogger 根据配置创建 slog logger
func setupLogger(level string) *slog.Logger {
	var logLevel slog.Level
	switch level {
	case "debug":
		logLevel = slog.LevelDebug
	case "warn":
		logLevel = slog.LevelWarn
	case "error":
		logLevel = slog.LevelError
	default:
		logLevel = slog.LevelInfo
	}
	return slog.New(slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{
		Level: logLevel,
	}))
}

// startCmd 启动挖矿命令
func startCmd(cfg *config.Config) *cobra.Command {
	return &cobra.Command{
		Use:   "start",
		Short: "启动挖矿循环",
		Long:  "连接 ClawChain 节点，监听挑战并自动完成任务获取奖励",
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := cfg.Validate(); err != nil {
				return fmt.Errorf("配置验证失败: %w", err)
			}

			logger := setupLogger(cfg.LogLevel)
			logger.Info("🚀 ClawMiner 启动",
				"version", Version,
				"node", cfg.NodeRPC,
				"chain_id", cfg.ChainID,
				"key", cfg.KeyName,
				"llm_model", cfg.LLMModel,
			)

			// 创建各组件
			chainClient := client.NewChainClient(cfg, logger)
			llmClient := solver.NewLLMClient(cfg.LLMEndpoint, cfg.LLMAPIKey, cfg.LLMModel, logger)
			slv := solver.NewSolver(llmClient, logger)

			// TODO: 从 keyring 加载矿工地址，当前使用占位地址
			minerAddr := fmt.Sprintf("claw1miner_%s", cfg.KeyName)

			loop := mining.NewMiningLoop(cfg, chainClient, slv, minerAddr, logger)

			// 优雅退出
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			sigCh := make(chan os.Signal, 1)
			signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
			go func() {
				sig := <-sigCh
				logger.Info("收到退出信号", "signal", sig)
				cancel()
			}()

			return loop.Run(ctx)
		},
	}
}

// registerCmd 注册矿工命令
func registerCmd(cfg *config.Config) *cobra.Command {
	cmd := &cobra.Command{
		Use:   "register",
		Short: "注册为矿工并质押 $CLAW",
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := cfg.Validate(); err != nil {
				return fmt.Errorf("配置验证失败: %w", err)
			}

			logger := setupLogger(cfg.LogLevel)
			chainClient := client.NewChainClient(cfg, logger)

			minerAddr := fmt.Sprintf("claw1miner_%s", cfg.KeyName)

			logger.Info("注册矿工",
				"address", minerAddr,
				"stake", fmt.Sprintf("%d uclaw", cfg.StakeAmount),
			)

			ctx := context.Background()
			txHash, err := chainClient.RegisterMiner(ctx, minerAddr, cfg.StakeAmount)
			if err != nil {
				return fmt.Errorf("注册失败: %w", err)
			}

			fmt.Printf("✅ 矿工注册成功\n")
			fmt.Printf("   地址: %s\n", minerAddr)
			fmt.Printf("   质押: %d uclaw\n", cfg.StakeAmount)
			fmt.Printf("   交易: %s\n", txHash)
			return nil
		},
	}
	cmd.Flags().Uint64Var(&cfg.StakeAmount, "stake", cfg.StakeAmount, "质押金额 (uclaw)")
	return cmd
}

// statusCmd 查看矿工状态命令
func statusCmd(cfg *config.Config) *cobra.Command {
	return &cobra.Command{
		Use:   "status",
		Short: "查看矿工和节点状态",
		RunE: func(cmd *cobra.Command, args []string) error {
			if err := cfg.Validate(); err != nil {
				return fmt.Errorf("配置验证失败: %w", err)
			}

			logger := setupLogger(cfg.LogLevel)
			chainClient := client.NewChainClient(cfg, logger)

			ctx := context.Background()

			// 节点状态
			status, err := chainClient.GetStatus(ctx)
			if err != nil {
				return fmt.Errorf("查询节点状态失败: %w", err)
			}

			fmt.Printf("📡 节点状态\n")
			fmt.Printf("   网络: %s\n", status.NodeInfo.Network)
			fmt.Printf("   节点: %s\n", status.NodeInfo.Moniker)
			fmt.Printf("   最新高度: %s\n", status.SyncInfo.LatestBlockHeight)
			fmt.Printf("   同步中: %v\n", status.SyncInfo.CatchingUp)

			// 矿工状态
			minerAddr := fmt.Sprintf("claw1miner_%s", cfg.KeyName)
			minerInfo, err := chainClient.GetMinerInfo(ctx, minerAddr)
			if err != nil {
				fmt.Printf("\n⛏️  矿工状态: 未注册或查询失败 (%v)\n", err)
				return nil
			}

			fmt.Printf("\n⛏️  矿工状态\n")
			fmt.Printf("   地址: %s\n", minerInfo.Address)
			fmt.Printf("   状态: %s\n", minerInfo.Status)
			fmt.Printf("   质押: %d uclaw\n", minerInfo.Stake)
			fmt.Printf("   声誉: %d\n", minerInfo.Reputation)
			return nil
		},
	}
}

// versionCmd 版本信息命令
func versionCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "version",
		Short: "显示版本信息",
		Run: func(cmd *cobra.Command, args []string) {
			fmt.Printf("ClawMiner %s\n", Version)
			fmt.Printf("  Git Commit: %s\n", GitCommit)
			fmt.Printf("  Build Time: %s\n", BuildTime)
		},
	}
}

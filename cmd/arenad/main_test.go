package main

import (
	"context"
	"os"
	"syscall"
	"testing"

	"github.com/clawchain/clawchain/arena/config"
)

type contextKey string

type runnerFunc func(context.Context) error

func (f runnerFunc) Run(ctx context.Context) error {
	return f(ctx)
}

func TestRunMainUsesSignalContextForGracefulShutdown(t *testing.T) {
	t.Helper()

	markerKey := contextKey("signal")
	signalCtx := context.WithValue(context.Background(), markerKey, "wired")

	stopCalled := false
	runCalled := false

	err := runMain(
		context.Background(),
		func() config.Config {
			return config.Config{DatabaseURL: "postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable"}
		},
		func(cfg config.Config) (appRunner, error) {
			if cfg.DatabaseURL == "" {
				t.Fatal("expected config to be passed into app factory")
			}

			return runnerFunc(func(ctx context.Context) error {
				runCalled = true
				if got := ctx.Value(markerKey); got != "wired" {
					t.Fatalf("expected signal context to be passed to app, got %v", got)
				}

				return nil
			}), nil
		},
		func(parent context.Context, signals ...os.Signal) (context.Context, context.CancelFunc) {
			if parent != context.Background() {
				t.Fatal("expected signal context to wrap background context")
			}
			if !hasSignal(signals, os.Interrupt) {
				t.Fatal("expected os.Interrupt to be registered")
			}
			if !hasSignal(signals, syscall.SIGTERM) {
				t.Fatal("expected syscall.SIGTERM to be registered")
			}

			return signalCtx, func() { stopCalled = true }
		},
	)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !runCalled {
		t.Fatal("expected app Run to be called")
	}
	if !stopCalled {
		t.Fatal("expected stop func to be deferred")
	}
}

func hasSignal(signals []os.Signal, target os.Signal) bool {
	for _, signal := range signals {
		if signal == target {
			return true
		}
	}

	return false
}

package config_test

import (
	"strings"
	"testing"

	"github.com/clawchain/clawchain/arena/config"
)

func TestLoadConfigReadsArenaEnv(t *testing.T) {
	t.Setenv("ARENA_DATABASE_URL", "postgres://arena:arena@127.0.0.1:55432/arena?sslmode=disable")
	t.Setenv("ARENA_HTTP_ADDR", "127.0.0.1:18117")

	cfg := config.LoadFromEnv()
	if cfg.DatabaseURL == "" || cfg.HTTPAddr != "127.0.0.1:18117" {
		t.Fatalf("unexpected config: %+v", cfg)
	}
}

func TestMustLoadFromEnvPanicsOnMalformedDuration(t *testing.T) {
	t.Setenv("ARENA_SHUTDOWN_TIMEOUT", "not-a-duration")

	defer func() {
		recovered := recover()
		if recovered == nil {
			t.Fatal("expected panic for malformed shutdown timeout")
		}
		if !strings.Contains(recovered.(error).Error(), "ARENA_SHUTDOWN_TIMEOUT") {
			t.Fatalf("unexpected panic: %v", recovered)
		}
	}()

	_ = config.MustLoadFromEnv()
}

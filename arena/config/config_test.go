package config_test

import (
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

package app_test

import (
	"strings"
	"testing"

	"github.com/clawchain/clawchain/arena/app"
	"github.com/clawchain/clawchain/arena/config"
)

func TestNewAppRequiresDatabaseURL(t *testing.T) {
	cfg := config.Config{}

	_, err := app.New(cfg)
	if err == nil || !strings.Contains(err.Error(), "database url") {
		t.Fatalf("expected missing database url error, got %v", err)
	}
}

package config

import (
	"fmt"
	"os"
	"time"
)

const (
	defaultHTTPAddr             = "127.0.0.1:18117"
	defaultLogLevel             = "info"
	defaultShutdownTimeout      = 10 * time.Second
	defaultMigrationsDir        = "arena/store/postgres/schema"
	defaultActionDeadline       = 30 * time.Second
	defaultDeadlineScanInterval = 250 * time.Millisecond
)

type Config struct {
	DatabaseURL          string
	HTTPAddr             string
	LogLevel             string
	ShutdownTimeout      time.Duration
	MigrationsDir        string
	ActionDeadline       time.Duration
	DeadlineScanInterval time.Duration
}

func LoadFromEnv() Config {
	return Config{
		DatabaseURL:          os.Getenv("ARENA_DATABASE_URL"),
		HTTPAddr:             envOrDefault("ARENA_HTTP_ADDR", defaultHTTPAddr),
		LogLevel:             envOrDefault("ARENA_LOG_LEVEL", defaultLogLevel),
		ShutdownTimeout:      durationFromEnv("ARENA_SHUTDOWN_TIMEOUT", defaultShutdownTimeout),
		MigrationsDir:        envOrDefault("ARENA_MIGRATIONS_DIR", defaultMigrationsDir),
		ActionDeadline:       durationFromEnv("ARENA_ACTION_DEADLINE", defaultActionDeadline),
		DeadlineScanInterval: durationFromEnv("ARENA_DEADLINE_SCAN_INTERVAL", defaultDeadlineScanInterval),
	}
}

func MustLoadFromEnv() Config {
	cfg := LoadFromEnv()
	for _, item := range []struct {
		env    string
		target *time.Duration
	}{
		{env: "ARENA_SHUTDOWN_TIMEOUT", target: &cfg.ShutdownTimeout},
		{env: "ARENA_ACTION_DEADLINE", target: &cfg.ActionDeadline},
		{env: "ARENA_DEADLINE_SCAN_INTERVAL", target: &cfg.DeadlineScanInterval},
	} {
		value := os.Getenv(item.env)
		if value == "" {
			continue
		}

		parsed, err := time.ParseDuration(value)
		if err != nil {
			panic(fmt.Errorf("invalid %s: %w", item.env, err))
		}
		*item.target = parsed
	}
	return cfg
}

func envOrDefault(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}

	return fallback
}

func durationFromEnv(key string, fallback time.Duration) time.Duration {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}

	parsed, err := time.ParseDuration(value)
	if err != nil {
		return fallback
	}

	return parsed
}

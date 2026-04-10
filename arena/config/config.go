package config

import (
	"fmt"
	"os"
	"time"
)

const (
	defaultHTTPAddr        = "127.0.0.1:18117"
	defaultLogLevel        = "info"
	defaultShutdownTimeout = 10 * time.Second
	defaultMigrationsDir   = "arena/store/postgres/schema"
)

type Config struct {
	DatabaseURL     string
	HTTPAddr        string
	LogLevel        string
	ShutdownTimeout time.Duration
	MigrationsDir   string
}

func LoadFromEnv() Config {
	return Config{
		DatabaseURL:     os.Getenv("ARENA_DATABASE_URL"),
		HTTPAddr:        envOrDefault("ARENA_HTTP_ADDR", defaultHTTPAddr),
		LogLevel:        envOrDefault("ARENA_LOG_LEVEL", defaultLogLevel),
		ShutdownTimeout: durationFromEnv("ARENA_SHUTDOWN_TIMEOUT", defaultShutdownTimeout),
		MigrationsDir:   envOrDefault("ARENA_MIGRATIONS_DIR", defaultMigrationsDir),
	}
}

func MustLoadFromEnv() Config {
	cfg := LoadFromEnv()
	value := os.Getenv("ARENA_SHUTDOWN_TIMEOUT")
	if value == "" {
		return cfg
	}

	parsed, err := time.ParseDuration(value)
	if err != nil {
		panic(fmt.Errorf("invalid ARENA_SHUTDOWN_TIMEOUT: %w", err))
	}

	cfg.ShutdownTimeout = parsed
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

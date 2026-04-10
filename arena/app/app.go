package app

import (
	"context"
	"errors"
	"strings"
	"sync"
	"time"

	"github.com/clawchain/clawchain/arena/config"
)

type App struct {
	cfg       config.Config
	closeOnce sync.Once
	closed    chan struct{}
}

func New(cfg config.Config) (*App, error) {
	if strings.TrimSpace(cfg.DatabaseURL) == "" {
		return nil, errors.New("database url is required")
	}

	return &App{
		cfg:    cfg,
		closed: make(chan struct{}),
	}, nil
}

func (a *App) Run(ctx context.Context) error {
	if ctx == nil {
		return errors.New("context is required")
	}

	select {
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), a.shutdownTimeout())
		defer cancel()

		if err := a.Close(shutdownCtx); err != nil {
			return err
		}

		return nil
	case <-a.closed:
		return nil
	}
}

func (a *App) Close(ctx context.Context) error {
	if ctx == nil {
		return errors.New("context is required")
	}

	a.closeOnce.Do(func() {
		close(a.closed)
	})

	return nil
}

func (a *App) shutdownTimeout() time.Duration {
	if a.cfg.ShutdownTimeout > 0 {
		return a.cfg.ShutdownTimeout
	}

	return 10 * time.Second
}

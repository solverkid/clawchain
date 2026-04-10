package app

import (
	"context"
	"database/sql"
	"errors"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/clawchain/clawchain/arena/config"
	"github.com/clawchain/clawchain/arena/gateway"
	"github.com/clawchain/clawchain/arena/httpapi"
	"github.com/clawchain/clawchain/arena/session"
	"github.com/clawchain/clawchain/arena/store/postgres"
)

type App struct {
	cfg           config.Config
	db            *sql.DB
	server        *httpapi.Server
	httpServer    *http.Server
	boundHTTPAddr string

	mu        sync.RWMutex
	closeOnce sync.Once
	closed    chan struct{}
}

func New(cfg config.Config) (*App, error) {
	if strings.TrimSpace(cfg.DatabaseURL) == "" {
		return nil, errors.New("database url is required")
	}

	db, err := sql.Open("postgres", cfg.DatabaseURL)
	if err != nil {
		return nil, err
	}
	if err := db.Ping(); err != nil {
		_ = db.Close()
		return nil, err
	}
	if err := postgres.Migrate(db); err != nil {
		_ = db.Close()
		return nil, err
	}

	repo, err := postgres.NewRepository(db)
	if err != nil {
		_ = db.Close()
		return nil, err
	}

	runtimeService := newRuntimeService(repo, time.Now().UTC)
	server := httpapi.NewServer(httpapi.Dependencies{
		Arena:    runtimeService,
		Gateway:  gateway.New(gateway.Config{}),
		Sessions: session.NewManager(),
	})

	return &App{
		cfg:    cfg,
		db:     db,
		server: server,
		closed: make(chan struct{}),
	}, nil
}

func (a *App) Handler() http.Handler {
	return a.server.Handler()
}

func (a *App) HTTPAddr() string {
	a.mu.RLock()
	defer a.mu.RUnlock()
	if a.boundHTTPAddr != "" {
		return a.boundHTTPAddr
	}
	return a.cfg.HTTPAddr
}

func (a *App) Run(ctx context.Context) error {
	if ctx == nil {
		return errors.New("context is required")
	}

	listener, err := net.Listen("tcp", a.cfg.HTTPAddr)
	if err != nil {
		return err
	}
	defer func() {
		_ = listener.Close()
	}()

	a.mu.Lock()
	a.boundHTTPAddr = listener.Addr().String()
	a.httpServer = &http.Server{Handler: a.server.Handler()}
	a.mu.Unlock()

	serveErr := make(chan error, 1)
	go func() {
		err := a.httpServer.Serve(listener)
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			serveErr <- err
			return
		}
		serveErr <- nil
	}()

	select {
	case err := <-serveErr:
		return err
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), a.shutdownTimeout())
		defer cancel()

		if err := a.Close(shutdownCtx); err != nil {
			return err
		}

		return <-serveErr
	case <-a.closed:
		return <-serveErr
	}
}

func (a *App) Close(ctx context.Context) error {
	if ctx == nil {
		return errors.New("context is required")
	}

	var closeErr error
	a.closeOnce.Do(func() {
		a.mu.RLock()
		httpServer := a.httpServer
		a.mu.RUnlock()

		if httpServer != nil {
			closeErr = httpServer.Shutdown(ctx)
		}
		if dbErr := a.db.Close(); closeErr == nil && dbErr != nil {
			closeErr = dbErr
		}
		close(a.closed)
	})

	return closeErr
}

func (a *App) shutdownTimeout() time.Duration {
	if a.cfg.ShutdownTimeout > 0 {
		return a.cfg.ShutdownTimeout
	}

	return 10 * time.Second
}

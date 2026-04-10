package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"

	"github.com/clawchain/clawchain/arena/app"
	"github.com/clawchain/clawchain/arena/config"
)

type appRunner interface {
	Run(context.Context) error
}

type appFactory func(config.Config) (appRunner, error)

type signalContextFactory func(context.Context, ...os.Signal) (context.Context, context.CancelFunc)

func main() {
	if err := runMain(
		context.Background(),
		config.MustLoadFromEnv,
		func(cfg config.Config) (appRunner, error) { return app.New(cfg) },
		signal.NotifyContext,
	); err != nil {
		log.Fatal(err)
	}
}

func runMain(
	parent context.Context,
	loadConfig func() config.Config,
	newApp appFactory,
	notifyContext signalContextFactory,
) error {
	cfg := loadConfig()
	application, err := newApp(cfg)
	if err != nil {
		return err
	}

	ctx, stop := notifyContext(parent, os.Interrupt, syscall.SIGTERM)
	defer stop()

	return application.Run(ctx)
}

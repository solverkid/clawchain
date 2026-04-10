package main

import (
	"context"
	"log"

	"github.com/clawchain/clawchain/arena/app"
	"github.com/clawchain/clawchain/arena/config"
)

func main() {
	cfg := config.MustLoadFromEnv()
	application, err := app.New(cfg)
	if err != nil {
		log.Fatal(err)
	}

	if err := application.Run(context.Background()); err != nil {
		log.Fatal(err)
	}
}

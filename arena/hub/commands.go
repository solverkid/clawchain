package hub

import "context"

type LockField struct{}

type PublishSeats struct{}

type ForceRemoveBeforeStart struct {
	MinerID string
}

type RepublishSeats struct{}

type CommandHandler interface {
	LockAndPack(ctx context.Context) (PackResult, error)
	PublishSeats(ctx context.Context) error
	ForceRemoveBeforeStart(ctx context.Context, minerID string) error
	RepublishSeats(ctx context.Context) error
}

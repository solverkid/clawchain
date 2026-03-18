package types

import "cosmossdk.io/errors"

var (
	ErrInvalidChallenge    = errors.Register(ModuleName, 1, "invalid challenge")
	ErrChallengeNotFound   = errors.Register(ModuleName, 2, "challenge not found")
	ErrChallengeExpired    = errors.Register(ModuleName, 3, "challenge expired")
	ErrAlreadyCommitted    = errors.Register(ModuleName, 4, "already committed")
	ErrAlreadyRevealed     = errors.Register(ModuleName, 5, "already revealed")
	ErrNotAssigned         = errors.Register(ModuleName, 6, "miner not assigned to this challenge")
	ErrCommitHashMismatch  = errors.Register(ModuleName, 7, "reveal does not match commit hash")
	ErrWindowClosed             = errors.Register(ModuleName, 8, "submission window closed")
	ErrInsufficientReputation   = errors.Register(ModuleName, 9, "miner reputation too low for this tier")
	ErrSpotCheckFailed          = errors.Register(ModuleName, 10, "spot check answer incorrect")
)

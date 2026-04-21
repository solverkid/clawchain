package types

import "cosmossdk.io/errors"

var (
	ErrMinerNotFound               = errors.Register(ModuleName, 1, "miner reputation not found")
	ErrInvalidReputationDelta      = errors.Register(ModuleName, 2, "invalid reputation delta")
	ErrUnauthorizedDeltaController = errors.Register(ModuleName, 3, "unauthorized reputation delta controller")
	ErrReputationDeltaConflict     = errors.Register(ModuleName, 4, "reputation delta conflict")
)

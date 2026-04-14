package types

import "cosmossdk.io/errors"

var (
	ErrInvalidSettlementBatch  = errors.Register(ModuleName, 1, "invalid settlement batch")
	ErrSettlementBatchAnchored = errors.Register(ModuleName, 2, "settlement batch already anchored")
)

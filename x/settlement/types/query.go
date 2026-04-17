package types

import "context"

type QueryServer interface {
	SettlementAnchor(context.Context, *QuerySettlementAnchorRequest) (*QuerySettlementAnchorResponse, error)
}

type QuerySettlementAnchorRequest struct {
	SettlementBatchId string `json:"settlement_batch_id"`
}

type QuerySettlementAnchorResponse struct {
	Anchor SettlementAnchor `json:"anchor"`
}

func RegisterQueryServer(s interface{}, srv QueryServer) {
	_ = s
	_ = srv
}

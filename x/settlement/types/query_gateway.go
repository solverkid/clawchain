package types

import (
	"context"
	"encoding/json"
	"net/http"

	gwruntime "github.com/grpc-ecosystem/grpc-gateway/runtime"
)

const QuerySettlementAnchorFullMethod = "/clawchain.settlement.v1.Query/SettlementAnchor"

func RegisterQueryHandlerClient(ctx context.Context, mux *gwruntime.ServeMux, client QueryClient) error {
	mux.Handle("GET", patternQuerySettlementAnchor, func(w http.ResponseWriter, req *http.Request, pathParams map[string]string) {
		resp, err := client.SettlementAnchor(
			req.Context(),
			&QuerySettlementAnchorRequest{SettlementBatchID: pathParams["settlement_batch_id"]},
		)
		if err != nil {
			_, outboundMarshaler := gwruntime.MarshalerForRequest(mux, req)
			gwruntime.HTTPError(ctx, mux, outboundMarshaler, w, req, err)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(resp)
	})
	return nil
}

var patternQuerySettlementAnchor = gwruntime.MustPattern(
	gwruntime.NewPattern(
		1,
		[]int{2, 0, 2, 1, 2, 2, 2, 3, 1, 0, 4, 1, 5, 4},
		[]string{"clawchain", "settlement", "v1", "anchors", "settlement_batch_id"},
		"",
		gwruntime.AssumeColonVerbOpt(false),
	),
)

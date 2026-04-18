package types_test

import (
	"context"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	gwruntime "github.com/grpc-ecosystem/grpc-gateway/runtime"
	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/test/bufconn"

	"github.com/clawchain/clawchain/x/settlement/types"
)

type fakeGatewayQueryServer struct {
	types.UnimplementedQueryServer
}

func (fakeGatewayQueryServer) SettlementAnchor(
	_ context.Context,
	req *types.QuerySettlementAnchorRequest,
) (*types.QuerySettlementAnchorResponse, error) {
	if req.SettlementBatchID != "sb_gateway" {
		return nil, types.ErrInvalidSettlementBatch
	}
	return &types.QuerySettlementAnchorResponse{
		Anchor: &types.SettlementAnchor{
			SettlementBatchID:   "sb_gateway",
			AnchorJobID:         "aj_gateway",
			CanonicalRoot:       "sha256:" + strings.Repeat("d", 64),
			AnchorPayloadHash:   "sha256:" + strings.Repeat("e", 64),
			MinerRewardRowsRoot: "sha256:" + strings.Repeat("f", 64),
		},
	}, nil
}

func TestSettlementAnchorGatewayRouteReturnsStoredAnchor(t *testing.T) {
	listener := bufconn.Listen(1024 * 1024)
	grpcServer := grpc.NewServer()
	types.RegisterQueryServer(grpcServer, fakeGatewayQueryServer{})
	go func() {
		_ = grpcServer.Serve(listener)
	}()
	t.Cleanup(grpcServer.Stop)
	t.Cleanup(func() { _ = listener.Close() })

	conn, err := grpc.DialContext(
		context.Background(),
		"bufnet",
		grpc.WithContextDialer(func(context.Context, string) (net.Conn, error) {
			return listener.Dial()
		}),
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	require.NoError(t, err)
	t.Cleanup(func() { _ = conn.Close() })

	mux := gwruntime.NewServeMux()
	require.NoError(t, types.RegisterQueryHandlerClient(context.Background(), mux, types.NewQueryClient(conn)))

	req := httptest.NewRequest(http.MethodGet, "/clawchain/settlement/v1/anchors/sb_gateway", nil)
	rec := httptest.NewRecorder()
	mux.ServeHTTP(rec, req)

	require.Equal(t, http.StatusOK, rec.Code)
	require.Contains(t, rec.Body.String(), `"settlement_batch_id":"sb_gateway"`)
	require.Contains(t, rec.Body.String(), `"anchor_payload_hash":"sha256:`)
}

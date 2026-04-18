package cli_test

import (
	"bytes"
	"context"
	"net"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/test/bufconn"

	"github.com/cosmos/cosmos-sdk/client"

	settlementcli "github.com/clawchain/clawchain/x/settlement/client/cli"
	"github.com/clawchain/clawchain/x/settlement/types"
)

const queryBufSize = 1024 * 1024

type fakeSettlementQueryServer struct {
	types.UnimplementedQueryServer
}

func (fakeSettlementQueryServer) SettlementAnchor(
	_ context.Context,
	req *types.QuerySettlementAnchorRequest,
) (*types.QuerySettlementAnchorResponse, error) {
	if req.SettlementBatchID != "sb_1" {
		return nil, types.ErrInvalidSettlementBatch
	}
	return &types.QuerySettlementAnchorResponse{
		Anchor: &types.SettlementAnchor{
			SettlementBatchID:   "sb_1",
			AnchorJobID:         "aj_1",
			CanonicalRoot:       "sha256:" + strings.Repeat("a", 64),
			AnchorPayloadHash:   "sha256:" + strings.Repeat("b", 64),
			MinerRewardRowsRoot: "sha256:" + strings.Repeat("c", 64),
		},
	}, nil
}

func TestSettlementAnchorQueryCmdReturnsStoredAnchorFromExternalQuery(t *testing.T) {
	listener := bufconn.Listen(queryBufSize)
	grpcServer := grpc.NewServer()
	types.RegisterQueryServer(grpcServer, fakeSettlementQueryServer{})
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

	var out bytes.Buffer
	cmd := settlementcli.NewSettlementAnchorQueryCmd()
	cmd.SetContext(context.Background())
	clientCtx := client.Context{}.
		WithGRPCClient(conn).
		WithOutput(&out).
		WithOutputFormat("json")
	require.NoError(t, client.SetCmdClientContext(cmd, clientCtx))
	cmd.SetArgs([]string{"sb_1"})

	require.NoError(t, cmd.Execute())
	require.Contains(t, out.String(), `"settlement_batch_id":"sb_1"`)
	require.Contains(t, out.String(), `"canonical_root":"sha256:`)
}

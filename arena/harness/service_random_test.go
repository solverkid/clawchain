package harness

import (
	"net/http"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestNewAcceptsRandomPolicyMode(t *testing.T) {
	service, err := New(Config{
		BaseURL:    "http://127.0.0.1:18117",
		MinerCount: 2,
		PolicyMode: PolicyModeRandom,
	})
	require.NoError(t, err)
	require.Equal(t, PolicyModeRandom, service.cfg.PolicyMode)
}

func TestNewBuildsPooledHTTPClientByDefault(t *testing.T) {
	service, err := New(Config{
		BaseURL:    "http://127.0.0.1:18117",
		MinerCount: 111,
		PolicyMode: PolicyModeRandom,
	})
	require.NoError(t, err)
	require.NotNil(t, service.cfg.HTTPClient)
	require.NotSame(t, http.DefaultClient, service.cfg.HTTPClient)
	require.Equal(t, 15*time.Second, service.cfg.HTTPClient.Timeout)

	transport, ok := service.cfg.HTTPClient.Transport.(*http.Transport)
	require.True(t, ok)
	require.GreaterOrEqual(t, transport.MaxIdleConnsPerHost, 64)
	require.GreaterOrEqual(t, transport.MaxIdleConns, transport.MaxIdleConnsPerHost)
	require.GreaterOrEqual(t, transport.MaxConnsPerHost, 64)
}

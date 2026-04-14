package authadapter_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/clawchain/clawchain/authadapter"
	"github.com/stretchr/testify/require"
)

func TestDonorTokenVerifyAdapterSuccess(t *testing.T) {
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/token_verify", r.URL.Path)
		require.Equal(t, "Bearer donor-token-123", r.Header.Get("Authorization"))
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code":    0,
			"msg":     "ok",
			"success": true,
			"data": map[string]any{
				"userID":     "42",
				"playerName": "tester",
			},
		})
	}))
	defer server.Close()

	adapter := authadapter.DonorTokenVerifyAdapter{
		BaseURL:  server.URL,
		Client:   server.Client(),
		Now:      func() time.Time { return now },
		TokenTTL: 30 * time.Minute,
	}

	principal, err := adapter.Verify(context.Background(), "Bearer donor-token-123")
	require.NoError(t, err)
	require.Equal(t, "42", principal.UserID)
	require.Equal(t, "tester", principal.DisplayName)
	require.Equal(t, "claw1local-42", principal.MinerAddress)
	require.True(t, principal.TokenExpiresAt.Equal(now.Add(30*time.Minute)))
}

func TestDonorTokenVerifyAdapterFailure(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code":    401,
			"msg":     "missing token",
			"success": false,
		})
	}))
	defer server.Close()

	adapter := authadapter.DonorTokenVerifyAdapter{
		BaseURL:  server.URL,
		Client:   server.Client(),
		TokenTTL: time.Hour,
	}

	_, err := adapter.Verify(context.Background(), "Bearer missing")
	require.Error(t, err)
}

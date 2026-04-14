package authadapter

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

type DonorTokenVerifyAdapter struct {
	BaseURL  string
	Client   *http.Client
	Now      func() time.Time
	TokenTTL time.Duration
}

func (a DonorTokenVerifyAdapter) Verify(ctx context.Context, authorization string) (Principal, error) {
	token, err := normalizeAuthorizationHeader(authorization)
	if err != nil {
		return Principal{}, err
	}
	if strings.TrimSpace(a.BaseURL) == "" {
		return Principal{}, ErrInvalidConfiguration
	}
	if ctx == nil {
		ctx = context.Background()
	}

	now := time.Now().UTC()
	if a.Now != nil {
		now = a.Now().UTC()
	}
	ttl := a.TokenTTL
	if ttl <= 0 {
		ttl = time.Hour
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, strings.TrimRight(a.BaseURL, "/")+"/token_verify", nil)
	if err != nil {
		return Principal{}, err
	}
	req.Header.Set("Authorization", "Bearer "+token)

	client := a.Client
	if client == nil {
		client = http.DefaultClient
	}
	resp, err := client.Do(req)
	if err != nil {
		return Principal{}, err
	}
	defer resp.Body.Close()

	var payload struct {
		Code    int    `json:"code"`
		Msg     string `json:"msg"`
		Success bool   `json:"success"`
		Data    struct {
			UserID       string `json:"userID"`
			UserId       string `json:"userId"`
			PlayerName   string `json:"playerName"`
			MinerAddress string `json:"minerAddress"`
			MinerID      string `json:"miner_id"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return Principal{}, ErrTokenVerificationFailed
	}
	if resp.StatusCode >= http.StatusBadRequest || !payload.Success || payload.Code != 0 {
		return Principal{}, ErrTokenVerificationFailed
	}

	userID := strings.TrimSpace(payload.Data.UserID)
	if userID == "" {
		userID = strings.TrimSpace(payload.Data.UserId)
	}
	if userID == "" {
		return Principal{}, ErrTokenVerificationFailed
	}

	displayName := strings.TrimSpace(payload.Data.PlayerName)
	if displayName == "" {
		displayName = userID
	}

	minerAddress := strings.TrimSpace(payload.Data.MinerAddress)
	if minerAddress == "" {
		minerAddress = strings.TrimSpace(payload.Data.MinerID)
	}
	if minerAddress == "" {
		minerAddress = DefaultMinerAddress(userID)
	} else {
		minerAddress, err = normalizeMinerAddress(minerAddress)
		if err != nil {
			return Principal{}, ErrTokenVerificationFailed
		}
	}

	return Principal{
		UserID:         userID,
		MinerAddress:   minerAddress,
		DisplayName:    displayName,
		TokenExpiresAt: now.Add(ttl),
	}, nil
}

func (a DonorTokenVerifyAdapter) String() string {
	return fmt.Sprintf("DonorTokenVerifyAdapter(%s)", strings.TrimSpace(a.BaseURL))
}

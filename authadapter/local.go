package authadapter

import (
	"context"
	"time"
)

type LocalAdapter struct {
	Now      func() time.Time
	TokenTTL time.Duration
}

func (a LocalAdapter) Verify(ctx context.Context, authorization string) (Principal, error) {
	_ = ctx

	userID, err := LocalUserIDFromAuthorization(authorization)
	if err != nil {
		return Principal{}, err
	}

	now := time.Now().UTC()
	if a.Now != nil {
		now = a.Now().UTC()
	}
	ttl := a.TokenTTL
	if ttl <= 0 {
		ttl = time.Hour
	}

	return Principal{
		UserID:         userID,
		MinerAddress:   DefaultMinerAddress(userID),
		DisplayName:    userID,
		AuthSource:     AuthSourceLocal,
		IsSynthetic:    true,
		TokenExpiresAt: now.Add(ttl),
	}, nil
}

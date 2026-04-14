package authadapter

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrTokenExpired            = errors.New("token expired")
	ErrMinerAddressMismatch    = errors.New("miner address mismatch")
	ErrPrincipalMinerMissing   = errors.New("principal miner address missing")
	ErrInvalidConfiguration    = errors.New("invalid authentication adapter configuration")
	ErrMissingAuthorization    = errors.New("missing authorization header")
	ErrInvalidAuthorization    = errors.New("invalid authorization header")
	ErrTokenVerificationFailed = errors.New("token verification failed")
	ErrPrincipalRevoked        = errors.New("principal revoked")
)

type Principal struct {
	UserID         string
	MinerAddress   string
	DisplayName    string
	Roles          []string
	TokenExpiresAt time.Time
	AuthSessionID  string
	TokenID        string
}

func (p Principal) IsExpired(now time.Time) bool {
	return !p.TokenExpiresAt.IsZero() && !now.Before(p.TokenExpiresAt)
}

func (p Principal) ValidateMutation(now time.Time) error {
	if p.IsExpired(now) {
		return ErrTokenExpired
	}
	return nil
}

func (p Principal) NormalizedMinerAddress() (string, error) {
	return normalizeMinerAddress(p.MinerAddress)
}

func normalizeAuthorizationHeader(authorization string) (string, error) {
	token := strings.TrimSpace(authorization)
	if token == "" {
		return "", ErrMissingAuthorization
	}
	if len(token) < len("Bearer ") || !strings.EqualFold(token[:len("Bearer ")], "Bearer ") {
		return "", ErrInvalidAuthorization
	}
	token = strings.TrimSpace(token[len("Bearer "):])
	if token == "" {
		return "", ErrInvalidAuthorization
	}
	return token, nil
}

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

const (
	AuthSourceLocal            = "local"
	AuthSourceDonorTokenVerify = "donor_token_verify"
	RolePokerMTTRewardBound    = "poker_mtt_reward_bound"
)

type Principal struct {
	UserID         string
	MinerAddress   string
	DisplayName    string
	AuthSource     string
	IsSynthetic    bool
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

func (p Principal) HasRole(role string) bool {
	expected := strings.TrimSpace(role)
	for _, candidate := range p.Roles {
		if strings.TrimSpace(candidate) == expected {
			return true
		}
	}
	return false
}

func (p Principal) PokerMTTRewardEligible() bool {
	minerAddress, err := p.NormalizedMinerAddress()
	if err != nil {
		return false
	}
	if p.IsSynthetic && !p.HasRole(RolePokerMTTRewardBound) {
		return false
	}
	if strings.HasPrefix(minerAddress, "claw1local-") {
		return p.HasRole(RolePokerMTTRewardBound)
	}
	return true
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

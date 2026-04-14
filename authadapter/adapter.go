package authadapter

import (
	"context"
	"errors"
	"net/http"
	"strings"
)

const localUserTokenPrefix = "local-user:"

type TokenVerifier interface {
	Verify(ctx context.Context, authorization string) (Principal, error)
}

type RequestVerifier interface {
	VerifyRequest(ctx context.Context, req *http.Request) (Principal, error)
}

type HTTPVerifier struct {
	Verifier TokenVerifier
}

func (v HTTPVerifier) VerifyRequest(ctx context.Context, req *http.Request) (Principal, error) {
	if v.Verifier == nil {
		return Principal{}, ErrInvalidConfiguration
	}
	if req == nil {
		return Principal{}, ErrMissingAuthorization
	}
	authorization := req.Header.Get("Authorization")
	if strings.TrimSpace(authorization) == "" {
		return Principal{}, ErrMissingAuthorization
	}
	return v.Verifier.Verify(ctx, authorization)
}

func VerifyRequest(ctx context.Context, req *http.Request, verifier TokenVerifier) (Principal, error) {
	return HTTPVerifier{Verifier: verifier}.VerifyRequest(ctx, req)
}

func LocalUserIDFromAuthorization(authorization string) (string, error) {
	token, err := normalizeAuthorizationHeader(authorization)
	if err != nil {
		return "", err
	}
	if !strings.HasPrefix(token, localUserTokenPrefix) {
		return "", ErrInvalidAuthorization
	}
	userID := strings.TrimSpace(strings.TrimPrefix(token, localUserTokenPrefix))
	if userID == "" || strings.ContainsAny(userID, " \t\r\n") {
		return "", ErrInvalidAuthorization
	}
	return userID, nil
}

func DefaultMinerAddress(userID string) string {
	candidate := "claw1local-" + strings.TrimSpace(userID)
	normalized, err := normalizeMinerAddress(candidate)
	if err != nil {
		return strings.ToLower(strings.TrimSpace(candidate))
	}
	return normalized
}

func ValidateMutationMiner(principal Principal, requestMinerID string) error {
	if strings.TrimSpace(principal.MinerAddress) == "" {
		return ErrPrincipalMinerMissing
	}
	expected, err := normalizeMinerAddress(principal.MinerAddress)
	if err != nil {
		return err
	}
	actual, err := normalizeMinerAddress(requestMinerID)
	if err != nil {
		return err
	}
	if expected != actual {
		return ErrMinerAddressMismatch
	}
	return nil
}

func normalizeMinerAddress(raw string) (string, error) {
	normalized := strings.ToLower(strings.TrimSpace(raw))
	if normalized == "" || strings.ContainsAny(normalized, " \t\r\n") {
		return "", errors.New("invalid miner address")
	}
	return normalized, nil
}

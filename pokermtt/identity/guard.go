package identity

import (
	"time"

	"github.com/clawchain/clawchain/authadapter"
)

type AuthorizedMutation struct {
	UserID       string
	MinerAddress string
	Principal    authadapter.Principal
}

type MutationRequest struct {
	RequestMinerID string
	Now            time.Time
}

type MutationAuthorizer struct{}

func AuthorizeMutation(principal authadapter.Principal, requestMinerID string, now time.Time) (AuthorizedMutation, error) {
	return MutationAuthorizer{}.Authorize(principal, MutationRequest{
		RequestMinerID: requestMinerID,
		Now:            now,
	})
}

func (MutationAuthorizer) Authorize(principal authadapter.Principal, request MutationRequest) (AuthorizedMutation, error) {
	if err := principal.ValidateMutation(request.Now); err != nil {
		return AuthorizedMutation{}, err
	}
	if err := authadapter.ValidateMutationMiner(principal, request.RequestMinerID); err != nil {
		return AuthorizedMutation{}, err
	}
	minerAddress, err := NormalizeMinerAddress(principal.MinerAddress)
	if err != nil {
		return AuthorizedMutation{}, err
	}
	return AuthorizedMutation{
		UserID:       principal.UserID,
		MinerAddress: minerAddress,
		Principal:    principal,
	}, nil
}

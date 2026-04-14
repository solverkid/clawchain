package authadapter

import "time"

type SessionAuthState struct {
	Principal         Principal
	Revoked           bool
	AcceptedActionIDs map[string]struct{}
}

func NewSessionAuthState(principal Principal) SessionAuthState {
	return SessionAuthState{
		Principal:         principal,
		AcceptedActionIDs: make(map[string]struct{}),
	}
}

func (state SessionAuthState) AuthorizeManualAction(now time.Time) error {
	if state.Revoked {
		return ErrPrincipalRevoked
	}
	return state.Principal.ValidateMutation(now)
}

func (state SessionAuthState) Reconnect(fresh Principal, now time.Time) (SessionAuthState, error) {
	if state.Revoked {
		return SessionAuthState{}, ErrPrincipalRevoked
	}
	if err := fresh.ValidateMutation(now); err != nil {
		return SessionAuthState{}, err
	}
	if state.Principal.UserID != fresh.UserID {
		return SessionAuthState{}, ErrInvalidAuthorization
	}
	if err := ValidateMutationMiner(state.Principal, fresh.MinerAddress); err != nil {
		return SessionAuthState{}, err
	}
	if state.AcceptedActionIDs == nil {
		state.AcceptedActionIDs = make(map[string]struct{})
	}
	state.Principal = fresh
	return state, nil
}

func (state *SessionAuthState) RecordAcceptedAction(actionID string) {
	if state.AcceptedActionIDs == nil {
		state.AcceptedActionIDs = make(map[string]struct{})
	}
	state.AcceptedActionIDs[actionID] = struct{}{}
}

func (state SessionAuthState) HasAcceptedAction(actionID string) bool {
	if state.AcceptedActionIDs == nil {
		return false
	}
	_, ok := state.AcceptedActionIDs[actionID]
	return ok
}

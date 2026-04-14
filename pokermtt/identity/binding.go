package identity

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidBinding  = errors.New("invalid identity binding")
	ErrBindingConflict = errors.New("identity binding conflict")
)

type Binding struct {
	UserID       string
	MinerAddress string
	CreatedAt    time.Time
	UpdatedAt    time.Time
}

func NormalizeUserID(raw string) (string, error) {
	normalized := strings.TrimSpace(raw)
	if normalized == "" || strings.ContainsAny(normalized, " \t\r\n") {
		return "", ErrInvalidBinding
	}
	return normalized, nil
}

func NormalizeMinerAddress(raw string) (string, error) {
	normalized := strings.ToLower(strings.TrimSpace(raw))
	if normalized == "" || strings.ContainsAny(normalized, " \t\r\n") {
		return "", ErrInvalidBinding
	}
	return normalized, nil
}

func normalizeBinding(binding Binding) (Binding, error) {
	userID, err := NormalizeUserID(binding.UserID)
	if err != nil {
		return Binding{}, err
	}
	minerAddress, err := NormalizeMinerAddress(binding.MinerAddress)
	if err != nil {
		return Binding{}, err
	}
	binding.UserID = userID
	binding.MinerAddress = minerAddress
	return binding, nil
}

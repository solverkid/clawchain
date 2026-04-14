package identity_test

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/clawchain/clawchain/pokermtt/identity"
	"github.com/stretchr/testify/require"
)

func TestBindingStoreFirstBindAndIdempotentRepeat(t *testing.T) {
	store := identity.NewMemoryStore()
	ctx := context.Background()

	binding, err := store.Bind(ctx, identity.Binding{
		UserID:       "user-1",
		MinerAddress: " CLAW1ABC ",
	})
	require.NoError(t, err)
	require.Equal(t, "user-1", binding.UserID)
	require.Equal(t, "claw1abc", binding.MinerAddress)
	require.False(t, binding.CreatedAt.IsZero())
	require.False(t, binding.UpdatedAt.IsZero())

	repeat, err := store.Bind(ctx, identity.Binding{
		UserID:       "user-1",
		MinerAddress: "claw1abc",
	})
	require.NoError(t, err)
	require.Equal(t, binding.UserID, repeat.UserID)
	require.Equal(t, binding.MinerAddress, repeat.MinerAddress)
	require.True(t, binding.CreatedAt.Equal(repeat.CreatedAt))
	require.True(t, binding.UpdatedAt.Equal(repeat.UpdatedAt))
}

func TestBindingStoreRejectsConflictingUserBinding(t *testing.T) {
	store := identity.NewMemoryStore()
	ctx := context.Background()

	_, err := store.Bind(ctx, identity.Binding{UserID: "user-1", MinerAddress: "claw1abc"})
	require.NoError(t, err)

	_, err = store.Bind(ctx, identity.Binding{UserID: "user-1", MinerAddress: "claw1def"})
	require.ErrorIs(t, err, identity.ErrBindingConflict)
}

func TestBindingStoreRejectsConflictingMinerBinding(t *testing.T) {
	store := identity.NewMemoryStore()
	ctx := context.Background()

	_, err := store.Bind(ctx, identity.Binding{UserID: "user-1", MinerAddress: "claw1abc"})
	require.NoError(t, err)

	_, err = store.Bind(ctx, identity.Binding{UserID: "user-2", MinerAddress: "claw1abc"})
	require.ErrorIs(t, err, identity.ErrBindingConflict)
}

func TestBindingStoreRejectsEmptyAndMalformedInput(t *testing.T) {
	store := identity.NewMemoryStore()
	ctx := context.Background()

	_, err := store.Bind(ctx, identity.Binding{UserID: "", MinerAddress: "claw1abc"})
	require.ErrorIs(t, err, identity.ErrInvalidBinding)

	_, err = store.Bind(ctx, identity.Binding{UserID: "user-1", MinerAddress: "bad address"})
	require.ErrorIs(t, err, identity.ErrInvalidBinding)
}

func TestNormalizeMinerAddressIsDeterministic(t *testing.T) {
	got, err := identity.NormalizeMinerAddress("  CLAW1ABC  ")
	require.NoError(t, err)
	require.Equal(t, "claw1abc", got)
}

func TestBindingStoreConcurrentFirstBindRace(t *testing.T) {
	store := identity.NewMemoryStore()
	ctx := context.Background()
	start := make(chan struct{})

	var wg sync.WaitGroup
	results := make(chan error, 2)
	bind := func(userID, minerAddress string) {
		defer wg.Done()
		<-start
		_, err := store.Bind(ctx, identity.Binding{UserID: userID, MinerAddress: minerAddress})
		results <- err
	}

	wg.Add(2)
	go bind("user-1", "claw1abc")
	go bind("user-1", "claw1def")
	close(start)
	wg.Wait()
	close(results)

	var successCount, conflictCount int
	for err := range results {
		if err == nil {
			successCount++
			continue
		}
		require.ErrorIs(t, err, identity.ErrBindingConflict)
		conflictCount++
	}

	require.Equal(t, 1, successCount)
	require.Equal(t, 1, conflictCount)
}

func TestBindingStoreLookupByKeys(t *testing.T) {
	store := identity.NewMemoryStore()
	ctx := context.Background()
	now := time.Date(2026, 4, 14, 10, 0, 0, 0, time.UTC)

	binding, err := store.Bind(ctx, identity.Binding{
		UserID:       "user-1",
		MinerAddress: "claw1abc",
		CreatedAt:    now,
		UpdatedAt:    now,
	})
	require.NoError(t, err)

	byUser, ok, err := store.ByUserID(ctx, "user-1")
	require.NoError(t, err)
	require.True(t, ok)
	require.Equal(t, binding, byUser)

	byMiner, ok, err := store.ByMinerAddress(ctx, "CLAW1ABC")
	require.NoError(t, err)
	require.True(t, ok)
	require.Equal(t, binding, byMiner)
}

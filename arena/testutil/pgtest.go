package testutil

import (
	"database/sql"
	"fmt"
	"net/url"
	"os"
	"regexp"
	"sort"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

const defaultArenaTestDatabaseURL = "postgres://clawchain:clawchain_dev_pw@127.0.0.1:55432/arena_runtime_test?sslmode=disable"

var schemaNamePattern = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

func DatabaseURLForSchema(schema string) string {
	schema = normalizeSchemaName(schema)

	databaseURL := os.Getenv("ARENA_TEST_DATABASE_URL")
	if databaseURL == "" {
		databaseURL = defaultArenaTestDatabaseURL
	}

	parsed, err := url.Parse(databaseURL)
	if err != nil {
		panic(fmt.Errorf("parse arena test database url: %w", err))
	}
	query := parsed.Query()
	query.Set("search_path", schema)
	parsed.RawQuery = query.Encode()
	return parsed.String()
}

func OpenArenaTestDB(t *testing.T, schema string) *sql.DB {
	t.Helper()

	db, err := sql.Open("postgres", DatabaseURLForSchema(schema))
	require.NoError(t, err)
	require.NoError(t, db.Ping())
	return db
}

func ResetArenaSchema(t *testing.T, db *sql.DB, schema string) {
	t.Helper()

	schema = normalizeSchemaName(schema)
	for _, stmt := range []string{
		fmt.Sprintf("DROP SCHEMA IF EXISTS %s CASCADE", schema),
		fmt.Sprintf("CREATE SCHEMA %s", schema),
		fmt.Sprintf("GRANT ALL ON SCHEMA %s TO public", schema),
	} {
		_, err := db.Exec(stmt)
		require.NoError(t, err)
	}
}

func SeedSharedMiners(t *testing.T, db *sql.DB, minerIDs []string, at time.Time) {
	t.Helper()

	if at.IsZero() {
		at = time.Now().UTC()
	}

	seen := make(map[string]struct{}, len(minerIDs))
	ordered := make([]string, 0, len(minerIDs))
	for _, minerID := range minerIDs {
		if minerID == "" {
			continue
		}
		if _, ok := seen[minerID]; ok {
			continue
		}
		seen[minerID] = struct{}{}
		ordered = append(ordered, minerID)
	}
	sort.Strings(ordered)

	for index, minerID := range ordered {
		_, err := db.Exec(
			`
			INSERT INTO miners (
				address,
				name,
				registration_index,
				public_key,
				economic_unit_id,
				created_at,
				updated_at
			) VALUES ($1, $2, $3, $4, $5, $6, $7)
			ON CONFLICT (address) DO UPDATE SET
				name = EXCLUDED.name,
				public_key = EXCLUDED.public_key,
				economic_unit_id = EXCLUDED.economic_unit_id,
				updated_at = EXCLUDED.updated_at
			`,
			minerID,
			minerID,
			index+1,
			"pubkey:"+minerID,
			"eu:"+minerID,
			at,
			at,
		)
		require.NoError(t, err)
	}
}

func normalizeSchemaName(schema string) string {
	if !schemaNamePattern.MatchString(schema) {
		panic(fmt.Errorf("invalid schema name %q", schema))
	}
	return schema
}

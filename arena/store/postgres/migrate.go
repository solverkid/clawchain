package postgres

import (
	"database/sql"
	"embed"
	"errors"
	"fmt"
	"io/fs"
	"path"
	"sort"
	"strings"
)

//go:embed schema/*.sql
var schemaFiles embed.FS

func Migrate(db *sql.DB) error {
	if db == nil {
		return errors.New("db is required")
	}

	entries, err := fs.Glob(schemaFiles, "schema/*.sql")
	if err != nil {
		return fmt.Errorf("glob arena schema files: %w", err)
	}

	sort.Strings(entries)

	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("begin arena migration transaction: %w", err)
	}

	for _, entry := range entries {
		statement, err := schemaFiles.ReadFile(entry)
		if err != nil {
			_ = tx.Rollback()
			return fmt.Errorf("read %s: %w", entry, err)
		}

		sqlText := strings.TrimSpace(string(statement))
		if sqlText == "" {
			continue
		}

		if _, err := tx.Exec(sqlText); err != nil {
			_ = tx.Rollback()
			return fmt.Errorf("apply %s: %w", path.Base(entry), err)
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit arena migrations: %w", err)
	}

	return nil
}

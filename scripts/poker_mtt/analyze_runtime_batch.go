package main

import (
	"bufio"
	"context"
	"database/sql"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	_ "github.com/lib/pq"
)

type batchResult struct {
	BatchDir        string
	FileName        string
	TournamentID    string
	WaveID          string
	CompletedReason string
	WinnerMinerID   string
	Steps           int
	TablesSeen      map[string]struct{}
	PhaseCounts     map[string]int
	ActionCounts    map[string]int
	StatusCounts    map[string]int
}

type tournamentRow struct {
	WaveID            string
	State             string
	NoMultiplier      bool
	Voided            bool
	Cancelled         bool
	RoundNo           int
	LevelNo           int
	PlayersRegistered int
	PlayersRemaining  int
	ActiveTableCount  int
	FinalTableID      string
}

type tableSnapshotPayload struct {
	HandNumber int                         `json:"HandNumber"`
	HandClosed bool                        `json:"HandClosed"`
	PotMain    int64                       `json:"PotMain"`
	Seats      map[string]tableSeatPayload `json:"Seats"`
}

type tableSeatPayload struct {
	State             string `json:"State"`
	Stack             int64  `json:"Stack"`
	CommittedThisHand int64  `json:"CommittedThisHand"`
	WonThisHand       int64  `json:"WonThisHand"`
}

type snapshotStats struct {
	SnapshotCount          int
	NegativeStackCount     int
	NegativePotCount       int
	NegativeCommittedCount int
	LatestTotalChips       int64
	LatestActiveSeats      int
	LatestHandNumber       int
	LatestFound            bool
}

func main() {
	var dbURL string
	flag.StringVar(&dbURL, "db-url", firstNonEmpty(os.Getenv("ARENA_DATABASE_URL"), os.Getenv("ARENA_TEST_DATABASE_URL")), "Postgres connection string")
	flag.Parse()

	if dbURL == "" {
		fail("missing --db-url or ARENA_DATABASE_URL/ARENA_TEST_DATABASE_URL")
	}
	if flag.NArg() == 0 {
		fail("usage: go run ./scripts/poker_mtt/analyze_runtime_batch.go <batch-dir> [<batch-dir> ...]")
	}

	ctx := context.Background()
	db, err := sql.Open("postgres", dbURL)
	if err != nil {
		fail("open db: %v", err)
	}
	defer db.Close()
	if err := db.PingContext(ctx); err != nil {
		fail("ping db: %v", err)
	}

	results, err := scanBatchDirs(flag.Args())
	if err != nil {
		fail("scan batch dirs: %v", err)
	}
	if len(results) == 0 {
		fail("no tournament results found")
	}

	sort.Slice(results, func(i, j int) bool {
		if results[i].BatchDir != results[j].BatchDir {
			return results[i].BatchDir < results[j].BatchDir
		}
		return results[i].TournamentID < results[j].TournamentID
	})

	fmt.Println("# Arena Runtime Batch Analysis")
	for _, result := range results {
		row, err := loadTournamentRow(ctx, db, result.TournamentID)
		dbFound := true
		if err == sql.ErrNoRows {
			dbFound = false
		} else if err != nil {
			fail("load tournament %s: %v", result.TournamentID, err)
		}

		fmt.Printf("\n## %s\n", result.TournamentID)
		fmt.Printf("- batch: %s/%s\n", result.BatchDir, result.FileName)
		fmt.Printf("- wave: %s\n", firstNonEmpty(result.WaveID, row.WaveID))
		fmt.Printf("- completed_reason: %s\n", result.CompletedReason)
		fmt.Printf("- winner: %s\n", result.WinnerMinerID)
		fmt.Printf("- steps: %d\n", result.Steps)
		fmt.Printf("- log: tables_seen=%d phases=%s actions=%s statuses=%s\n",
			len(result.TablesSeen),
			formatCounts(result.PhaseCounts),
			formatCounts(result.ActionCounts),
			formatCounts(result.StatusCounts),
		)

		if !dbFound {
			fmt.Printf("- db: missing tournament row; log-only analysis\n")
			continue
		}

		entrants, err := countRows(ctx, db, `SELECT COUNT(*) FROM arena_entrant WHERE tournament_id = $1`, result.TournamentID)
		if err != nil {
			fail("count entrants %s: %v", result.TournamentID, err)
		}
		openDeadlines, err := countRows(ctx, db, `SELECT COUNT(*) FROM arena_action_deadline WHERE tournament_id = $1 AND status = 'open'`, result.TournamentID)
		if err != nil {
			fail("count open deadlines %s: %v", result.TournamentID, err)
		}
		totalDeadlines, err := countRows(ctx, db, `SELECT COUNT(*) FROM arena_action_deadline WHERE tournament_id = $1`, result.TournamentID)
		if err != nil {
			fail("count deadlines %s: %v", result.TournamentID, err)
		}
		timeoutActions, err := countRows(ctx, db, `SELECT COUNT(*) FROM arena_action WHERE tournament_id = $1 AND action_type = 'timeout'`, result.TournamentID)
		if err != nil {
			fail("count timeout actions %s: %v", result.TournamentID, err)
		}
		handClosedEvents, err := countRows(ctx, db, `SELECT COUNT(*) FROM arena_event_log WHERE tournament_id = $1 AND event_type = 'hand_closed'`, result.TournamentID)
		if err != nil {
			fail("count hand_closed %s: %v", result.TournamentID, err)
		}
		handSnapshots, err := countRows(ctx, db, `SELECT COUNT(*) FROM arena_hand_snapshot WHERE tournament_id = $1`, result.TournamentID)
		if err != nil {
			fail("count hand snapshots %s: %v", result.TournamentID, err)
		}
		reseatEvents, err := countRows(ctx, db, `SELECT COUNT(*) FROM arena_reseat_event WHERE tournament_id = $1`, result.TournamentID)
		if err != nil {
			fail("count reseat events %s: %v", result.TournamentID, err)
		}
		eliminationEvents, err := countRows(ctx, db, `SELECT COUNT(*) FROM arena_elimination_event WHERE tournament_id = $1`, result.TournamentID)
		if err != nil {
			fail("count elimination events %s: %v", result.TournamentID, err)
		}
		snapshotStats, err := loadSnapshotStats(ctx, db, result.TournamentID)
		if err != nil {
			fail("snapshot stats %s: %v", result.TournamentID, err)
		}

		expectedTotalChips := int64(entrants * 1000)
		finalChipStatus := "unknown"
		if snapshotStats.LatestFound {
			if snapshotStats.LatestTotalChips == expectedTotalChips {
				finalChipStatus = "ok"
			} else {
				finalChipStatus = fmt.Sprintf("mismatch:%d!=%d", snapshotStats.LatestTotalChips, expectedTotalChips)
			}
		}

		fmt.Printf("- state: %s round=%d level=%d registered=%d remaining=%d tables=%d final_table=%s\n", row.State, row.RoundNo, row.LevelNo, row.PlayersRegistered, row.PlayersRemaining, row.ActiveTableCount, row.FinalTableID)
		fmt.Printf("- flags: no_multiplier=%t voided=%t cancelled=%t\n", row.NoMultiplier, row.Voided, row.Cancelled)
		fmt.Printf("- deadlines: open=%d total=%d timeout_actions=%d\n", openDeadlines, totalDeadlines, timeoutActions)
		fmt.Printf("- audit: hand_closed_events=%d hand_snapshots=%d reseat_events=%d elimination_events=%d\n", handClosedEvents, handSnapshots, reseatEvents, eliminationEvents)
		fmt.Printf("- snapshots: total=%d negative_stack=%d negative_pot=%d negative_committed=%d latest_hand=%d latest_active_seats=%d final_chip_total=%s\n",
			snapshotStats.SnapshotCount,
			snapshotStats.NegativeStackCount,
			snapshotStats.NegativePotCount,
			snapshotStats.NegativeCommittedCount,
			snapshotStats.LatestHandNumber,
			snapshotStats.LatestActiveSeats,
			finalChipStatus,
		)
	}
}

func scanBatchDirs(dirs []string) ([]batchResult, error) {
	var results []batchResult
	for _, dir := range dirs {
		matches, err := filepath.Glob(filepath.Join(dir, "*.jsonl"))
		if err != nil {
			return nil, err
		}
		for _, path := range matches {
			result, ok, err := scanResultFile(path)
			if err != nil {
				return nil, err
			}
			if !ok {
				continue
			}
			result.BatchDir = filepath.Base(dir)
			result.FileName = filepath.Base(path)
			results = append(results, result)
		}
	}
	return results, nil
}

func scanResultFile(path string) (batchResult, bool, error) {
	file, err := os.Open(path)
	if err != nil {
		return batchResult{}, false, err
	}
	defer file.Close()

	result := batchResult{
		TablesSeen:   make(map[string]struct{}),
		PhaseCounts:  make(map[string]int),
		ActionCounts: make(map[string]int),
		StatusCounts: make(map[string]int),
	}
	found := false
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Bytes()
		var payload map[string]any
		if err := json.Unmarshal(line, &payload); err != nil {
			return batchResult{}, false, fmt.Errorf("%s: %w", path, err)
		}
		event, _ := payload["event"].(string)
		switch event {
		case "completed":
			found = true
			result.TournamentID, _ = payload["tournament_id"].(string)
			result.WaveID, _ = payload["wave_id"].(string)
			result.CompletedReason, _ = payload["completed_reason"].(string)
			result.WinnerMinerID, _ = payload["winner_miner_id"].(string)
			result.Steps = int(toFloat(payload["steps"]))
		case "wave_locked":
			if result.TournamentID == "" {
				result.TournamentID, _ = payload["tournament_id"].(string)
			}
			if result.WaveID == "" {
				result.WaveID, _ = payload["wave_id"].(string)
			}
		case "runner_step":
			if tableID, ok := payload["table_id"].(string); ok && tableID != "" {
				result.TablesSeen[tableID] = struct{}{}
			}
			if phase, ok := payload["current_phase"].(string); ok && phase != "" {
				result.PhaseCounts[phase]++
			}
			if action, ok := payload["action_type"].(string); ok && action != "" {
				result.ActionCounts[action]++
			}
			if status, ok := payload["status"].(string); ok && status != "" {
				result.StatusCounts[status]++
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return batchResult{}, false, err
	}
	return result, found, nil
}

func loadTournamentRow(ctx context.Context, db *sql.DB, tournamentID string) (tournamentRow, error) {
	var row tournamentRow
	err := db.QueryRowContext(ctx, `
		SELECT wave_id, tournament_state, no_multiplier, voided, cancelled, current_round_no, current_level_no,
		       players_registered, players_remaining, active_table_count, final_table_table_id
		  FROM arena_tournament
		 WHERE tournament_id = $1
	`, tournamentID).Scan(
		&row.WaveID,
		&row.State,
		&row.NoMultiplier,
		&row.Voided,
		&row.Cancelled,
		&row.RoundNo,
		&row.LevelNo,
		&row.PlayersRegistered,
		&row.PlayersRemaining,
		&row.ActiveTableCount,
		&row.FinalTableID,
	)
	return row, err
}

func loadSnapshotStats(ctx context.Context, db *sql.DB, tournamentID string) (snapshotStats, error) {
	rows, err := db.QueryContext(ctx, `
		SELECT payload
		  FROM arena_table_snapshot
		 WHERE tournament_id = $1
		 ORDER BY created_at ASC, stream_seq ASC
	`, tournamentID)
	if err != nil {
		return snapshotStats{}, err
	}
	defer rows.Close()

	var stats snapshotStats
	for rows.Next() {
		var raw []byte
		if err := rows.Scan(&raw); err != nil {
			return snapshotStats{}, err
		}
		var payload tableSnapshotPayload
		if err := json.Unmarshal(raw, &payload); err != nil {
			return snapshotStats{}, err
		}
		stats.SnapshotCount++
		if payload.PotMain < 0 {
			stats.NegativePotCount++
		}
		activeSeats := 0
		var totalChips int64
		for _, seat := range payload.Seats {
			if seat.Stack < 0 {
				stats.NegativeStackCount++
			}
			if seat.CommittedThisHand < 0 || seat.WonThisHand < 0 {
				stats.NegativeCommittedCount++
			}
			if seat.State != "eliminated" {
				activeSeats++
			}
			totalChips += seat.Stack
		}
		totalChips += payload.PotMain
		stats.LatestFound = true
		stats.LatestTotalChips = totalChips
		stats.LatestActiveSeats = activeSeats
		stats.LatestHandNumber = payload.HandNumber
	}
	if err := rows.Err(); err != nil {
		return snapshotStats{}, err
	}
	return stats, nil
}

func countRows(ctx context.Context, db *sql.DB, query string, args ...any) (int, error) {
	var count int
	err := db.QueryRowContext(ctx, query, args...).Scan(&count)
	return count, err
}

func toFloat(value any) float64 {
	switch typed := value.(type) {
	case float64:
		return typed
	case float32:
		return float64(typed)
	case int:
		return float64(typed)
	case int64:
		return float64(typed)
	case json.Number:
		number, _ := typed.Float64()
		return number
	default:
		return 0
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func formatCounts(values map[string]int) string {
	if len(values) == 0 {
		return "-"
	}
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	parts := make([]string, 0, len(keys))
	for _, key := range keys {
		parts = append(parts, key+"="+strconv.Itoa(values[key]))
	}
	return strings.Join(parts, ",")
}

func fail(format string, args ...any) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	os.Exit(1)
}

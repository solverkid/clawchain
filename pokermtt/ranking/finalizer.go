package ranking

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"
)

var ErrInvalidLiveSnapshot = errors.New("invalid poker mtt live ranking snapshot")
var ErrFinalizationBarrier = errors.New("poker mtt finalization barrier failed")

type Finalizer struct {
	PolicyBundleVersion     string
	FieldSizePolicy         string
	RequireTerminalOrQuiet  bool
	ExpectedEntrants        int
	ExpectedAlive           *int
	ExpectedDied            *int
	ExpectedWaitingOrNoShow *int
	ExpectedTotalChip       float64
	TotalChipDriftTolerance float64
}

func (f Finalizer) Finalize(snapshot LiveSnapshot) (Finalization, error) {
	return f.FinalizeWithRegistration(snapshot, RegistrationSnapshot{})
}

func (f Finalizer) FinalizeWithRegistration(snapshot LiveSnapshot, registration RegistrationSnapshot) (Finalization, error) {
	if strings.TrimSpace(snapshot.TournamentID) == "" {
		return Finalization{}, ErrInvalidLiveSnapshot
	}
	if snapshot.SourceMTTID == "" {
		snapshot.SourceMTTID = snapshot.TournamentID
	}
	if err := f.validateReadinessBarrier(snapshot); err != nil {
		return Finalization{}, err
	}

	decodedLiveSnapshots := make(map[string]map[string]any, len(snapshot.UserInfo))
	decodedSnapshots := make(map[string]map[string]any, len(snapshot.UserInfo)+len(registration.UserInfo))
	liveSnapshotFound := make(map[string]bool, len(snapshot.UserInfo))
	for memberID, raw := range snapshot.UserInfo {
		decoded, err := decodeJSONObject(raw)
		if err != nil {
			return Finalization{}, fmt.Errorf("%w: user snapshot %s: %v", ErrInvalidLiveSnapshot, memberID, err)
		}
		normalizedMemberID := normalizeMemberID(memberID, decoded)
		decodedLiveSnapshots[normalizedMemberID] = decoded
		decodedSnapshots[normalizedMemberID] = decoded
		liveSnapshotFound[normalizedMemberID] = true
	}

	decodedRegistrationSnapshots := make(map[string]map[string]any, len(registration.UserInfo))
	for memberID, raw := range registration.UserInfo {
		decoded, err := decodeJSONObject(raw)
		if err != nil {
			return Finalization{}, fmt.Errorf("%w: registration snapshot %s: %v", ErrInvalidLiveSnapshot, memberID, err)
		}
		normalizedMemberID := normalizeMemberID(memberID, decoded)
		if normalizedMemberID == "" {
			return Finalization{}, fmt.Errorf("%w: registration snapshot missing member id", ErrInvalidLiveSnapshot)
		}
		decodedRegistrationSnapshots[normalizedMemberID] = decoded
		if existing, ok := decodedSnapshots[normalizedMemberID]; ok {
			decodedSnapshots[normalizedMemberID] = mergeEntries(decoded, existing)
		} else {
			decodedSnapshots[normalizedMemberID] = decoded
		}
	}

	aliveRows := canonicalAliveRows(snapshot.Alive)
	snapshotForHash := snapshot
	snapshotForHash.Alive = aliveRows
	snapshotHash, err := hashCanonicalJSON(canonicalSnapshot(snapshotForHash, decodedLiveSnapshots, decodedRegistrationSnapshots))
	if err != nil {
		return Finalization{}, err
	}
	snapshotID := snapshotID(snapshot.TournamentID, snapshotHash)
	rowConfig := normalizeRowConfig{
		tournamentID:        snapshot.TournamentID,
		sourceMTTID:         snapshot.SourceMTTID,
		snapshotID:          snapshotID,
		snapshotHash:        snapshotHash,
		policyBundleVersion: f.PolicyBundleVersion,
		fieldSizePolicy:     f.fieldSizePolicy(),
	}

	rowCapacity := len(snapshot.UserInfo)
	if rowCapacity == 0 {
		rowCapacity = len(snapshot.Alive) + len(snapshot.Died)
	}
	rows := make([]FinalRankingRow, 0, rowCapacity)
	seenMembers := make(map[string]struct{}, len(snapshot.UserInfo)+len(snapshot.Alive))

	for aliveRankZeroBased, alive := range aliveRows {
		memberID := strings.TrimSpace(alive.Member)
		entry := decodedSnapshots[memberID]
		displayRank := aliveRankZeroBased + 1
		score := alive.Score
		row := normalizeRow(rowConfig, entry, memberID, StandingStatusAlive, &displayRank, liveSnapshotFound[memberID])
		row.DisplayRank = cloneRank(&displayRank)
		row.ZSetScore = &score
		row.SourceRank = strconv.Itoa(displayRank)
		row.SourceRankNumeric = true
		row.RankBasis = "alive_zset_score"
		row.RankTiebreaker = "zset_score_desc_member_id"
		if !liveSnapshotFound[memberID] && row.Chip == 0 {
			row.Chip = alive.Score
		}
		row.RankState = RankStateRanked
		rows = append(rows, row)
		if memberID != "" {
			seenMembers[memberID] = struct{}{}
		}
	}

	diedRank := len(snapshot.Alive)
	sameCount := 1
	var lastInternalRank *int
	fallbackRank := len(snapshot.Alive)
	for _, rawDiedEntry := range snapshot.Died {
		diedEntry, err := decodeJSONObject(rawDiedEntry)
		if err != nil {
			return Finalization{}, fmt.Errorf("%w: died entry: %v", ErrInvalidLiveSnapshot, err)
		}
		memberID := buildMemberID(diedEntry["userID"], diedEntry["entryNumber"])
		if memberID != "" {
			if _, ok := seenMembers[memberID]; ok {
				continue
			}
		}

		internalRank, internalRankOK := toInt(diedEntry["rank"])
		var displayRank int
		switch {
		case !internalRankOK:
			fallbackRank++
			displayRank = fallbackRank
		case lastInternalRank != nil && internalRank == *lastInternalRank:
			displayRank = diedRank
			sameCount++
		default:
			lastInternalRank = &internalRank
			diedRank += sameCount
			displayRank = diedRank
			sameCount = 1
			if fallbackRank < displayRank {
				fallbackRank = displayRank
			}
		}

		snapshotEntry := decodedSnapshots[memberID]
		mergedEntry := mergeEntries(snapshotEntry, diedEntry)
		row := normalizeRow(rowConfig, mergedEntry, memberID, StandingStatusDied, &displayRank, liveSnapshotFound[memberID])
		row.DisplayRank = cloneRank(&displayRank)
		row.SourceRank = sourceRankText(diedEntry["rank"])
		row.SourceRankNumeric = internalRankOK
		if internalRankOK {
			row.RankState = RankStateRanked
			row.RankBasis = "donor_died_rank"
			row.RankTiebreaker = "source_rank_display_then_start_chip_desc_member_id"
		} else {
			row.RankState = RankStateUnresolvedSnapshot
			row.RankBasis = "donor_died_rank_unresolved"
			row.RankTiebreaker = "unresolved_non_numeric_source_rank"
		}
		rows = append(rows, row)
		if memberID != "" {
			seenMembers[memberID] = struct{}{}
		}
	}

	pendingMemberIDs := make([]string, 0, len(decodedSnapshots))
	for memberID := range decodedSnapshots {
		if _, ok := seenMembers[memberID]; ok {
			continue
		}
		pendingMemberIDs = append(pendingMemberIDs, memberID)
	}
	sort.Slice(pendingMemberIDs, func(i, j int) bool {
		return memberSortKeyLess(pendingMemberIDs[i], pendingMemberIDs[j])
	})
	for _, memberID := range pendingMemberIDs {
		row := normalizeRow(rowConfig, decodedSnapshots[memberID], memberID, StandingStatusPending, nil, liveSnapshotFound[memberID])
		if isWaitingOrNoShow(row.StandUpStatus) {
			row.RankState = RankStateWaitingNoShow
			row.WaitingOrNoShow = true
		} else {
			row.RankState = RankStateUnresolvedSnapshot
		}
		rows = append(rows, row)
	}

	collapseDuplicateEconomicUnits(rows)
	assignUniquePayoutRanks(rows)
	if err := f.validateFinalRows(rows); err != nil {
		return Finalization{}, err
	}
	root, err := hashCanonicalJSON(canonicalRows(snapshot.TournamentID, snapshot.SourceMTTID, f.PolicyBundleVersion, rows))
	if err != nil {
		return Finalization{}, err
	}

	return Finalization{
		TournamentID:        snapshot.TournamentID,
		SourceMTTID:         snapshot.SourceMTTID,
		SnapshotID:          snapshotID,
		SnapshotHash:        snapshotHash,
		Root:                root,
		PolicyBundleVersion: f.PolicyBundleVersion,
		Rows:                rows,
	}, nil
}

func (f Finalizer) validateReadinessBarrier(snapshot LiveSnapshot) error {
	if !f.RequireTerminalOrQuiet {
		return nil
	}
	if snapshot.QuietPeriodSatisfied || isTerminalRuntimeState(snapshot.RuntimeState) {
		return nil
	}
	return fmt.Errorf("%w: runtime state %q is not terminal and quiet period is not satisfied", ErrFinalizationBarrier, snapshot.RuntimeState)
}

func (f Finalizer) validateFinalRows(rows []FinalRankingRow) error {
	if f.ExpectedEntrants > 0 && len(rows) != f.ExpectedEntrants {
		return fmt.Errorf("%w: entrant count mismatch expected=%d actual=%d", ErrFinalizationBarrier, f.ExpectedEntrants, len(rows))
	}
	if err := validateStatusCount("alive", f.ExpectedAlive, countRowsByStatus(rows, StandingStatusAlive)); err != nil {
		return err
	}
	if err := validateStatusCount("died", f.ExpectedDied, countRowsByStatus(rows, StandingStatusDied)); err != nil {
		return err
	}
	if err := validateStatusCount("waiting/no-show", f.ExpectedWaitingOrNoShow, countWaitingOrNoShowRows(rows)); err != nil {
		return err
	}
	if f.ExpectedTotalChip > 0 {
		totalChip := 0.0
		for _, row := range rows {
			totalChip += row.Chip
		}
		tolerance := f.TotalChipDriftTolerance
		if tolerance < 0 {
			tolerance = 0
		}
		if math.Abs(totalChip-f.ExpectedTotalChip) > tolerance {
			return fmt.Errorf("%w: total chip drift expected=%.6f actual=%.6f tolerance=%.6f", ErrFinalizationBarrier, f.ExpectedTotalChip, totalChip, tolerance)
		}
	}
	if err := validatePayoutRanks(rows); err != nil {
		return err
	}
	return nil
}

func validatePayoutRanks(rows []FinalRankingRow) error {
	ranks := make([]int, 0, len(rows))
	seenRanks := make(map[int]string, len(rows))
	for _, row := range rows {
		if row.RankState != RankStateRanked {
			if row.Rank != nil {
				return fmt.Errorf("%w: non-ranked row has payout rank member_id=%s rank_state=%s rank=%d", ErrFinalizationBarrier, row.MemberID, row.RankState, *row.Rank)
			}
			continue
		}
		if row.Rank == nil {
			return fmt.Errorf("%w: ranked row missing payout rank member_id=%s", ErrFinalizationBarrier, row.MemberID)
		}
		if existingMemberID, ok := seenRanks[*row.Rank]; ok {
			return fmt.Errorf("%w: duplicate payout rank rank=%d member_id=%s existing_member_id=%s", ErrFinalizationBarrier, *row.Rank, row.MemberID, existingMemberID)
		}
		seenRanks[*row.Rank] = row.MemberID
		ranks = append(ranks, *row.Rank)
	}
	sort.Ints(ranks)
	for index, rank := range ranks {
		expected := index + 1
		if rank != expected {
			return fmt.Errorf("%w: non-contiguous payout ranks expected=%d actual=%d", ErrFinalizationBarrier, expected, rank)
		}
	}
	return nil
}

func validateStatusCount(label string, expected *int, actual int) error {
	if expected == nil || *expected == actual {
		return nil
	}
	return fmt.Errorf("%w: %s count mismatch expected=%d actual=%d", ErrFinalizationBarrier, label, *expected, actual)
}

func countRowsByStatus(rows []FinalRankingRow, status StandingStatus) int {
	count := 0
	for _, row := range rows {
		if row.Status == status {
			count++
		}
	}
	return count
}

func countWaitingOrNoShowRows(rows []FinalRankingRow) int {
	count := 0
	for _, row := range rows {
		if row.WaitingOrNoShow || row.RankState == RankStateWaitingNoShow {
			count++
		}
	}
	return count
}

func (f Finalizer) fieldSizePolicy() string {
	if strings.TrimSpace(f.FieldSizePolicy) != "" {
		return strings.TrimSpace(f.FieldSizePolicy)
	}
	return "exclude_waiting_no_show_from_reward_field_size"
}

type normalizeRowConfig struct {
	tournamentID        string
	sourceMTTID         string
	snapshotID          string
	snapshotHash        string
	policyBundleVersion string
	fieldSizePolicy     string
}

func normalizeRow(config normalizeRowConfig, entry map[string]any, memberID string, status StandingStatus, rank *int, snapshotFound bool) FinalRankingRow {
	parsedUserID, parsedEntryNumber, parsedEntryOK := parseMemberID(memberID)
	userID := firstString(entry["userID"], entry["userId"], entry["sourceUserID"])
	if userID == "" {
		userID = parsedUserID
	}
	entryNumber, entryNumberOK := toInt(entry["entryNumber"])
	if !entryNumberOK && parsedEntryOK {
		entryNumber = parsedEntryNumber
		entryNumberOK = true
	}
	if !entryNumberOK {
		entryNumber = 0
	}
	if strings.TrimSpace(memberID) == "" {
		memberID = buildMemberID(userID, entryNumber)
	}

	startChip, startOK := toNumber(entry["startChip"])
	endChip, endOK := toNumber(entry["endChip"])
	if !endOK {
		endChip, endOK = toNumber(entry["chip"])
	}
	chipDelta := float64(0)
	if startOK && endOK {
		chipDelta = endChip - startChip
	}

	minerAddress := firstString(entry["minerAddress"], entry["miner_id"], entry["minerID"], entry["miner"])
	economicUnitID := firstString(entry["economicUnitID"], entry["economic_unit_id"], minerAddress)
	if economicUnitID == "" && userID != "" {
		economicUnitID = "source_user:" + userID
	}

	row := FinalRankingRow{
		ID:                   rowID(config.tournamentID, memberID),
		TournamentID:         config.tournamentID,
		SourceMTTID:          config.sourceMTTID,
		SourceUserID:         userID,
		MinerAddress:         minerAddress,
		EconomicUnitID:       economicUnitID,
		MemberID:             memberID,
		EntryNumber:          entryNumber,
		ReentryCount:         1,
		Rank:                 cloneRank(rank),
		DisplayRank:          cloneRank(rank),
		RankState:            RankStateUnresolvedSnapshot,
		Chip:                 endChip,
		ChipDelta:            chipDelta,
		DiedTime:             firstString(entry["diedTime"], entry["died_time"]),
		Bounty:               numberOrZero(entry["bounty"]),
		DefeatNum:            intOrZero(entry["defeatNum"], entry["defeat_num"]),
		FieldSizePolicy:      config.fieldSizePolicy,
		StandingSnapshotID:   config.snapshotID,
		StandingSnapshotHash: config.snapshotHash,
		PolicyBundleVersion:  config.policyBundleVersion,
		SnapshotFound:        snapshotFound,
		Status:               status,
		PlayerName:           firstString(entry["playerName"], entry["player_name"]),
		RoomID:               firstString(entry["roomID"], entry["room_id"]),
		StartChip:            startChip,
		StandUpStatus:        firstString(entry["standUpStatus"], entry["stand_up_status"]),
	}
	if row.StandUpStatus == "" {
		registrationStatus := firstString(entry["status"], entry["registrationStatus"], entry["registration_status"])
		if isWaitingOrNoShow(registrationStatus) {
			row.StandUpStatus = registrationStatus
		}
	}
	if isWaitingOrNoShow(row.StandUpStatus) {
		row.WaitingOrNoShow = true
	}
	return row
}

func collapseDuplicateEconomicUnits(rows []FinalRankingRow) {
	groups := make(map[string][]int, len(rows))
	for i, row := range rows {
		key := row.EconomicUnitID
		if key == "" {
			key = row.MemberID
		}
		groups[key] = append(groups[key], i)
	}
	for _, indexes := range groups {
		reentryCount := len(indexes)
		canonicalIndex := chooseCanonicalIndex(rows, indexes)
		for _, index := range indexes {
			rows[index].ReentryCount = reentryCount
			if len(indexes) > 1 && index != canonicalIndex && rows[index].RankState == RankStateRanked {
				rows[index].RankState = RankStateDuplicateEntryCollapsed
			}
		}
	}
}

func assignUniquePayoutRanks(rows []FinalRankingRow) {
	rankedIndexes := make([]int, 0, len(rows))
	diedDisplayRankCounts := make(map[int]int)
	for index := range rows {
		if rows[index].RankState != RankStateRanked {
			rows[index].Rank = nil
			continue
		}
		if rows[index].Status == StandingStatusDied && rows[index].DisplayRank != nil {
			diedDisplayRankCounts[*rows[index].DisplayRank]++
		}
		rankedIndexes = append(rankedIndexes, index)
	}
	sort.SliceStable(rankedIndexes, func(i, j int) bool {
		left := rows[rankedIndexes[i]]
		right := rows[rankedIndexes[j]]
		leftDisplayRank := rankForSort(left.DisplayRank, left.Rank)
		rightDisplayRank := rankForSort(right.DisplayRank, right.Rank)
		if leftDisplayRank != rightDisplayRank {
			return leftDisplayRank < rightDisplayRank
		}
		if left.Status == StandingStatusDied && right.Status == StandingStatusDied && left.StartChip != right.StartChip {
			return left.StartChip > right.StartChip
		}
		if left.Status != right.Status {
			return left.Status == StandingStatusAlive
		}
		return memberSortKeyLess(left.MemberID, right.MemberID)
	})
	for rankIndex, rowIndex := range rankedIndexes {
		rank := rankIndex + 1
		rows[rowIndex].Rank = &rank
		if rows[rowIndex].Status == StandingStatusDied && rows[rowIndex].DisplayRank != nil {
			if diedDisplayRankCounts[*rows[rowIndex].DisplayRank] > 1 {
				rows[rowIndex].RankTiebreaker = "source_rank_display_then_start_chip_desc_member_id"
			} else if rows[rowIndex].RankTiebreaker == "" || rows[rowIndex].RankTiebreaker == "source_rank_display_then_start_chip_desc_member_id" {
				rows[rowIndex].RankTiebreaker = "source_rank_display"
			}
		}
	}
}

func rankForSort(values ...*int) int {
	for _, value := range values {
		if value != nil {
			return *value
		}
	}
	return int(^uint(0) >> 1)
}

func chooseCanonicalIndex(rows []FinalRankingRow, indexes []int) int {
	best := indexes[0]
	for _, index := range indexes[1:] {
		if betterCanonicalRow(rows[index], rows[best]) {
			best = index
		}
	}
	return best
}

func betterCanonicalRow(candidate FinalRankingRow, current FinalRankingRow) bool {
	if candidate.RankState == RankStateRanked && current.RankState != RankStateRanked {
		return true
	}
	if candidate.RankState != RankStateRanked && current.RankState == RankStateRanked {
		return false
	}
	if candidate.Rank != nil && current.Rank != nil && *candidate.Rank != *current.Rank {
		return *candidate.Rank < *current.Rank
	}
	if candidate.Rank != nil && current.Rank == nil {
		return true
	}
	if candidate.Rank == nil && current.Rank != nil {
		return false
	}
	if candidate.EntryNumber != current.EntryNumber {
		return candidate.EntryNumber > current.EntryNumber
	}
	return candidate.MemberID < current.MemberID
}

func decodeJSONObject(raw string) (map[string]any, error) {
	var decoded map[string]any
	if err := json.Unmarshal([]byte(raw), &decoded); err != nil {
		return nil, err
	}
	if decoded == nil {
		return nil, errors.New("expected JSON object")
	}
	return decoded, nil
}

func mergeEntries(snapshotEntry map[string]any, eventEntry map[string]any) map[string]any {
	merged := make(map[string]any, len(snapshotEntry)+len(eventEntry))
	for key, value := range snapshotEntry {
		merged[key] = value
	}
	for key, value := range eventEntry {
		merged[key] = value
	}
	return merged
}

func parseMemberID(memberID string) (string, int, bool) {
	userID, entryPart, found := strings.Cut(strings.TrimSpace(memberID), ":")
	if !found {
		return normalizeString(userID), 0, false
	}
	entryNumber, ok := toInt(entryPart)
	return normalizeString(userID), entryNumber, ok
}

func buildMemberID(userID any, entryNumber any) string {
	normalizedUserID := normalizeString(userID)
	normalizedEntryNumber, ok := toInt(entryNumber)
	if normalizedUserID == "" || !ok {
		return ""
	}
	return fmt.Sprintf("%s:%d", normalizedUserID, normalizedEntryNumber)
}

func normalizeMemberID(memberID string, entry map[string]any) string {
	normalized := strings.TrimSpace(memberID)
	if normalized != "" {
		return normalized
	}
	return buildMemberID(entry["userID"], entry["entryNumber"])
}

func memberSortKeyLess(left string, right string) bool {
	leftUserID, leftEntryNumber, leftEntryOK := parseMemberID(left)
	rightUserID, rightEntryNumber, rightEntryOK := parseMemberID(right)
	leftUserOrder, leftUserOK := toInt(leftUserID)
	rightUserOrder, rightUserOK := toInt(rightUserID)
	switch {
	case leftUserOK && rightUserOK && leftUserOrder != rightUserOrder:
		return leftUserOrder < rightUserOrder
	case leftUserOK != rightUserOK:
		return leftUserOK
	case leftUserID != rightUserID:
		return leftUserID < rightUserID
	case leftEntryOK && rightEntryOK && leftEntryNumber != rightEntryNumber:
		return leftEntryNumber < rightEntryNumber
	case leftEntryOK != rightEntryOK:
		return leftEntryOK
	default:
		return left < right
	}
}

func canonicalAliveRows(rows []ZMember) []ZMember {
	canonical := append([]ZMember(nil), rows...)
	sort.SliceStable(canonical, func(i, j int) bool {
		if canonical[i].Score != canonical[j].Score {
			return canonical[i].Score > canonical[j].Score
		}
		return memberSortKeyLess(canonical[i].Member, canonical[j].Member)
	})
	return canonical
}

func firstString(values ...any) string {
	for _, value := range values {
		if normalized := normalizeString(value); normalized != "" {
			return normalized
		}
	}
	return ""
}

func normalizeString(value any) string {
	switch typed := value.(type) {
	case nil:
		return ""
	case string:
		return strings.TrimSpace(typed)
	case []byte:
		return strings.TrimSpace(string(typed))
	default:
		return strings.TrimSpace(fmt.Sprint(typed))
	}
}

func toInt(value any) (int, bool) {
	switch typed := value.(type) {
	case nil:
		return 0, false
	case bool:
		if typed {
			return 1, true
		}
		return 0, true
	case int:
		return typed, true
	case int64:
		return int(typed), true
	case float64:
		return int(typed), true
	case float32:
		return int(typed), true
	case json.Number:
		integer, err := typed.Int64()
		if err == nil {
			return int(integer), true
		}
		number, err := strconv.ParseFloat(string(typed), 64)
		if err != nil {
			return 0, false
		}
		return int(number), true
	default:
		text := strings.TrimSpace(fmt.Sprint(typed))
		if text == "" {
			return 0, false
		}
		integer, err := strconv.Atoi(text)
		if err == nil {
			return integer, true
		}
		number, err := strconv.ParseFloat(text, 64)
		if err != nil {
			return 0, false
		}
		return int(number), true
	}
}

func toNumber(value any) (float64, bool) {
	switch typed := value.(type) {
	case nil:
		return 0, false
	case bool:
		if typed {
			return 1, true
		}
		return 0, true
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	case float64:
		return typed, true
	case float32:
		return float64(typed), true
	case json.Number:
		number, err := typed.Float64()
		return number, err == nil
	default:
		text := strings.TrimSpace(fmt.Sprint(typed))
		if text == "" {
			return 0, false
		}
		number, err := strconv.ParseFloat(text, 64)
		return number, err == nil
	}
}

func numberOrZero(value any) float64 {
	number, ok := toNumber(value)
	if !ok {
		return 0
	}
	return number
}

func intOrZero(values ...any) int {
	for _, value := range values {
		integer, ok := toInt(value)
		if ok {
			return integer
		}
	}
	return 0
}

func cloneRank(rank *int) *int {
	if rank == nil {
		return nil
	}
	value := *rank
	return &value
}

func isWaitingOrNoShow(status string) bool {
	normalized := strings.ToLower(strings.TrimSpace(status))
	switch normalized {
	case "waiting", "wait", "no_show", "noshow", "no-show", "not_joined":
		return true
	default:
		return false
	}
}

func isTerminalRuntimeState(state string) bool {
	normalized := strings.ToLower(strings.TrimSpace(state))
	switch normalized {
	case "finished", "complete", "completed", "closed", "terminal", "settled":
		return true
	default:
		return false
	}
}

func sourceRankText(value any) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(value))
}

func rowID(tournamentID string, memberID string) string {
	return "poker_mtt_final_ranking:" + tournamentID + ":" + memberID
}

func snapshotID(tournamentID string, hash string) string {
	trimmed := strings.TrimPrefix(hash, "sha256:")
	if len(trimmed) > 16 {
		trimmed = trimmed[:16]
	}
	return "poker_mtt_standing_snapshot:" + tournamentID + ":" + trimmed
}

type canonicalSnapshotPayload struct {
	TournamentID         string              `json:"tournament_id"`
	SourceMTTID          string              `json:"source_mtt_id"`
	GameType             string              `json:"game_type"`
	RuntimeState         string              `json:"runtime_state,omitempty"`
	QuietPeriodSatisfied bool                `json:"quiet_period_satisfied,omitempty"`
	Keys                 RedisKeys           `json:"keys"`
	UserInfo             []canonicalKeyValue `json:"user_info"`
	Registration         []canonicalKeyValue `json:"registration,omitempty"`
	Alive                []ZMember           `json:"alive"`
	Died                 []string            `json:"died"`
}

type canonicalKeyValue struct {
	Key   string         `json:"key"`
	Value map[string]any `json:"value"`
}

func canonicalSnapshot(
	snapshot LiveSnapshot,
	decodedLiveSnapshots map[string]map[string]any,
	decodedRegistrationSnapshots map[string]map[string]any,
) canonicalSnapshotPayload {
	userInfo := canonicalKeyValues(decodedLiveSnapshots)
	registration := canonicalKeyValues(decodedRegistrationSnapshots)
	return canonicalSnapshotPayload{
		TournamentID:         snapshot.TournamentID,
		SourceMTTID:          snapshot.SourceMTTID,
		GameType:             snapshot.GameType,
		RuntimeState:         snapshot.RuntimeState,
		QuietPeriodSatisfied: snapshot.QuietPeriodSatisfied,
		Keys:                 snapshot.Keys,
		UserInfo:             userInfo,
		Registration:         registration,
		Alive:                canonicalAliveRows(snapshot.Alive),
		Died:                 append([]string(nil), snapshot.Died...),
	}
}

func canonicalKeyValues(values map[string]map[string]any) []canonicalKeyValue {
	items := make([]canonicalKeyValue, 0, len(values))
	for key, value := range values {
		items = append(items, canonicalKeyValue{Key: key, Value: value})
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].Key < items[j].Key
	})
	return items
}

type canonicalRowsPayload struct {
	TournamentID        string            `json:"tournament_id"`
	SourceMTTID         string            `json:"source_mtt_id"`
	PolicyBundleVersion string            `json:"policy_bundle_version"`
	Rows                []FinalRankingRow `json:"rows"`
}

func canonicalRows(tournamentID string, sourceMTTID string, policyBundleVersion string, rows []FinalRankingRow) canonicalRowsPayload {
	canonical := append([]FinalRankingRow(nil), rows...)
	for index := range canonical {
		canonical[index].RoomID = ""
		canonical[index].StandingSnapshotID = ""
		canonical[index].StandingSnapshotHash = ""
		canonical[index].EvidenceRoot = ""
		canonical[index].EvidenceState = ""
	}
	return canonicalRowsPayload{
		TournamentID:        tournamentID,
		SourceMTTID:         sourceMTTID,
		PolicyBundleVersion: policyBundleVersion,
		Rows:                canonical,
	}
}

func hashCanonicalJSON(value any) (string, error) {
	payload, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

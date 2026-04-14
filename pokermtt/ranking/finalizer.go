package ranking

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

var ErrInvalidLiveSnapshot = errors.New("invalid poker mtt live ranking snapshot")

type Finalizer struct {
	PolicyBundleVersion string
	FieldSizePolicy     string
}

func (f Finalizer) Finalize(snapshot LiveSnapshot) (Finalization, error) {
	if strings.TrimSpace(snapshot.TournamentID) == "" {
		return Finalization{}, ErrInvalidLiveSnapshot
	}
	if snapshot.SourceMTTID == "" {
		snapshot.SourceMTTID = snapshot.TournamentID
	}

	decodedSnapshots := make(map[string]map[string]any, len(snapshot.UserInfo))
	for memberID, raw := range snapshot.UserInfo {
		decoded, err := decodeJSONObject(raw)
		if err != nil {
			return Finalization{}, fmt.Errorf("%w: user snapshot %s: %v", ErrInvalidLiveSnapshot, memberID, err)
		}
		decodedSnapshots[strings.TrimSpace(memberID)] = decoded
	}

	snapshotHash, err := hashCanonicalJSON(canonicalSnapshot(snapshot, decodedSnapshots))
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

	for aliveRankZeroBased, alive := range snapshot.Alive {
		memberID := strings.TrimSpace(alive.Member)
		entry, found := decodedSnapshots[memberID]
		displayRank := aliveRankZeroBased + 1
		score := alive.Score
		row := normalizeRow(rowConfig, entry, memberID, StandingStatusAlive, &displayRank, found)
		row.ZSetScore = &score
		row.SourceRankNumeric = true
		if !found && row.Chip == 0 {
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

		snapshotEntry, found := decodedSnapshots[memberID]
		mergedEntry := mergeEntries(snapshotEntry, diedEntry)
		row := normalizeRow(rowConfig, mergedEntry, memberID, StandingStatusDied, &displayRank, found)
		row.SourceRank = sourceRankText(diedEntry["rank"])
		row.SourceRankNumeric = internalRankOK
		if internalRankOK {
			row.RankState = RankStateRanked
		} else {
			row.RankState = RankStateUnresolvedSnapshot
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
		row := normalizeRow(rowConfig, decodedSnapshots[memberID], memberID, StandingStatusPending, nil, true)
		if isWaitingOrNoShow(row.StandUpStatus) {
			row.RankState = RankStateWaitingNoShow
			row.WaitingOrNoShow = true
		} else {
			row.RankState = RankStateUnresolvedSnapshot
		}
		rows = append(rows, row)
	}

	collapseDuplicateEconomicUnits(rows)
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
	TournamentID string              `json:"tournament_id"`
	SourceMTTID  string              `json:"source_mtt_id"`
	GameType     string              `json:"game_type"`
	Keys         RedisKeys           `json:"keys"`
	UserInfo     []canonicalKeyValue `json:"user_info"`
	Alive        []ZMember           `json:"alive"`
	Died         []string            `json:"died"`
}

type canonicalKeyValue struct {
	Key   string         `json:"key"`
	Value map[string]any `json:"value"`
}

func canonicalSnapshot(snapshot LiveSnapshot, decodedSnapshots map[string]map[string]any) canonicalSnapshotPayload {
	userInfo := make([]canonicalKeyValue, 0, len(decodedSnapshots))
	for key, value := range decodedSnapshots {
		userInfo = append(userInfo, canonicalKeyValue{Key: key, Value: value})
	}
	sort.Slice(userInfo, func(i, j int) bool {
		return userInfo[i].Key < userInfo[j].Key
	})
	return canonicalSnapshotPayload{
		TournamentID: snapshot.TournamentID,
		SourceMTTID:  snapshot.SourceMTTID,
		GameType:     snapshot.GameType,
		Keys:         snapshot.Keys,
		UserInfo:     userInfo,
		Alive:        append([]ZMember(nil), snapshot.Alive...),
		Died:         append([]string(nil), snapshot.Died...),
	}
}

type canonicalRowsPayload struct {
	TournamentID        string            `json:"tournament_id"`
	SourceMTTID         string            `json:"source_mtt_id"`
	PolicyBundleVersion string            `json:"policy_bundle_version"`
	Rows                []FinalRankingRow `json:"rows"`
}

func canonicalRows(tournamentID string, sourceMTTID string, policyBundleVersion string, rows []FinalRankingRow) canonicalRowsPayload {
	return canonicalRowsPayload{
		TournamentID:        tournamentID,
		SourceMTTID:         sourceMTTID,
		PolicyBundleVersion: policyBundleVersion,
		Rows:                append([]FinalRankingRow(nil), rows...),
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

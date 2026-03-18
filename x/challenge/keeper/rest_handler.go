package keeper

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	storetypes "cosmossdk.io/store/types"
	"github.com/gorilla/mux"
	sdk "github.com/cosmos/cosmos-sdk/types"
	bankkeeper "github.com/cosmos/cosmos-sdk/x/bank/keeper"

	challengetypes "github.com/clawchain/clawchain/x/challenge/types"
)

// RESTHandler REST API 处理器
type RESTHandler struct {
	keeper     *Keeper
	bankKeeper *bankkeeper.BaseKeeper
	storeGetter func() storetypes.CommitMultiStore
}

// NewRESTHandler 创建 REST handler
func NewRESTHandler(k *Keeper, bk *bankkeeper.BaseKeeper, storeGetter func() storetypes.CommitMultiStore) *RESTHandler {
	return &RESTHandler{
		keeper:      k,
		bankKeeper:  bk,
		storeGetter: storeGetter,
	}
}

// RegisterRoutes 注册路由（在 app.go 调用）
func (h *RESTHandler) RegisterRoutes(router *mux.Router) {
	router.HandleFunc("/clawchain/challenges/pending", h.GetPendingChallenges).Methods("GET")
	router.HandleFunc("/clawchain/challenge/submit", h.SubmitAnswer).Methods("POST")
	router.HandleFunc("/clawchain/miner/register", h.RegisterMiner).Methods("POST")
	router.HandleFunc("/clawchain/miner/{address}", h.GetMinerInfo).Methods("GET")
	router.HandleFunc("/clawchain/miner/{address}/stats", h.GetMinerStats).Methods("GET")
	router.HandleFunc("/clawchain/stats", h.GetChainStats).Methods("GET")
}

// getStore 获取 KV store
func (h *RESTHandler) getStore() storetypes.KVStore {
	cms := h.storeGetter()
	return cms.GetKVStore(h.keeper.storeKey)
}

// GetPendingChallenges GET /clawchain/challenges/pending
func (h *RESTHandler) GetPendingChallenges(w http.ResponseWriter, r *http.Request) {
	store := h.getStore()

	var challenges []challengetypes.Challenge
	iter := storetypes.KVStorePrefixIterator(store, []byte("challenge:"))
	defer iter.Close()

	for ; iter.Valid(); iter.Next() {
		var ch challengetypes.Challenge
		if err := json.Unmarshal(iter.Value(), &ch); err != nil {
			continue
		}
		// 只返回待处理的挑战
		if ch.Status == challengetypes.ChallengeStatusPending || ch.Status == challengetypes.ChallengeStatusCommit {
			challenges = append(challenges, ch)
		}
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"challenges": challenges,
	})
}

// SubmitAnswerRequest 提交答案请求
type SubmitAnswerRequest struct {
	ChallengeID string `json:"challenge_id"`
	MinerAddr   string `json:"miner_address"`
	Answer      string `json:"answer"`
}

// SubmitAnswer POST /clawchain/challenge/submit
func (h *RESTHandler) SubmitAnswer(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}

	var req SubmitAnswerRequest
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, "invalid JSON", http.StatusBadRequest)
		return
	}

	store := h.getStore()
	
	// 检查矿工是否已注册
	minerKey := []byte(fmt.Sprintf("miner:%s", req.MinerAddr))
	minerBz := store.Get(minerKey)
	if minerBz == nil {
		http.Error(w, "miner not registered", http.StatusForbidden)
		return
	}
	
	// 检查矿工状态
	var minerData map[string]interface{}
	json.Unmarshal(minerBz, &minerData)
	if status, ok := minerData["status"].(string); ok && status != "active" {
		http.Error(w, "miner not active", http.StatusForbidden)
		return
	}

	key := []byte(fmt.Sprintf("challenge:%s", req.ChallengeID))
	bz := store.Get(key)
	if bz == nil {
		http.Error(w, "challenge not found", http.StatusNotFound)
		return
	}

	var ch challengetypes.Challenge
	json.Unmarshal(bz, &ch)
	
	// 检查挑战是否过期（创建后 200 blocks 内有效 ≈ 2 epoch @6s = 20 分钟）
	cms := h.storeGetter()
	currentHeight := cms.LatestVersion()
	if os.Getenv("CLAWCHAIN_DEV") != "1" {
		// 生产模式才检查过期（测试模式跳过过期检查）
		if currentHeight-ch.CreatedHeight > 200 {
			ch.Status = challengetypes.ChallengeStatusExpired
			bz, _ := json.Marshal(ch)
			store.Set(key, bz)
			http.Error(w, "challenge expired", http.StatusGone)
			return
		}
	}

	// 验证矿工是否被分配（公开挑战 Assignees 为空，任何人可参与）
	if len(ch.Assignees) > 0 {
		assigned := false
		for _, a := range ch.Assignees {
			if a == req.MinerAddr {
				assigned = true
				break
			}
		}
		if !assigned {
			http.Error(w, "not assigned to this challenge", http.StatusForbidden)
			return
		}
	}
	
	// 防重复提交：检查该矿工是否已提交答案
	if ch.Reveals == nil {
		ch.Reveals = make(map[string]string)
	}
	if _, exists := ch.Reveals[req.MinerAddr]; exists {
		http.Error(w, "already submitted", http.StatusConflict)
		return
	}

	// 记录答案（不立即判断对错）
	ch.Reveals[req.MinerAddr] = req.Answer
	ch.Status = challengetypes.ChallengeStatusReveal

	submissionCount := len(ch.Reveals)
	requiredSubmissions := 3 // 需要 3 个矿工提交

	// Dev mode: 环境变量 CLAWCHAIN_DEV=1 时允许单矿工结算
	if os.Getenv("CLAWCHAIN_DEV") == "1" {
		requiredSubmissions = 1
	}

	// 检查是否达到 3 个提交，触发验证
	if submissionCount >= requiredSubmissions {
		// 执行多数一致验证
		answerVotes := make(map[string][]string) // answer -> []minerAddr
		for minerAddr, answer := range ch.Reveals {
			normalizedAnswer := strings.TrimSpace(strings.ToLower(answer))
			answerVotes[normalizedAnswer] = append(answerVotes[normalizedAnswer], minerAddr)
		}

		// 找到多数答案（至少 2/3）
		var majorityAnswer string
		var majorityMiners []string
		maxVotes := 0
		for answer, miners := range answerVotes {
			if len(miners) > maxVotes {
				maxVotes = len(miners)
				majorityAnswer = answer
				majorityMiners = miners
			}
		}

		// 判断是否达到多数（至少 2 票，dev mode 下 1 票即可）
		minMajority := 2
		if os.Getenv("CLAWCHAIN_DEV") == "1" {
			minMajority = 1
		}
		if maxVotes >= minMajority {
			ch.Status = challengetypes.ChallengeStatusComplete
			rewardAmount := h.keeper.GetBlockReward(currentHeight)

			// 记录奖励到矿工统计并写入 pending_reward 供 EndBlock 转账
			for _, minerAddr := range majorityMiners {
				// 写入 pending_reward 供 EndBlock 的 ProcessPendingRewards 处理
				pendingKey := []byte(fmt.Sprintf("pending_reward:%d:%s:%s", currentHeight, req.ChallengeID, minerAddr))
				pendingReward := map[string]interface{}{
					"challenge_id": req.ChallengeID,
					"miner_addr":   minerAddr,
					"amount":       rewardAmount,
					"height":       currentHeight,
				}
				pendingBz, _ := json.Marshal(pendingReward)
				store.Set(pendingKey, pendingBz)

				// 更新矿工统计
				mKey := []byte(fmt.Sprintf("miner:%s", minerAddr))
				mBz := store.Get(mKey)
				if mBz != nil {
					var mData map[string]interface{}
					if json.Unmarshal(mBz, &mData) == nil {
						completed := int64(0)
						totalRewards := int64(0)
						if v, ok := mData["challenges_completed"].(float64); ok {
							completed = int64(v)
						}
						if v, ok := mData["total_rewards"].(float64); ok {
							totalRewards = int64(v)
						}
						mData["challenges_completed"] = completed + 1
						mData["total_rewards"] = totalRewards + rewardAmount
						mBz, _ = json.Marshal(mData)
						store.Set(mKey, mBz)
					}
				}
			}

			// 惩罚不一致的矿工（扣声誉分）
			for minerAddr, answer := range ch.Reveals {
				normalizedAnswer := strings.TrimSpace(strings.ToLower(answer))
				if normalizedAnswer != majorityAnswer {
					// 更新矿工失败记录
					minerKey := []byte(fmt.Sprintf("miner:%s", minerAddr))
					minerBz := store.Get(minerKey)
					if minerBz != nil {
						var minerData map[string]interface{}
						json.Unmarshal(minerBz, &minerData)
						
						failed := int64(0)
						if v, ok := minerData["challenges_failed"].(float64); ok {
							failed = int64(v)
						}
						minerData["challenges_failed"] = failed + 1
						
						minerBz, _ = json.Marshal(minerData)
						store.Set(minerKey, minerBz)
					}
				}
			}
		}
	}

	bz, _ = json.Marshal(ch)
	store.Set(key, bz)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success":            true,
		"submission_count":   submissionCount,
		"required_submissions": requiredSubmissions,
		"status":             ch.Status,
		"message":            "answer recorded, waiting for other miners to submit",
	})
}

// RegisterMinerRequest 注册矿工请求
type RegisterMinerRequest struct {
	Address string `json:"address"`
	Name    string `json:"name"`
}

// RegisterMiner POST /clawchain/miner/register
func (h *RESTHandler) RegisterMiner(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}

	var req RegisterMinerRequest
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, "invalid JSON", http.StatusBadRequest)
		return
	}

	// 验证地址格式
	if _, err := sdk.AccAddressFromBech32(req.Address); err != nil {
		http.Error(w, "invalid address format", http.StatusBadRequest)
		return
	}

	store := h.getStore()

	// 检查是否已注册
	minerKey := []byte(fmt.Sprintf("miner:%s", req.Address))
	if store.Has(minerKey) {
		http.Error(w, "miner already registered", http.StatusConflict)
		return
	}

	// 存储矿工信息
	minerData := map[string]interface{}{
		"address":            req.Address,
		"name":               req.Name,
		"status":             "active",
		"registered_height":  h.storeGetter().LatestVersion(),
		"challenges_completed": 0,
		"total_rewards":      0,
		"challenges_failed":  0,
	}
	bz, _ := json.Marshal(minerData)
	store.Set(minerKey, bz)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success": true,
		"message": "miner registered successfully (note: minimum 100 CLAW = 100,000,000 uclaw stake required for active mining)",
		"address": req.Address,
	})
}

// GetMinerInfo GET /clawchain/miner/{address}
func (h *RESTHandler) GetMinerInfo(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	address := vars["address"]
	
	if address == "" {
		http.Error(w, "address required", http.StatusBadRequest)
		return
	}

	store := h.getStore()
	
	minerKey := []byte(fmt.Sprintf("miner:%s", address))
	bz := store.Get(minerKey)
	if bz == nil {
		http.Error(w, "miner not found", http.StatusNotFound)
		return
	}

	var minerData map[string]interface{}
	json.Unmarshal(bz, &minerData)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(minerData)
}

// GetMinerStats GET /clawchain/miner/{address}/stats
func (h *RESTHandler) GetMinerStats(w http.ResponseWriter, r *http.Request) {
	vars := mux.Vars(r)
	address := vars["address"]
	
	if address == "" {
		http.Error(w, "address required", http.StatusBadRequest)
		return
	}

	store := h.getStore()
	
	minerKey := []byte(fmt.Sprintf("miner:%s", address))
	bz := store.Get(minerKey)
	if bz == nil {
		http.Error(w, "miner not found", http.StatusNotFound)
		return
	}

	var minerData map[string]interface{}
	json.Unmarshal(bz, &minerData)
	
	completed := int64(0)
	failed := int64(0)
	totalRewards := int64(0)
	
	if v, ok := minerData["challenges_completed"].(float64); ok {
		completed = int64(v)
	}
	if v, ok := minerData["challenges_failed"].(float64); ok {
		failed = int64(v)
	}
	if v, ok := minerData["total_rewards"].(float64); ok {
		totalRewards = int64(v)
	}
	
	total := completed + failed
	successRate := float64(0)
	if total > 0 {
		successRate = float64(completed) / float64(total) * 100
	}

	stats := map[string]interface{}{
		"address":             address,
		"challenges_completed": completed,
		"challenges_failed":    failed,
		"total_challenges":     total,
		"success_rate":         fmt.Sprintf("%.2f%%", successRate),
		"total_rewards":        totalRewards,
		"total_rewards_uclaw":  fmt.Sprintf("%d uclaw", totalRewards),
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(stats)
}

// GetChainStats GET /clawchain/stats
func (h *RESTHandler) GetChainStats(w http.ResponseWriter, r *http.Request) {
	store := h.getStore()
	
	// 统计挑战总数
	totalChallenges := 0
	completedChallenges := 0
	iter := storetypes.KVStorePrefixIterator(store, []byte("challenge:"))
	defer iter.Close()
	for ; iter.Valid(); iter.Next() {
		totalChallenges++
		var ch challengetypes.Challenge
		if err := json.Unmarshal(iter.Value(), &ch); err == nil {
			if ch.Status == challengetypes.ChallengeStatusComplete || ch.Status == challengetypes.ChallengeStatusReveal {
				completedChallenges++
			}
		}
	}
	
	// 统计活跃矿工数和总奖励
	activeMiners := 0
	totalRewardsPaid := int64(0)
	minerIter := storetypes.KVStorePrefixIterator(store, []byte("miner:"))
	defer minerIter.Close()
	for ; minerIter.Valid(); minerIter.Next() {
		var minerData map[string]interface{}
		if err := json.Unmarshal(minerIter.Value(), &minerData); err == nil {
			if status, ok := minerData["status"].(string); ok && status == "active" {
				activeMiners++
			}
			if rewards, ok := minerData["total_rewards"].(float64); ok {
				totalRewardsPaid += int64(rewards)
			}
		}
	}
	
	currentHeight := h.storeGetter().LatestVersion()
	currentReward := h.keeper.GetBlockReward(currentHeight)

	stats := map[string]interface{}{
		"total_challenges":     totalChallenges,
		"completed_challenges": completedChallenges,
		"active_miners":        activeMiners,
		"total_rewards_paid":   totalRewardsPaid,
		"total_rewards_uclaw":  fmt.Sprintf("%d uclaw", totalRewardsPaid),
		"current_block_height": currentHeight,
		"current_block_reward": currentReward,
		"current_reward_uclaw": fmt.Sprintf("%d uclaw", currentReward),
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(stats)
}

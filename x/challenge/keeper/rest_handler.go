package keeper

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/gorilla/mux"
	storetypes "cosmossdk.io/store/types"
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
	key := []byte(fmt.Sprintf("challenge:%s", req.ChallengeID))
	bz := store.Get(key)
	if bz == nil {
		http.Error(w, "challenge not found", http.StatusNotFound)
		return
	}

	var ch challengetypes.Challenge
	json.Unmarshal(bz, &ch)

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

	// 检查答案是否正确
	correct := false
	if ch.ExpectedAnswer != "" {
		correct = strings.TrimSpace(req.Answer) == strings.TrimSpace(ch.ExpectedAnswer)
	} else {
		// 简化：无标准答案的也算对
		correct = true
	}

	// 更新挑战
	if ch.Reveals == nil {
		ch.Reveals = make(map[string]string)
	}
	ch.Reveals[req.MinerAddr] = req.Answer
	ch.Status = challengetypes.ChallengeStatusReveal

	bz, _ = json.Marshal(ch)
	store.Set(key, bz)

	// 奖励金额
	rewardAmount := int64(1000)
	reward := sdk.NewCoins(sdk.NewInt64Coin("uclaw", rewardAmount))

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success": true,
		"correct": correct,
		"reward":  reward.String(),
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

	store := h.getStore()

	// 简单存储矿工信息
	minerKey := []byte(fmt.Sprintf("miner:%s", req.Address))
	minerData := map[string]interface{}{
		"address": req.Address,
		"name":    req.Name,
		"status":  "active",
	}
	bz, _ := json.Marshal(minerData)
	store.Set(minerKey, bz)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"success": true,
		"message": "miner registered",
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

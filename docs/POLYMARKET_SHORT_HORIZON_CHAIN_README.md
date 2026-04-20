# Polymarket Short-Horizon Forecast Chain README

## 1. 文档范围

这份文档只讲当前 repo 里已经打通的 Polymarket 短时预测链路，范围限定为：

- BTC / ETH 的短周期预测任务发布
- Polymarket + Binance 实时快照冻结
- miner commit / reveal
- 任务解析、奖励窗口、settlement batch
- anchor job 生成、typed tx 广播、链上确认
- 这次对话里实测暴露出来的 Polymarket 数据抓取注意点

不涉及：

- `daily_anchor` 的产品设计
- Arena / 风控 /前端页面细节
- 泛化的链上协议设计

---

## 2. 这条链路现在是怎么跑的

当前完整链路是一个以 `mining-service` 为运行时权威的服务侧状态机：

1. `server.py` 启动 FastAPI，并根据配置装配 repo、market data provider、chain adapter。
2. `ForecastMiningService` 先发布当前 bucket 的短时任务，再由独立 reconcile 路径处理旧 bucket 的 resolution / settlement。
3. `LiveMarketDataProvider` 同时抓 Binance 和 Polymarket：
   - Binance 提供盘口、逐笔成交和微观价格信号
   - Polymarket 提供当前 5m market 的 slug、question、CLOB midpoint / book、最终 resolution
4. miner 通过 `/v1/task-runs/{id}/commit` 和 `/v1/task-runs/{id}/reveal` 提交预测。
5. 任务到 `resolve_at` 后，后台 resolution loop 或手动 reconcile endpoint 继续轮询 Gamma：
   - 如果 Polymarket 还没真正 resolved，任务进入 `awaiting_resolution`
   - submission 进入 `pending_resolution`
   - 一旦 Gamma 给出确定 outcome，才进入最终计分
6. 已 resolved 的任务按小时聚合成 `reward_window`，再汇总成 `settlement_batch`。
7. `retry-anchor` 为 batch 生成 canonical anchor payload，`submit-anchor` 生成 anchor job。
8. `chain_adapter.py` 生成 typed tx，调用 `clawchaind tx settlement anchor-batch ...` 离线签名并广播。
9. 广播后再通过 RPC `tx` 查询确认，成功后把 anchor job 标为 `anchored`。

这个实现里，Polymarket 不是一个“展示数据源”，而是：

- 任务快照的一部分
- baseline 概率的一部分
- fast task 最终 outcome 的权威来源

---

## 3. 关键代码落点

### 3.1 服务装配与 HTTP 入口

`mining-service/server.py`

- `create_app(...)`
  - 装配 repo、market data provider、chain broadcaster
  - 入口处决定整条链路跑 synthetic 还是 live
  - runtime 模式下会额外挂起 task resolution loop，把 miner 热路径和旧任务结算拆开
- `_build_default_market_data_provider(settings)`
  - `live_market_data_enabled=true` 时，默认构造 `HybridMarketDataProvider(live=LiveMarketDataProvider(...))`
  - 这个点修过一次，避免“注入 repository 以后 provider 退回 synthetic”的问题
- 主要 API
  - `GET /v1/task-runs/active`
  - `GET /v1/forecast/task-runs/{task_run_id}`
  - `POST /v1/task-runs/{task_run_id}/commit`
  - `POST /v1/task-runs/{task_run_id}/reveal`
  - `POST /admin/reconcile/resolutions`
  - `GET /admin/settlement-batches`
  - `POST /admin/settlement-batches/{id}/retry-anchor`
  - `POST /admin/settlement-batches/{id}/submit-anchor`
  - `GET /admin/anchor-jobs/{id}/chain-tx-plan`
  - `POST /admin/anchor-jobs/{id}/broadcast-typed`
  - `POST /admin/anchor-jobs/{id}/confirm-chain`

### 3.2 运行时配置

`mining-service/config.py`

关键配置项：

- `CLAWCHAIN_LIVE_MARKET_DATA_ENABLED`
- `CLAWCHAIN_POLYMARKET_GAMMA_URL`
- `CLAWCHAIN_POLYMARKET_CLOB_URL`
- `CLAWCHAIN_FAST_TASK_SECONDS`
- `CLAWCHAIN_COMMIT_WINDOW_SECONDS`
- `CLAWCHAIN_REVEAL_WINDOW_SECONDS`
- `CLAWCHAIN_RESOLUTION_RETRY_SECONDS`
- `CLAWCHAIN_TASK_RESOLUTION_LOOP_ENABLED`
- `CLAWCHAIN_TASK_RESOLUTION_LOOP_INTERVAL_SECONDS`
- `CLAWCHAIN_MAX_POLYMARKET_SNAPSHOT_FRESHNESS_SECONDS`

当前 repo 里 lane 名仍然叫 `forecast_15m`，但实际 bucket 长度由 `fast_task_seconds` 决定。做 5m 实测时，真正要改的是 `CLAWCHAIN_FAST_TASK_SECONDS=300`。

### 3.3 Polymarket / Binance 数据抓取

`mining-service/market_data.py`

这是 Polymarket 短时预测链路最关键的文件。

- `POLYMARKET_SERIES_CONFIG`
  - 定义 BTC / ETH 5m 系列的 `series_slug`、`slug_template`、`positive_outcome`
  - 当前映射：
    - BTC: `btc-updown-5m-{bucket_ts}`
    - ETH: `eth-updown-5m-{bucket_ts}`
- `_bucket_timestamp(now, seconds)`
  - 把当前时间对齐到 300s bucket
- `_select_series_market(...)`
  - direct slug miss 之后的 fallback 选择器
  - 会优先选择还没结束的 future candidate，再选刚结束不久的 recent candidate
- `LiveMarketDataProvider._fetch_polymarket_snapshot(...)`
  - 先走 direct slug
  - 拿到市场后再调用 CLOB `/book` 与 `/midpoint`
  - 组装冻结到 `pack_json["polymarket_snapshot"]`
- `LiveMarketDataProvider._get_polymarket_resolution(...)`
  - 用 Gamma `/markets/slug/{slug}` 读取最终 outcome
- `HybridMarketDataProvider`
  - live 构建失败时才 fallback 到 synthetic
  - live resolution 失败时不会伪造 resolved outcome，而是返回 pending

### 3.4 任务状态机与结算

`mining-service/forecast_engine.py`

- `build_fast_task(...)`
  - 生成 task id、publish / commit / reveal / resolve 时间边界
- `_publish_current_tasks(...)`
  - 只负责发布当前 bucket task，不处理旧任务 resolution
- `reconcile_due_work(...)`
  - 专门跑 due task settlement、reward window、settlement batch 和 rank 刷新
- `snapshot_metadata(...)`
  - 冻结 `snapshot_source` 与各源 freshness
- `_settle_due_tasks(...)`
  - 处理 fast task resolution
  - Polymarket 未 resolved 时，把 task 标成 `awaiting_resolution`
  - 把 submission 标成 `pending_resolution`
  - 现在会写 `last_resolution_attempt_at`，并按 `resolution_retry_seconds` 节流 pending market 的重试
- `_build_settlement_batches(...)`
  - 把 reward window 汇总到 settlement batch
  - 这里修过一次，保证同一小时内多轮任务继续累加到同一个 open batch，而不是只保留第一次的 `task_count`
- `retry_anchor_settlement_batch(...)`
  - 重新生成 canonical payload / hash
- `submit_anchor_job(...)`
  - 创建 anchor job
- `build_chain_tx_plan(...)` / `broadcast_chain_tx_typed(...)` / `confirm_anchor_job_on_chain(...)`
  - 从服务侧进入链侧广播与确认

### 3.5 Typed anchor tx 与链确认

`mining-service/chain_adapter.py`

- `build_anchor_tx_plan(...)`
  - 从 settlement batch 生成 typed tx intent
- `build_typed_anchor_signing_material(...)`
  - 解析 sender、account number、sequence、公钥
- `resolve_typed_broadcast_spec(...)`
  - 组装 `clawchaind tx settlement anchor-batch ... --generate-only`
  - 再组装 `clawchaind tx sign ...`
- `_normalize_tx_hash_param(...)`
  - 把 hex tx hash 编成 CometBFT `tx` RPC 需要的 base64 raw hash
  - 这是 confirm-chain 路径里修掉的一个关键兼容问题

### 3.6 Go 侧 CLI / 编码修补

`app/encoding.go`

- `MakeEncodingConfig()`
  - 现在用 `gogoproto.HybridResolver` 作为 `ProtoFiles`
  - 修复了 `tx sign` 无法识别 `/clawchain.settlement.v1.MsgAnchorSettlementBatch` 的问题

`cmd/clawchaind/main.go`

- `NewRootCmd()`
  - 通过 `server.NewDefaultContext()` 提前挂好 server context
  - 修复 `start` 预跑阶段拿不到 `minimum-gas-prices` 的问题

### 3.7 miner 脚本侧

`skill/scripts/mine.py`

- `get_active_tasks()` 拉取 `/v1/task-runs/active`
- `get_task_detail()` 拉取 `/v1/forecast/task-runs/{task_run_id}`
- `compute_prediction(task)` 从冻结快照里算 `p_yes_bps`
- `post_commit(...)` / `post_reveal(...)` 打提交接口
- `mine_task(...)` 是单任务 commit-reveal 的完整执行

`skill/scripts/status.py`

- 拉 miner status、reward window、settlement batch、anchor job
- 适合压测时观察是否已经从 Polymarket pending 进入最终结算

---

## 4. 这次对话里踩出来的 Polymarket 数据抓取注意点

下面这些不是“理论建议”，而是这次实测里真正踩到或专门修掉的点。

### 4.1 5m 市场发现要优先走 direct slug，不要先扫列表

当前实现优先调用：

- `GET /markets/slug/btc-updown-5m-{bucket_ts}`
- `GET /markets/slug/eth-updown-5m-{bucket_ts}`

其中：

- `bucket_ts = floor(now_ts / 300) * 300`

只有 direct slug 404 时，才退回：

- `GET /markets?active=true&closed=false&limit=200`

然后再用 `_select_series_market(...)` 过滤。

原因很直接：

- 5m 系列的 slug 是稳定且可预测的
- 直接拿 slug 更快
- 不容易因为同类 market 太多而选错
- 对压测尤其重要，避免“拿到 ETH 但其实是别的 market”这种脏数据

### 4.2 Outcome 语义要按 5m 系列处理，不能默认写死 `Yes`

当前 BTC / ETH 5m 系列的正向 outcome 是 `Up`，不是通用 binary market 常见的 `Yes`。

代码里已经显式写在 `POLYMARKET_SERIES_CONFIG`：

- BTC / ETH 都是 `positive_outcome = "Up"`

实现里虽然保留了 defensive fallback：

- 如果市场 metadata 里没有 `Up`
- 就回退到 `Yes` 或列表第一个 outcome

但这只是兜底，不应该作为主路径假设。

### 4.3 Gamma 的字段经常是 JSON 字符串，不能直接按 list 用

实测里 `clobTokenIds`、`outcomes`、`outcomePrices` 这些字段并不稳定，有时是 JSON string。

所以当前实现统一通过 `_safe_json_loads(...)` 先解：

- `clobTokenIds`
- `outcomes`
- `outcomePrices`

否则很容易出现：

- token index 对不齐
- `positive_outcome` 找不到
- resolution 判断错位

### 4.4 `endDate` 到了，不等于 Gamma 已经 resolved

这是这次 live 5m 压测里最明显的点。

在 43 个 miner、连续 5 轮 BTC/ETH 5m live 实测里：

- 430 次 commit 全部完成
- 430 次 reveal 全部完成
- 但第 5 轮结束后，仍然有一批任务停在 `awaiting_resolution`

根因不是 commit / reveal 出错，而是：

- Gamma 还没把这些 market 标成真正 resolved
- `closed=false`
- 或 `umaResolutionStatus != resolved`
- 或 `outcomePrices` 还不是确定的 0/1

所以当前正确做法是：

- task 进入 `awaiting_resolution`
- submission 进入 `pending_resolution`
- 持续 reconcile，等 Gamma 真正 resolved 后再结算

不要把“已经过了 5 分钟”误判成“应该立刻能结算”。

### 4.5 live 压测时必须确认 `snapshot_source == live`

这个 repo 的默认 live provider 是：

- `HybridMarketDataProvider(live=LiveMarketDataProvider(...))`

如果 live 抓取失败，它会 fallback 成 synthetic，并把：

- `pack_json["snapshot_source"] = "synthetic_fallback"`
- `task_state = "degraded"`

所以做严格 live 实测时，不能只看接口通了，还要确认任务 pack 里是：

- `snapshot_source == "live"`

否则你以为自己在打 Polymarket live，其实已经悄悄退到 synthetic。

### 4.6 live 构建可以 fallback，但 live resolution 不能伪造

构建阶段 fallback 到 synthetic 还可以接受，因为这是“任务无法实时抓到快照”的降级。

但 resolution 阶段不能这样做。

当前实现里，如果 live resolution 报错，`HybridMarketDataProvider.resolve_fast_task(...)` 返回的是 pending，而不是 synthetic resolved outcome。

这个约束很重要，因为一旦在 resolution 阶段回退到 synthetic，就会把真实 Polymarket task 结算成假的结果。

### 4.7 midpoint 取不到时，要回退到 bestBid / bestAsk 均值

当前实现先读：

- `GET /midpoint?token_id=...`

如果 midpoint 缺失或 `<= 0`，就回退到：

- `(bestBid + bestAsk) / 2`

这个兜底是必要的，因为实际市场里 midpoint 不是每次都稳定可用，尤其是薄盘口或某些瞬时状态下。

### 4.8 5m bucket 对齐必须严格按 300 秒做

当前 direct slug 的核心前提是 bucket 时间要对齐。

也就是：

- 09:00:01 UTC 应该去找 `...-09:00` 这个 bucket
- 09:05:01 UTC 应该去找 `...-09:05` 这个 bucket

如果 bucket 算错，direct slug 就会 miss，然后退回列表扫描，结果：

- 要么更慢
- 要么选到相邻 bucket
- 要么直接落到 recent candidate，产生肉眼不明显但结算会错的偏差

### 4.9 5m live 实测时，lane 名字别误导自己

当前服务里的 lane 名还是 `forecast_15m`，但 5m 压测实际靠的是：

- `fast_task_seconds=300`

所以：

- bucket 长度请看 `fast_task_seconds`
- 不要根据 lane 名字推断当前是不是 15m

这是这次实测里的一个高频混淆点。

### 4.10 Polymarket resolution 延迟会直接影响 anchor 时机

如果你要把完整链路一直跑到 anchor：

1. 先确认目标轮次的 task 都已经 `resolved`
2. 再确认 reward window 的 `task_count` 符合预期
3. 再确认 settlement batch 的 `task_count` 也已经刷新到位
4. 最后再 `retry-anchor -> submit-anchor -> broadcast-typed -> confirm-chain`

否则 anchor 的不是你想要的完整轮次，而只是“截至当下已经 resolved 的那部分”。

### 4.11 `active/detail` 热路径不能顺手做旧任务 resolution

这次 10 round live 里真正把 miner 拖慢的，不是 commit / reveal，而是：

- `/v1/task-runs/active`
- `/v1/forecast/task-runs/{task_run_id}`

之前这两个接口都会直接触发 `reconcile()`，而 `reconcile()` 会同步去跑旧 bucket 的 Gamma resolution。pending market 一多，miner 刚拿 active list 或 task detail 就会被慢查询拖住。

现在实现已经改成：

- `get_active_tasks()` / `get_task_detail()` 只保证当前 bucket task 已发布
- 旧任务 resolution 走后台 `task resolution loop`
- 手动补跑则走 `POST /admin/reconcile/resolutions`

这点对 5m live 压测非常关键，不然 miner 热路径和 Polymarket resolution 延迟会互相污染。

---

## 5. 这条链路里建议直接看的测试

### Python

`tests/mining_service/test_market_data.py`

- 覆盖 BTC / ETH 5m direct slug 抓取
- 覆盖 `snapshot_source`
- 覆盖 Gamma resolved / pending
- 覆盖 synthetic fallback

`tests/mining_service/test_forecast_api.py`

- `test_create_app_uses_live_provider_when_repo_is_injected`
- `test_settlement_batch_refreshes_open_batch_for_later_same_hour_tasks`
- 覆盖从 API 触发 settlement / anchor / confirm 的主路径

`tests/mining_service/test_chain_adapter.py`

- 覆盖 tx hash hex -> base64 RPC 编码
- 覆盖 confirmed / pending 两种 confirm-chain 返回

### Go

`cmd/clawchaind/main_test.go`

- `TestSettlementAnchorBatchGeneratedTxCanBeSigned`
- `TestStartCommandPreRunLoadsMinimumGasPrices`

这两个测试分别对应这次对话里修掉的两个链侧问题：

- typed settlement tx 可签名
- `start` 预跑拿到正确 gas price

---

## 6. 一句话结论

现在这条链路已经不是“只有 commit / reveal 的 demo”，而是：

- 能用 live Polymarket 5m slug 发现 market
- 能冻结快照并跑 miner commit / reveal
- 能把未 resolved 的任务安全地挂起
- 能在 resolved 后生成 reward window / settlement batch
- 能生成 typed anchor tx 并完成链上确认

真正还需要长期盯住的，不是 commit / reveal 本身，而是 Polymarket 5m market 的抓取稳定性、bucket 对齐、以及 Gamma resolution 的实际延迟。

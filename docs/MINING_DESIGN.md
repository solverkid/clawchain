# ClawChain V1 挖矿设计

**版本**: 1.3
**日期**: 2026-04-11
**状态**: 协议/机制权威方案
**关联文档**:
- [docs/superpowers/specs/2026-04-10-companion-miner-product-layer-design.md](/Users/yanchengren/Documents/Projects/clawchain/docs/superpowers/specs/2026-04-10-companion-miner-product-layer-design.md)
- [docs/HARNESS_BACKEND_ARCHITECTURE.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_BACKEND_ARCHITECTURE.md)
- [docs/HARNESS_API_CONTRACTS.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_API_CONTRACTS.md)
- [docs/HARNESS_SIMULATION_PLAN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_SIMULATION_PLAN.md)
- [docs/DYNAMIC_ARENA_ALPHA_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/DYNAMIC_ARENA_ALPHA_DESIGN.md)

说明：
- 本文档是 **协议、评分、结算、anti-abuse** 的权威方案
- 矿工主产品层、companion shell、surface 语言以 companion spec 为权威

---

## 1. 执行摘要

从矿工视角，ClawChain V1 的最新定义是：

> **一个 companion-first 的 agent mining shell：用户拥有一个常驻 mining buddy，它在后台自动参与 forecast、daily、arena 等 activities 来挖取 CLAW。**

从协议视角，它建立在以下四层结构上：

V1 的四层结构：

1. **15m Forecast Mining**
   - 主赛道
   - 使用 Polymarket 作为市场发现和公开基线
   - 使用 Binance 作为主要参考价格源
   - 奖励“比市场更早、更准、更稳定”的判断

2. **Daily Lane**
   - 慢反馈校准赛道
   - 使用 canonical daily contracts
   - Alpha day-1 只作为全局 calibration / reliability anchor

3. **Arena Multiplier**
   - 泛能力校准器
   - 用 tournament-like Simplified Bluff Arena 测试长链路规划、隐藏信息推理、风险管理和抗一维脚本能力
   - 不单独主导奖励池

4. **Harness Core**
   - 统一的数据包、提交流程、评分、风控、回放、结算、排行榜基础设施
   - 未来扩展到 tool sandbox、sub-agent runtime、campaign layer、独立 `poker mtt` skill-game mining lane

V1 不是“绝对防作弊”，而是：

- 强 AI 的长期收益显著高于弱 AI
- 弱 AI 的长期收益显著高于简单启发式脚本
- 简单脚本的长期收益显著高于查表和低成本程序化套利
- Sybil、复制市场、延迟抄袭、arena 共谋的边际收益低于正常参与收益

---

## 2. 设计目标与边界

## 2.1 目标

1. **吸引矿工**
   - 快反馈
   - 公开排名
   - 真实 crypto 数据语境

2. **相对公平**
   - 不奖励先来先得
   - 不奖励纯在线时长
   - 不让“复制市场”长期拿高分

3. **anti-farm**
   - 压低低成本工程化撸毛收益
   - 让 Sybil、跟单、重放、模板 exploit 不划算

4. **可量化**
   - 不依赖在线 LLM judge
   - 结果可重放、可复算、可审计

5. **crypto native**
   - 输入来自真实 crypto 市场
   - 输出是公开竞争、概率、声誉、赛季和奖励

6. **沉淀 Harness 能力**
   - 不只做一个玩法
   - 要沉淀成统一的 agent evaluation infra

## 2.2 非目标

V1 不做：

- 挂机在线就发币
- 开放式作文/摘要评分
- 自由文本 bluff 主赛道
- 实时 LLM 评委网络
- task marketplace
- 5m 高频主赛道
- 链上逐步执行每一步游戏动作
- 对外承诺“完全公平”或“绝对防作弊”

---

## 3. 已锁定决策

## 3.1 15m 主赛道

- 目标设计上，15m lane 是 **Claw 自定义合成任务**，不是必须对应一个真实 Polymarket 15m 合约
- Polymarket 主要提供：
  - 市场发现
  - 公开概率基线
  - 盘口和活跃度特征
- 目标设计上，15m lane 结果用 Claw 自己的参考价格规则结算

当前实现 truth（2026-04-23）：

- active runtime 更接近 `Polymarket-derived short-horizon tasks`
- live provider 当前直接消费 Polymarket Gamma 数据做 market discovery / resolution
- `end_ref_price` 当前仍未落成独立 `ReferencePriceService` 的 fully-materialized path
- 所以这一节里 “Claw 自有参考价格规则” 仍然是目标态，不是已经完全落地的 runtime truth

## 3.2 资产与任务范围

- Alpha 只做 `BTCUSDT`、`ETHUSDT`
- 每个 15 分钟窗口固定生成 `1-2` 个全网相同任务
- Daily lane 只做 `BTC` / `ETH` 的 canonical daily binaries

## 3.3 统一提交协议

- Forecast / Daily 统一使用 `commit-reveal`
- 输出统一为 `p_yes_bps`
- `p_yes_bps` 使用整数固定点，范围默认 `1500..8500`
- `side` 仅作展示，后端统一以 `p_yes_bps >= 5000` 推导

## 3.4 Arena 角色

- Arena 不是主奖励池
- Arena 是独立 tournament service
- Arena 结果先更新 rolling rating，再导出 `arena_multiplier`
- Alpha 阶段 `arena_multiplier` 范围收窄为 `0.96..1.04`

## 3.5 Poker MTT 角色

- `poker mtt` 是后续独立 skill-game mining lane，不复用 `arena` 语义
- donor runtime 参考 `lepoker-gameserver`
- donor control/read model 参考 `lepoker-auth`
- scoring 使用 `tournament_result + hidden_eval + consistency`
- live ranking、final ranking、long-term ranking 必须拆开
- short-term HUD、long-term HUD 必须拆开
- ELO / public rating 不直接参与奖励计算
- reward 进入 `poker_mtt_daily` / `poker_mtt_weekly` reward window
- 链上第一阶段只锚定 `settlement_batch` root，不逐手或逐场上链
- reward window 只消费 `final_ranking` projections，不消费 live standings、public ELO 或 donor payout execution
- `poker_mtt_daily` / `poker_mtt_weekly` 必须从同一 miner emission budget 中拿到显式子预算，不创造额外奖励池
- Phase 1：result entries、poker MTT multiplier、reward windows、settlement anchor
- Phase 2：raw hand evidence、short/long HUD、hidden eval、public rating
- reputation follow-on phase：窗口级 `reputation_delta` 写入 `x/reputation`；keeper-level append-only contract 已落地，但不属于当前 Poker MTT Phase 3 production-readiness gate，外部 enablement 仍需单独 release review
- Go 实现边界上，`pokermtt/*` 不应 import `arena/*` domain，也不应让 donor structs 穿透进 ClawChain domain model

## 3.6 技术形态

- 先做 **模块化单体**
- 核心建议：
  - `FastAPI`
  - `Postgres`
  - `Redis Streams`
  - `Object Storage`
- 不一开始拆微服务

---

## 4. 产品定义

## 4.1 一句话定义

> **ClawChain V1 的矿工主产品层是一个 persistent mining buddy；协议层则通过 forecast / daily / arena 三类 activities 结算它的表现。**

## 4.2 面向矿工的主叙事

不是：

- 答题得积分
- 在线挂机挖币
- 写作文给 AI 打分

而是：

> **你拥有一个会自己出去工作的 mining buddy。它在真实 crypto 市场信息流里持续做判断、参与活动、带回结果；你每天只需要轻量查看状态并偶尔给一点方向。**

## 4.3 产品对象

面向矿工的 V1 壳层固定为 4 个对象：

1. **Companion**
   - 用户拥有的长期身份
   - 有名字、状态、心情、战绩和 activity history
   - 不是奖励源，也不是协议真相来源

2. **Runtime**
   - 后台 mining runtime
   - 调度 forecast / daily / arena
   - companion 的身份和偏好必须独立持久化，不能只依赖 OpenClaw session transcript

3. **Activities**
   - 产品层统一叫 activity
   - 内部协议层仍保留 `lane`
   - activity 角色至少要标注 `direct reward` / `calibration` / `multiplier` / `practice`

4. **Surfaces**
   - macOS menu bar
   - TUI
   - Control UI / WebChat
   - plugin commands / slash commands

## 4.4 V1 主 surfaces

- **macOS menu bar**：优先 companion 入口，最适合常驻状态
- **TUI**：ambient chat/status surface，不假设自定义面板系统
- **Control UI / WebChat**：完整 companion home、activities、history、review 子集
- **plugin commands / slash commands**：`/buddy`、`/status`、`/activities`、`/checkin`、`/pause`、`/wake`

约束：

- companion 不能只靠对话 session 保持“记忆”
- 需要独立的 companion state store
- 若命令承担确定性控制，优先 native plugin command 或 tool-dispatch，而不是纯模型中介 skill

## 4.5 V1 每日交互边界

V1 允许每天一次轻互动：

- 时长目标 `10-30s`
- 作用是状态同步、轻偏好输入、陪伴感
- 不直接发放奖励
- 不影响 runtime 是否继续工作

明确不做：

- 喂养 / 清洁 / 掉血 / 死亡
- 漏签惩罚
- 一天多次强打扰

## 4.6 产品语言与内部术语映射

产品层：

- `activity`
- `daily brief`
- `current work`
- `buddy`

协议层：

- `lane`
- `reward_window`
- `baseline_q`
- `settlement_batch`

## 4.7 面向矿工的可见信息

V1 的矿工主界面至少包含：

- current work state
- current activity / recommended activity
- daily brief status
- companion mood / availability
- scoped `public rank / public ELO / calibration / streak`
- `reward timeline`
- `score explanation`
- `arena multiplier`
- `probation / reward maturity / review status`
- `snapshot hash / settlement version / reference source`

其中：

- Arena 内的本场 `arena_tournament_standing / stack / blind level / bubble pressure` 只在进入 Arena 视图时显示
- `Market Ops`、`Settlement Ops` 等后台面板不直接等于矿工主界面

---

## 5. V1 总体机制

## 5.1 四层分数结构

V1 不是按完成次数发币，而是按四层结果组合：

```text
fast_direct_score
  = normalized_fast_tickets

slow_direct_score
  = 0   (Alpha day-1 default)

base_score
  = fast_direct_score
  + slow_direct_score

quality_envelope
  = model_reliability
  * ops_reliability
  * arena_multiplier
  * anti_abuse_discount

final_mining_score
  = base_score * quality_envelope
```

说明：

 - `slow_direct_score` 在 Alpha day-1 关闭，只保留给 post-Alpha 小权重启用
 - 当前 runtime 里，`model_reliability` 仍然主要来自 fast lane settled history；daily lane 的 broader reliability merge 还是目标态，不是已实现事实
 - `ops_reliability` 只反映 reveal/在线履约纪律，不允许主导奖励
- `arena_multiplier` 是 rolling arena skill 的小幅放大器
- `anti_abuse_discount` 用于 risk-adjusted discount，不一刀切封禁

## 5.2 Cross-lane invariants

为避免同一信号在多个 lane 被重复计分，V1 明确锁定以下不变量：

- `fast_direct_score` 只来自 15m lane 的 `fast_tickets`
- `slow_direct_score` 在 Alpha day-1 默认关闭
- daily 的 `anchor score` 只进入 `model_reliability`
- Arena 只通过 `arena_multiplier` 进入质量包络
- Poker MTT 只通过独立 `poker_mtt_daily` / `poker_mtt_weekly` 窗口进入奖励，不复用 `arena_multiplier`
- Poker MTT 的 `poker_mtt_public_rating` 不直接参与 reward weight
- `anti_abuse_discount` 只允许在 `reward_window` 级别应用一次
- `public ELO` 永远不直接参与奖励计算
- 高置信 cluster 在同一 `task_run` 只允许一个 reward-eligible submission

## 5.3 默认取值范围

- `arena_multiplier`: `0.96 ~ 1.04`
- `model_reliability`: `0.97 ~ 1.03`
- `ops_reliability`: `0.95 ~ 1.05`
- `anti_abuse_discount`: `0.00 ~ 1.00`

## 5.4 结算节奏

- 链侧 epoch：保留，用于结算锚定
- 15m lane：每 15 分钟一个窗口
- daily lane：每天 `2` 个全网统一任务
- arena：Alpha launch 默认 `1` 场 rated + `1` 场 practice tournament
- poker mtt：后续按 `poker_mtt_daily` / `poker_mtt_weekly` 窗口结算，不绑定单场即时发奖
- season：每 7 天一个赛季

---

## 6. Lane A: 15m Forecast Mining（产品层：Forecast Activity）

## 6.1 任务定义

每个 15m task 是一个标准化市场判断任务：

- 标的：`BTCUSDT` / `ETHUSDT`
- 题型：`15m above/below canonical strike`
- horizon：15 分钟
- 输入：统一冻结的数据包
- 输出：`p_yes_bps`

推荐定义：

- `YES` = `end_ref_price > strike_price`
- `NO` = `end_ref_price <= strike_price`

其中：

- `strike_price` 在 Alpha launch 固定为 `commit_close_ref_price`
- 后续版本可引入小 band 或动态 strike policy，但 Alpha 先固定

## 6.2 时间模型

对每个窗口 `T`：

- `freeze_window = [T-10s, T]`
- `publish_at = T`
- `commit_deadline = T+3s`
- `reveal_deadline = T+13s`
- `resolve_at = T+15m`

这意味着：

- 所有 miner 基于同一快照包作答
- fast lane 的 infra race window 被强行压短
- `commit_close_ref_price` 由官方参考价源在 `commit_deadline` 时刻确定

## 6.3 输入包

最小 pack 字段：

- `task_id`
- `lane`
- `asset`
- `question_type`
- `freeze_at`
- `publish_at`
- `commit_deadline`
- `reveal_deadline`
- `resolve_at`
- `pack_hash`
- `schema_version`
- `baseline_q`
- `baseline_method`
- `baseline_q_source`
- `polymarket_refs[]`
- `binance_symbol`
- `feature_bundle`
- `text_summary`
- `noise_blocks[]`
- `snapshot_health`

## 6.4 Polymarket 作用

Polymarket 在 15m lane 中负责：

- 市场发现
- 公开概率基线
- orderbook / spread / depth / volume 特征

它不负责：

- 15m 快速结果结算

## 6.5 Binance 作用

Binance 在 15m lane 中负责：

- 主要参考价格
- top-of-book
- partial depth
- trades / realized vol / imbalance 特征

Alpha 不维护完整本地 L2 order book，只冻结固定层数 partial depth 和预聚合微观结构特征。

## 6.6 Baseline 与 Reference Price

### BaselineForecaster

`baseline_q` 使用 **公开可复算** 的 deterministic baseline：

- 输入：
  - `q_pm`: Polymarket 映射市场的 book-implied probability
  - `q_bin`: Binance 微观结构基线概率
- 输出：`baseline_q`
- 要求：
  - pack 中明确公开
  - 版本化
  - 不允许隐式黑箱

Alpha 默认口径：

```text
q_pm
  = midpoint_implied_probability

q_bin
  = sigmoid(
      0.45 * depth_imbalance_z
    + 0.35 * trade_imbalance_z
    + 0.20 * microprice_drift_z
    )

baseline_q
  = clamp(0.05, 0.95, 0.85 * q_pm + 0.15 * q_bin)
```

若 Polymarket 数据不健康：

- 退化为 `baseline_q = clamp(0.05, 0.95, q_bin)`
- pack 中显式标记 `baseline_method = q_bin_only`
- `q_pm` 不健康定义为：
  - 无双边盘口
  - book staleness `> 15s`
  - best ask - best bid `> 0.10` 概率点

### ReferencePriceService

15m 的 `commit_close_ref_price` / `end_ref_price` 由独立的 `ReferencePriceService` 给出：

- 主来源：Binance spot top-of-book midpoint
- 默认方法：`5s midpoint TWAP`
- 需要：
  - fallback hierarchy
  - cross-venue sanity check
  - void logic

Alpha 默认口径：

- `commit_close_ref_price = TWAP(midpoint, [commit_deadline-5s, commit_deadline], 1s cadence)`
- `end_ref_price = TWAP(midpoint, [resolve_at-5s, resolve_at], 1s cadence)`
- `fallback_1 = Binance last-trade VWAP(5s)`
- `fallback_2 = internal cross-venue median TWAP(5s)`，仅在已接入时启用
- 少于 `4` 个有效样本：`DEGRADED`
- 少于 `3` 个有效样本：`VOID`
- primary 与 `fallback_1` 偏离超过 `15 bps`：`DEGRADED`
- primary 与 `fallback_2` 偏离超过 `25 bps`：`VOID`

## 6.7 提交流程

### Commit

miner 提交：

```json
{
  "task_id": "string",
  "miner_id": "string",
  "commit_hash": "hex",
  "nonce": "random",
  "schema_version": "v1"
}
```

### Reveal

reveal payload 采用 canonical serialization，最小字段：

```json
{
  "task_id": "string",
  "miner_id": "string",
  "p_yes_bps": 6730,
  "nonce": "random",
  "schema_version": "v1"
}
```

规则：

- `p_yes_bps` 默认限制在 `1500..8500`
- 当前原型按 **rolling 1d fast participation** 计分：最近 `1d` 内跳过比例在 `20%` 以内不损伤 `ops_reliability`
- rolling `7d` selective-skip accounting 仍然是后续增强，不是当前 runtime 已实现项
- `no-reveal / late-reveal / invalid payload` 记 0 ticket，并打击 `ops_reliability`
- 显式 commit 后不 reveal，仍按违约处理

## 6.8 单题评分

Alpha 使用：

> **improvement over baseline + 轻方向奖励 + anti-copy cap**

定义：

- `q` = `baseline_q`
- `p` = `p_yes_bps / 10000`
- `y` = `0 or 1`
- `direction_bonus = 0.015 if sign(p-0.5) == y else 0`
- `copy_cap = 0.25 if abs(p - q) < 0.03 else 1.00`
- `task_weight = 1.00`
- `liquidity_weight = 1.00` for healthy tasks, `0.50` for degraded-liquidity tasks

```text
baseline_score = 1 - (q - y)^2
miner_score    = 1 - (p - y)^2
edge_score     = miner_score - baseline_score

fast_ticket
  = max(0, edge_score + direction_bonus)
  * copy_cap
  * liquidity_weight
  * task_weight
```

说明：

- 方向正确会额外加成，但不是硬门槛
- 靠近 `baseline_q` 的 nudging 会被显式压上限
- 复制市场和小幅扰动 baseline 的长期收益会被压低

## 6.9 长期质量分

15m lane 的长期质量不只看命中率，而看：

- `edge_sum`
- `calibration`
- `ops_reliability`
- `consistency`

推荐：

```text
model_reliability
  = normalized_fast_ticket_sum
  * fast_calibration_factor
  * consistency_factor

ops_reliability
  = reveal_completion_factor
  * commit_discipline_factor
  * skip_budget_factor
```

其中：

- `ops_reliability` 必须被限制在 `0.95..1.05`
- 它只能调节履约纪律，不允许压过模型质量本身

---

## 7. Lane B: Daily Lane（产品层：Daily Calibration Activity）

## 7.1 角色定位

Daily lane 是：

> **slow-feedback calibration lane**

它不是第二主赛道，而是：

- 提供更稳的长期校准锚
- 降低 15m 噪声的影响
- 强化 patience discipline

## 7.2 题面定义

Daily lane 使用 **canonical daily contracts**：

- 只做 `BTC` / `ETH`
- 只做 `daily above/below`
- 先定义 Claw 自己的标准题面
- 再去映射 Polymarket 市场

每个 canonical contract 至少固定：

- 标的
- strike
- cutoff 时间
- 参考价格源
- 价格取样规则
- 异常值规则
- void 条件

## 7.3 默认范围

- Alpha 默认每天 `2` 个全网统一任务
- 每个资产每天 `1` 个接近 ATM 的 strike
- 不开放长尾或主观题型

Alpha 默认口径：

- `assets = BTC, ETH`
- `publish_time = 00:00 UTC`
- `cutoff_time = 00:00 UTC + 24h`
- `strike = start_ref_price`
- 不做 OTM/ITM 多 strike 扩展

## 7.4 生命周期

Daily task 状态机：

```text
OPEN
-> LOCKED
-> PROVISIONAL_RESOLVED
-> MATURED
-> RECONCILED / VOID
```

设计原则：

- 先给 miner `provisional settlement`
- 再做 `official maturity / reconciliation`

## 7.5 评分方式

Daily lane 与 15m lane 共享：

- `commit-reveal`
- `p_yes_bps`
- `proper-score improvement`

但它更强调：

- `slow edge`
- `calibration`
- `patience discipline`

## 7.6 direct score 与 anchor score

Daily lane 结果拆成两部分：

### direct score

- 在 Alpha day-1 默认关闭
- 仅保留为 post-Alpha 可选能力，且直接权重上限不超过 `5%`

### anchor score

- 更新 `model_reliability`
- 强化全局 calibration / reliability

这比在 day-1 就让 daily 直接分配奖励更稳。

## 7.7 默认权重

Alpha 启动时：

- `slow_direct_score = 0%`
- Daily 通过 `anchor score` 间接影响 `model_reliability`
- `daily_anchor` 的单日影响先钳在 `0.97 .. 1.03`

当前 runtime：

- 已经实现 `daily_anchor -> model_reliability`
- 当前实现对单题使用 `±1.5%` 的 anchor multiplier，因此 `BTC + ETH` 每日合计最大影响约为 `±3%`
- 当前实现仍不发放 daily direct reward
- 当前实现仍是最小 `resolved / awaiting_resolution` 语义，没有把 `provisional -> matured -> reconciled` 全部展开
- 当前 companion runtime 会在每轮优先尝试 active `daily_anchor`，再按 fast cap 处理 `forecast_15m`

原因：

- daily 样本少
- 同日任务相关性高
- day-1 更适合先做可靠的 anchor lane，而不是直接分配奖励

## 7.8 风险控制

Daily lane 必须有：

- `Market Health Score`
- `Maturity Queue`
- `void policy`
- `cross-lane correlation cap`

如果 same-day 的 fast lane 和 slow lane 高度同向：

- Daily 只更新 anchor，不增加 direct score
- `cross-lane correlation cap` 默认把 daily 单日 anchor 影响限制在 `±3%`

---

## 8. Lane C: Arena Multiplier（产品层：Arena Activity）

## 8.1 角色定位

Arena 是：

> **Tournament-like Simplified Bluff Arena**

它测的是 forecast lane 不容易单独测到的能力：

- 长链路规划
- 隐藏信息推理
- 风险管理
- 多轮稳定性
- 抗单模板脚本

## 8.2 关键约束

- Arena 是 **independent tournament service**
- 不绑定 10 分钟 chain epoch
- 每场 tournament 独立运行 `12-25` 分钟
- 完赛后把 rolling rating 写回最近结算窗口

## 8.3 默认赛制

- 目标 field size：`64`
- `56-64`：正常开赛
- `48-55`：仅允许 `practice / exhibition`
- `<48`：取消，不产出 multiplier
- 目标桌规模：`8`
- `7/9` 仅作平衡座位补位
- `10` 人桌在 Alpha 关闭
- Alpha launch 默认：
  - `1` 场 rated tournament
  - `1` 场 practice tournament

Alpha 默认开赛时段：

- `09:00 UTC`
- `17:00 UTC`

## 8.4 multiplier 口径

Arena 不直接用单场 `deep run / final table` 给二次加权。

正确链路：

```text
tournament result
-> arena rating update
-> rolling conservative arena skill
-> arena_multiplier
```

Alpha 默认：

- `arena_multiplier = 0.96 .. 1.04`
- `rolling_window = last 20 eligible tournaments`
- `beta = 0.015`
- rated multiplier 只从 human-only rated tournaments 产生

当前 runtime：

- 已实现最小 `arena result -> arena_multiplier` ingestion
- 输入通过 admin 写入口提供已完赛 tournament 结果，不实现 Arena runtime 本身
- `practice` 和非 `human_only rated` 结果只存档，不更新 multiplier
- 前 `15` 场 eligible tournaments 强制 `arena_multiplier = 1.00`
- 当前 runtime 直接把 `arena_score ∈ [-1, 1]` 视为 conservative-skill proxy
- 当前 runtime 尚未实现独立的 Arena `mu/sigma` 和 Arena 专属 `public ELO`

## 8.5 可见信息

Arena 的实时排名是 **tournament-scoped**，只在 `hand close` 后刷新官方 standing。
长期 `public ELO` 只在 tournament 进入 `RATED` 后更新，不做逐手刷新。

live 期间只显示：

- 当前 table 公共动作
- 当前 table stack
- 当前 arena standing snapshot
- players remaining
- blind level

不显示：

- 对手真实 miner id
- 对手长期 ELO
- 内部 rating
- 风控分
- shadow-bot 身份
- multiplier 草算值
- practice/exhibition 不显示对 multiplier 的任何影响

---

## 9. Harness Core

## 9.1 统一抽象

Harness Core 统一抽象为：

```text
Registry
-> Snapshot
-> Feature Build
-> Pack Publish
-> Commit/Reveal or Action
-> Outcome
-> Score
-> Rating
-> Risk
-> Settlement
-> Replay / Read Model
```

## 9.2 必要模块

- `Registry / Policy Control Plane`
- `Feed Ingestors`
- `Scheduler / Clock Authority`
- `Snapshot Freezer`
- `Feature Builder`
- `Noise Injection`
- `Task Adapters`
- `Pack Publisher`
- `Submission Gateway`
- `Ground Truth / Outcome Service`
- `Scoring Engine`
- `Rating Engine`
- `Anti-Abuse Engine`
- `Settlement Engine`
- `Chain Adapter`
- `Replay / Audit`
- `Leaderboard / Read Model Projector`

## 9.3 三个新增关键模块

这轮评审后新增锁定：

1. **ReferencePriceService**
   - 管理 start/end price、fallback hierarchy、void logic

2. **BaselineForecaster**
   - 公开可复算地产出 `baseline_q`

3. **Artifact Store Abstraction**
   - 统一存储 snapshot、noise、pack、replay 大对象

详细后端链条见 [docs/HARNESS_BACKEND_ARCHITECTURE.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_BACKEND_ARCHITECTURE.md)。

---

## 10. 公平性、trust boundary 与 anti-farm

## 10.1 Alpha 能承诺什么

Alpha 能承诺的是：

- 中心化运营下的 **可审计长期公平**
- 统一官方快照
- 统一评分版本
- 可回放和可复算
- 压低低成本撸毛收益

Alpha 不能承诺：

- 绝对防作弊
- 无需信任的完全公平
- 完全去中心化结算

## 10.2 风险主线

V1 主要攻击面：

- Sybil farming
- copy-trading
- latency gaming
- replay attacks
- pack overfitting
- arena soft-play / chip-dumping / collusion
- leaderboard gaming
- cross-lane exploitation

## 10.3 默认防护

- `canonical snapshot freeze`
- `commit-reveal`
- `probation`
- `reward maturity escrow`
- `risk-adjusted discount`
- `hidden audit lanes`
- `copy-trade detector`
- `arena collusion graph`
- `arena bot_adjusted policy`
- `arena final-table no-bot rule`
- `pack diversity budget`
- `operator accountability`

## 10.4 执法梯度

默认采用：

```text
rating decay
-> reward discount
-> delayed maturity
-> multiplier clamp
-> freeze / manual review
-> slash (only for provable protocol abuse)
```

`slash` 只用于强证据协议滥用，例如：

- 伪造签名
- 重放提交
- 篡改 payload
- 绕过 commit-reveal
- 明确伪造身份材料
- 高置信协同操纵

性能差、过度自信、低校准、弱相关可疑行为，优先走评分和奖励层面的衰减，不直接罚没。

## 10.5 公开与隐藏边界

应公开：

- 数据源
- 评分原则
- baseline 口径
- multiplier 上限
- settlement 版本
- void / delay 记录

应隐藏：

- 风控阈值
- shadow packs / shadow tables
- cluster heuristics
- probation 细阈值
- 内部 risk score
- bot 或 shadow 参与身份

## 10.6 Alpha 默认运营参数

### cross-account policy

- 系统不把“多账户”当作产品特性对外承诺
- 内部允许 linked accounts 被识别为同一 **cluster**
- 当前原型的 `economic_unit_id` 由服务端派发，不接受客户端自报作为 truth source
- 当前 runtime 使用 **服务端证据图** 做最小 cluster：
  - exact client IP
  - user-agent hash
  - 连通分量闭包
- 这意味着 `A` 与 `B` 共享 IP、`B` 与 `C` 共享 user-agent 时，`A/B/C` 会被收进同一 economic unit
- 高置信 cluster 在同一 `task_run` 只允许一个 reward-eligible submission
- 同 cluster 的额外提交只进入 audit，不产生 direct ticket
- 当前 runtime 会为这两类情形自动创建 open risk case：
  - `economic_unit_cluster`
  - `economic_unit_duplicate`
- 同 cluster 账户不应高频进入同一 Arena 桌
- 同 cluster 不共享新号 probation 豁免

设计原则：

- `true alpha` 的高质量 miner 是系统想吸引的对象，不是 abuse
- anti-abuse 的目标不是压制真正有 edge 的高手
- anti-abuse 的目标是压制 `copy market`、`baseline nudge`、`multi-account amplification`、`selective participation`
- 顶级 miner 可以赢，但不能以近乎零边际成本把同一套 alpha 放大成多份主要奖励

### reward maturity

- `admission_hold`: 当前原型使用 `7d` 或 `500` 个 fast reveals 作为 graduate gate；在此之前，`20%` 立即释放，`80%` 进入 held rewards
- daily reveal gate 仍保留在目标设计里，但当前 runtime 还没有把 daily lane 接到 release gate
- `clean_established`: `70%` 在 reward window `FINALIZED` 后可领取，`30%` 进入 `72h` maturity
- `new_or_probation`: `20%` 可领取，`80%` 进入 `7d` maturity
- `monitored`: `0%` 立即释放，`100%` 进入 `14d` hold
- `frozen`: 不释放，等待 review

说明：

- 在真正的外部 stake/bond 之前，`admission_hold` 是 Alpha 的资本约束层
- 当前原型已经实现 `reward_hold_entries` ledger，并在 miner graduate 时按 ledger 释放 held rewards
- 仍未实现的是更细粒度的 forfeiture / manual-review / partial-release surfaces
- 对外叙事应写成 `held rewards can be forfeited for provable abuse`，而不是强表述 `slash`

### anti-abuse 自动权限上限

- 自动系统最多可施加 `25%` 的 reward discount
- 自动系统最多可将 `arena_multiplier` 上限钳制到 `1.00`
- 超过该阈值必须进入人工 review
- `held` 状态必须在 `72h` 内进入人工 review，否则自动降级到较轻限制

### retention policy

- raw feeds：`30d hot + 180d cold`
- snapshot / feature / pack / replay artifacts：`180d hot + 365d cold`
- device/network 指纹：`90d rolling`
- risk cases / operator overrides：`365d`

### public ELO cadence

- Arena `public ELO` 在 tournament `RATED` 后更新
- 全局 public ladder 每 `60m` 发布一次快照
- 任何 public ladder 都只使用 finalized rating snapshot

---

## 11. 矿工体验、运营与可解释性

## 11.1 必须有的 miner 可解释层

V1 上线前必须有：

- `Companion State`
  - current work
  - current activity
  - daily brief status
  - mood / availability
  - “我的 buddy 最近在做什么”

- `Score Explanation`
  - `baseline_q`
  - `my p`
  - `outcome`
  - `edge`
  - `ticket earned`
  - `calibration impact`
  - `reliability impact`

- `Reward Timeline`
  - fast tickets
  - slow direct score status
  - arena multiplier
  - anti-abuse discount
  - season bonus
  - maturity status

- `Trust & Audit Card`
  - snapshot hash
  - reference source
  - settlement version
  - provisional/final 状态

## 11.2 必须有的 operator surfaces

这些面板是 **内部运营面**，不是矿工主产品层。矿工只应看到经过裁剪的 companion-facing 子集。

最少 5 个后台面板：

- `Market Ops`
- `Settlement Ops`
- `Arena Ops`
- `Abuse Review`
- `Support Console`

当前这个 forecast-first 分支里，已经真正落地的是最小可用子集：

- `Settlement Ops`
  - `reward_window rebuild`
  - `settlement_batch retry-anchor / submit-anchor`
  - `anchor_job build-plan / broadcast / confirm`
- `Abuse Review`
  - `risk case` queue
  - operator `clear / suppress / escalate`
- miner / operator 共享的 read surfaces
  - latest `reward_window`
  - latest `settlement_batch`
  - latest `anchor_job`

仍然明确 deferred：

- `Market Ops`
- `Arena Ops`
- `Support Console`
- background reconciler / payout execution

## 11.3 观测与 SLO

最少监控：

- `pack generation latency`
- `commit acceptance rate`
- `reveal completion rate`
- `settlement lag`
- `leaderboard freshness`
- `replay parity`
- `feed quality`
- `market-copy rate`
- `collusion suspicion rate`

## 11.4 事件分类

必须建立统一 `Event Taxonomy` 和 warehouse schema，避免后续分析、客服、风控和回放各自建模。

---

## 12. Rollout 策略

当前 rollout 从“功能顺序”升级为“带 exit criteria 的上线策略”：

除协议链路外，companion shell 还必须满足以下 go/no-go 条件：

- companion activation 路径可用
- companion state store 可用，不能只依赖 session transcript
- macOS menu bar / TUI / Control UI 至少有两个 surfaces 能正确显示 current work
- `/buddy`、`/status`、`/activities`、`/checkin` 控制链路可用
- daily brief 可选且不影响奖励
- V1 不依赖 Electron

1. **offline replay**
   - 历史数据回放
   - 核验 ticket / rating / discount 分布

2. **internal shadow**
   - 内部账户跑完整链路
   - 不发真实奖励
   - 必须同时跑：
     - copy-bot
     - baseline-nudge bot
     - multi-account spray cluster
     - delayed-reveal / no-reveal bot
     - Arena collusion bot

3. **invite-only, no rewards**
   - 只开放 15m lane
   - 看提交成功率、回放一致性、客服压力

4. **limited rewards, 15m only**
   - 小规模真实奖励
   - probation 和 maturity 生效
   - Daily 仅作 anchor，不作 direct reward

5. **daily lane on**
   - 先引入 daily anchor
   - slow direct score 继续 shadow，不立即发奖

6. **arena multiplier low-cap**
   - 先用 `0.96..1.04`
   - 只接 human-only rated tournaments
   - practice tournaments 不接入 multiplier

每个阶段必须有 go/no-go 指标：

- settlement 错误率
- replay mismatch
- support case volume
- abuse false positive rate
- feed quality
- copy-market bot ROI
- multi-account spray cluster ROI
- Arena rated fill rate
- bot-adjusted rated count = 0

---

## 13. Alpha 默认参数收口

这一版默认值已经收口为：

1. `baseline_q = 0.85 * q_pm + 0.15 * q_bin`，Polymarket 不健康时退化为 `q_bin_only`
2. `ReferencePriceService` 使用 `commit_close_ref_price + end_ref_price` 两点结算，基于 `5s midpoint TWAP`
3. fast lane `commit_deadline = T+3s`，`reveal_deadline = T+13s`
4. fast lane 评分使用 `pure improvement + direction bonus + anti-copy cap`
5. daily lane 固定 `00:00 UTC` 发布，`24h` 后 cutoff，day-1 只作 anchor，不作 direct reward
6. high-confidence cluster 在同一 `task_run` 只允许一个 reward-eligible submission
7. `admission_hold` 作为 Alpha 资本约束层；`new_or_probation = 20/80`
8. public ladder 每 `60m` 刷新一次，Arena `public ELO` post-rating 更新
9. Arena day-1 采用 `1 rated + 1 practice`，`0.96..1.04` cap，最近 `20` 场窗口
10. Poker MTT 若启用，按独立 `poker_mtt_daily` / `poker_mtt_weekly` 子预算窗口结算，Phase 1 不做单场即时发奖

---

## 14. 最终结论

ClawChain V1 不应再回到：

- 题库挖矿
- 签到挖矿
- 先来先得倍率
- 自由文本 bluff 主赛道

当前唯一自洽的方案是：

> **对矿工来说：先拥有一个 companion-first mining buddy；对协议来说：15m forecast mining 做主赛道，daily lane 做慢反馈校准，tournament-like Simplified Bluff Arena 做泛能力 multiplier，Harness Core 做统一基础设施。**

这套方案满足：

- **有吸引力**：真实 crypto 数据、快反馈、公开竞争
- **更合理**：奖励超越市场的信息价值，而不是在线时长
- **anti-farm**：复制市场、多号、脚本、跟单难以长期获利
- **工程可做**：不依赖在线 LLM judge，核心链路可 deterministic replay

这应作为 ClawChain 当前唯一对内和对外一致的 V1 基线：**companion-first shell + forecast-first protocol**。

# Poker MTT 奖励 / Multiplier / Reputation 集成设计

**版本**: 0.1
**日期**: 2026-04-10
**状态**: Phase 1 设计 + 实现状态对齐；2026-04-17 已补 Poker MTT Evidence Phase 2 local beta / harness gate 口径
**范围**: `poker mtt` 独立产品线，不混入现有 `arena / bluff arena` 语义
**依赖前提**: `docs/POKER_MTT_SIDECAR_INTEGRATION.md`
**Phase 2 执行源头**: `docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2.md`
**Phase 2 TDD 执行清单**: `docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2-tdd-execution.md`
**Phase 2 Harness Specs**: `docs/POKER_MTT_PHASE2_HARNESS_SPECS.md`

---

## 1. 文档目的

这份文档回答四个具体问题：

1. `poker mtt` 的奖励是不是应该从“单场发大奖”改成“单场小奖励 + 日/周窗口主奖励 + rolling rating / multiplier”
2. 你提出的 `tournament_result + hidden_eval + consistency_or_rating` 三层评分，能不能接到当前代码
3. `x/reputation` 现在到底适不适合直接承接 `poker mtt` 的主评分
4. `poker mtt` 的结果、奖励和 multiplier 应该怎么和链集成

本文档只做一件事：

**把 `poker mtt` 的奖励、multiplier、隐藏评测、长期信誉、链锚定分成清晰的四层，并明确每一层应该落在哪个系统里。**

---

## 2. 结论先行

### 2.1 总结论

你的 review 方向是对的，而且比“按单场发大奖”更适合当前这套系统。

推荐结构如下：

- 单场只发小奖励，不发决定性大奖
- 主奖励改成日榜 / 周榜结算
- multiplier 改成慢变量，按窗口或滚动样本缓慢变化
- hidden evaluation 用来压 solver edge、压运气、压多号收益
- `reputation` 不做主评分引擎，只做长期信誉层
- 链上先做 settlement anchor，不做逐手或逐场实时上链

### 2.2 最重要的架构判断

`poker mtt` 这条线里，必须把下面三种东西拆开：

1. **快变量**
   - 单场名次
   - 单场积分
   - 单场 hidden eval
   - 单场 multiplier 输入样本

2. **慢变量**
   - rolling rating
   - multiplier
   - reputation tier
   - streak / reliability

3. **链上变量**
   - 日/周结算窗口
   - canonical root
   - reward window / settlement batch anchor

如果把这三类东西混在一起，后面一定会出现：

- 单场 luck 被过度放大
- solver 的局部 edge 被直接变现
- 多号刷局和低质量 volume 被奖励
- 链上状态频繁抖动，且难以审计

### 2.3 本轮综合评审后的冻结口径

结合 `clawchain` GitNexus、`lepoker-auth` GitNexus、现有产品文档和链集成代码，本轮进一步冻结以下口径:

1. `poker mtt` 是 ClawChain 的**独立 skill-game mining lane**，不改名为 arena，也不复用 `arena_result_entries` 的业务语义
2. `lepoker-gameserver` 参考 runtime / table / ws / live ranking；`lepoker-auth` 参考 auth / MQ / final ranking / HUD / hand history / ELO / admin read model
3. ClawChain 第一阶段主真相仍在链下: raw hand history 和结果投影先落库，链上只锚定窗口级 `settlement_batch`
4. `live_ranking`、`final_ranking`、`long_term_ranking` 必须分开；只有 `final_ranking` 派生出的锁定结果能进 reward window
5. `short_term_hud` 与 `long_term_hud` 必须分开；前者服务 hidden eval / 风控，后者服务 rating / multiplier / long-term reputation
6. ELO / public rating 是长期展示和匹配信号，不是直接奖励权重
7. `x/reputation` 是长期信誉层，只接窗口级慢变量结果，不接原始牌谱、单场 hidden eval 或单场 total score
8. `total_score` 是内部 reward / audit score，不是公开排行榜分数；公开展示只用 `poker_mtt_public_rank` / `poker_mtt_public_rating`
9. `poker_mtt_daily` / `poker_mtt_weekly` 必须来自同一 CLAW miner emission budget 的显式配置切片，不能创造额外奖励池
10. Phase 1 不做单场即时发奖；所谓“单场小奖励”只作为窗口内 score component 或展示项，后续若启用也必须从日/周窗口预算里扣
11. settlement 只消费 `locked` / `anchorable` 结果；`live_ranking`、未锁定 final ranking、未完成 hidden eval、证据不完整的结果都不能进入最终 anchor
12. donor 的 `tournament_id` 在现有 settlement schema 里先映射到 `task_run_ids_root` 对应的 activity run 集合；后续可把字段泛化为 `activity_run_ids_root`
13. controlled bot / shadow samples 属于 hidden evaluation evidence，不改变 public rated tournament 的 `human_only` 口径；如果 bot 进入公开对局，则该样本不得进入 human-only multiplier
14. Go 版实现边界优先按仓库现有 `arena/*` 风格新开顶层 `pokermtt/*`，不要放进 `arena/*`，也不要把 donor Java structs 穿透进 ClawChain domain model
15. Phase 1 reward / settlement 必须有显式 rollout gate：默认不自动打开 `poker_mtt_daily` / `poker_mtt_weekly` 发奖，也默认不把 poker MTT settlement batch 锚上链

### 2.3.1 2026-04-17 Phase 2 综合评审后的新增冻结口径

这轮 Phase 2 不是 ClawChain 产品总 Phase 2，也不是链上 reputation Phase 3。为了避免文档混淆，后续统一叫：

**Poker MTT Evidence Phase 2**

新增冻结口径：

1. Phase 2 的主目标是 evidence-backed rewards beta：把 raw completed hand、HUD、hidden eval、rating / multiplier snapshot、reward projection root、settlement anchor verification 补成可审计链路
2. Phase 2 先扩 `mining-service` 的 evidence / scoring / snapshot / settlement 合约；Go 侧优先补 durable finalization worker 和 typed handoff，不迁移奖励公式
3. `poker_mtt_history.py` / `poker_mtt_hud.py` 当前是 in-memory / disabled-by-default 语义，不能被描述为生产 evidence store
4. hidden eval 必须由服务端从 sealed inputs、hand history、HUD、baseline / control samples 生成；legacy/admin apply 不能凭请求字段提供 reward-ready hidden score
5. DynamoDB 是 completed-hand hot store 的优先生产候选，但 ClawChain domain 只依赖 hand evidence store interface；本地和测试可以先用 Postgres / fake repository
6. `x/settlement` 现在是 tamper-evident root registry，不是链上发奖执行器；Phase 2 必须补 anchor query 和 state-confirmation，不只看 tx code
7. `x/reputation` 暂不进入 Phase 2 写路径；它要等 window-level reputation delta schema 和 correction policy 成熟后再接
8. 10k-20k MTT 目标要求 indexed reward-window queries、paged artifacts、observability 和 staged load tests；不能长期依赖 all-result scans 或单 payload 装完整 miner rows

### 2.4 术语表

| 术语 | 本文档含义 |
|------|------------|
| `poker mtt` / `Poker MTT` | 独立 skill-game mining lane，不是 `arena` mode |
| `arena` | forecast/bluff arena 线的 tournament-like multiplier，不等于 Poker MTT |
| `live_ranking` | 赛中展示 / 恢复 / 观测，不进 reward window |
| `final_ranking` | 完赛 canonical standings，进入 `poker_mtt_result_entries` 的唯一排名输入 |
| `long_term_ranking` | public rating / ladder / quality snapshot，不直接发币 |
| `short_term_hud` | 最近手牌窗口的行为特征，服务 hidden eval / risk |
| `long_term_hud` | 长期 HUD aggregate，服务 consistency / multiplier / reputation delta |
| `public_rating` / ELO | 展示、匹配、风控辅助；不进入正向 reward weight |
| MQ / event bus | donor transport 或 ClawChain event input，不是 scoring engine |
| `settlement_batch` | 窗口级链锚定载体，不承载逐手或逐场实时发奖 |

---

## 3. 当前代码里的现成落点

## 3.1 `mining-service` 已经有 multiplier 骨架

当前 `mining-service` 的 `miners` 表已经有这些字段：

- `arena_multiplier`
- `public_rank`
- `public_elo`
- `model_reliability`
- `ops_reliability`

这说明系统已经接受一种“链下评分 -> 慢变量 -> 对外展示 / 奖励修正”的模式。

## 3.2 现有 arena result 流程能作为 `poker mtt` 的模板，但不该直接复用语义

当前 `apply_arena_results()` 会：

- 接收一场比赛结果
- 为每个 miner 写一条 result entry
- 对 rated + human-only 结果计算 `conservative_skill`
- 把 multiplier 缓慢更新到一个有界区间

这条路径很适合拿来做模板，但不建议直接把 `poker mtt` 写进现有 `arena_result_entries` 和 `arena_multiplier`：

- 现有 `arena` 语义来自 forecast / bluff arena 线
- `poker mtt` 的评分成分更多，包含排名、ICM、hidden eval、consistency
- 以后如果把两种 multiplier 混写到同一个字段，解释和审计都会变脏

**建议：复用机制，不复用业务字段名。**

## 3.3 现有 settlement anchor 路径已经能承接 `poker mtt`

当前系统已经有：

- `reward_windows`
- `settlement_batches`
- `MsgAnchorSettlementBatch`
- `build_anchor_tx_plan`

这意味着：

- `poker mtt` 不需要一上来就做链上逐人逐场发奖
- 先做链下聚合、链上锚定，是当前最顺的路径

## 3.4 当前 `poker mtt` 代码现实

当前 `clawchain` 已经有一条最小结果入口，不是完整 runtime:

- `mining-service/models.py`
  - `poker_mtt_tournaments`
  - `poker_mtt_final_rankings`
  - `poker_mtt_result_entries`
- `mining-service/server.py`
  - `POST /admin/poker-mtt/final-rankings/project`
  - `POST /admin/poker-mtt/results/apply`
  - `POST /admin/poker-mtt/reward-windows/build`
- `mining-service/forecast_engine.py`
  - `project_poker_mtt_final_rankings()`
  - `apply_poker_mtt_results()`
  - `build_poker_mtt_reward_window()`
  - `_build_poker_mtt_reward_windows()`

这条路径当前已经做了:

- 接收已完赛 tournament 结果
- 先保存 canonical `poker_mtt_final_rankings`，再投影 reward-bearing `poker_mtt_result_entries`
- 计算 `0.55 tournament_result + 0.25 hidden_eval + 0.20 consistency_input`
- 写入 `poker_mtt_result_entries`
- 对 `rated + human_only` 结果更新独立的 `poker_mtt_multiplier`
- 生成 `poker_mtt_daily` / `poker_mtt_weekly` reward window
- 复用 settlement batch / anchor payload 链路
- `poker_mtt_reward_windows_enabled` 控制自动日 / 周窗口生成
- `poker_mtt_settlement_anchoring_enabled` 控制 poker MTT settlement batch 进入 anchor payload
- `poker_mtt_hud` 只提供 disabled-by-default 的 hot-store / manifest hook，不在 Phase 1 计算完整 HUD/ELO reward weight
- legacy/admin `apply_poker_mtt_results()` 只有在 refs 能对上已保存 canonical final ranking 时才允许 reward-eligible
- `x/settlement` anchor submitter 必须来自 genesis `authorized_submitters`，默认无授权 submitter 时不能写链上 anchor

它当前还没有做:

- raw hand history ingest
- MQ consumer
- full short-term HUD / long-term HUD projector
- ELO / public rating projector
- `reputation_delta` 输出
- final standings 的完整 canonicalization
- hidden eval 的真实 seed/bot/shadow replay pipeline

所以工程口径应当是:

**先把 donor sidecar 的最终 standings 和 raw hand history 接进这条最小结果入口，再逐步补 HUD / ELO / reputation，而不是把 Java control plane 整体搬进 ClawChain。**

## 3.5 donor 参考代码库

当前 `poker mtt` 这条线已经有两份 donor 参考库，职责不要混看：

- `lepoker-gameserver`
  - 主要参考 runtime、table orchestration、ws、live ranking、比赛进程
  - 参考文档见 `docs/POKER_MTT_SIDECAR_INTEGRATION.md`
- `lepoker-auth`
  - 主要参考 auth、MQ consumer、hand history、HUD、MTT control/read model、admin feature surface
  - 参考文档见 `docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md`

后续如果问题是“比赛怎么跑”，优先看 `lepoker-gameserver`。
如果问题是“结果怎么存、榜怎么做、HUD 怎么算、auth 怎么接”，优先看 `lepoker-auth`。

---

## 4. 产品层设计

## 4.1 不再按单场发大奖

单场奖励只承担三个职责：

- 激励参赛
- 激励打完
- 给后续 rating / multiplier 积累样本

单场奖励不应该承担“定义谁是最终赢家”的职责。

推荐的单场奖励结构：

- 参赛基础奖励：只要完成有效参赛即可获得
- 打完奖励：完成比赛且没有提前逃逸、没有明显异常行为
- 少量名次奖励：前若干名有轻量加成

不建议：

- 冠军吃走绝大部分奖励池
- 单场 multiplier 大幅波动
- 单场成绩直接改写长期信誉

## 4.2 主奖励改成日榜 / 周榜窗口

主奖励应该在窗口上发，而不是在单场上发。

推荐两层窗口：

- `daily`
  - 更快反馈
  - 让新用户也有明确目标
- `weekly`
  - 作为主奖励池
  - 平滑运气和样本噪音

窗口奖励的直接好处：

- 降低单场 lucky run 的收益占比
- 把“稳定参加 + 稳定赢率”变成主要激励
- 更适合和链上的 `reward_window` / `settlement_batch` 对齐

## 4.3 multiplier 应该是慢变量

multiplier 不该是“这局打赢，下一局立刻翻倍”。

推荐把 multiplier 定义成：

- 来源于最近 `N` 场的滚动表现
- 只在达到最小样本后才生效
- 变化有上下限
- 每次更新幅度非常小

这和当前 `arena_multiplier` 的思路是一致的，只是 `poker mtt` 应该有自己独立的字段和样本。

---

## 5. 评分模型设计

## 5.1 总分结构

推荐采用你提出的三段式：

```text
TotalScore =
  0.55 * tournament_result_score
  + 0.25 * hidden_eval_score
  + 0.20 * consistency_score
```

它适合作为：

- 日榜 / 周榜排序输入
- multiplier 的主要更新输入
- 公开 leaderboard 和私有审计报表的共同基础

## 5.2 三个分量分别代表什么

### A. `tournament_result_score`

公开成绩层。

建议包含：

- 实际最终名次
- 参赛人数归一化
- 可选的 ICM-style placement score
- 可选的生存时长 / 晋级层级

不建议只用最终名次整数做线性评分。
更合理的是“按 field size 归一化后的 percentile / payout-equivalent score”。

### B. `hidden_eval_score`

隐藏评测层。

它不直接向用户解释全部细节，只用于：

- 压 solver 在某些桌型里的局部 edge
- 压短样本 lucky heater
- 压多号靠 volume 抢榜

推荐来源：

- hidden seed tables
- baseline bot tables
- shadow replay / shadow payout evaluation

### C. `consistency_score`

稳定性层。

建议来源：

- 最近 `N` 场的 rolling score 均值
- 最近 `N` 场的方差惩罚
- 最低参赛样本门槛
- 异常行为扣分

它的目标不是奖励 volume 本身，而是奖励：

- 有足够样本
- 样本质量正常
- 结果稳定，不是纯靠 heater

### D. `rating / ELO`

长期公开 rating 层。

`lepoker-auth` 的 `EloService` 可以作为参考，但在 ClawChain 里它不属于 `TotalScore` 的直接分量。

推荐用途:

- public ladder
- 匹配 / seat quality
- 长期实力展示
- 风控和异常样本解释

不推荐用途:

- 直接乘以窗口奖励
- 直接替代 `consistency_score`
- 直接替代 `reputation`

原因是 ELO 容易被赛制、样本量、对手池、配桌策略影响；它适合做长期状态，不适合做第一阶段发币权重。

### E. `short_term_hud / long_term_hud`

HUD 应该进入 hidden eval 和 consistency，但不要以原始指标直接发币。

建议:

- `short_term_hud`
  - 来自最近手牌
  - 输入 hidden eval / risk flag / action style classifier
  - 例: VPIP、PFR、3-bet、c-bet、WTSD、WSSD、异常跟注/弃牌/全下频率
- `long_term_hud`
  - 来自日维度 / rolling 维度
  - 输入 `consistency_score`、`poker_mtt_multiplier`、long-term risk review
  - 例: 长期 VPIP/PFR、长期 ITM、长期 win/profitable、长期 showdown 质量

这样做比“把 HUD 做成奖励公式的一堆可见参数”更稳，因为可见参数会快速变成刷榜目标。

## 5.3 分值归一化建议

三个分量必须先归一化到相同区间，再加权。

推荐统一到 `[-1, 1]` 或 `[0, 1]`。
为了和当前 arena 流程保持一致，更推荐 `[-1, 1]`。

推荐约束：

- `tournament_result_score in [-1, 1]`
- `hidden_eval_score in [-1, 1]`
- `consistency_score in [-1, 1]`
- `total_score in [-1, 1]`

这样后续 multiplier 公式可以直接沿用当前的“有界、慢更新”思路。

## 5.4 内部分数、公开分数与窗口权重

`total_score` 包含 hidden eval 和 consistency，因此只能作为内部 reward / audit score。

公开侧必须拆开：

- `poker_mtt_public_rank`
- `poker_mtt_public_rating`
- `poker_mtt_public_score`（如果需要，只能由可公开解释的 final ranking / public rating 派生）

公开榜不能直接展示 hidden-eval-derived `total_score`，否则长期会泄露 hidden seed、bot pool、shadow payout policy 的相对权重。

窗口分配建议：

- `reward_weight = max(0, total_score)`，避免负分消耗奖励池
- 同一 `economic_unit_id` 在同一 tournament / window 只能有一个 reward-eligible canonical entry
- re-entry 必须折叠到 canonical miner result，并保留 `reentry_count` 作为审计字段
- 如果一个窗口所有 eligible rows 的 `reward_weight = 0`，该窗口不应按名次强行平分；建议进入 `no_positive_weight` 状态，预算回滚或滚入下一窗口，具体由 reward policy 版本定义

这可以避免“多打很多场，只累计正分、负分归零”的 volume grinding。

---

## 6. Hidden Evaluation 设计

## 6.1 hidden eval 的定位

hidden eval 不是另一套公开比赛。
它是公开比赛结果之外的“私有质量评分层”。

它有三个核心目标：

1. 把单场 luck 从主奖励里稀释掉
2. 让纯 solver 本地最优策略难以稳定套现
3. 给反作弊和多号风控留一个隐式观察面

## 6.2 推荐的第一版 hidden eval

第一版不要做太复杂，建议按下面优先级：

### 第一优先级：hidden seed tables

做法：

- 同结构比赛
- 局部 seating / blind / table split 采用隐藏 seed
- 用户无法预知自己落在哪类桌面样本

作用：

- 打断固定脚本化 exploit
- 增加跨桌样本的不可预测性

### 第二优先级：baseline bot tables

做法：

- 在部分 hidden eval 样本里引入固定策略、受控 bot pool
- 不是为了替代真人对局，而是为了构造可比较基线

作用：

- 看玩家在稳定 baseline 对手上的表现
- 给 solver / bot / collusion 检测提供对照样本

注意：

- 如果 baseline bot 只出现在 hidden evaluation / shadow evidence 中，它不改变公开 rated tournament 的 `human_only` 口径
- 如果 bot 进入公开牌桌或公开比赛路径，该样本不得进入 `human_only` multiplier / 主奖励高权重路径
- bot pool、seed group、shadow policy 都必须版本化并进入 evidence manifest，但不能公开到用户侧

### 第三优先级：shadow payout / shadow replay

做法：

- 对相同 hand history 或相同阶段样本
- 用不同 payout / ICM / risk-adjusted scheme 离线重评分

作用：

- 检查某些“只适合单一 payout”的 exploit 是否只是局部最优

这个阶段复杂度最高，建议放到 V2。

## 6.3 hidden eval 不应该怎么用

不建议：

- 把 hidden eval 直接变成单场现金奖励
- 比赛结束立即公开 hidden eval 分数
- 对 hidden eval 的具体抽样规则完全透明
- 让 hidden eval 直接决定封禁

正确用法是：

- 作为 `total_score` 的一个组成部分
- 作为 multiplier 和风险评估的一个慢变量输入
- 延迟结算、延迟披露或只披露区间，不披露全部细节

---

## 7. Multiplier 设计

## 7.1 multiplier 的目标

multiplier 应该只承担一件事：

**把长期稳定优质样本轻微放大，把长期低质样本轻微压缩。**

它不是主奖励本身，也不是封禁工具。

## 7.2 multiplier 推荐公式

推荐沿用当前系统的“保守 multiplier”风格：

```text
rolling_skill = avg(last_N total_score)
multiplier = clamp(1.0 + k * rolling_skill, lower_bound, upper_bound)
```

第一版参数建议：

- `N = 20`
- 最小生效样本 `min_samples = 16`
- `k = 0.015 ~ 0.025`
- `lower_bound = 0.96`
- `upper_bound = 1.04`

也就是说：

- 样本不足时 multiplier 固定为 `1.0`
- 样本足够后缓慢上/下调
- 不允许出现大于 `4%` 的短期抖动

## 7.3 multiplier 更新频率

建议两种做法二选一：

- 每场结束后更新 rolling state，但只在日结算时正式生效
- 每场结束后就更新，但对外只在下个窗口展示

两者里更稳的是第一种，因为更便于审计和回滚。

## 7.4 multiplier 作用面

建议 multiplier 只作用在：

- 窗口奖励分配
- 某些 admission / seat quality 权重

不建议 multiplier 直接作用在：

- 单场 buy-in
- 单场起始筹码
- 单场盲注结构

否则会破坏比赛公平性。

---

## 8. `reputation` 的正确定位

## 8.1 `x/reputation` 当前真实能力

当前 `x/reputation` 实际上已经能做：

- 存矿工分数
- 更新分数
- 计算 level
- 更新 streak
- 触发 suspend event

但它当前还不适合直接承接 `poker mtt` 主评分，原因有四个：

1. 当前模块偏底层 KV 状态，不是完整评分服务
2. `RegisterServices()` 还是空的
3. `challenge` 依赖的接口和 `reputation` keeper 实际暴露的方法签名不一致
4. `app` 里虽然初始化了 keeper 和 module，但没有形成完整闭环

## 8.2 适合怎么融合

推荐把 `reputation` 当成长期信誉层，而不是比赛结果层。

适合放进去的东西：

- 长期活跃度
- 长期违规惩罚
- 长期可靠性 tier
- streak bonus
- 低信誉阈值后的降权或暂停资格

不适合现在放进去的东西：

- 单场 `total_score`
- hidden eval 原始分
- 每场 multiplier 结果
- 日榜 / 周榜的完整排序依据

## 8.3 推荐融合方式

推荐结构：

- `poker mtt` 主评分、日榜、周榜、multiplier 全部链下算
- 每个窗口产出一份聚合后的信誉增量
- 由授权的 settlement / controller 逻辑把“缓慢变化后的长期信誉结果”写入 `x/reputation`

也就是说：

- `reputation` 接的是**压平后的长期结果**
- 不是原始比赛明细

## 8.4 为什么这样分层更稳

因为 `reputation` 的语义应当是：

- 持久
- 保守
- 可解释
- 不容易频繁回滚

而 `poker mtt` 的单场评分恰好相反：

- 高频
- 带噪音
- 包含私有 hidden eval
- 需要不断调参数

这两层语义天然不该混在一起。

---

## 9. 数据面设计

## 9.1 不建议直接复用 `arena_result_entries`

虽然当前已有 `arena_result_entries`，但 `poker mtt` 建议新开表或新开一组模型。

推荐原因：

- 语义独立
- 未来字段会更丰富
- 可以避免和现有 `arena` 排行、elo、multiplier 串义

## 9.2 第一阶段存储原则

第一阶段推荐采用混合存储，而不是把所有数据硬塞进一个库：

- **DynamoDB**
  - 承接 `poker mtt` 的高并发热写入
  - 保存 raw hand history
  - 保存 table 级热状态和上传游标
- **Postgres**
  - 承接赛果、multiplier、rating、leaderboard、reward window、settlement
  - 承接所有需要聚合、排序、窗口结算和链锚定的数据
- **S3**
  - 第一阶段不是主路径
  - 只作为后续冷归档或历史压缩迁移目标

这个分层的原因不是“技术栈偏好”，而是三种数据的访问模式完全不同：

- raw hand history 是高写入、按手 append、按桌顺序读取
- 赛果和 multiplier 是低频写入、高聚合、高审计需求
- settlement 是窗口级聚合和链锚定输入

**第一阶段冻结原则：**

- 不把每个 action 单独永久写入
- 不把 DynamoDB 当作结算和复杂查询主库
- 不把 Postgres 当作 raw hand history 热写入库

## 9.3 DynamoDB：raw hand history 与热状态

### A. `poker_mtt_hands`

这一张表保存 raw hand history，推荐粒度为：

- **一手结束后，上传一条 canonical hand record**

不是每个 action 一个 item，而是一手完成后写一条完整记录。

推荐键设计：

- `PK = TOUR#<tournament_id>#TABLE#<table_id>`
- `SK = HAND#<hand_no>`

如果后续发现超大赛事下单桌分区过热，再引入 bucket，不在第一阶段提前复杂化。

每条 hand record 推荐包含：

- `tournament_id`
- `table_id`
- `hand_no`
- `hand_id`
- `started_at`
- `ended_at`
- `button_seat`
- `small_blind`
- `big_blind`
- `ante`
- `seat_map`
- `starting_stacks`
- `hole_cards`
- `board_cards`
- `action_sequence`
- `pots`
- `showdown`
- `ending_stacks`
- `winners`
- `stack_deltas`
- `version`
- `checksum`
- `source_topic`
- `source_partition`
- `source_offset`
- `source_message_id`
- `biz_id`

这里的 `action_sequence` 是完整动作序列，但不重复保存“每一步动作后的全量桌状态快照”。

### B. `poker_mtt_table_state`

这一张表保存桌级热状态和上传游标：

- `tournament_id`
- `table_id`
- `last_completed_hand_no`
- `last_uploaded_hand_no`
- `upload_state`
- `upload_retry_count`
- `last_upload_error`
- `updated_at`

它的主要用途是：

- uploader 断线恢复
- 补传未成功的最近手牌
- 观察当前桌的上传健康度

### C. `poker_mtt_tournament_hot_state`（可选）

如果第一阶段需要管理端快速查看当前比赛热状态，可以再加一张轻量索引表，保存：

- `tournament_id`
- `active_table_count`
- `active_player_count`
- `last_hand_no`
- `updated_at`

这张表不是必须的。
如果运行时已有足够的内存态或 Redis 态，也可以后补。

### D. DynamoDB 写入语义

raw hand history 的推荐写入语义是：

1. 牌局在运行时内存态推进
2. 一手结束
3. 生成 canonical hand record
4. **异步**写入 DynamoDB
5. 写入成功后更新 `table_state.last_uploaded_hand_no`

这里最重要的是：

- **及时上传**
- 但**不阻塞下一手开始**

也就是说，“一手结束后及时上传”不等于“游戏主循环等待上传完成”。

### E. 幂等要求

每手上传必须天然幂等。

推荐约束：

- `hand_id` 全局稳定
- 同一手重传时覆盖同一主键
- 通过 version / checksum 检测重复或异常重写
- 条件写入：低版本消息不能覆盖高版本消息
- 同版本不同 checksum 必须进入 `conflict` / `manual_review`，不能静默覆盖
- `source_message_id` / `biz_id` 只做幂等辅助，canonical key 仍然是 `tournament_id + table_id + hand_no`

### F. item 大小控制

DynamoDB 单 item 上限是 `400 KB`，但第一阶段建议主动设软约束：

- 目标 item 大小：`< 32 KB`
- 警戒线：`64 KB`

超过警戒线时，要审查是不是保存了冗余状态。
如果极少数 hand record 因异常 action log 或 replay payload 超过警戒线，应把大对象冷落到 S3 / object storage，并在 DynamoDB item 里保存 content hash、object key、size、compression 和 schema version。

## 9.4 Postgres：赛果、评分、结算

Postgres 继续承接所有结构化聚合结果。

### A. `poker_mtt_tournaments`

记录一场 MTT 的基础元信息：

- `tournament_id`
- `runtime_source`
- `rated_or_practice`
- `human_only`
- `field_size`
- `buy_in_tier`
- `structure_version`
- `started_at`
- `completed_at`
- `status`
- `policy_bundle_version`

### B. `poker_mtt_final_rankings`

这一层是 `live_ranking` 到 reward input 的 canonical artifact。
它必须在 `poker_mtt_result_entries` 之前生成。

推荐字段：

- `id`
- `tournament_id`
- `source_mtt_id`
- `source_user_id`
- `miner_address`
- `economic_unit_id`
- `member_id`
- `entry_number`
- `reentry_count`
- `rank`
- `rank_state`
- `chip`
- `chip_delta`
- `died_time`
- `waiting_or_no_show`
- `bounty`
- `defeat_num`
- `field_size_policy`
- `standing_snapshot_id`
- `standing_snapshot_hash`
- `evidence_root`
- `evidence_state`
- `policy_bundle_version`
- `locked_at`
- `anchorable_at`
- `created_at`
- `updated_at`

推荐 `rank_state`：

- `ranked`
- `waiting_no_show`
- `unresolved_snapshot`
- `voided`
- `duplicate_entry_collapsed`

只有 `rank_state = ranked` 且证据状态满足 policy 的 row，才能派生出 reward-eligible `poker_mtt_result_entries`。

### C. `poker_mtt_result_entries`

每个矿工在一场 MTT 的主记录：

- `id`
- `tournament_id`
- `miner_address`
- `final_rank`
- `field_size`
- `economic_unit_id`
- `entry_number`
- `reentry_count`
- `finish_percentile`
- `chip_delta`
- `tournament_result_score`
- `hidden_eval_score`
- `consistency_input_score`
- `total_score`
- `eligible_for_multiplier`
- `multiplier_before`
- `multiplier_after`
- `evaluation_state`
- `evaluation_version`
- `rank_state`
- `evidence_root`
- `evidence_state`
- `standing_snapshot_id`
- `standing_snapshot_hash`
- `risk_flags`
- `no_multiplier_reason`
- `locked_at`
- `anchorable_at`
- `anchor_state`
- `created_at`
- `updated_at`

Phase 1 的 reward-bearing 入口只接受 canonical final ranking 派生结果。Legacy/admin apply 可以保留为兼容入口，但只有当 `final_ranking_id` 在 `poker_mtt_final_rankings` 中存在，并且 tournament、miner、rank、standing snapshot、evidence root、policy bundle 全部对齐时，才允许 `eligible_for_multiplier = true`。

### D. `poker_mtt_hidden_eval_entries`

隐藏评测的细分记录：

- `id`
- `tournament_id`
- `miner_address`
- `eval_type`
- `sample_weight`
- `raw_score`
- `normalized_score`
- `seed_group`
- `bot_pool_version`
- `shadow_policy_version`
- `reveal_policy`
- `created_at`

### E. `poker_mtt_rating_snapshots`

滚动 rating / multiplier 快照：

- `id`
- `miner_address`
- `window_id`
- `sample_count`
- `rolling_mean_score`
- `rolling_variance`
- `consistency_score`
- `multiplier_before`
- `multiplier_after`
- `effective_from`
- `created_at`

### F. Postgres projector 的职责

推荐由一个异步 projector 从运行时结果或 Dynamo hand stream 生成 Postgres 聚合结果。

它至少负责：

- 在比赛结束后写 `poker_mtt_tournaments`
- 生成 `poker_mtt_final_rankings`
- 写 `poker_mtt_result_entries`
- 触发 hidden eval pipeline
- 计算 rating / multiplier snapshot
- 产生日榜 / 周榜窗口输入

也就是说：

- **DynamoDB 保存原始手牌真相层**
- **Postgres 保存赛后聚合真相层**

这两层不应该混为一层。

## 9.5 现有 `reward_windows` / `settlement_batches` 继续复用

不建议给 `poker mtt` 重新造一套链锚定结构。

建议直接复用现有：

- `reward_windows`
- `settlement_batches`

但 lane 独立命名，例如：

- `poker_mtt_daily`
- `poker_mtt_weekly`

奖励预算必须显式配置：

- 默认从同一 miner emission budget 中划出 poker MTT 子预算
- 不新增超出 21M / 50 CLAW per epoch 叙事之外的奖励池
- `single_match_small_reward` 在 Phase 1 只是窗口内 score component / 展示项，不做即时单场链上 payout
- 如果以后要做单场小额即时感知，也必须先从 `poker_mtt_daily` 或 `poker_mtt_weekly` 预算中预留，并通过同一 settlement batch 结算

Phase 3 Task 7 已把这个口径落成服务端 contract：

- `poker_mtt_budget_ledgers` 记录 `budget_source_id`、`emission_epoch_id`、lane、reward window、settlement batch、requested / approved / paid / forfeited / rolled amounts 和 `budget_root`
- 打开 `poker_mtt_budget_enforcement_enabled` 后，daily 和 weekly window 必须共享同一个 emission epoch slice；缺 `budget_source_id`、缺 epoch 或超预算都会在 settlement 前 fail closed
- Projection artifact 同时保存 `budget_disposition` 与 `budget_root`，所以链锚定和外部审计可以从 reward window root 追溯到预算来源
- 未开启预算 enforcement 的本地/harness 仍会生成 `budget_root`，但 `budget_enforcement = disabled`，避免测试路径和生产路径的 artifact shape 分叉

---

## 10. 链集成设计

## 10.1 推荐链路

推荐完整链路：

1. donor `poker mtt` sidecar 打完一场比赛
2. 每手结束后异步写 DynamoDB `poker_mtt_hands`
3. sidecar / adapter 产出最终 standings、行动摘要、必要证据
4. `mining-service` projector 写入 `poker_mtt_result_entries`
5. hidden eval pipeline 补齐 `hidden_eval_score`
6. rolling rating job 计算 `consistency_score` 与 `multiplier_after`
7. 日 / 周窗口聚合出奖励结果
8. 生成 `reward_window`
9. 生成 `settlement_batch`
10. 构建 canonical root 和 anchor payload
11. 调用 `MsgAnchorSettlementBatch` 把 batch root 锚上链

Phase 1 rollout gate:

- `CLAWCHAIN_POKER_MTT_REWARD_WINDOWS_ENABLED=1` 后，`reconcile()` 才会自动构建 `poker_mtt_daily` / `poker_mtt_weekly`
- `CLAWCHAIN_POKER_MTT_SETTLEMENT_ANCHORING_ENABLED=1` 后，poker MTT lane 的 `settlement_batch` 才允许 `retry_anchor_settlement_batch()`
- 手动 `POST /admin/poker-mtt/reward-windows/build` 保留为 admin / test 入口，但即使手动构建了窗口，也必须显式打开 settlement anchoring gate 才能上链
- reward window membership 只读 `locked_at` 落在窗口内的结果；anchor payload 只读 projection artifact 中的 locked / anchorable roots
- 链上 `MsgAnchorSettlementBatch` 还要求 submitter 在 `x/settlement` genesis `authorized_submitters` 白名单内；相同 batch id + 相同 root/hash 幂等，相同 batch id + 不同 root/hash 冲突拒绝

## 10.2 链上应该锚什么

应该锚的是窗口级聚合结果，而不是逐手历史。

推荐锚定内容：

- `reward_window_ids_root`
- `task_run_ids_root`
- `miner_reward_rows_root`
- `budget_root`
- `policy_bundle_version`
- `evaluation_version`
- `canonical_root`
- `total_reward_amount`

必要时可以加：

- `activity_run_ids_root`（后续泛化字段；Phase 1 可由 `task_run_ids_root` 承载 tournament IDs）
- `reputation_delta_rows_root`
- `multiplier_snapshot_root`

对 `poker mtt` 来说，链下 projection artifact 还应该保存但不一定直接上链:

- `final_ranking_root`
- `hand_history_evidence_root`
- `short_term_hud_root`
- `long_term_hud_snapshot_root`
- `hidden_eval_sample_root`
- `public_rating_snapshot_root`
- `mq_consumer_checkpoint_root`
- `aggregation_policy_version`
- `budget_disposition`

其中 `hand_history_evidence_root` 和 `hidden_eval_sample_root` 的作用是支持审计与重算，不是把完整手牌或隐藏样本公开上链。

projection artifact 必须是 locked manifest：

- stable sorting
- fixed decimal precision
- root schema version
- policy bundle version
- evaluation version
- redacted hidden sample references
- raw evidence object hashes
- consumer checkpoint / cursor
- rebuild rules

batch 已经 anchored 后，历史 anchor 不应原地修改；如需纠错，应产生 superseding / compensating artifact，并在后续窗口或纠错 batch 中显式引用前序 batch。

## 10.3 链上不应该先做什么

第一版不建议：

- 每场比赛结束立即发链上奖励
- 每条 hidden eval 样本单独上链
- 把完整 hand history 上链
- 把实时 leaderboard 写成链上状态

这样做成本高、噪音大、参数难调。

---

## 11. 与现有 public leaderboard 的关系

当前系统已有 `public_rank` 和 `public_elo`。

`poker mtt` 不建议直接写入这两个现有字段，原因是：

- 当前 rank/elo 语义来自另一条产品线
- `poker mtt` 的主评分不仅是名次，还有 hidden eval 和 consistency
- 把两个产品线的 public rank 混写，后面解释不清

建议：

- 单独做 `poker_mtt_public_rank`
- 单独做 `poker_mtt_public_rating`
- 或者在 leaderboard API 上明确增加 `board_type`

---

## 12. 边缘情况

## 12.0 统一状态机

Poker MTT 结果进入 settlement 前建议统一使用以下状态机：

```text
raw_ingested
-> replay_ready
-> hud_ready
-> hidden_eval_ready
-> result_ready
-> locked
-> anchorable
-> anchored
```

允许的异常旁路：

- `incomplete`
- `stale`
- `degraded`
- `partial`
- `void`
- `rebuild_required`
- `manual_review`

窗口 membership 默认按 `locked_at` 归属，而不是按 `completed_at` 或 hidden eval 实际返回时间归属。
如果 hidden eval 或 corrected hand history 在 batch anchored 后才到达，不能改旧 anchor，只能生成 correction / compensating batch。

## 12.1 hidden eval 延迟返回

这是第一类必须显式处理的边缘情况。

如果比赛结束时：

- `tournament_result_score` 已有
- `hidden_eval_score` 还没有

则不能直接把这场结果当成最终版。

推荐处理：

- 先写 `evaluation_state = provisional`
- 允许生成临时 public score
- 不进入最终日/周 settlement
- hidden eval 补齐后再转成 `locked`

## 12.2 比赛被取消、异常终止、全员掉线

推荐分类：

- `void`
- `degraded`
- `partial`
- `final`

其中：

- `void` 不参与评分、不参与 multiplier
- `degraded` 只给基础参与样本，不给 hidden eval
- `partial` 只做有限权重计分

donor 状态映射要更严格：

- `CANCELED` 不进入 reward window
- `FAILED_TO_START` 不进入 reward window
- `PRIZE_POOL` 只是 bubble / payout threshold 状态，不是 terminal state
- `FINISHED` 不是 reward-ready；必须等 `final_ranking` artifact、evidence readiness、evaluation state 都满足 policy 后才可进入 `locked`

## 12.3 human-only 判定失败

如果某场后来发现：

- 实际不是 human-only
- 或无法证明 human-only

则该场：

- 可以保留结果
- 但 `eligible_for_multiplier = false`
- 不进入高权重 hidden eval 样本
- 如已进入 reward window 但随后发现 `human_only = false`，不能原地删除已锚定结果；必须走 hold / correction / compensating delta

## 12.4 多号和 collusion 风险

hidden eval 和 reputation 都不该单独承担反作弊结论。
推荐把它们只作为风险信号来源。

建议保留：

- `risk_flag`
- `collusion_suspect_score`
- `identity_confidence`

风险高时：

- 可以冻结 multiplier 更新
- 可以剔除窗口主奖励资格
- 但不要直接把原始比赛结果删掉

## 12.5 样本不足的新用户

新用户是最容易被 multiplier 误伤的一类。

推荐：

- 在 `min_samples` 前 multiplier 固定 `1.0`
- 只给基础参与奖励
- 日榜可见，但周榜主奖励权重更保守

## 12.6 payout policy 版本切换

任何影响评分或 hidden eval 的规则变更，都必须打版本号。

至少要有：

- `policy_bundle_version`
- `evaluation_version`
- `multiplier_version`

否则 anchor root 即便存在，也无法解释“为什么这周和上周算法不一样”。

## 12.7 hand history 上传失败与补传

如果一手结束后 DynamoDB 上传失败：

- 该手不能直接丢弃
- 运行时必须把它标记成 `pending_upload`
- `table_state.last_uploaded_hand_no` 不前推

推荐处理：

- 内存或本地轻量 spool 保留最近未上传 hand
- 后台 uploader 自动重试
- 比赛结束时再做一次补传 sweep

如果仍有 hand 未上传成功：

- 该场比赛可先进入 `result_ready`
- 但 `evidence_state = incomplete`
- 不进入最终 settlement anchor

只有在：

- 关键 hand history 已补齐
- 或已明确进入可接受的降级策略

时，才允许进入 `locked` / `anchorable`。

## 12.8 MQ 重复、乱序和延迟

如果沿用 donor 的 MQ 路径，必须默认消息会重复、乱序、延迟到达。

推荐处理:

- 每条 MQ 消息必须有稳定 `biz_id` / `message_id`
- consumer 必须幂等
- 每手 raw hand record 使用 `hand_id` 或 `tournament_id + table_id + hand_no` 做幂等键
- 同一手的更新必须带 `version` 或 `checksum`
- 低版本消息不能覆盖高版本消息
- 同版本不同 checksum 进入 conflict review
- replay / HUD projector 必须能从 raw hand history 重放，不依赖实时 MQ 顺序
- idempotency marker 和 projection side effect 需要可恢复；如果 marker 写失败但 Dynamo/Redis side effect 已完成，重试不能制造重复 reward/HUD
- donor 式短期 Redis version guard 不能作为 ClawChain 长期 evidence guard

对 reward window 的要求:

- MQ 延迟不能阻塞比赛 runtime
- 但 evidence 不完整时不能进入最终 settlement anchor
- 可先进入 `result_ready / provisional`
- 补齐后进入 `locked / anchorable`

## 12.9 final ranking 异常

必须显式处理：

- waiting / no-show 用户是否计入 `field_size`
- 同一手同时淘汰导致的 tie / split rank
- donor `rank = "-"` 这种非数值排名
- re-entry 多个 `entry_number` 映射到同一 `miner_address`
- Redis standings 与 final snapshot 不一致
- stuck table 或 long break 导致 tournament-level watermark 误判

默认建议：

- reward input 只接受数值 rank + `rank_state = ranked`
- waiting / no-show 进归档和展示，但不默认 reward-eligible
- re-entry 折叠到 canonical miner result，并保留 entry count / audit rows
- tie policy、field size basis、rounding rule 都进入 `policy_bundle_version`

---

## 13. 推荐的第一阶段落地方案

## 13.1 Phase 1

目标：

- 先把 `poker mtt` 的奖励和 multiplier 路径立起来
- 不碰链上 reputation 主逻辑
- 不做复杂 hidden replay

原始设计里的“Phase 1 做法”包含 DynamoDB raw hand history 等内容。以 2026-04-17 实现状态为准，当前 Phase 1 已落地的是：

1. 顶层 `authadapter/*` 和 `pokermtt/*`，不混入 `arena/*`
2. donor sidecar HTTP / WS / Redis ranking adapter
3. canonical final ranking finalizer 与 result apply payload builder
4. `poker_mtt_tournaments`
5. `poker_mtt_final_rankings`
6. `poker_mtt_result_entries`
7. `miners.poker_mtt_multiplier`
8. final ranking -> reward-bearing result projection
9. daily / weekly `poker_mtt_*` reward window builder
10. settlement batch / anchor payload projection roots
11. rollout gates:
    - `CLAWCHAIN_POKER_MTT_REWARD_WINDOWS_ENABLED`
    - `CLAWCHAIN_POKER_MTT_SETTLEMENT_ANCHORING_ENABLED`
12. `x/settlement` authorized submitter whitelist

Phase 1 不做：

- `x/reputation` 写入
- ELO 进奖励公式
- 单场即时链上发奖
- Java monolith port
- Cognito 强耦合
- MQ consumer 直接变成 scoring engine
- production completed-hand store
- full short-term / long-term HUD projector
- real hidden seed / bot / shadow eval pipeline

## 13.2 Phase 2

目标：

- 把 evidence 做成真实可重放链路
- 把 hidden eval 做成服务端生成、可审计但不可公开逆推的评分输入
- 把 rating / consistency / multiplier snapshot 做稳
- 把 settlement anchor confirmation 从“tx 成功”提升到“链上 state 匹配”
- 为 10k-20k MTT 和 2k early tables 做 indexed query、paged artifact、observability、load harness

做法：

1. 加 persistent hand evidence store:
   - `poker_mtt_hand_events`
   - `poker_mtt_table_upload_states`
   - `poker_mtt_consumer_checkpoints`
2. 加 HUD / hidden eval / rating / multiplier snapshot:
   - `poker_mtt_short_term_hud_snapshots`
   - `poker_mtt_long_term_hud_snapshots`
   - `poker_mtt_hidden_eval_entries`
   - `poker_mtt_rating_snapshots`
   - `poker_mtt_multiplier_snapshots`
3. 补 Go finalization worker:
   - stable Redis snapshot barrier
   - canonical final rankings
   - typed mining-service handoff
4. 补 `x/settlement` anchor query 和 typed state confirmation
5. 补 correction / supersession policy，anchored root 永不原地改
6. 补 admin/auth protection、production identity binding、economic unit eligibility
7. 补 load / scale / recovery / observability gates
8. 详细执行步骤见 `docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2.md`

### 13.2.1 2026-04-17 local beta / harness gate 落地状态

当前 Phase 2 已形成一条本地可回归的 evidence-to-anchor beta slice，但这不是 reward-bearing production ready。后续生产验收以 `docs/POKER_MTT_PHASE2_HARNESS_SPECS.md` 为准。

1. completed hand event 以 `hand_id + version + checksum` 幂等入 `poker_mtt_hand_events`
2. hand-history manifest、short-term HUD、long-term HUD、hidden eval manifest 进入 artifact ledger
3. hidden eval 设计口径是只从 service-owned `poker_mtt_hidden_eval_entries` 进入 reward-ready projection；legacy/admin payload 不能自带 hidden / consistency 分数解锁奖励。2026-04-17 closeout 已补 `accepted_degraded` audit-only 和 legacy score injection harness gate
4. final ranking handoff 使用 canonical `poker_mtt_final_rankings`；未锁定、证据不完整、缺 hidden eval 的结果不应进最终 reward window。2026-04-17 closeout 已补 reward-window policy/evaluation version filter；degraded allowlist 仍必须显式 policy 化后才能 reward-bearing
5. `poker_mtt_rating_snapshots` 和 `poker_mtt_multiplier_snapshots` 已与 forecast `public_elo` / `arena_multiplier` 分离
6. reward window membership 有 indexed locked/evidence-ready query 形状；production gate 仍需证明 policy isolation、bounded query count 和 no N+1
7. 大字段 projection 已分页：主 artifact 保留 `miner_reward_rows_root` 和 page refs，page artifact 保存实际 rows；production gate 仍需通过 Postgres-backed 20k service path
8. typed `x/settlement` anchor plan 已有 state-query confirmation 语义；2026-04-17 closeout 已补 tx-only 不等于 anchored、full-field typed confirmation、duplicate metadata drift rejection。production gate 仍需外部 gRPC/gateway/CLI query wiring
9. admin APIs 和 projector auth 已补本地 harness gate：`/admin/*` auth enabled 时统一 bearer 保护，projector client 可带 bearer token 并对 401/403 非重试。production gate 仍需非本地/shared runtime fail-closed startup gate 和 durable reward-bound miner identity
10. 本地 beta slice 测试覆盖：
    - hand ingest -> hand-history manifest -> HUD -> hidden eval -> final ranking projection -> reward window -> settlement batch -> typed tx plan -> query confirmation
    - 30-player smoke、300-player medium shape、20k-player synthetic projection paging、2,000-table early burst shape

2026-04-19 Phase 2 closeout:

- 新增 `make test-poker-mtt-phase2` 作为 Evidence Phase 2 local beta 一键 gate。
- 当前 gate 已通过 Go authadapter / Poker MTT / settlement tests、136 个 Phase 2 Python tests，以及 `run_phase2_load_check.sh --players 30 --local`。
- 这只证明 local beta evidence-to-anchor slice；Phase 3 的 DB-backed 20k、non-mock finish、typed settlement query receipt 和 release review 仍是 reward-bearing rollout 前置条件。

第二波 review 冻结的 production harness blockers：

- `accepted_degraded` 不能自动 reward-ready，必须有 policy allowlist 和 degraded reason root
- legacy/admin apply 不能通过 caller-provided score 产生 reward-ready total score
- reward-window selection 必须按 lane / locked range / evidence / eligibility / policy 过滤
- `economic_unit_id` 必须来自服务端 miner/economic-unit binding
- typed settlement confirmation 必须比较 batch id、root/hash、lane、policy、window、reward roots、row roots、amount/count metadata
- 20k scale gate 必须走 DB-backed service path，不只走 offline artifact paging
- admin auth、projector auth、本地 mock identity 非奖励化必须成为验收测试
- donor parity 必须补 registration/waitlist merge、MQ checkpoint/replay、scheduler stuck/fail handling

仍然保持关闭的 rollout gate：

- `CLAWCHAIN_POKER_MTT_REWARD_WINDOWS_ENABLED` 默认关闭自动日/周窗口
- `CLAWCHAIN_POKER_MTT_SETTLEMENT_ANCHORING_ENABLED` 默认关闭 poker MTT lane 上链锚定
- `x/reputation` 不在 Phase 2 写路径中
- production DynamoDB hand-history adapter、真实 MQ consumer、真实 hidden seed/bot/shadow eval pipeline 仍是后续任务

## 13.3 Phase 3 - production readiness，不是直接 reward rollout

2026-04-17 六个 `gpt-5.4 xhigh` review agents 复核后，Phase 3 口径从“把长期信誉和链上资格层并上来”收敛为 **Poker MTT Production Readiness**。

Canonical spec: `docs/POKER_MTT_PHASE3_PRODUCTION_READINESS_SPEC.md`

Execution plan: `docs/superpowers/plans/2026-04-17-poker-mtt-phase3-production-readiness.md`

Phase 3 的目标:

- 把 Go finalizer / projector 与 FastAPI final ranking schema 锁成跨语言 contract
- 补 registration / waitlist / no-show donor parity，Redis live ranking 不能单独作为 final archive
- 把 hand history / HUD / hidden eval / MQ checkpoint 做成 policy-owned evidence readiness
- 把 admin auth、projector auth、durable reward-bound identity 做成 fail-closed production gate
- 20k reward-window 已从 offline shape test 提升到 service-path load contract；真实 staging Postgres artifact 作为上线前证据补充
- 把 reward budget、window aggregation、multiplier effective-window 做成版本化经济合同
- 把 `x/settlement` 从 keeper/local proof 提升到 external gRPC/gateway/CLI query proof
- 只产出 window-level `reputation_delta` draft，不直接写 `x/reputation`

Phase 3 的明确 non-goals:

- 不打开 high-value mainnet rewards
- 不把 public ELO 或 public rating 放进正向 reward weight
- 不把 raw hand history、单场 total score、hidden eval 原始分或 HUD 指标直接写 `x/reputation`
- 不把 donor Java `MttService` / `HandHistoryService` monolith 搬进 ClawChain
- 不做 per-hand / per-game on-chain writes

Phase 3 完成前，仍保持:

- `CLAWCHAIN_POKER_MTT_REWARD_WINDOWS_ENABLED=false`
- `CLAWCHAIN_POKER_MTT_SETTLEMENT_ANCHORING_ENABLED=false`
- public surface 只展示 final ranking、public rating、provisional/locked/anchored 状态
- hidden eval、shadow/bot seed、risk thresholds、单场 multiplier 草算值不公开

### 13.3.1 Phase 3 P0 gates

1. **Final ranking contract**: Go payload 必须通过 Python schema golden test；projection 用 `projection_id` / `final_ranking_root` 幂等；同 root 可重放，不同 root 冲突。
2. **Donor parity**: finalizer 必须合并 Redis live ranking 与 registration/waitlist/no-show source，waiting/no-show 进入 archive 但不 reward-bearing。
3. **Evidence / MQ**: checkpoint、lag、DLQ、conflict、replay root 进入 evidence policy；缺 hand/HUD/checkpoint/hidden eval 不能靠 caller allowlist 变成 `complete`。
4. **Auth / identity**: non-local/shared runtime fail closed；donor token 只证明 user，不证明 reward-bound miner；`claw1local-*` 和 synthetic identity 不能进 reward window。
5. **20k DB path**: `POST /admin/poker-mtt/reward-windows/build` 真实 Postgres path under 30 SQL statements，response under 256 KB，20k rows 通过 4 个 5,000-row page artifacts 重建 root。
6. **Budget / aggregation / multiplier**: daily/weekly payout 受同一 emission slice 约束；window aggregation policy 版本化；multiplier 只能按后续窗口生效。
7. **Settlement query**: external query 已能通过 gRPC/gateway/CLI 读取 stored anchor state；当前比对 batch id、root/hash、lane、policy、window/reward roots、amount，并且 budget / reputation / correction lineage 已进入 projection 和 settlement payload；tx success 不等于 anchored。
8. **Ops gate**: 30-player non-mock WS explicit join/action-to-finish 是 hard gate；2,000-table burst 必须生成 completed-hand/finalizer inputs；observability 必须真实 emit。
9. **Reputation delta**: 已做窗口级 dry-run root：projection 产出 `reputation_delta_rows_root`、bounded sample、row count、correction lineage；settlement anchor 产出 per-window roots 和 settlement-level root。`x/reputation` 写入仍需另起 release review。

2026-04-18 Task 9 closeout:

- Window-level reputation delta schema 已落地为 dry-run contract，包含 window id、settlement batch id、policy version、prior rating snapshot ref、delta cap、reason、source-result root、score weight、gross reward、submission count 和 correction lineage root。
- Reward-window projection root、`poker_projection_roots`、settlement anchor canonical root 都会覆盖 `reputation_delta_rows_root`，所以后续 controller 只能基于已锚定窗口做 append-only reputation 写入。
- 单场 tournament result、raw HUD、hidden eval、public ELO/public rating 仍不会直接写 `x/reputation`。

2026-04-18 Task 1 closeout:

- Final ranking contract gate 的 projector/schema/API 幂等部分已落地。
- `projection_id`、`final_ranking_root`、standing snapshot refs、policy version、payload `locked_at` 是 FastAPI request schema 的必需字段。
- Mining-service projection response 会回传 canonical metadata；同一 `projection_id`/root replay 返回 artifact 中保存的 existing result，同一 `projection_id` 搭配不同 root 返回 409。

2026-04-18 Task 3 closeout:

- non-local/shared runtime 已 fail closed：没有 admin auth/token 不能启动；绑定 `0.0.0.0` / external host 时也不能默认裸开 admin routes。
- local/test 要裸开 external admin routes 必须显式设置 insecure-local override；默认 loopback 本地 harness 仍保持可测。
- admin mutation audit 改成 resolved principal：bearer token 映射成 `admin:<token-hash>` / `admin`，本地 harness 映射成 `local-admin` / `local`，payload 里的 `operator_id` 不能伪造审计人。
- donor `/token_verify` 缺 miner binding 时只会生成 synthetic `claw1local-*` participation identity，不会被当成 reward-bound miner。
- miner durable identity 已进入 mining-service row：`poker_mtt_user_id`、`poker_mtt_auth_source`、`poker_mtt_reward_bound`、`poker_mtt_reward_bound_at`、`poker_mtt_is_synthetic`、`poker_mtt_identity_expires_at`、`poker_mtt_identity_revoked_at`。
- final ranking projection 和 reward-window selection 都会拒绝 missing / synthetic / not-bound / expired / revoked / `claw1local-*` identity；因此本地 mock 30 人可以跑完整游戏，但不能直接进入 payout window。

2026-04-18 Task 4 closeout:

- completed-hand MQ ingest 已有 durable checkpoint：topic / queue / consumer group / offset / donor `bizId` / message id / hand id / replay root / lag 都会保存。
- duplicate replay、higher-version update、lower-version stale replay 都会推进 checkpoint；如果先写 hand/HUD 后 crash，没有 checkpoint 的 replay 会以 duplicate 修复 checkpoint。
- same hand/version checksum drift 会落 `poker_mtt_mq_conflicts`，状态为 `manual_review`，并阻断 evidence readiness。
- malformed hand payload 会落 `poker_mtt_mq_dlq` 并 checkpoint 为 `dlq`，consumer 不再因为坏消息直接崩掉。
- evidence readiness 改成 policy-owned：hand history 和 consumer checkpoint 是 required，不接受 caller degrade；hidden eval 和 short/long HUD 可由 policy 降级，但只能得到 `accepted_degraded`，不能冒充 `complete`。
- open conflict、open DLQ、checkpoint lag 都会使 evidence result 进入 `blocked`。
- evidence artifacts 改成 content-addressed ID，manifest root 变化后旧 artifact 仍可读取，便于 replay / audit / ELO/HUD 复算。

2026-04-18 Task 5 closeout:

- 20k reward-window gate 已从 offline shape test 升级为 service-path load test：`build_poker_mtt_reward_window()` 覆盖 300 / 20k reward-ready rows、4 个 5,000-row page artifacts、response < 256 KB、root reconstruction 和 memory guard。
- Reward-window selection 改为 bulk input snapshot：一次性读取 candidate results、final rankings、reward-bound miner identities、latest rating snapshots，不再按 result/miner 做 N+1。
- 大窗口 response 不再返回完整 20k `miner_addresses`；返回 root/count/sample，并通过 projection artifact + page artifacts 获取完整 reward rows。
- Unchanged rebuild 用 `input_snapshot_root` 判定幂等，不更新 reward window，也不重写 artifact rows。
- 自动 daily/weekly reconcile 改成 lookback-bounded closed-window candidate query，不再调用 `list_poker_mtt_results()` 全量扫描历史。
- `scripts/poker_mtt/run_phase3_db_load_check.sh` 是当前可重复执行的 Phase 3 load contract 入口。

2026-04-18 Task 6 closeout:

- `x/settlement` 的 `SettlementAnchor` query 已从 placeholder 提升为 generated gogo gRPC server/client、gateway route 和 CLI query；mining-service 可以按 stored anchor state 做确认。
- Tx inclusion 不再等于 anchored：确认必须匹配 batch id、canonical root、anchor payload hash 以及当前 first-class metadata；tx-only / fallback-memo-only / root drift / metadata drift 都会拒绝确认。
- `anchor_jobs.chain_confirmation_status` 持久化 normalized 状态：`confirmed`、`typed_state_missing`、`fallback_memo_only`、`root_mismatch`、`metadata_mismatch`、`failed`、`pending`。
- Settlement anchor payload 不再内联 20k `miner_reward_rows`；主 anchor artifact/API response 保留 `miner_reward_rows_root`、`artifact_page_count`、`artifact_pages`，实际 rows 进入 `settlement_anchor_miner_reward_rows_page` artifacts。
- `/admin/settlement-batches` 默认返回 bounded summary，所以即使历史 payload 曾经内联大字段，也不会通过 admin path 重新膨胀响应。

2026-04-18 Task 7 closeout:

- `poker_mtt_budget_ledgers` 已成为 reward-window economics 的 durable ledger。生产开启 enforcement 后，daily/weekly 不再能各自创造奖励池，而是共享同一个 `budget_source_id + emission_epoch_id` 预算切片。
- Reward-window projection 默认聚合策略改为 `capped_top3_mean_v1`：每个 economic unit 取 top 3 positive `total_score` 的均值，而不是无版本的 `max()`。这能压低 lucky spike、单窗口 solver edge 和多号刷样本收益。
- Projection artifact 新增 `aggregation_policy_version`、`budget_disposition`、`budget_root`。Settlement 的 `poker_projection_roots` 也会包含 `budget_root`，使链上 anchor 可回查预算来源。
- `poker_mtt_multiplier_snapshots` 新增 `effective_window_start_at` / `effective_window_end_at`，以 source result 锁定/完成时间的下一个 UTC daily window 生效。它可以更新 miner 当前展示值，但 reward/reputation 消费时必须按 effective window 读取，避免同窗口反馈。

2026-04-18 Task 8 closeout:

- Donor sidecar orchestration calls now have retry/backoff only for transient timeout/429/502/503/504 failures. 400/401 are not retried, and donor error messages are preserved for operator diagnosis.
- `non_mock_play_harness.py --until-finish` now fails hard unless all expected players joined, received ranking, sent actions, exactly one player remains alive, all others died/finished, no pending players remain, and WS errors are only allowed close/lost-connection cases.
- `generate_hand_history_load.py` now emits a completed-hand checksum root for the 2,000-table early burst shape, so the load contract is closer to real hand-ingest pressure instead of only table metadata.
- `make test-poker-mtt-phase3-ops` ties together sidecar retry tests, load-contract tests, and DB-backed Phase 3 reward-window scale checks.

2026-04-18 Task 2 closeout:

- Donor parity finalizer gate 已补 registration/waitlist/no-show snapshot merge。
- Registration-only waiting/no-show 用户进入 final ranking archive，但因 `rank_state=waiting_no_show` / `status=pending` 不会成为 reward-bearing result。
- Optional finalization barriers 覆盖 terminal-or-quiet、entrant count、alive/died/waiting count 和 total chip drift tolerance。

---

## 14. 我建议冻结的决策

这几个决策建议现在就冻结：

1. `poker mtt` 是独立产品线，不与现有 `arena` 混写
2. Phase 1 不做单场即时发奖；单场结果只作为日/周窗口输入
3. 总分采用三段式：
   - `0.55 tournament_result`
   - `0.25 hidden_eval`
   - `0.20 consistency`
4. multiplier 是慢变量，且必须有界
5. `reputation` 只做长期信誉层
6. 链上第一阶段只锚定 settlement root，不做逐场逐手奖励结算
7. ELO / public rating 不直接参与奖励计算
8. HUD 指标先进入 hidden eval / consistency / risk review，不作为公开可刷的直接奖励公式

---

## 15. 下一步实现建议

按 2026-04-17 Phase 3 review 后的工程优先级，下一步最合理的是：

1. 锁 Go finalizer/projector 与 FastAPI final ranking schema 的跨语言 contract
2. 补 registration / waitlist / no-show final archive parity
3. 补 admin fail-closed、resolved admin principal、durable reward-bound identity
4. 补 MQ checkpoint / replay / DLQ / lag 和 policy-owned evidence readiness
5. 20k reward-window 已迁到 service path，并消掉 N+1 / full historical scan；后续只需要接真实 staging Postgres load artifact
6. 补 settlement external query、bounded anchor artifacts、terminal mismatch states
7. budget ledger、aggregation policy、multiplier effective-window 已落地；后续只需要接生产配置和 staging epoch cap artifact
8. sidecar retry、30-player finish gate、2,000-table burst 已有本地 ops gate；real staging metrics/log sink artifact 仍需上线前补证据
9. window-level `reputation_delta` dry-run 已完成；下一步只剩最终文档、CI target、release review 和 staging evidence 归档，`x/reputation` 写入另起 release review

一句话总结：

**先把 `poker mtt` 做成“donor runtime 外接、Go final ranking contract 稳定、evidence/reward/settlement 可重放、20k DB path 可证明、链上只锚定窗口 root”的系统，再把 `reputation` 作为长期信誉层补进去。**

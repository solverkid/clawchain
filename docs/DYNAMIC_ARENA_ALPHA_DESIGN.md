# ClawChain MTT-like Simplified Bluff Arena 规则书

**版本**: 0.4  
**日期**: 2026-04-09  
**状态**: Lane 级规则书  
**定位**: ClawChain V1 的 `Arena Multiplier` 细化方案  
**总方案**: [docs/MINING_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md)  
**仿真计划**: [docs/HARNESS_SIMULATION_PLAN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_SIMULATION_PLAN.md)

---

## 1. 定位

Arena 不是主赛道，也不是自由文本游戏。

它是：

> **一个独立运行的 MTT-like Simplified Bluff Arena，用来测量 forecast 主赛道不容易单独覆盖的泛能力，并输出小幅 `arena_multiplier`。**

它吸收的是德扑 MTT 的结构压力，不复刻真实扑克规则。

保留：

- 多桌并行
- 随机分桌
- 重分桌
- stack / blind / bubble / final table 压力
- 不完全信息
- bluff

不保留：

- 标准扑克牌
- solver 友好的完整德扑规则
- 自由文本聊天
- 链上逐手结算

---

## 2. Tournament Rule Constants

Alpha 默认常量如下。

## 2.1 Field 与时长

- `field_size_target = 64`
- `field_size_normal = 56..64`
- `field_size_bot_adjusted = 48..55`
- `field_size_cancel = <48`
- `tournament_duration_cap = 24m`
- `daily_rated_tournaments = 1`
- `daily_practice_tournaments = 1`
- `rated_window_utc = 09:00`
- `practice_window_utc = 17:00`

规则：

- `56-64`：正常开赛
- `48-55`：仅允许 `practice / exhibition`
- `<48`：取消，不产出 multiplier
- 一场 tournament 超过 `24m` 时，在当前 hand 结束后按 standing 结算

## 2.2 Table 与 final table

- `table_size_target = 8`
- `table_size_fill_only = 7 or 9`
- `table_size_disabled = 10`
- `final_table_size = 8`
- `bubble_threshold = 10`

规则：

- Alpha 默认只开 `8-handed`
- `7/9-handed` 仅用于平衡座位
- `10-handed` 在 Alpha 关闭
- 剩余 `10` 人进入 bubble
- 剩余 `8` 人进入 final table

## 2.3 资金与盲注

- `starting_stack = 200`
- `late_reg = false`
- `rebuy = false`
- `add_on = false`

盲注表：

| Level | SB | BB | Ante | Hands |
|---|---:|---:|---:|---:|
| L1 | 1 | 2 | 0 | 4 |
| L2 | 2 | 4 | 0 | 4 |
| L3 | 3 | 6 | 1 | 4 |
| L4 | 5 | 10 | 1 | 4 |
| L5 | 8 | 16 | 2 | 4 |
| L6 | 12 | 24 | 3 | 4 |
| L7 | 16 | 32 | 4 | 4 |
| L8 | 24 | 48 | 6 | 4 |

规则：

- final table 后若仍未结束，后续 level 按上一档盲注乘 `1.5x`
- 所有升级都在 hand close 后生效

## 2.4 multiplier 常量

- `arena_multiplier_range = 0.96 .. 1.04`
- `bot_adjusted_rating_weight = 0.00`
- `rolling_window = last 20 eligible tournaments`
- `conservative_skill = mu - 1.5 * sigma`
- `beta = 0.015`

---

## 3. 生命周期

Tournament 状态机：

```text
SCHEDULED
-> SEATING
-> LIVE
-> REBALANCING
-> FINAL_TABLE
-> COMPLETED
-> RATED
-> SETTLED
```

说明：

- 无 late registration
- 无 rebuy / add-on
- 无中途改规则
- 完赛后先更新 arena rating，再更新长期 public ELO，再将结果写入 reward window

---

## 4. 分桌、重分桌与 bot policy

## 4.1 初始分桌

分桌必须同时满足：

1. `rating band`
2. `anti-repeat`
3. `anti-collusion`
4. `seat-order fairness`
5. `probation isolation`

## 4.2 重分桌

只允许在以下时点重分桌：

- `hand close`
- `level boundary`

规则：

- 不允许 hand 中间换桌
- 先拆最短桌
- 再平衡到 `7-9` 人桌
- 重分桌后重新分配 `button`
- 不允许同一玩家连续两手拿到 `button`

## 4.3 bot policy

规则：

- 主池 tournament 不应依赖 bot 开赛
- `48-55` 人只允许 `practice / exhibition`
- practice / exhibition 不进入 multiplier
- 若 bot 进入 final table，则该场自动 `no_multiplier`
- live 期间不展示 bot 身份

---

## 5. 单手结构

## 5.1 三阶段模型

每手固定为：

1. `signal phase`
2. `probe phase`
3. `wager phase`
4. `showdown / award`

执行方式：

- `signal`：同步提交
- `probe`：同步提交
- `wager`：按 seat-order 串行
- 每手只有 `1` 个 betting round

## 5.2 seat order

Arena 保留：

- `button` 轮转
- `seat-order` 顺序行动
- blind/ante 压力

规则：

- 先收 blind/ante
- 再由 button 左侧首位行动
- `button` 每手顺时针移动一位

---

## 6. 隐藏信息模型

## 6.1 latent kernel

每手为每位 active player 生成：

- `private_strength_bucket ∈ {-3,-2,-1,0,1,2,3}`

每手再生成：

- `public_event_bias ∈ {-2,-1,0,1,2}`

每位玩家还会收到：

- `1` 条高置信私有 clue
- `1` 条低置信私有 clue
- `1-2` 条噪声 clue

Alpha rated Arena 至少在以下 3 个 regime family 之间切换：

- `signal_noisy`
- `event_skewed`
- `pressure_heavy`

每个 regime 只允许改变：

- probe 精度
- `public_event_bias` 分布
- raise payoff 权重

## 6.2 briefing

每位玩家收到的 briefing 由以下部分组成：

- 基础局面摘要
- 私有 clue
- 事件文本包装
- posture 模板解释

文本允许轻度风格扰动，但底层语义不变。

## 6.3 showdown_value

仍留在牌局中的玩家在 showdown 获得：

```text
showdown_value
  = private_strength_bucket
  + public_event_bias
  + probe_information_bonus
  + tiebreak_noise
```

说明：

- bluff 的价值来自让别人提前 fold
- 并不依赖真实牌型大小

---

## 7. 动作规则

## 7.1 signal phase

每位 active player 可选：

- `signal_none`
- `signal_strong`
- `signal_weak`
- `signal_uncertain`
- `signal_pressure`
- `signal_trap_warning`

这些是 posture template，不是自由文本。

## 7.2 probe phase

每手每人最多 `1` 次 probe。

`probe_cost = max(1, ante)`，直接从 stack 扣除。

| Probe Type | 作用 | 返回粒度 | 默认精度 | 每手上限 |
|---|---|---|---:|---:|
| `probe_self_strength` | 观察自身强度 | `weak / neutral / strong` | 80% | 1 |
| `probe_event_bias` | 观察公共事件方向 | `negative / flat / positive` | 75% | 1 |
| `probe_noise_filter` | 识别 briefing 噪声 | 标记一条 clue 为 `likely_reliable` 或 `likely_noise` | 70% | 1 |

规则：

- 每人每手总 probe 次数最多 `1`
- probe 只返回粗粒度 clue，不返回确定答案
- `probe_information_bonus` 只进入 hand outcome，不再单独进入 tournament 评分

## 7.3 wager phase

行动集：

- `fold()`
- `check()`
- `call()`
- `raise_small()`
- `raise_large()`

定义：

- `raise_small = to_call + 1 * BB`
- `raise_large = to_call + 2 * BB`
- 每手最多 `2` 次 raise reopen
- 无 all-in
- 无 side pot

### legal action matrix

| 条件 | 合法动作 |
|---|---|
| `to_call = 0` | `check / raise_small / raise_large` |
| `to_call > 0` | `fold / call / raise_small / raise_large` |

补充规则：

- stack 不足以完成 `call` 时，只允许 `fold`
- stack 不足以完成 raise 时，不展示 raise
- `expected_state_seq` 不匹配的 action 必须拒绝

---

## 8. 超时、SIT_OUT 与淘汰

## 8.1 phase timeout

单个 phase 超时自动执行：

- `signal phase` -> `auto signal_none`
- `probe phase` -> `auto pass_probe`
- `wager phase`
  - 若 `to_call = 0` -> `auto check`
  - 若 `to_call > 0` -> `auto fold`

## 8.2 SIT_OUT 规则

- 连续 `1` 手超时：记录 `sit_out_warning`
- 连续 `2` 手超时：标记 `inactive`
- 连续 `4` 手超时：直接淘汰

## 8.3 elimination

规则：

- hand 结束后 `stack <= 0` 即淘汰
- hand 开始时若 stack 小于 `SB + ante`，仍照常入手并扣除强制成本
- hand 结束后若为负或归零，则淘汰

---

## 9. 单手结算

## 9.1 折叠结算

若只剩一位 active player：

- 该玩家直接赢得主池
- 不进入 showdown

## 9.2 showdown 结算

若仍有多位玩家存活到 showdown：

- 比较 `showdown_value`
- 最大者赢得主池
- 平局平均分池

## 9.3 hand record

每手至少记录：

- `pot_main`
- `winner_count`
- `stack_before`
- `stack_after`
- `stack_delta`
- `probe_spend`
- `fold_path`
- `raise_count`

---

## 10. 站内实时信息

## 10.1 Live Table

live 期间本桌可见：

- button
- blind level
- 当前 pot
- 各 seat 公共动作
- 各 seat 可见 stack
- 剩余行动位

不显示：

- 隐藏 clue
- probe 返回
- 真实 miner id
- public ELO
- risk 状态

## 10.2 Live Tournament Snapshot

全场 standing 只在 `hand close` 后刷新，不做 action 级跨桌实时榜。

推荐展示：

- players remaining
- self exact rank
- non-table opponents standing band
- average stack
- bubble / final table distance
- current level

## 10.3 Alias lifecycle

- alias 在单场 tournament 内固定
- 赛后延迟 `10m` 才允许映射回 profile
- live 期间不展示长期身份层

---

## 11. Bubble、Final Table 与时间上限

## 11.1 bubble

当剩余玩家数 `<= 10`：

- 进入 bubble 状态
- UI 展示 bubble pressure
- standing 以 hand-close cadence 刷新

## 11.2 final table

当剩余玩家数 `<= 8`：

- 进入 final table
- 使用固定 `8` 人 final table
- 继续按既定 blind schedule 前进

## 11.3 time-cap finish

若 tournament 达到 `24m` 上限：

- 在当前 hand 完成后终止
- 按 `stack rank + percentile + blind-adjusted chip EV` 混合结算
- 相同 stack 时，看最近 hand 的 survival precedence

---

## 12. 评分与 multiplier

## 12.1 单场 tournament_score

单场得分由以下组件构成：

```text
tournament_score
  = 0.45 * placement_component
  + 0.35 * stack_efficiency_component
  + 0.20 * decision_validity_component
  - timeout_penalty
  - invalid_penalty
  - collusion_adjustment
```

含义：

- `placement_component`：看 finishing percentile
- `stack_efficiency_component`：看相对盲注增长后的 stack path
- `decision_validity_component`：合法动作率、超时率、`state_seq` 一致率

重要约束：

- `deep run / final table / bubble survive` 只进入 rating 和 explanation
- 不允许再单独做二次 bonus，避免双重计分

## 12.2 rating 更新

单场 Arena 结果先更新：

- `mu`
- `sigma`
- `arena_reliability`

rating 更新必须显式包含：

- `field_strength_adjustment`
- `bot_adjustment`
- `time_cap_adjustment`

长期 `public ELO`：

- 只作为展示层
- 仅在 tournament 进入 `RATED` 后更新一次
- 不直接参与 multiplier

## 12.3 multiplier 生成

```text
conservative_skill
  = mu - 1.5 * sigma

arena_multiplier
  = clamp(0.96, 1.04, 1 + beta * zscore(conservative_skill))
```

说明：

- `beta = 0.015`
- rolling window 使用最近 `20` 场 eligible tournaments
- 前 `15` 场 eligible tournaments 内，`arena_multiplier` 强制收缩到 `1.00`

---

## 13. 反共谋与 anti-farm

Arena 最大风险不是普通 Sybil，而是：

- `soft_play`
- `chip_dumping`
- `repeat_seating_collusion`
- `targeted_elimination`
- `synchronized_timeout`

## 13.1 核心指标

必须监控：

- `repeat_seating_score`
- `mutual_soft_play_score`
- `chip_transfer_score`
- `targeted_elimination_score`
- `synchronized_timeout_score`

## 13.2 执法链路

Arena 先做局内调整，再进入全局 risk engine：

```text
collusion metrics
-> collusion_adjustment
-> rating weight reduction
-> anti_abuse_discount
-> freeze / review
```

说明：

- practice / exhibition 不进入 multiplier
- final table 若存在 bot，则整场不产出 multiplier

---

## 14. 必要后端模块

Arena 至少需要这些专用模块：

- `Tournament Orchestrator`
- `Table Runtime Actor`
- `Turn Order Service`
- `Standing Projection Service`
- `Identity Projection Service`
- `Multiplier Service`
- `Collusion Analytics`
- `Replay / Reveal Service`

## 14.1 Table Runtime Actor

每桌必须有单写 actor：

- 串行处理 action
- 串行推进 state
- 统一管理 deadline

不要多写者直接改 table state。

## 14.2 Standing Projection

官方 standing 只在：

- hand close
- level close

刷新。

## 14.3 Replay / Reveal

赛后延迟揭示：

- private briefing
- probe 结果
- hidden state

live 期间不公开。

---

## 15. 数据模型

在通用 harness 实体之外，Arena 需要：

- `arena_tournament`
- `arena_level`
- `arena_hand`
- `arena_phase`
- `arena_table`
- `arena_seat`
- `arena_alias_map`
- `arena_action`
- `arena_reseat_event`
- `arena_elimination_event`
- `arena_action_deadline`
- `arena_public_snapshot`
- `arena_collusion_metric`

关键字段：

- `button_seat`
- `acting_seat`
- `current_to_call`
- `min_raise_size`
- `pot_main`
- `hand_number`
- `level_number`
- `players_remaining`
- `current_standing`
- `bot_adjusted`
- `state_seq`

---

## 16. 玩家可见页面

客户端至少分三套视图：

1. `Live Table`
2. `Live Tournament Snapshot`
3. `Postgame Forensics`

其中 `Postgame Forensics` 至少展示：

- finishing percentile
- stack timeline
- key hands
- probe efficiency
- tournament score decomposition
- multiplier delta
- replay link

---

## 17. Alpha MVP

## 17.1 必做

- 独立 tournament service
- `64` 人目标 field
- `8` 人桌
- 多桌并行
- hand-close standing refresh
- alias live identity
- 三阶段单手模型
- 顺序行动
- 完整盲注表
- probe table
- legal action matrix
- SIT_OUT / timeout / elimination 规则
- rolling arena rating
- `0.96..1.04` multiplier

## 17.2 可延后

- 更复杂 probe 库
- 更强 shadow bots
- 更高级 replay 可视化
- 更复杂公开 posture 模板

---

## 18. 结论

Arena 现在的正确定位不是“小游戏”，而是：

> **一个独立运行、赛制清晰、实时可观、赛后可审计的 MTT-like Simplified Bluff Arena。**

Alpha 阶段只要坚持：

- 独立 tournament service
- 8 人桌与固定盲注表
- 三阶段手牌模型
- hand-close refreshed standing
- post-rating public ELO
- bot_adjusted 降权与 no-bot final-table rule

它就能成为一个工程上可实现、产品上可传播、机制上真正有价值的 `Arena Multiplier`。

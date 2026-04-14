# ClawChain Arena Measurement Spec

**版本**: 0.1  
**日期**: 2026-04-10  
**状态**: Arena 测量与信号质量规范  
**流程基线**: [docs/ARENA_MTT_USER_FLOW.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_MTT_USER_FLOW.md)  
**运行架构**: [docs/ARENA_RUNTIME_ARCHITECTURE.md](/Users/yanchengren/Documents/Projects/clawchain/docs/ARENA_RUNTIME_ARCHITECTURE.md)  
**规则基线**: [docs/DYNAMIC_ARENA_ALPHA_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/DYNAMIC_ARENA_ALPHA_DESIGN.md)  
**总方案**: [docs/MINING_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md)

---

## 1. 目的

这份文档回答一个核心问题：

> **Arena 一场 tournament 到底有没有“有效测到” AI 能力？**

Arena 不是娱乐扑克产品。  
Arena 的任务是：

- 提供 forecast lane 难以单独覆盖的 skill evidence
- 把 evidence 汇总成 rolling `mu / sigma`
- 最终只输出一个小幅 `arena_multiplier`

所以 Arena 的正确目标不是：

- 单场必须绝对精确地区分所有玩家

而是：

- 单场提供足够多、足够干净、足够可解释的 evidence
- 多场滚动后让 rating 稳定收敛

---

## 2. 测量哲学

## 2.1 不追求“单场定终身”

Arena 不应该把一场 MTT 当作终局判决。  
单场天然有噪声：

- seating
- regime family
- 对手风格
- bubble 压力
- time-cap finish

正确做法是：

- 单场产出 `tournament_score`
- 单场带上 `confidence_weight`
- rating 引擎只按置信度吸收
- multiplier 只看 rolling conservative skill

## 2.2 真正要最大化的是信号密度

Arena 不应该优化：

- 单场尽可能长
- 单场尽可能大

Arena 应该优化：

- 每分钟有多少有效决策
- 每个 entrant 平均经历多少高杠杆节点
- 决策是否覆盖 early / mid / bubble / final table 不同压力区间
- 结果是否主要来自信息处理与风险管理，而不是纯 blind attrition

一句话：

> **Arena 追求的是 high-density skill sampling，不是 long-duration survival theater。**

---

## 3. Arena 想测的能力画像

Arena 主要测五类能力：

1. **隐藏信息推理**
   - 根据不完备 clue、公共动作和历史轨迹调整判断
2. **风险管理**
   - 在 stack / blind / bubble 压力下控制风险暴露
3. **多轮稳定性**
   - 不在短期好运或坏运里崩掉策略纪律
4. **对手建模**
   - 面对不同风格 alias 的行动模式做响应
5. **执行纪律**
   - 合法动作率、超时率、`state_seq` 一致性、低断线率

Arena 不主要测：

- 长篇语言表达
- 文采
- 外部知识
- 纯记忆题

---

## 4. Evidence 层级

Arena 的 measurement 不能只盯最终名次，要分层采样。

## 4.1 Decision-level evidence

最小 evidence 单位是单个决策机会。

Arena 中主要包括：

- `signal decision`
- `probe decision`
- `wager decision`

每个决策记录至少需要：

- `decision_type`
- `was_auto_action`
- `legal_action_count`
- `chosen_action`
- `stack_before`
- `pot_before`
- `blind_level`
- `stage`
- `facing_to_call`
- `expected_state_seq`
- `accepted_state_seq`

## 4.2 Hand-level evidence

每手汇总：

- 本手参与人数
- 决策机会数
- 有效决策数
- auto action 数
- raise / call / fold / probe 结构
- `stack_delta`
- 是否淘汰
- 是否为关键阶段手

## 4.3 Tournament-level evidence

整场汇总：

- finishing percentile
- hand count
- meaningful decision count
- stage coverage
- timeout share
- blind-only elimination share
- final table exposure
- time-cap finish flag

## 4.4 Rolling profile

最终给 rating 的不是某一场的故事，而是最近多场的统计画像：

- `mu`
- `sigma`
- `arena_reliability`
- `rolling_stage_coverage`
- `rolling_timeout_rate`
- `rolling_confidence_weight`

---

## 5. 什么叫“有效决策”

这里必须从“动作存在”升级到“动作有测量价值”。

## 5.1 定义：decision opportunity

一个 seat 在某手某阶段，若满足：

- seat 仍 active
- 非 forced blind/ante 扣费
- 存在至少 `2` 个不同后果的合法动作

则记为一次 `decision opportunity`。

## 5.2 定义：meaningful decision

一次决策若满足：

- 不是 auto action
- 不是协议层无效动作
- 不是唯一合法动作
- 对 stack、pot、survival、信息量至少一项有实际影响

则记为一次 `meaningful decision`。

## 5.3 三类 meaningful decision

### Meaningful signal

满足：

- 该手仍处于正常多人对抗环境
- 玩家主动提交非默认 signal
- signal 会进入本手后续公共上下文

### Meaningful probe

满足：

- 玩家有足够 stack 支付 `probe_cost`
- probe 与 pass_probe 后续信息集不同
- 该选择不是超时自动生成

### Meaningful wager

满足：

- 玩家面临至少两个真实不同的 wager 路径
- 例如 `check vs bet`、`fold vs call`、`call vs raise`
- 最终动作不是 auto check / auto fold

## 5.4 明确不算 meaningful 的情况

以下不应计入 meaningful decisions：

- forced blind / ante
- auto action
- 被协议拒绝的无效动作
- 只有唯一合法动作时的被动推进
- 纯 UI 重试且无状态变化

---

## 6. 单场 tournament 的信号质量结构

一场赛的质量不由冠军故事决定，而由五类结构指标决定。

## 6.1 Sample Sufficiency

看每个 entrant 是否真正拿到了足够样本。

关键指标：

- `median_hands_played_per_entrant`
- `p75_hands_played_per_entrant`
- `median_meaningful_decisions_per_entrant`
- `p75_meaningful_decisions_per_entrant`

## 6.2 Stage Coverage

看样本是否只停留在前期，还是覆盖了多种压力场景。

关键指标：

- `early_stage_decision_share`
- `mid_stage_decision_share`
- `bubble_stage_decision_share`
- `final_table_decision_share`

## 6.3 Execution Cleanliness

看赛果是不是被 infra / timeout 污染。

关键指标：

- `timeout_auto_action_rate`
- `invalid_action_rate`
- `state_seq_mismatch_rate`
- `disconnect_recovery_rate`

## 6.4 Blind Attrition Dominance

看淘汰是不是主要来自纯 blind 税。

关键指标：

- `blind_only_elimination_rate`
- `low_interaction_hand_share`
- `pre_showdown_forced_exit_share`

## 6.5 Tournament Closure Quality

看 tournament 是自然收敛还是被 time-cap 生硬截断。

关键指标：

- `time_cap_finish`
- `time_cap_finish_rate`
- `final_table_mean_hands`
- `average_stack_bb_at_final_table_start`

---

## 7. V1 建议的最低门槛

以下阈值不是链上真理，但建议作为 Alpha 运营与仿真 baseline。

## 7.1 Hard fail

命中以下任一条件，这场赛不应产出 multiplier：

- `practice` 或 `exhibition`
- 非 `human_only rated`
- final table 出现 bot
- replay parity 失败
- authoritative event 缺失
- 严重 collusion case 命中 `no_multiplier`
- tournament 过程中出现不可恢复 state corruption

## 7.2 Soft fail

命中以下情况时，允许存档并更新低权重 rating，但应降权：

- `time_cap_finish = true`
- `median_hands_played_per_entrant < 8`
- `median_meaningful_decisions_per_entrant < 18`
- `final_table_mean_hands < 6`
- `timeout_auto_action_rate` 过高
- `blind_only_elimination_rate` 过高
- `invalid_action_rate` 明显高于正常值

## 7.3 Target zone

建议把以下视为“合格 rated shard”目标区：

- `median_hands_played_per_entrant >= 8`
- `p75_hands_played_per_entrant >= 12`
- `median_meaningful_decisions_per_entrant >= 18`
- `p75_meaningful_decisions_per_entrant >= 24`
- `final_table_mean_hands >= 6`
- `time_cap_finish_rate <= 10%`
- `timeout_auto_action_rate <= 8%`
- `blind_only_elimination_rate <= 25%`

这些不是 UI 指标，而是 measurement quality gate。

---

## 8. 单场 confidence_weight

每场 rated tournament 除了 `tournament_score`，还应生成：

- `confidence_weight ∈ [0,1]`

它表示这场 evidence 值得被吸收多少。

## 8.1 计算思路

建议把置信度拆成四个因子：

```text
confidence_weight
  = sample_sufficiency_factor
  * stage_coverage_factor
  * execution_cleanliness_factor
  * closure_quality_factor
```

每个因子都在 `[0,1]`。

## 8.2 因子含义

### sample_sufficiency_factor

若 entrant 普遍只打很少手，则下降。

### stage_coverage_factor

若整场几乎没有 bubble / FT / 中后段压力样本，则下降。

### execution_cleanliness_factor

若 timeout、invalid、state mismatch 过高，则下降。

### closure_quality_factor

若频繁靠 time-cap 收场，或 FT 过短，则下降。

## 8.3 V1 简化离散桶

Alpha 阶段建议先不用复杂连续函数，先用离散桶：

- `1.00`：完全合格
- `0.75`：轻度降权
- `0.50`：明显降权
- `0.25`：只保留弱证据
- `0.00`：存档但不进 multiplier

这样更容易解释和排障。

---

## 9. 单个 entrant 的 per-tournament measurement

一场赛结束后，不只给一个名次，还要给一组 entrant 级 measurement。

## 9.1 必要字段

建议 `arena_rating_input` 至少包含：

- `tournament_id`
- `miner_id`
- `rated_or_practice`
- `human_only`
- `entrants`
- `finish_rank`
- `finish_percentile`
- `hands_played`
- `meaningful_decisions`
- `auto_actions`
- `timeouts`
- `invalid_actions`
- `stage_reached`
- `reached_bubble`
- `reached_final_table`
- `stack_path_summary`
- `placement_component`
- `stack_efficiency_component`
- `decision_validity_component`
- `timeout_penalty`
- `invalid_penalty`
- `collusion_adjustment`
- `tournament_score`
- `confidence_weight`
- `field_strength_adjustment`
- `bot_adjustment`
- `time_cap_adjustment`

## 9.2 stage_reached 口径

建议固定为：

- `early`
- `mid`
- `bubble`
- `final_table`
- `champion`

这样后面更容易做 rolling stage coverage。

## 9.3 stack_path_summary

不要只保留最终 stack。

至少保留：

- `stack_bb_at_start`
- `stack_bb_at_mid`
- `stack_bb_at_bubble`
- `stack_bb_at_ft_start`
- `max_stack_bb_seen`
- `min_stack_bb_seen`

这样才能区分：

- 一路稳健推进
- 大起大落
- 纯被 blind 吃死

---

## 10. `tournament_score` 的正确使用方式

现有规则中：

```text
tournament_score
  = 0.45 * placement_component
  + 0.35 * stack_efficiency_component
  + 0.20 * decision_validity_component
  - timeout_penalty
  - invalid_penalty
  - collusion_adjustment
```

这个结构是对的，但使用上必须注意三点。

## 10.1 不把单场名次神化

`placement_component` 不应一票否决其他信号。  
名次是结果，不是全部原因。

## 10.2 不给 final table 二次 bonus

进入 bubble、deep run、FT 这些信息：

- 可以进入 rating explanation
- 可以进入 stage coverage
- 不应再额外二次加分

否则会双重计量。

## 10.3 一定乘以 confidence_weight

真正喂给 rating 的不是裸 `tournament_score`，而是：

```text
effective_tournament_score
  = tournament_score * confidence_weight
```

这是把“赛制质量”显式带进测量链路的关键。

---

## 11. Rating 更新应该如何吸收单场结果

## 11.1 先吸收 score，再投影 multiplier

正确链路仍然是：

```text
tournament result
-> effective_tournament_score
-> arena rating update
-> conservative skill
-> arena_multiplier
```

## 11.2 `mu / sigma` 的直觉

- `mu`：Arena 里的当前能力估计
- `sigma`：这份估计还有多不确定

Arena 的 multiplier 看的是：

```text
conservative_skill = mu - 1.5 * sigma
```

所以：

- 单场证据越干净，越能帮助 `sigma` 收缩
- 单场证据越脏，越应该小权重甚至不吸收

## 11.3 比“更长 tournament”更重要的是“更快 sigma 收缩”

从测量角度看，真正重要的问题是：

- 多快把弱信号玩家和强信号玩家分开

而不是：

- 单场能否演出足够长的大戏

所以多场中等规模、信号密度高的 shard 往往优于一场巨型长赛。

---

## 12. 什么时候一场赛应该 no_multiplier

`no_multiplier` 不应该只在极端条件下使用。

建议分三类：

## 12.1 Structural no_multiplier

结构上天然不应进 multiplier：

- `practice`
- `exhibition`
- 非 `human_only rated`
- entrants 不达 rated 最低门槛

## 12.2 Integrity no_multiplier

完整性出问题：

- final table 出现 bot
- event log / snapshot 缺失
- replay parity mismatch
- state corruption

## 12.3 Measurement no_multiplier

测量质量太差：

- `confidence_weight = 0`
- `blind_only_elimination_rate` 极端异常
- `timeout_auto_action_rate` 极端异常
- tournament 基本没有形成有效交互

这里的原则是：

> **与其写入一场低质量 multiplier，不如只让它留在审计层。**

---

## 13. Wave / shard 视角下的测量

如果未来一个 wave 里有多个并发 MTT shard，measurement 应这样看。

## 13.1 Wave 不是比赛单位，是 sampling container

wave 负责：

- 收集同一时窗 entrants
- 按规则分配到 shard
- 统一 policy bundle

真正的比赛和 measurement 单位仍然是：

- `arena_tournament` shard

## 13.2 Shard 之间要做可比性校准

多个 shard 并发时，要记录：

- shard entrant count
- shard average pre-tournament rating
- shard timeout ecology
- shard time-cap flag

这样 rating 更新时，`field_strength_adjustment` 才有依据。

## 13.3 不要求每个 shard 一模一样

多个 shard 不需要：

- 完全相同 hands 数
- 完全相同 bubble 时长
- 完全相同 FT 时长

但必须：

- 同政策版本
- 同 blind schedule
- 同评分公式
- 同 confidence gate

---

## 14. 线上监控与看板

Arena measurement 需要单独看板，不然产品会误判“比赛开了很多就说明有效”。

## 14.1 Tournament quality dashboard

至少展示：

- entrants
- rounds played
- hands played
- time-cap finish flag
- median hands per entrant
- median meaningful decisions per entrant
- FT mean hands
- timeout auto-action rate
- blind-only elimination rate
- confidence_weight bucket
- no_multiplier reason

## 14.2 Entrant quality dashboard

至少展示：

- rolling hands played
- rolling meaningful decisions
- rolling timeout rate
- rolling stage coverage
- rolling `mu`
- rolling `sigma`
- rolling confidence

## 14.3 Ops alert

建议直接告警：

- `time_cap_finish_rate` 连续超阈值
- `timeout_auto_action_rate` 异常飙升
- `blind_only_elimination_rate` 异常飙升
- `median_meaningful_decisions_per_entrant` 断崖下降
- `replay parity mismatch > 0`

---

## 15. 仿真与验收

Arena 是否“测得准”，不能靠主观感觉，必须靠仿真。

## 15.1 必做 bot 桶

至少持续跑：

- random bot
- tight/passive bot
- always-probe bot
- timeout bot
- soft-play pair
- chip-dump pair
- single-strong-clean bot

## 15.2 重点看什么

不是只看谁冠军更多，而要看：

- stronger bots 的 `mu` 是否稳定更高
- `sigma` 是否能随样本数正常收缩
- timeout / collusion bots 是否被显著拉低
- shard 之间 rating 是否可比
- time-cap finish 是否扭曲 ranking

## 15.3 最重要的验收问题

建议把下面三问当成 Arena measurement 的核心验收：

1. **如果两个 agent 实力有真实差异，系统能否在 10-20 场内分开它们？**
2. **如果两个 agent 实力接近，系统会不会因为单场偶然性过度放大差距？**
3. **如果一场赛很脏，系统能不能主动少信它？**

如果这三问答不出来，Arena 就还没准备好上 multiplier。

---

## 16. 调参原则

如果 Arena 测量效果不好，优先级应固定为：

1. 提升单手信息含量
2. 提升 meaningful decision 占比
3. 降低 timeout / auto-action 污染
4. 调整前中段 blind 节奏
5. 增加 wave 频率
6. 最后才考虑扩大单场 field 或延长总时长

这条顺序非常重要。  
不然很容易走到“用更长赛程掩盖低信号结构”的错误方向。

---

## 17. 最终结论

Arena 是否有效，不由“这场打了多久”决定，而由三件事决定：

1. **样本够不够**
2. **决策密不密**
3. **证据干不干净**

所以 Arena 的最终 measurement 原则应该是：

> **短而高密度、可 replay、可降权的 tournament evidence，优于长而低密度、解释困难的巨型 tournament。**

这也意味着：

> **Arena multiplier 的可信度来自 rolling confidence-aware rating，而不是单场戏剧性。**

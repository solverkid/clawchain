# ClawChain Harness Simulation Plan

**版本**: 0.1  
**日期**: 2026-04-09  
**状态**: Alpha launch simulation / backtest / shadow plan  
**上游文档**:
- [docs/MINING_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md)
- [docs/HARNESS_BACKEND_ARCHITECTURE.md](/Users/yanchengren/Documents/Projects/clawchain/docs/HARNESS_BACKEND_ARCHITECTURE.md)
- [docs/DYNAMIC_ARENA_ALPHA_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/DYNAMIC_ARENA_ALPHA_DESIGN.md)

---

## 1. 目标

本计划的目标不是证明“能跑”，而是证明以下四件事：

- 强 AI 与强 harness 的长期排序优于便宜脚本
- cluster spraying / baseline nudging / no-reveal 不会有正期望
- daily anchor 和 Arena multiplier 不会把噪声放大成奖励
- launch 后的运营恢复链路是可重放、可解释、可回滚的

---

## 2. 必测的五类仿真

## 2.1 Historical Replay

输入：

- Polymarket market snapshots
- Binance top-of-book / trade features
- official task pack generation logic

目的：

- 验证 `baseline_q`
- 验证 `commit_close_ref_price`
- 验证 `fast_ticket` 分布
- 验证 `copy_cap` 是否足以压住 baseline-nudge

## 2.2 Adversarial Forecast Bots

至少实现：

- `copy_market_bot`
- `baseline_nudge_bot`
- `single_strong_clean_bot`
- `multi_account_spray_cluster`
- `delayed_reveal_bot`
- `skip_aware_selective_bot`

目的：

- 测 Sybil / copy-trading / infra advantage
- 测 `economic_unit` 规则是否有效
- 测 `admission_hold` 和 `20/80` 是否足够硬

## 2.3 Cross-lane Aggregation Replay

把以下三条线一起回放：

- `forecast_15m`
- `daily_anchor`
- `arena_multiplier`

目的：

- 验证 `daily` 只作 anchor 时是否仍过度放大同日主题
- 验证 `reward_window` carry-forward 不会造成奖励跳变
- 验证 `arena_multiplier` 的噪声不会压过 fast lane

## 2.4 Arena Monte Carlo + Self-play

至少实现：

- random bot
- tight/passive bot
- always-probe bot
- soft-play pair
- chip-dump pair
- timeout bot

同时覆盖 3 个 regime family：

- `signal_noisy`
- `event_skewed`
- `pressure_heavy`

目的：

- 验证 multiplier 是否足够稳定
- 验证 human-only rated 是否能稳定成赛
- 验证 `time-cap finish` 不会系统性奖励被动生存

## 2.5 Operational Shadow Drills

至少演练：

- `feed gap at freeze`
- `task_degraded`
- `task_voided`
- `daily_reconciliation drift`
- `anchor_pending`
- `projector rebuild`
- `replay parity mismatch`

目的：

- 证明 reward correctness 始终高于 UI freshness
- 证明客服和运维不需要直接查库才看得懂问题

---

## 3. Alpha 默认参数 sweep

## 3.1 Forecast sweeps

围绕当前默认值做小范围 sweep：

- `baseline blend`
  - `0.90/0.10`
  - `0.85/0.15` default
  - `0.80/0.20`
- `epsilon`
  - `0.005`
  - `0.010` default
  - `0.015`
- `anti-copy threshold`
  - `0.02`
  - `0.03` default
  - `0.04`
- `commit window`
  - `2s`
  - `3s` default
  - `5s`
- `p_yes_bps clamp`
  - `1500..8500` default
  - `2000..8000`

## 3.2 Daily sweeps

- `daily_anchor cap`
  - `0.98..1.02`
  - `0.97..1.03` default
  - `0.96..1.04`
- `publish/cutoff`
  - `00:00 UTC` default
  - `08:00 UTC`

## 3.3 Arena sweeps

- `arena_multiplier cap`
  - `0.98..1.02`
  - `0.96..1.04` default
- `rolling_window`
  - `15`
  - `20` default
  - `30`
- `beta`
  - `0.010`
  - `0.015` default
  - `0.020`

---

## 4. 核心评估指标

## 4.1 Ranking Quality

- top-decile clean miners 的长期分是否稳定高于 copy bots
- selective strong bots 是否高于 always-online mediocre bots
- cluster spraying 的 cluster-level ROI 是否低于 clean single miner

## 4.2 Abuse Economics

- `copy_market_bot ROI`
- `baseline_nudge_bot ROI`
- `multi_account_spray_cluster ROI`
- `delayed_reveal_bot ROI`
- `no_reveal strategy ROI`

要求：

- 上述 abusive strategies 的期望收益必须为负或显著低于 clean miner

## 4.3 Cross-lane Stability

- daily anchor 对 `model_reliability` 的影响是否被稳定钳住
- Arena multiplier 是否造成总奖励排序反转
- `anti_abuse_discount` 是否只生效一次

## 4.4 Operational Correctness

- `replay parity`
- `reward_window rebuild delta`
- `projector rebuild parity`
- `settlement lag`
- `support case explainability`

---

## 5. Go / No-Go Gates

## 5.1 Offline Replay Gate

必须同时满足：

- `replay parity = 100%`
- `copy_market_bot median ROI <= clean miner top-decile ROI 的 10%`
- `baseline_nudge_bot ROI <= clean miner median ROI 的 25%`
- `multi_account_spray_cluster ROI <= clean single miner ROI`
- `same-day cross-lane amplification <= 1.05x fast-only baseline`

## 5.2 Internal Shadow Gate

必须同时满足：

- `pack publish p95 <= publish_at + 2s`
- `commit acceptance >= 99.5%`
- `reveal completion >= 98%`
- `degraded + voided forecast tasks <= 1%`
- `score explanation` 与 replay proof 一致

## 5.3 Limited Rewards Gate

必须同时满足：

- `reward_window` 重算后差异为 `0`
- 自动风控误杀率在目标范围内
- `support high-severity cases < 5 / 1000 task_runs`
- `admission_hold` 与 maturity 释放逻辑无歧义

## 5.4 Daily Anchor Gate

必须同时满足：

- `daily provisional vs reconciled drift <= 0.5%`
- `daily_anchor` 不把 `model_reliability` 推出 `0.97..1.03`
- `Market Health Score` 触发的 degraded/void 与规则一致

## 5.5 Arena Rated Gate

必须同时满足：

- `>= 80%` rated tournaments 达到 `>=56` human entrants
- `practice/exhibition` 不进入 multiplier
- `0` 个 multiplier-eligible tournament 含 bot final table
- `>= 90%` rated tournaments 在 `24m` cap 前自然结束
- 单场 tournament 对最终 `arena_multiplier` 的最大变动 `<= 0.01`

---

## 6. 仿真产物

每轮 simulation 至少产出：

- 参数配置清单
- bot roster 与版本
- reward distribution 报告
- ranking stability 报告
- abuse ROI 报告
- cross-lane amplification 报告
- replay parity 报告
- 推荐参数变更

建议输出到：

- `artifacts/simulation/<date>/<run_id>/summary.json`
- `artifacts/simulation/<date>/<run_id>/plots/`
- `artifacts/simulation/<date>/<run_id>/replay_checks/`

---

## 7. 首轮建议执行顺序

1. 历史 replay 跑 forecast scorer
2. 加入 adversarial forecast bots
3. 再叠 daily anchor
4. 最后接 Arena Monte Carlo
5. 全链路 shadow drill 放到上线前一周

原因：

- fast lane 是主奖励面
- 先把主评分稳定，再叠乘子与慢反馈
- 不要一开始就把 Arena 噪声引入主排序

---

## 8. 明确不做

在 Alpha launch 前，这份 simulation plan 不要求：

- 完整链上 settlement 模拟
- 真实外部 stake/delegation 市场模拟
- 开放式研究任务 benchmark
- 通用 agent 全能力 benchmark

Alpha 的目标是：

> **证明当前 mining mechanism 的排序、反撸、可解释性和运营可恢复性成立。**

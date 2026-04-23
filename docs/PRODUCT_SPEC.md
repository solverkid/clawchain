# ClawChain 产品全案

**版本**: 1.3
**日期**: 2026-04-23
**作者**: ClawChain 产品团队
**状态**: 已合并 wave-2 synthesis 的 companion-first 产品层
**关联文档**:
- [docs/superpowers/specs/2026-04-10-companion-miner-product-layer-design.md](/Users/yanchengren/Documents/Projects/clawchain/docs/superpowers/specs/2026-04-10-companion-miner-product-layer-design.md)
- [docs/MINING_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md)
- [docs/IMPLEMENTATION_STATUS_2026_04_10.md](/Users/yanchengren/Documents/Projects/clawchain/docs/IMPLEMENTATION_STATUS_2026_04_10.md)

---

## 第0章：文档权威与 OpenClaw 依赖边界

> **权威顺序**
>
> 1. stock OpenClaw 能力边界以官方 OpenClaw 文档与官方 release 为准
> 2. 当前 runtime 真相以 [`docs/IMPLEMENTATION_STATUS_2026_04_10.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/IMPLEMENTATION_STATUS_2026_04_10.md) 为准
> 3. 本文定义矿工产品语言、壳层目标、surface 边界
> 4. 协议、评分、结算、anti-abuse 以 [`docs/MINING_DESIGN.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md) 为准

本文只负责定义 **ClawChain 在 OpenClaw 之上的自定义 miner product layer**。
这意味着：

- OpenClaw 的 `Gateway / TUI / Control UI / WebChat / macOS menu bar / skills / plugins / commands / cron / heartbeat` 都是 **host capabilities**
- `Companion Home / Activities / History / Network` 是 **ClawChain custom surfaces**
- 任何 “today / current / already available” 的表述，都不能越过 `IMPLEMENTATION_STATUS`

### 0.1 官方 OpenClaw host contract 快照（2026-04-23 refresh）

基于官方 OpenClaw 文档与最新官方 release，当前必须锁死这些宿主边界：

| 项目 | 当前确认 truth |
|---|---|
| 最新官方 release | `v2026.4.21`，发布于 2026-04-22 |
| 架构中心 | OpenClaw 仍然是 **Gateway-first**；Gateway 是 session、routing、channel 的权威 |
| TUI | 是 host surface，不是 source of truth；`--local` 模式不等价于 Gateway-backed companion |
| Browser surface | `Control UI / WebChat` 已 shipped，但它们是宿主 chat/control/browser 面，不自动等于 ClawChain `Companion Home / Activities / History` |
| Native companion | 官方 shipped 的原生 companion 级桌面 surface 当前只有 macOS menu bar；Linux/Windows native companion app 仍是 upstream planned |
| Built-in commands | stock OpenClaw 内建命令不包含 `/buddy`、`/brief`、`/pause`、`/resume` |
| Deterministic control | 如果 ClawChain 需要确定性 companion verbs，必须自己注册 extension command，并通过 plugin command 或 `command-dispatch: tool` 路由 |
| Durable buddy state | OpenClaw session / presence / transcript 不能直接当 durable companion store |

## 第1章：产品定位与价值主张

### 1.1 一句话定义

**ClawChain 是一个 companion-first 的 AI agent mining 产品层: 用户先拥有一个常驻矿工伙伴，它在后台自动参与各种 activities 来挖取 CLAW。**

### 1.2 为什么 OpenClaw 用户要挖矿？

**理由一：零额外硬件成本。** OpenClaw 用户已经在运行 agent（Mac mini、VPS、树莓派），设备 24/7 在线但 agent 大部分时间不是在执行高价值用户请求。ClawChain 把这部分空闲运行时间变成挖矿机会。不需要额外 GPU，不需要再部署另一套客户端。当前支持路径是 `openclaw onboard --install-daemon` 后运行 repo-local `skill/scripts/setup.py -> mine.py -> status.py`；“安装 Skill 并激活 companion 即挖”仍然是 target-state distribution 话术，不是当前 install contract。

**理由二：奖励叙事和留存叙事终于统一。** 过去“运行矿工脚本”适合作为内核，不适合作为产品正脸。companion-first 让后台 runtime、前台状态反馈、每日轻互动和多玩法扩展有了统一容器。用户理解的是“我的伙伴在外面工作”，而不是“我在维护一个脚本”。

**理由三：$CLAW 的分发仍然有真实协议基础。** $CLAW 总量 2100 万，永不增发，100% 挖矿分发。V1 当前公开现实不是通用微任务，而是 `forecast_15m` 主公开赛道 + `daily_anchor` 校准赛道 + `arena_multiplier` 解释字段叠加 service-led settlement。Poker MTT、MTT-like bluff arena 以及其它新 activity 已进入 operator integration / acceptance 视野，但这不等于它们已经成为默认公开 miner activities。奖励仍来自活动结果与协议结算，而不是陪伴行为本身。收益推演见第6章。

### 1.3 差异化：OpenClaw Agent 的独特优势

| 维度 | Grass | Bittensor | Koii | **ClawChain** |
|------|-------|-----------|------|---------------|
| 参与门槛 | 装浏览器插件 | 需要 GPU + ML 专业知识 | 下载桌面应用 + 8GB RAM | **已有 OpenClaw + repo-local runtime；目标态再收口成 published companion install** |
| 用户拥有的对象 | 账号/插件 | Subnet / validator / miner | 节点 | **常驻 companion + wallet + activity history** |
| 贡献类型 | 被动带宽共享 | ML 模型推理/训练 | JS 计算任务 | **Forecast-first public activities + future game-like activities** |
| 是否需要额外硬件 | 否 | 是（GPU） | 否 | **否** |
| 工作是否有用 | 数据采集 | AI 模型训练 | 通用计算 | **真实市场判断与 agent evaluation** |
| 用户基础 | 从零开始获客 | 技术社区 | 开发者社区 | **复用 OpenClaw 存量用户** |

**核心差异化：ClawChain 不需要从零重建 agent 基础设施。** OpenClaw 已经有 Gateway、TUI、Control UI、WebChat、macOS 菜单栏状态、skills、plugins、cron / heartbeat 等 host capabilities。但这些 host capabilities 不等于已完成的 ClawChain companion 产品层。ClawChain 真正要做的是：在这些宿主表面之上定义并实现自己的 companion shell、activity IA、命令面和状态解释层。

### 1.3.1 外部产品模式综合

本轮深度调研后，V1 的 companion shell 应明确吸收这些外部模式：

- **官方 OpenClaw / EdgeClaw / ClawGPT / Drakeling 一致指向的一点**：强 companion 不是 Tamagotchi，而是 **one identity, many surfaces, explicit state store**
- **Fraction AI / Grass / Nodepay 一致验证的一点**：强 miner retention 不是重交互，而是 **被动主循环 + 可解释进展 + 少量 intentional action**
- **因此 ClawChain 的正确方向**：
  - 伙伴身份必须持久
  - ambient presence 要强，但不能变成 chore loop
  - activities 是 shell 的扩展，不是 shell 本体
  - 状态、收益、历史、变化原因必须可解释

### 1.4 产品语言规则

第一层产品语言统一使用：

- `companion` / `buddy` / `伙伴`
- `activity` / `活动`
- `check-in` / `daily brief`
- `current work` / `当前在做什么`

内部或高级文档保留：

- `lane`
- `reward_window`
- `settlement_batch`
- `baseline_q`
- `commit-reveal`

原则：

- 用户先看到宠物和活动，不先看到 lane 和脚本。
- 协议术语只在解释层、技术层、运营层展开。

---

## 第2章：Companion-first 产品层

### 2.1 V1 产品对象

V1 的主产品层由 4 个对象组成：

1. **Companion**
   - 用户先拥有一个常驻矿工伙伴
   - 它有名字、形象、状态、战绩、成长和陪伴记忆
   - 它不是某一种 activity，也不是某一个脚本

2. **Runtime**
   - 后台自动运行的挖矿内核
   - 负责调度 activity、提交结果、同步状态、领取奖励
   - 当前代码现实是 `skill/scripts/mine.py` + mining service，而不是旧 Go `clawminer`
   - companion 的身份、mood、偏好、history 需要独立持久化，不能只依赖 OpenClaw session transcript

3. **Activities**
   - `forecast_15m`（公开主 activity）
   - `daily_anchor`（公开校准 activity）
   - `arena_multiplier`（当前是 read-only multiplier explanation，不是独立公开 activity）
   - 未来的游戏类、预测类、挑战类玩法，例如 `poker mtt`
   - 用户层统一叫 activities，不让 `lane` 成为第一心智

4. **Surfaces**
   - TUI：跨平台的 ambient companion 入口
   - Slash commands / plugin commands：最短交互路径
   - Control UI / WebChat：中深度 browser host surface
   - macOS Menu Bar：仅 macOS 的 glanceable companion surface
   - Runtime：执行层，不是主产品入口

### 2.1.1 当前 activity 可见性矩阵

| 产品层对象 | 当前可见性 | 当前对矿工的正确说法 | 备注 |
|---|---|---|---|
| Forecast Activity | 公开 today | 默认公开主收益 activity | 协议源头是 `forecast_15m` |
| Daily Calibration Activity | 公开 today | 自动参与的慢反馈校准 activity | 协议源头是 `daily_anchor` |
| Arena Multiplier | 公开 explain-only | 只读 multiplier / explanation 字段 | 当前不是独立公开 activity surface |
| Poker MTT | operator-gated / future | 已有集成与 acceptance，但不是默认公开 miner activity | 未来独立 skill-game mining lane |
| Bluff arena / future games | future | 可并入 unified activity registry | 当前不应写成 shipped reality |

### 2.2 V1 companion 定义

用户首先拥有的是一个 persistent mining buddy，而不是一个“命令行矿工”。

它承担 3 件事：

- 把后台挖矿行为人格化和可见化
- 把多种 activity 统一装进一个稳定外壳
- 提供低打扰、强陪伴、强状态反馈的回访理由

它不承担 3 件事：

- 不能直接发奖励
- 不能替代协议结算逻辑
- 不能变成重交互电子宠物

### 2.2.1 Durable companion contract

如果 V1 要把 companion 做成可跨 surface 一致出现的对象，至少要把状态拆成这些稳定子对象：

- `CompanionProfile`
  - `companion_id`
  - `display_name`
  - `avatar_seed`
  - `created_at`
- `CompanionPreferences`
  - `activity_policy`
  - `daily_brief_reminder`
  - `notification_level`
  - `interaction_style`
- `CompanionRuntimeSnapshot`
  - `current_work`
  - `current_activity`
  - `mood`
  - `presence_state`
  - `updated_at`
- `CompanionDailyBrief`
  - `brief_date`
  - `status`
  - `recommended_action`
  - `last_check_in_at`
- `CompanionActivityView`
  - `activity_id`
  - `title`
  - `mode`
  - `earning_role`
  - `status`
  - `recommended_reason`
- `CompanionEventLog`
  - `event_type`
  - `headline`
  - `event_at`
- `CompanionSyncMeta`
  - `source`
  - `version`
  - `last_synced_at`

规则：

- browser truth 必须来自 service-owned envelope，而不是 session transcript
- 本地脚本缓存可以存在，但不能成为跨 surface 的权威状态
- personality 文案不能覆盖真实 runtime / reward / settlement 状态

### 2.3 Activity system

V1 统一把挖矿形式叫作 **Activities**，并按 3 类组织：

- **Auto Activities**
  - `forecast_15m`
  - `daily_anchor`
  - 默认由 runtime 自动参与

- **Scheduled Competitive Activities**
  - `arena`
  - `poker mtt`（后续独立 skill-game mining lane，不与 `arena` 混写）
  - 有固定窗口，用于 multiplier / practice / calibration

- **Light Interactive Activities**
  - 每日微互动
  - 未来的轻小游戏和短预测
  - 在 V1 中不构成主收益来源

每个 activity 卡片都要说明：

- 这是什么
- 是自动还是可互动
- 在收益里扮演什么角色
- companion 当前是否参与
- 最近结果如何
- 为什么今天推荐或不推荐

### 2.4 Durable V1 IA ownership

V1 需要把“谁拥有业务 IA”和“谁只是宿主壳”拆开：

- **ClawChain miner client**
  - `Companion Home`
  - `Activities`
  - `History`
  - `Network`
  - contextual `Review`
- **operator console**
  - `Abuse Review`
  - `Settlement Ops`
  - `Arena Ops`
  - support / override / rollback
- **stock OpenClaw host surfaces**
  - macOS menu bar status
  - TUI
  - Control UI
  - WebChat
  - skills / plugins / slash-command infrastructure

官方 host-surface support matrix：

| Surface | OpenClaw upstream 状态 | ClawChain V1 角色 |
|---|---|---|
| TUI | shipped | 跨平台 ambient / status / command 入口 |
| Control UI | shipped | browser host / chat / control |
| WebChat | shipped | browser host / chat / session continuity |
| macOS menu bar | shipped, macOS only | glanceable optional extra |
| Linux / Windows native companion app | not shipped upstream | 不作为 V1 依赖 |

推荐 surface 优先级：

- 跨平台默认：`TUI -> commands -> Control UI / WebChat`
- macOS 补充：`menu bar -> TUI -> commands -> Control UI / WebChat`
- operator surfaces 永远不参与 miner client 的一级入口排序

规则：

- `Risk` 不进入 miner 一级导航
- `Review` 在 V1 只作为 Home / History 的上下文解释层，不做 raw case queue
- stock OpenClaw surfaces 提供承载、认证、通知和命令路由，不自动提供 ClawChain 的 `Companion Home / Activities / History`
- 如果命令承担确定性控制，优先使用 plugin command 或 `command-dispatch: tool`

### 2.5 每日轻互动边界

V1 允许每天一次轻互动，目标是 10-30 秒：

- `鼓励 / 打招呼`
- `今日倾向`
- `打一把很短的微活动`

边界必须锁死：

- 不做喂食、清洁、掉血、死亡
- 不做漏签惩罚
- 不做一天点很多次
- 不把 check-in 直接做成发币龙头
- 用户今天不来，runtime 仍继续工作

### 2.6 V1 非目标

V1 不做：

- Electron 深度客户端
- 重交互宠物养成
- 以宠物行为替代协议奖励
- 把 operator dashboard 直接当用户产品层

Electron 只进入 roadmap，作为后续深度 activity 容器。

---

## 第3章：用户旅程（User Journey）

> **Current-runtime note:** 本章优先描述当前可运行路径；所有 “Companion Home / `/buddy` / daily brief / pause-resume shell” 只作为 target-state 产品目标，不应被读成已交付功能。

### 3.1 当前支持路径：从 OpenClaw 启动到跑通当前 miner

V1 今天真正支持的路径是：

1. 按官方路径启动 OpenClaw
   - `openclaw onboard --install-daemon`
   - `openclaw gateway status`
   - `openclaw dashboard`
2. 在 repo 内运行 ClawChain 当前脚本路径
   - `python3 skill/scripts/setup.py`
   - `python3 skill/scripts/mine.py`
   - `python3 skill/scripts/status.py`
3. 用 service-backed read surfaces 看状态
- `status.py`
- repo `dashboard`
- repo `network`
- repo `risk`（operator-oriented）

当前 repo 还没有默认 shipped 的：

- `Companion Home`
- `Activities`
- `History`
- durable companion state store
- deterministic `/buddy` / `/pause` / `/resume`

### 3.2 Target-state：companion activation 路径

长期目标仍然是：

- 用户先“拥有一个伙伴”
- 后台 runtime 自动工作
- 用户通过 Menu Bar / TUI / browser host / commands 做 glance、brief、history 和轻控制
- 跨平台默认依赖 `Gateway + TUI + Control UI / WebChat`
- macOS menu bar 是增强 surface，不是 V1 baseline

但这条 companion activation 路径在今天仍然是 **product target-state**，不是当前 runnable onboarding 契约。

### 3.3 当前错误处理与用户预期

当前应该向用户明确的不是“宠物化文案”，而是 runtime truth：

| 场景 | 当前正确说法 |
|---|---|
| 服务不可达 | 当前 miner 依赖 `mining-service`；如果 service 不可达，脚本会失败或降级，不能伪装成 companion 正常工作 |
| 钱包问题 | 当前钱包是 `~/.clawchain/wallet.json` 的本地加密私钥文件，不是 seed phrase / BIP-39 恢复流 |
| OpenClaw 表面 | stock OpenClaw 提供宿主表面，不等于已完成的 ClawChain custom miner UI |
| `daily_anchor` 长跑 | 当前 `daily_anchor` 路径仍有幂等性缺口，不能对外包装成 fully hardened always-on daemon |

### 3.4 FAQ（当前 truth 版）

**Q: 挖矿会影响我正常使用 OpenClaw 吗？**
A: 当前 repo 还没有真正的 idle detection / auto-pause control plane。不要把今天的脚本路径描述成“和正常使用完全隔离的后台 companion daemon”。

**Q: 需要什么模型？**
A: 当前最小路径可以走 `heuristic_v1`。如果你使用 `codex_v1`，需要本地可用的 Codex CLI。

**Q: 钱包是什么形态？**
A: 当前是本地 secp256k1 私钥文件，默认路径 `~/.clawchain/wallet.json`，不是 seed phrase 钱包。

**Q: 现在能看到真正的 buddy UI 吗？**
A: 还不能。当前只有 service-backed CLI/read-model surfaces；companion-first 壳层仍是目标态。

---

## 第4章：Companion Runtime 与控制面设计

> **Current vs target-state rule:** 本章同时描述当前运行时真相和目标 companion 壳层合同。凡是没有脚本、路由、默认页面或权威状态源支持的内容，一律视为 target-state。

### 4.1 当前安装与配置路径

当前受支持路径以 [`SETUP.md`](/Users/yanchengren/Documents/Projects/clawchain/SETUP.md) 为准，最小流程是：

```bash
openclaw onboard --install-daemon
openclaw gateway status
openclaw dashboard

python3 skill/scripts/setup.py
python3 skill/scripts/mine.py
python3 skill/scripts/status.py
```

说明：

- `openclaw dashboard` 打开的是 stock Control UI
- repo 当前主要是 repo-local runtime path，而不是已发布的 ClawHub skill / plugin contract
- `openclaw skills install <slug>` 只适用于已发布 skill；不能把 repo 本地目录直接冒充成官方主安装流

### 4.2 当前 runtime 真相与 source of truth

当前系统的 source of truth 分层如下：

- **服务端权威**
  - `mining-service + Postgres`
  - miners / tasks / submissions / rewards / holds / reward windows / settlement batches / anchor jobs / risk
- **本地状态**
  - `wallet.json`
  - `config.json`
  - append-only local mining log
- **尚未存在**
  - service-owned companion state store
  - cross-surface consistent companion identity
  - deterministic pause/resume control plane

当前 miner loop 真实结构：

1. `setup.py` 生成或加载钱包、注册 miner、写回 `miner_address` 和 `forecast_mode`
2. `mine.py` 拉 active tasks，优先 `daily_anchor`，再处理 capped `forecast_15m`
3. 客户端执行 commit / reveal
4. 结算、reward window、settlement batch、anchor progression 全部留在服务端 reconcile 链路

已知当前 gap：

- `daily_anchor` 在重复 already-committed / already-revealed 路径上还没有完全收成幂等
- 在修掉之前，不能把当前 loop 写成 fully hardened always-on companion daemon

### 4.3 当前命令面与 target-state verbs

#### 当前真实入口

- `python3 skill/scripts/setup.py`
- `python3 skill/scripts/mine.py`
- `python3 skill/scripts/status.py`

当前并不存在的 current-state 命令：

- `claw wallet ...`
- `claw stats`
- `claw history`
- `claw stake`
- `claw unstake`

#### Target-state product verbs

这些可以保留为 companion-first 的目标命令面，但必须标成 target-state：

- `/buddy`
- `/brief`
- `/activities`
- `/why`
- `/history`
- `/pause`
- `/resume`
- `/settings`

兼容 alias 只在命令注册和冲突规则明确后启用：

- `/checkin -> /brief`
- `/wake -> /resume`
- `/status -> /buddy` 仅在不与 stock OpenClaw `/status` 语义冲突时启用

规则：

- 控制类 verbs 如果要承担确定性行为，优先走 plugin command 或 `command-dispatch: tool`
- `/buddy` / `/brief` / `/pause` / `/resume` 是 **ClawChain extension commands**，不是 stock OpenClaw built-ins
- 在没有 deterministic control plane 前，它们不能被写成“当前默认可用”
- 不要把 stock OpenClaw `/status` 和 ClawChain 的 companion home verb 混写成同一个默认命令

### 4.4 当前可见 surfaces 与 durable V1 IA 目标

#### 当前 repo surfaces

- `status.py`
- `website /dashboard`
- `website /network`
- `website /risk`

其中：

- `/dashboard` 仍是 read-model surface，不是 Companion Home
- `/network` 更接近公开网络/排行视图
- `/risk` 是 operator-oriented，不应进入 miner 一级 IA

#### Durable V1 IA 目标

ClawChain V1 的业务 IA 应固定为：

- `Companion Home`
- `Activities`
- `History`
- `Network`
- contextual `Review`

不应进入 miner 一级 IA：

- `Risk`
- `Abuse Review`
- raw settlement tooling
- raw operator queue

### 4.5 当前有效配置 vs target-state 偏好层

当前有效配置以 [`skill/scripts/config.json`](/Users/yanchengren/Documents/Projects/clawchain/skill/scripts/config.json) 为准，主要包括：

| 配置项 | 当前作用 |
|---|---|
| `rpc_url` | 指向当前 mining-service |
| `miner_name` | 注册时使用的 miner 名称 |
| `wallet_path` | 本地钱包路径 |
| `forecast_mode` | `heuristic_v1` / `codex_v1` |
| `codex_binary` / `codex_model` / `codex_timeout_seconds` | `codex_v1` 辅助配置 |
| `request_timeout_seconds` | HTTP 请求超时 |
| `min_commit_time_remaining_seconds` | commit 前最低剩余时间 |
| `parallel_tasks` | 本地并行 worker 数 |
| `max_tasks_per_run` | 每轮处理的 fast task 上限 |
| `miner_address` | 当前 miner 地址 |

target-state 但当前还没有落地为权威 companion contract 的配置包括：

- `activity_policy`
- `daily_brief_reminder`
- `surface_mode`
- true pause / resume state
- durable companion preferences

也就是说，今天不能把这些 companion 偏好字段写成 current-state truth。

---

## 第5章：验证机制详细设计

本章描述协议层验证逻辑，不是用户第一心智。用户在产品层看到的是 companion、activities 和结果解释；底层仍由这些验证机制保证公平性与结算可信度。

### 5.1 设计原则

验证设计必须同时满足：
1. **正确性**：奖励来自标准化 activity 的真实结果，而不是陪伴行为
2. **可复算**：关键输入、评分版本、结算逻辑必须能解释和回放
3. **小网络可运行**：Alpha 不依赖大规模去中心化验证者集合
4. **anti-farm**：复制市场、多号、延迟抄袭、共谋不能长期吃满收益

### 5.2 Forecast activity 的验证

V1 当前主奖励来源是 `forecast_15m`。

验证链路：

```text
统一 snapshot pack
-> baseline_q
-> miner commit
-> miner reveal (p_yes_bps)
-> reference price resolve
-> proper-score improvement
-> fast tickets
```

关键规则：

- 所有矿工基于同一冻结数据包作答
- 输出统一为 `p_yes_bps`
- 通过 `commit-reveal` 避免直接抄袭
- 参考价格由独立 `ReferencePriceService` 结算
- 评分核心是 **improvement over baseline**

也就是说，系统奖励的是“比公开基线更早、更准、更稳定”的判断，而不是单纯命中方向。

### 5.3 Daily activity 的验证

`daily_anchor` 在 V1 主要承担 **slow-feedback calibration** 角色。

规则：

- 与 forecast 共用 `commit-reveal` 和 `p_yes_bps`
- 默认只通过 anchor score 影响 `model_reliability`
- V1 day-1 不默认发放 direct reward
- 结算状态允许 `provisional -> matured -> reconciled / void`

这保证 daily lane 先做可靠校准，再决定是否扩大直接奖励权重。

### 5.4 Arena activity 的验证

`arena` 在 V1 不是主奖励池，而是 multiplier 来源。

验证链路：

```text
tournament result
-> rating update
-> conservative arena skill
-> arena_multiplier
```

规则：

- practice 与 rated 分开
- multiplier 只使用合格 rated 结果
- V1 multiplier 范围收窄，避免 arena 喧宾夺主
- Arena runtime 与 mining runtime 解耦，结果通过服务写回

### 5.5 Poker MTT activity 的产品边界

`poker mtt` 是后续独立 skill-game mining lane，不等同于现有 `arena / bluff arena`。

产品层可以把它归入 scheduled competitive activity，但协议层必须保持独立:

- runtime 参考 `lepoker-gameserver` 的 table / ws / live ranking
- control/read model 参考 `lepoker-auth` 的 auth / MQ / final ranking / hand history / HUD / ELO
- reward 仍接 ClawChain 的 `reward_window / settlement_batch`
- reward-bearing 结果只从 canonical `poker_mtt_final_rankings` 投影；legacy/admin 结果入口必须引用并匹配已保存 final ranking
- 链上第一阶段只锚定窗口 root，不逐手或逐场上链
- 第一阶段默认关闭自动 `poker_mtt_daily` / `poker_mtt_weekly` 发奖和 poker settlement anchoring，通过环境级 rollout gate 显式打开
- settlement anchor submitter 必须显式授权，不允许任意账户提交窗口 root
- final ranking 可能晚于比赛结束出现，因为 donor finish handling、hand history、hidden eval、evidence lock 都是异步链路
- 公开侧使用 `poker_mtt_public_rank` / `poker_mtt_public_rating`，不展示 hidden-eval-derived internal `total_score`

2026-04-17 Phase 2 执行口径统一为 **Poker MTT Evidence Phase 2**。它不是 ClawChain 产品总 Phase 2，也不是链上 reputation 阶段，范围只包含：

- completed-hand evidence ingest
- final ranking durable handoff
- short-term / long-term HUD projector
- service-owned hidden eval
- `poker_mtt_public_rank` / `poker_mtt_public_rating`
- multiplier / rating snapshot
- daily / weekly reward-window hardening
- settlement anchor query / verification
- 10k-20k MTT scale gate 和 abuse / recovery gate

它明确不包含：

- per-hand / per-game on-chain writes
- public ELO 直接参与奖励权重
- `x/reputation` 直接写入
- donor Java monolith port
- 高价值 mainnet 奖励默认开启

截至 2026-04-17，Poker MTT Evidence Phase 2 已经形成本地可回归的 beta slice，但 production harness gates 仍未全部通过：

- 一手完成后写 completed-hand evidence，不按 action 永久写入
- final ranking、hand-history manifest、HUD、hidden eval、rating / multiplier snapshot 都进入可审计链路
- daily / weekly reward window 设计上只吃 locked、evidence-ready 的 `poker_mtt_result_entries`；production rollout 前还要补 `accepted_degraded`、policy filter、server economic-unit、identity binding 等 harness gate
- 20k-player reward projection 不返回整包 rows，主 artifact 保存 root/page refs，page artifact 保存 rows
- settlement batch 设计上通过 typed `x/settlement` state query 确认 root/hash，不只看 tx success；production rollout 前还要补外部 query wiring 和 full-field metadata confirmation

2026-04-19 更新：`make test-poker-mtt-phase2` 已成为 Poker MTT Evidence Phase 2 的 local beta 一键 gate，覆盖 Go authadapter / Poker MTT / settlement tests、Phase 2 Python evidence-to-anchor tests、以及 30/300/20k/2,000-table offline load shape。它证明本地 beta slice，不代表 reward-bearing production rollout。

产品上仍然按 beta / internal rollout 处理：自动发奖和 poker settlement anchoring 默认关闭，公开页面只展示 `poker_mtt_public_rank` / `poker_mtt_public_rating`，不展示 hidden-eval-derived `total_score`。

当前公开矿工契约额外边界：

- `Poker MTT` 不进入默认公开 activity catalog
- `poker_mtt_daily` / `poker_mtt_weekly` 不应被写成当前公开 task lane
- reward-window build、hidden eval、HUD、projection、rollback、release-review bundle 都仍属于 operator / release-review 语境

2026-04-17 Phase 3 统一定义为 **Poker MTT Production Readiness**，不是 high-value reward launch。Phase 3 的目标是关闭这些闸门：

- Go finalizer/projector 与 FastAPI final ranking contract
- registration / waitlist / no-show donor parity
- MQ checkpoint / replay / DLQ / lag 与 policy-owned evidence readiness
- admin fail-closed、resolved admin principal、durable reward-bound identity
- Postgres-backed 20k reward-window service path、budget ledger、aggregation policy、multiplier effective-window
- external `x/settlement` query proof 和 bounded anchor artifacts
- window-level `reputation_delta` dry-run，仍不直接写 `x/reputation`

2026-04-18 Phase 3 收口口径：

- `make test-poker-mtt-phase3-fast` 是本地合并前 gate
- `make test-poker-mtt-phase3-heavy` 是 staging/manual release evidence gate
- heavy gate 证据写入 `artifacts/poker-mtt/phase3/`，但不进 git
- `make materialize-poker-mtt-phase3-release-artifacts` 会把本地 canonical Phase 3 closeout 证据和 release-review bundle 一次性落到 `artifacts/poker-mtt/phase3/` 与 `artifacts/poker-mtt/release-review/`
- reward-bearing rollout 仍要单独 release review，明确 budget source、operator roles、chain submitter、monitoring 和 rollback；现在已有 `make build-poker-mtt-release-review-bundle`、[`docs/POKER_MTT_REWARD_ROLLOUT_RELEASE_REVIEW.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/POKER_MTT_REWARD_ROLLOUT_RELEASE_REVIEW.md) 和 [`docs/runbooks/poker-mtt-rollout-rollback.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/runbooks/poker-mtt-rollout-rollback.md) 作为标准入口
- 2026-04-22 follow-on：`x/reputation` 已补 keeper-level append-only `reputation_delta` apply contract、challenge wiring、以及 anchored settlement batch guard；它仍不是公开 tx/gRPC 写路径，也不改变 “单场 Poker MTT 结果不能直接写 reputation” 这个边界

面向用户只展示:

- 当前 MTT 状态
- 公开 final ranking / `poker_mtt_public_rating`
- reward timeline
- evidence / settlement 状态
- provisional / locked / anchored 状态

不展示:

- hidden eval 细则
- shadow table / bot table 身份
- 对手长期 ELO
- 风控阈值
- 单场 multiplier 草算值

详细设计见 [docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/POKER_MTT_REWARDS_AND_MULTIPLIER_DESIGN.md)、[docs/POKER_MTT_PHASE3_PRODUCTION_READINESS_SPEC.md](/Users/yanchengren/Documents/Projects/clawchain/docs/POKER_MTT_PHASE3_PRODUCTION_READINESS_SPEC.md)、[docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md](/Users/yanchengren/Documents/Projects/clawchain/docs/LEPOKER_AUTH_MTT_HUD_REFERENCE.md)、[docs/POKER_MTT_PHASE2_HARNESS_SPECS.md](/Users/yanchengren/Documents/Projects/clawchain/docs/POKER_MTT_PHASE2_HARNESS_SPECS.md)、[docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2.md](/Users/yanchengren/Documents/Projects/clawchain/docs/superpowers/plans/2026-04-17-poker-mtt-evidence-phase2.md) 和 [docs/superpowers/plans/2026-04-20-poker-mtt-phase3-production-readiness.md](/Users/yanchengren/Documents/Projects/clawchain/docs/superpowers/plans/2026-04-20-poker-mtt-phase3-production-readiness.md)。

### 5.6 anti-abuse、review 与成熟度

V1 的核心防护不是“绝对封禁”，而是风险调节：

- `economic_unit` / cluster 去重
- `probation`
- `reward maturity / held rewards`
- `anti_abuse_discount`
- `manual review`

对用户要解释为：

- 为什么某个窗口没有拿满收益
- 为什么奖励进入了 hold / review
- 当前是系统折扣还是人工审查

而不是只给一个黑盒封禁结论。

### 5.7 必须可解释的验证结果

V1 必须能向矿工解释：

- `baseline_q`
- 我的 `p_yes_bps`
- 真实 outcome
- edge / ticket / calibration impact
- reward timeline
- arena multiplier
- review / maturity / hold 状态

矿工看到的是 companion 汇报结果；底层仍然是统一的评分、风控和结算系统。

---

## 第6章：Token 经济模型

本章描述的是协议层奖励与供给设计。产品层的 companion、daily brief 和活动可见性不改变奖励源头。尤其需要明确：**每日 check-in 不是直接奖励 faucet。**

### 6.1 基本参数

```
名称:      $CLAW
总量:      21,000,000（硬顶，永不增发）
精度:      6 位小数（最小单位 = 1 uCLAW = 0.000001 CLAW）
共识:      CometBFT (Tendermint BFT)
出块时间:  6 秒
Epoch:     100 区块 = 10 分钟
```

### 6.2 Token 分配 — 100% 挖矿，真正的公平发射

| 类别 | 比例 | 数量 (CLAW) | 释放规则 |
|------|------|------------|---------|
| 挖矿奖励 | **100%** | **21,000,000** | 减半曲线释放，~130年挖完 |
| 创始团队 | 0% | 0 | — |
| 生态基金 | 0% | 0 | — |
| 早期贡献者 | 0% | 0 | — |

**Every single CLAW was mined, not printed.** 创世流通量 = 0。没有预挖，没有 ICO/IDO，没有团队预留。所有 21,000,000 CLAW 只能通过挖矿获得。

### 6.3 释放曲线（前10年）

每 epoch（10分钟）释放的挖矿奖励：
- 基础奖励 = 50 CLAW/epoch → **100% 给矿工**
- 每 210,000 epoch（约4年）减半
- 每天 144 epoch（24h × 6 = 144 个 10分钟周期）
- **每天矿工产出 = 50 × 144 = 7,200 CLAW**

| 年份 | Epoch 奖励 | 每天矿工产出 | 年产出 | 累计已挖 | 已挖占比 |
|------|-----------|------------|--------|---------|---------|
| 第1年 | 50 CLAW | 7,200 CLAW | 2,628,000 | 2,628,000 | 12.5% |
| 第2年 | 50 CLAW | 7,200 CLAW | 2,628,000 | 5,256,000 | 25.0% |
| 第3年 | 50 CLAW | 7,200 CLAW | 2,628,000 | 7,884,000 | 37.5% |
| 第4年 | 50 CLAW | 7,200 CLAW | 2,628,000 | 10,512,000 | 50.1% |
| 第5年 | 25 CLAW | 3,600 CLAW | 1,314,000 | 11,826,000 | 56.3% |
| 第6年 | 25 CLAW | 3,600 CLAW | 1,314,000 | 13,140,000 | 62.6% |
| 第7年 | 12.5 CLAW | 1,800 CLAW | 657,000 | 13,797,000 | 65.7% |
| 第8年 | 12.5 CLAW | 1,800 CLAW | 657,000 | 14,454,000 | 68.8% |
| 第9年 | 6.25 CLAW | 900 CLAW | 328,500 | 14,782,500 | 70.4% |
| 第10年 | 6.25 CLAW | 900 CLAW | 328,500 | 15,111,000 | 71.9% |

> **注**：100% 挖矿分配 = 21,000,000 CLAW 全部通过减半曲线释放。第一减半期产出 10,500,000 CLAW（占总量 50%）。预计 ~130 年挖完全部供应量。

**计算过程**：
- 每 epoch 10 分钟 → 每天 60×24/10 = 144 epoch
- 第一减半期（~4年）= 210,000 epoch = 210,000 × 10min ÷ 60 ÷ 24 ÷ 365 ≈ 3.995 年
- 第一减半期产出 = 50 × 210,000 = 10,500,000 CLAW → 100% 给矿工

### 6.4 每 Epoch 奖励分配明细

```text
每 epoch 50 CLAW 分配（100% Fair Launch）:
└── 矿工池: 50 CLAW (100%)
    └── 按 final_mining_score 加权分配

final_mining_score
  = base_score
  * model_reliability
  * ops_reliability
  * arena_multiplier
  * anti_abuse_discount
```

其中：

- `base_score` 主要来自 fast forecast activities
- `daily_anchor` 在 V1 默认只通过 calibration / reliability 间接影响奖励
- `arena` 在 V1 默认只通过 multiplier 小幅影响奖励
- `poker_mtt_daily` / `poker_mtt_weekly` 如果启用，必须从同一 miner emission budget 中划出显式子预算，不产生额外发行
- `daily check-in`、鼓励动作、陪伴行为不直接发币

验证者收益与生态建设仍按后续网络阶段单独处理，不从 companion 行为本身出发。

### 6.5 矿工收益推演（最关键）

**假设条件**：
- 每 epoch 矿工池 = **50 CLAW**（100% Fair Launch）
- 每天 144 epoch
- **每天矿工池总量 = 50 × 144 = 7,200 CLAW**
- 所有矿工平均完成相同数量任务（简化假设）
- 不考虑早鸟倍率和连续在线加成（取基础值）

#### 每个矿工每天挖矿收益

| 矿工数量 | 每人每天 CLAW | FDV $1M (≈$0.048/CLAW) | FDV $10M (≈$0.48/CLAW) | FDV $100M (≈$4.76/CLAW) |
|---------|-------------|----------------------|----------------------|------------------------|
| 100 | 72 | $3.43 | $34.29 | $342.86 |
| 500 | 14.4 | $0.69 | $6.86 | $68.57 |
| 1,000 | 7.2 | $0.34 | $3.43 | $34.29 |
| 5,000 | 1.44 | $0.07 | $0.69 | $6.86 |
| 10,000 | 0.72 | $0.03 | $0.34 | $3.43 |

> **计算**: FDV $1M 时单个 CLAW 价格 = $1,000,000 / 21,000,000 = $0.04762

**加入早鸟倍率后的收益（前 1000 名矿工享受 3x）**：

| 矿工数量 | 基础 CLAW/天 | 3x 早鸟 CLAW/天 | FDV $10M 早鸟日收益 |
|---------|------------|---------------|-------------------|
| 100 | 72 | 216 | $103.68 |
| 500 | 14.4 | 43.2 | $20.74 |
| 1,000 | 7.2 | 21.6 | $10.37 |

> **注**：如果上线阶段启用早鸟活动，它只应作为冷启动增长杠杆，而不是 companion 产品层的核心承诺。实际协议分配仍按 `final_mining_score` 加权。

#### 与竞品矿工收益对比

| 项目 | 矿工数量 | 每人日收益（估算） | 门槛 | 额外成本 |
|------|---------|-----------------|------|---------|
| **Grass** | ~3,000,000 | 积分制，首次空投约 $70/人均（$200M / 2.8M 人） | 装插件 | 无 |
| **Bittensor** | ~10,000 矿工 | 变动大，高端 subnet 矿工 $50-500/天 | GPU + ML 技能 | GPU 电费 + API |
| **Koii** | ~87,000 节点 | $0.5-5/天（依任务） | 桌面应用 + 8GB RAM | 电费 |
| **io.net** | ~数千供应商 | 按 GPU 型号定价，A100 约 $1-2/小时 | GPU 硬件 | 硬件 + 电费 |
| **ClawChain (100矿工)** | 100 | **$34.29/天 (FDV $10M)** | repo-local runtime（target-state 为 published companion install） | 无额外成本 |
| **ClawChain (1000矿工)** | 1,000 | **$3.43/天 (FDV $10M)** | repo-local runtime（target-state 为 published companion install） | 无额外成本 |

**关键洞察**：100% Fair Launch 让矿工收益比之前提升 67%（从 4,320 → 7,200 CLAW/天）。早期矿工（<500人）在 FDV $10M 场景下，日收益远超 Koii 顶级节点，且零额外硬件成本。

### 6.6 通胀率计算

"通胀率"在 ClawChain 语境下指：新挖出的 CLAW 占已流通量的比例。

| 时间点 | 已流通量（估算） | 日新增 | 年化通胀率 |
|--------|----------------|--------|----------|
| 第1个月 | ~216,000 | 7,200 | ~1,217% |
| 第6个月 | ~1,296,000 | 7,200 | ~203% |
| 第1年末 | ~2,628,000 | 7,200 | ~100% |
| 第2年末 | ~5,256,000 | 7,200 | ~50% |
| 第4年末 | ~10,512,000 | 7,200→3,600 | ~12.5% |
| 第6年末 | ~13,140,000 | 1,800 | ~5.0% |

> **注**：早期通胀率极高是所有公平发射项目的特征（BTC 第一年通胀率也是无穷大）。关键是流通量绝对值小，市场冲击有限。100% Fair Launch 意味着没有团队/贡献者大额解锁抛压，但早期流通量绝对值小，市场冲击有限。

### 6.7 锁定期设计

| 角色 | 是否锁定 | 设计理由 |
|------|---------|---------|
| 挖矿奖励 | **默认不锁定**，但可进入 maturity / hold | 降低门槛，同时保留 probation / anti-abuse 空间 |
| 质押中的 CLAW | 7天解质押冷却期 | 防止快速进出操纵 |

**100% Fair Launch 意味着没有团队锁定期、没有生态基金释放——因为根本没有这些分配。** 所有人获得 CLAW 的唯一方式是挖矿。

**设计决策：默认即时可得，但允许协议层 maturity/hold。** 理由：
1. companion-first 产品层需要尽快反馈，不适合把所有奖励都做成长锁仓
2. 但 forecast / arena / risk review 场景下仍需要 maturity 和 held rewards 作为 anti-abuse 手段
3. 产品层必须把这件事解释成 `reward maturity / review`，而不是电子宠物式惩罚

### 6.8 生态建设和治理

**100% Fair Launch 没有预留生态基金。** 生态建设通过以下方式实现：

1. **交易手续费**：Task Marketplace 上线后，交易手续费的一部分用于验证者激励和生态建设
2. **社区提案**：矿工通过 DAO 提案自愿捐赠 CLAW 支持生态项目
3. **开发者激励**：通过 Task Marketplace 发布开发任务，用 CLAW 支付

**治理机制**：
- Phase 1（<1000 矿工）：社区多签（3/5）管理
- Phase 2（>1000 矿工）：完全 DAO 治理，1 CLAW = 1 票，提案需 10% 质押量法定人数

---

## 第7章：冷启动策略

### Phase 0: 内测与 dogfood（4周）

**谁来测？**
- OpenClaw 核心用户（Discord 社区活跃成员，约 50-100 人）
- 创始团队自运行 5-10 个节点

**怎么测？**
```text
Week 1: companion activation + wallet + runtime dogfood
Week 2: 邀请 20 名核心用户，验证 gateway-backed TUI / extension command / brief 路径
Week 3: 扩展到 50 名用户，验证 forecast / daily / arena 状态反馈
Week 4: 压力测试，修 bug，完善文档和 Control UI IA
```

**内测激励**：
- "Genesis Buddy" 徽章 / NFT
- Companion 名称与首批身份标记
- 发现关键 bug 额外奖励

### Phase 1: invite-only 测试网（6-8周）

**测试网目标：**
- 验证 companion-first shell 是否比“脚本挖矿”有更高留存
- 验证 `forecast_15m + daily_anchor + arena_multiplier` 的状态表达是否清晰
- 验证 TUI / plugin command / Control UI 的职责边界

**测试网积分设计：**

```text
Claw Points:
├── Activation point: 成功激活 companion
├── Quality point: 完成有效 forecast / daily / approved future activity
├── Return point: 回来查看状态与完成 daily brief
├── Bug report: 有效问题反馈
└── No idle-online farming: 不因纯在线时长发积分
```

原则：

- 不给“挂机在线”本身发点
- 不把每日轻互动做成强制任务
- 不把推荐奖励设计成简单拉人头分成

### Phase 2: 公开测试网 / 公开 companion launch

**创世配置：**
```text
初始矿工: invite-only 用户迁移
主入口: stock OpenClaw host surfaces（跨平台默认 `TUI / Control UI / WebChat`；macOS 可加 `menu bar`）承载 ClawChain miner client
默认一级 IA: Companion Home / Activities / History / Network
默认 activities: forecast-first（forecast_15m + daily_anchor），arena 先以 read-only multiplier 解释层存在
默认日互动: 1 次可选 daily brief
```

**上线清单：**
- [ ] companion activation 路径打通
- [ ] service-owned companion state store 可用
- [ ] `daily_anchor` 幂等性缺口已修复，或已被明确 quarantined 出 launch contract
- [ ] 选择并实现 extension command transport（plugin command 或 skill command + `command-dispatch: tool`）
- [ ] `/buddy`、`/brief`、`/activities`、`/pause`、`/resume` 定义清楚
- [ ] miner client `Companion Home / Activities / History / Network` 可用
- [ ] `Risk` 不出现在 miner 一级导航
- [ ] operator console 与 miner client route 分离
- [ ] settlement explanation 和 reward timeline 可解释
- [ ] 文档与 onboarding 同步更新

### Phase 3: 主网上线与增长策略

Poker MTT 不直接进入本节的增长策略。它先走 `docs/POKER_MTT_PHASE3_PRODUCTION_READINESS_SPEC.md` 的 production readiness gates；所有 P0 gates 通过前，只允许 internal/staging/provisional reward 展示，不作为 high-value mainnet reward 增长手段。

**从 100 到 1000 矿工：**

```text
策略 1: companion-first 内容传播
├── “我的 buddy 今天又挖了多少” 状态截图
├── TUI / Control UI companion 展示
└── 强化回访与陪伴，而不是单纯收益截图

策略 2: activity 扩展
├── 先做 forecast / daily / arena 的可见性完整闭环
├── 再逐步加入轻互动小游戏和预测扩展
└── 每新增 activity，都挂进统一 activity catalog

策略 3: 生态外溢
├── 开放给更多 OpenClaw 用户
├── 再考虑非 OpenClaw agent framework
└── 保持 companion shell 不变
```

**从 1000 到 10000 矿工：**

```text
策略 4: 更完整的 history / ranking / review surfaces
策略 5: 更多 activity 供给
策略 6: 后续深度客户端（Electron）只作为 optional engagement layer
```

### 社区运营计划

| 渠道 | 内容 | 频率 |
|------|------|------|
| Discord | 挖矿 FAQ、技术支持、策略讨论 | 每日 |
| Twitter/X | 网络统计、矿工收益展示、生态更新 | 每周 3 次 |
| Blog | 技术深潜、路线图更新、生态报告 | 每月 2 篇 |
| YouTube | 安装教程、挖矿收益展示、AMA 录播 | 每月 2 次 |
| Telegram | 中文社区运营 | 每日 |

---

## 第8章：技术路线图

### 已完成 ✅

| 功能 | 状态 | 说明 |
|------|------|------|
| companion-first 产品层设计 | ✅ | 持久伙伴 + activities + surfaces 已锁定 |
| forecast-first 挖矿设计 | ✅ | `forecast_15m + daily_anchor + arena_multiplier` 已锁定 |
| 产品全案文档 | ✅ | 本文档 |
| browser read-surface / skill runtime 原型 | ✅ | 已有 `dashboard / network / risk / skill runtime` 基础，但尚未完成 durable V1 IA split |
| Token 经济模型设计 | ✅ | 21M CLAW，减半曲线 |

### Q2 2026（4-6月）

| 功能 | 优先级 | 预计工时 |
|------|--------|---------|
| 文档 truth 收口（authority / current-vs-target） | P0 | 1 周 |
| operator console 与 miner client IA 拆分 | P0 | 1 周 |
| companion identity + state model | P0 | 1 周 |
| non-stock extension command transport + registration（`/buddy` 等） | P0 | 1 周 |
| TUI 状态表达与 daily brief 提醒 | P0 | 1 周 |
| miner client `Companion Home` browser prototype | P0 | 2 周 |
| Activities / History / Network IA | P0 | 2 周 |
| runtime 状态同步与 API contract | P0 | 1 周 |
| reward timeline / explanation surfaces | P1 | 1 周 |

### Q3 2026（7-9月）

| 功能 | 优先级 | 预计工时 |
|------|--------|---------|
| 公开测试网 companion launch | P0 | 1 周 |
| Arena read surfaces / public ranking surfaces | P0 | 2 周 |
| Home / History contextual review explanation | P1 | 1 周 |
| Activity registry 扩展机制 | P1 | 2 周 |
| 文档与 onboarding polish | P1 | 1 周 |
| 安全审计 / abuse policy 收敛 | P0 | 外包，4 周 |

### Q4 2026（10-12月）

| 功能 | 优先级 | 预计工时 |
|------|--------|---------|
| 主网上线 | P0 | 2 周 |
| Bug Bounty 计划 | P0 | 持续 |
| 更多 light interactive activities | P1 | 2 周 |
| 移动端 companion 状态查看 | P2 | 2 周 |
| Electron 深度 activity 容器探索 | P2 | 2 周 |

### 2027 长期愿景

- **多 Agent 框架支持**：扩展 companion shell 到更多 agent runtime
- **更丰富的 activity catalog**：加入更多游戏化和预测类挖矿活动
- **深度桌面层**：Electron 作为 optional deep engagement surface，而不是 V1 主入口
- **去中心化 AI agent evaluation infra**：ClawChain 成为 agent evaluation 和激励基础设施
- **DAO 完全自治**：社区治理所有协议参数

---

## 第9章：风险分析

### 9.1 技术风险

| 风险 | 概率 | 影响 | 缓解方案 |
|------|------|------|---------|
| 链安全漏洞（共识攻击） | 中 | 高 | 使用经过实战检验的 CometBFT；主网前做第三方安全审计；Bug Bounty 持续运行 |
| 智能合约 bug | 中 | 高 | 模块化设计，每个模块独立审计；升级采用 governance proposal 机制 |
| 验证机制被绕过 | 低 | 高 | 多层防御（精确匹配 + 多数投票 + spot check）；动态难度调整 |
| LLM 输出一致性差 | 中 | 中 | 确定性任务占 40%+；非确定性任务用宽松阈值容忍差异 |

### 9.2 经济风险

| 风险 | 概率 | 影响 | 缓解方案 |
|------|------|------|---------|
| Token 价值归零 | 中 | 高 | 不做价格承诺；聚焦网络实际用途（Task Marketplace）；公平发射无预挖 |
| 早期通胀过高导致抛压 | 中 | 中 | 质押锁定减少流通量；早期流通量绝对值小；100% 挖矿无团队抛压 |
| 矿工收益不够吸引人 | 中 | 高 | 早鸟倍率制造早期高收益；积极推动 FDV 增长；Task Marketplace 提供额外收入 |
| 早期流动性不足 | 中 | 中 | 100% 公平发射创世流通=0，靠挖矿产出建立流通；DEX 上线后改善 |

### 9.3 运营风险

| 风险 | 概率 | 影响 | 缓解方案 |
|------|------|------|---------|
| 矿工不来（冷启动失败） | 中 | 极高 | OpenClaw 存量用户是天然种子矿工；早鸟倍率 + 推荐奖励；测试网积分兑换 |
| 验证不可靠（小网络） | 高 | 高 | 小网络只开确定性任务；创始团队节点临时充当验证者；渐进去中心化 |
| 团队开发资源不足 | 中 | 中 | 核心功能优先（链 + 挖矿 Skill）；社区治理提案资助外部开发者 |
| companion 壳层表达不清 | 中 | 高 | companion home、activity catalog、status surfaces 必须先于大规模拉新稳定 |
| 社区活跃度低 | 中 | 中 | 每日 Discord 运营；buddy 状态分享内容；Hackathon 和教育活动 |

### 9.4 法律风险

| 风险 | 概率 | 影响 | 缓解方案 |
|------|------|------|---------|
| $CLAW 被认定为证券 | 低 | 极高 | **100% 公平发射**：零预挖、零团队分配、无预售、无 ICO/IDO、无投资合同；所有 CLAW 通过挖矿获得（类比 BTC 的矿工分发）；不做收益承诺 |
| 不同司法管辖区监管差异 | 高 | 中 | 初期不针对美国市场营销；遵循各地 KYC/AML 要求（如需）；法律顾问评估 |
| 挖矿活动的税务问题 | 高 | 低 | 提供工具帮助矿工追踪收益（税务导出）；不提供税务建议 |
| Task Marketplace 上的内容审核 | 中 | 中 | 任务发布需要质押；社区举报机制；违规任务 slash |
| Poker MTT 被误解为赌博或真钱锦标赛 | 中 | 高 | 明确其为 skill-game mining lane；不做逐场现金大奖；buy-in tier / prize pool / jurisdiction gating 必须经法律评估后再公开 |

### 9.5 风险优先级总结

```
最高风险（必须在主网前解决）:
├── 矿工不来 → 冷启动策略 + 存量用户转化
├── 验证不可靠 → 渐进式去中心化 + 确定性任务优先
└── Token 被认定为证券 → 公平发射 + 法律评估

中等风险（持续监控）:
├── Token 价值归零 → 聚焦实际用途
├── 安全漏洞 → 审计 + Bug Bounty
└── 团队资源不足 → 优先级管理

可接受风险:
├── 税务问题 → 提供工具
└── 早期流动性不足 → DEX 上线 + 社区流动性
```

---

## 附录 A：竞品研究数据汇总

| 项目 | 总供应量 | 矿工/节点数 | 冷启动方式 | 矿工日收益 | FDV (2026) |
|------|---------|------------|----------|----------|-----------|
| **Grass** | 1B GRASS | ~3M 用户 | 浏览器插件 + 空投 | 积分制 | ~$500M |
| **Bittensor** | 21M TAO | ~10K 矿工 | Subnet 创建低门槛 | $50-500/天 (高端) | ~$5B |
| **Koii** | KOII | ~87K 节点 | 桌面应用 + Docker | $0.5-5/天 | ~$50M |
| **io.net** | 800M IO | 数千供应商 | GPU 矿场转型 | 按 GPU 定价 | ~$500M |
| **Filecoin** | 2B FIL | 数千 SP | 质押 + 存储合约 | 变动大 | ~$3B |
| **Helium** | HNT | ~600K 热点 | 硬件 + PoC 激励 | 变动大 | ~$1B |
| **ClawChain** | **21M CLAW** | **目标 10K** | **OpenClaw companion + Skill** | **见第6章** | **TBD** |

## 附录 B：关键决策记录

| 决策 | 选择 | 理由 | 日期 |
|------|------|------|------|
| 总量 | 21M（非 1B） | 稀缺性叙事，比特币心智模型 | 2026-03-17 |
| 共识 | CometBFT | 成熟、经过实战、Cosmos 生态 | 2026-03-17 |
| 主产品层 | companion-first miner | 稳定外壳承接多 activity，避免 miner script 成为主入口 | 2026-04-10 |
| 挖矿奖励不锁定 | 即时到账 | 降低参与门槛，参考 Grass | 2026-03-18 |
| 小网络临时中心化 | 创始节点充当验证者 | 安全性 > 去中心化（早期） | 2026-03-18 |
| 公平发射 | 100% 挖矿，零团队/生态/贡献者分配 | 法律风险缓解 + 社区信任 + 比特币精神 | 2026-03-20 |
| 非确定性验证 | Multi-Judge 而非 Yuma | 小网络可行性 + 实现简单 | 2026-03-18 |

---

*本文档为 ClawChain 产品全案 v1.2，将随项目发展持续迭代。*

# ClawChain 产品全案

**版本**: 1.1
**日期**: 2026-04-11
**作者**: ClawChain 产品团队
**状态**: 已合并 companion-first 产品层
**关联文档**:
- [docs/superpowers/specs/2026-04-10-companion-miner-product-layer-design.md](/Users/yanchengren/Documents/Projects/clawchain/docs/superpowers/specs/2026-04-10-companion-miner-product-layer-design.md)
- [docs/MINING_DESIGN.md](/Users/yanchengren/Documents/Projects/clawchain/docs/MINING_DESIGN.md)

---

## 第1章：产品定位与价值主张

### 1.1 一句话定义

**ClawChain 是一个 companion-first 的 AI agent mining 产品层: 用户先拥有一个常驻矿工伙伴，它在后台自动参与各种 activities 来挖取 CLAW。**

### 1.2 为什么 OpenClaw 用户要挖矿？

**理由一：零额外硬件成本。** OpenClaw 用户已经在运行 agent（Mac mini、VPS、树莓派），设备 24/7 在线但 agent 大部分时间不是在执行高价值用户请求。ClawChain 把这部分空闲运行时间变成挖矿机会。不需要额外 GPU，不需要再部署另一套客户端，安装 Skill 并激活 companion 就能开始。

**理由二：奖励叙事和留存叙事终于统一。** 过去“运行矿工脚本”适合作为内核，不适合作为产品正脸。companion-first 让后台 runtime、前台状态反馈、每日轻互动和多玩法扩展有了统一容器。用户理解的是“我的伙伴在外面工作”，而不是“我在维护一个脚本”。

**理由三：$CLAW 的分发仍然有真实协议基础。** $CLAW 总量 2100 万，永不增发，100% 挖矿分发。V1 当前现实不是通用微任务，而是 `forecast_15m`、`daily_anchor`、`arena_multiplier` 三类 activities 叠加 service-led settlement；后续 `poker mtt` 作为独立 skill-game mining lane 接入同一 `reward_window / settlement_batch` 框架。奖励仍来自活动结果与协议结算，而不是陪伴行为本身。收益推演见第6章。

### 1.3 差异化：OpenClaw Agent 的独特优势

| 维度 | Grass | Bittensor | Koii | **ClawChain** |
|------|-------|-----------|------|---------------|
| 参与门槛 | 装浏览器插件 | 需要 GPU + ML 专业知识 | 下载桌面应用 + 8GB RAM | **已有 OpenClaw + Skill = 激活 companion 即挖** |
| 用户拥有的对象 | 账号/插件 | Subnet / validator / miner | 节点 | **常驻 companion + wallet + activity history** |
| 贡献类型 | 被动带宽共享 | ML 模型推理/训练 | JS 计算任务 | **Forecast / Arena / 未来游戏化 activities** |
| 是否需要额外硬件 | 否 | 是（GPU） | 否 | **否** |
| 工作是否有用 | 数据采集 | AI 模型训练 | 通用计算 | **真实市场判断与 agent evaluation** |
| 用户基础 | 从零开始获客 | 技术社区 | 开发者社区 | **复用 OpenClaw 存量用户** |

**核心差异化：ClawChain 不需要从零发明矿工容器。** OpenClaw 已经有 Gateway、TUI、Control UI/WebChat、macOS 菜单栏 companion、后台服务和命令面。ClawChain 的机会不是再造一个“miner app”，而是把这些 surfaces 统一到一个 persistent companion shell 里。

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
   - `forecast_15m`
   - `daily_anchor`
   - `arena`
   - 未来的游戏类、预测类、挑战类玩法
   - 用户层统一叫 activities，不让 `lane` 成为第一心智

4. **Surfaces**
   - macOS Menu Bar：最强 companion 入口
   - TUI：陪伴和即时状态
   - Slash commands / plugin commands：最短交互路径
   - Control UI / WebChat：完整信息面
   - Runtime：执行层，不是主产品入口

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

### 2.4 Surface 分工

- **macOS Menu Bar**：companion 的优先入口，适合常驻状态和回访
- **TUI**：终端内的 ambient chat/status surface
- **Plugin commands / slash commands**：`/buddy`、`/status`、`/activities`、`/checkin`、`/arena`、`/pause`、`/wake`
- **Control UI / WebChat**：Companion Home、Activities、Rankings、History、Review/Risk 子集
- **Operator surfaces**：仍然存在，但不是矿工主入口

说明：

- V1 不把公开 Web 页面直接等同于 OpenClaw Control UI
- 如果需要可控的命令行为，优先使用 native plugin command 或 skill `command-dispatch: tool`

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

### 3.1 完整步骤：从"听说"到"获得第一笔 $CLAW"

V1 目标仍然是 **5 分钟内从安装到开始挖矿**，但主路径从“运行脚本”改成“激活 companion”。

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 0: 听说 ClawChain                                        │
│  ├── Discord/Twitter/朋友推荐                                   │
│  └── "你的 companion 闲着也是闲着，不如让它出去挖矿"            │
│                                                                  │
│  Step 1: 安装 Skill / Plugin 并激活 companion（1分钟）           │
│  ├── git clone https://github.com/0xVeryBigOrange/clawchain     │
│  ├── cd clawchain                                               │
│  ├── openclaw onboard --install-daemon                          │
│  ├── openclaw skills install ... 或 openclaw plugins install... │
│  ├── 如需本地开发，再手动挂载 workspace 中的 skill/plugin        │
│  ├── python3 scripts/setup.py                                   │
│  └── 输出: "✅ Companion activated, wallet created"              │
│                                                                  │
│  Step 2: 初始化身份和钱包（30秒）                                 │
│  ├── 首次运行自动生成钱包                                        │
│  ├── 显示: 你的地址 claw1abc...xyz                               │
│  ├── 显示: 助记词（提示用户备份）                                 │
│  └── 输出: "💰 Wallet ready. Your buddy is ready to work."      │
│                                                                  │
│  Step 3: companion 开始自动工作                                  │
│  ├── runtime 连接 Gateway 与 ClawChain 服务                       │
│  ├── 自动进入 forecast / daily / arena 调度                       │
│  ├── companion 显示当前 work state                               │
│  └── 输出: "⛏️ Mining started. First activity joined."          │
│                                                                  │
│  Step 4: 第一次回来看状态（约10-15分钟后）                         │
│  ├── companion 汇报最近 activity                                  │
│  ├── 用户看到当前收益、活动、状态                                 │
│  └── 输出: "🎉 +0.42 CLAW earned! Buddy is now focused."        │
└─────────────────────────────────────────────────────────────────┘
```

**关键设计原则：**
- **零配置启动**：不需要手动设置 RPC、端口、网络参数
- **自动钱包生成**：不要求用户预先拥有钱包
- **自动为主**：安装后 companion 自动工作，不要求持续操作
- **即时反馈**：第一个 15m 窗口内就能看到工作状态
- **回访理由明确**：用户回来不是看原始脚本日志，而是看 buddy brief 和 activity 结果

### 3.2 新手引导设计

```
首次安装后的引导流程：

1. 欢迎消息:
   "🦞 Welcome to ClawChain.
    You now have a mining buddy that can earn $CLAW
    by joining activities while your agent is idle."

2. 激活 companion:
   "✨ Your buddy is waking up...
    It will work automatically in the background
    and report back through TUI / Control UI."

3. 钱包设置:
   "🔑 Generating your wallet...
    Address: claw1q2w3e4r5t...
    ⚠️ IMPORTANT: Write down your seed phrase:
    [abandon ability able about above absent ...]
    This is the ONLY way to recover your wallet."
    
    [I've saved my seed phrase] ← 用户确认后继续

4. companion 偏好（可选，默认值即可工作）:
   "⚙️ Companion Preferences (all optional):
    • Auto-mine when idle: ON (default)
    • Activity policy: Balanced (default)
    • Max CPU usage: 50% (default)
    • Daily brief reminder: ON (default)
    
    Type 'claw config' to change later."

5. 开始工作:
   "⛏️ Companion activated
    Current work: scouting forecast activities
    Mining status: ACTIVE
    Next forecast window in: 8:32
    
    Type '/buddy' or 'python3 scripts/status.py'
    anytime to check on your buddy."
```

### 3.3 错误处理

| 错误场景 | 用户看到的消息 | 自动处理 |
|---------|---------------|---------|
| 网络连接失败 | "⚠️ Buddy cannot reach ClawChain right now. Retrying in 30s..." | 指数退避重试，最大间隔 5 分钟 |
| 当前窗口未成功提交 | "⏰ Missed this activity window. Buddy will rejoin the next one." | 自动进入下一个 activity |
| 钱包文件损坏 | "🔑 Wallet file corrupted. Use 'claw wallet recover' with your seed phrase." | 引导恢复流程 |
| OpenClaw 版本过低 | "📦 ClawChain requires a recent OpenClaw version for TUI / control surfaces." | 显示升级命令 |
| AI 模型不可用 | "🤖 No AI model configured. Mining needs at least one LLM provider or local model." | 引导配置 LLM |
| Daily check-in 未完成 | "📝 No daily brief yet. Mining is still running." | 不扣收益，只保留轻提醒 |

### 3.4 FAQ

**Q: 挖矿会影响我正常使用 OpenClaw 吗？**  
A: 不会。挖矿 Skill 有空闲检测机制，只在 agent 没有处理用户请求时才接任务。一旦你开始和 agent 交互，挖矿自动暂停。

**Q: 需要什么 AI 模型？**  
A: 任何 OpenClaw 支持的 LLM 都行——本地模型（Ollama）或 API（OpenAI、Anthropic）。但注意，使用 API 模型挖矿会产生 API 费用，建议用本地模型。

**Q: 我的数据安全吗？**  
A: V1 当前主 activity 是标准化 forecast / daily / arena 数据包，不涉及你的个人会话内容。你的 companion 只处理公开或协议定义的任务输入。

**Q: 能在多台设备上挖矿吗？**  
A: 可以，但同一 IP 最多 3 个矿工节点（防女巫攻击）。每个矿工需要独立钱包和独立质押。

---

## 第4章：Companion Runtime 与控制面设计

### 4.1 安装与配置

```bash
# 安装（详见 SETUP.md）
git clone https://github.com/0xVeryBigOrange/clawchain.git
cd clawchain
openclaw onboard --install-daemon

# 优先使用 active workspace / official install flow
openclaw skills install ./skill
# 或在 plugin 化后:
# openclaw plugins install ./plugin

cd skill

# 初始化钱包 & 注册
python3 scripts/setup.py

# 启动后台 runtime
python3 scripts/mine.py

# 查看 companion 状态
python3 scripts/status.py

# 配置（可选）— 编辑 scripts/config.json
# 包括: 节点地址、LLM 配置、activity policy、提醒策略等
```

这几条命令在实现层仍然存在，但在产品层它们不再是主心智。主心智是 companion activation、background runtime 和 gateway-backed status surfaces。

### 4.2 Runtime 工作流程

```
┌──────────────────────────────────────────────────────────────┐
│                 ClawChain companion runtime 主循环             │
│                                                                │
│  1. COMPANION STATE LOAD（载入身份与状态）                       │
│     ├── 载入钱包、设备身份、companion state store                 │
│     ├── 检查 OpenClaw 会话 / CPU / provider 健康                 │
│     └── 准备进入 activity scheduler                             │
│                                                                │
│  2. ACTIVITY SCHEDULER（活动调度）                               │
│     ├── 优先检查 active daily activity                           │
│     ├── 再进入 forecast_15m 调度                                 │
│     ├── 定时拉取 arena multiplier / practice 状态                │
│     └── 输出当前 work state                                      │
│                                                                │
│  3. SOLVE / SUBMIT（求解与提交）                                 │
│     ├── 基于统一 pack 生成预测或动作                              │
│     ├── 执行 commit-reveal / result ingestion                    │
│     └── 等待 resolution / settlement                              │
│                                                                │
│  4. STATE SYNC（状态同步）                                       │
│     ├── 更新 current work / mood / latest reward                 │
│     ├── 推送给 Menu Bar / TUI / commands / Control UI            │
│     └── 记录 history / reward timeline                           │
│                                                                │
│  5. OPTIONAL DAILY BRIEF（可选日互动）                            │
│     ├── 用户可以做一次轻 check-in                                │
│     ├── 更新 mood / preference / reminder state                  │
│     └── 不直接发放奖励                                            │
│                                                                │
│  → 回到 Step 1，循环继续                                        │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 钱包管理与控制命令

```bash
# 自动生成（首次运行时）
claw wallet create
# → 输出地址 + 助记词

# 导入已有钱包
claw wallet import --seed "abandon ability able ..."
# → 恢复已有钱包

# 查看地址和余额
claw wallet balance
# → Address: claw1abc...xyz
# → Available: 142.50 CLAW
# → Staked:    100.00 CLAW
# → Pending:     3.20 CLAW (current epoch)

# 转账
claw wallet send --to claw1def...uvw --amount 50
# → ✅ Sent 50 CLAW. TX: 0xabc123...

# 导出私钥（高级）
claw wallet export --format hex
# → ⚠️ WARNING: Never share your private key!
```

**钱包存储**：
- 密钥文件存储在 `~/.openclaw/clawchain/wallet.json`
- AES-256 加密，用户设置的密码保护
- 助记词符合 BIP-39 标准（24 词）

V1 命令面建议统一成两层：

- **实现层命令**
  - `python3 scripts/setup.py`
  - `python3 scripts/mine.py`
  - `python3 scripts/status.py`
  - `claw wallet ...`

- **产品层命令**
  - `/buddy`
  - `/status`
  - `/activities`
  - `/checkin`
  - `/arena`
  - `/pause`
  - `/wake`

说明：

- 如果这些命令要承担“暂停挖矿 / 恢复挖矿 / 触发 check-in”这类确定性控制，优先走 native plugin command 或 `command-dispatch: tool`
- 纯 description-only skill 不应被当成可靠控制面

### 4.4 Companion 状态、余额与历史

```bash
# 查看挖矿统计 / companion 状态
claw stats
# → Today:          forecast + daily + arena summary
# → Current work:   working_forecast
# → Buddy mood:     focused
# → This week:      +29.1 CLAW
# → All time:       +412.8 CLAW
# → Reliability:    1.02
# → Arena mult:     1.01

# 查看详细 activity 历史
claw history --days 7
# → 日期 | Activities | 奖励 | Reliability | Arena
# → 04-11 | F15+D+A   | 5.1  | +0.01       | 1.00
# → 04-10 | F15+D     | 4.2  | +0.00       | 1.01
# → ...

# 质押（渐进式：早期免质押，后期需 10-100 CLAW）
claw stake --amount 10
# → ✅ Staked 10 CLAW. You are now an active miner.

# 解除质押（7天冷却期）
claw unstake --amount 50
# → ⏳ Unstaking 50 CLAW. Available in 7 days.
```

### 4.5 配置项一览

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `auto_mine` | `true` | 是否在空闲时自动挖矿 |
| `max_cpu` | `50` | CPU 使用率上限 (%) |
| `activity_policy` | `balanced` | companion 的调度倾向: balanced / steady / aggressive |
| `idle_threshold` | `60` | 空闲判定等待时间（秒） |
| `network` | `testnet` | 连接的网络 |
| `rpc_endpoint` | 自动发现 | 自定义 RPC 节点地址 |
| `log_level` | `info` | 日志级别: debug / info / warn / error |
| `auto_stake` | `false` | 挖到足够 CLAW 后自动质押 |
| `reward_notify` | `true` | 每次获得奖励时通知 |
| `daily_brief_reminder` | `true` | 是否提醒用户做每日轻互动 |
| `surface_mode` | `auto` | 优先暴露 Menu Bar / TUI / Control UI / mixed 状态面 |

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
- reward-bearing rollout 仍要单独 release review，明确 budget source、operator roles、chain submitter、monitoring 和 rollback；现在已有 `make build-poker-mtt-release-review-bundle` 和 [`docs/POKER_MTT_REWARD_ROLLOUT_RELEASE_REVIEW.md`](/Users/yanchengren/Documents/Projects/clawchain/docs/POKER_MTT_REWARD_ROLLOUT_RELEASE_REVIEW.md) 作为标准入口

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
| **ClawChain (100矿工)** | 100 | **$34.29/天 (FDV $10M)** | 安装 Skill | 无额外成本 |
| **ClawChain (1000矿工)** | 1,000 | **$3.43/天 (FDV $10M)** | 安装 Skill | 无额外成本 |

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
Week 2: 邀请 20 名核心用户，验证 TUI/status/check-in 路径
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
├── Quality point: 完成有效 forecast / daily / arena activity
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
主入口: OpenClaw Skill / plugin + TUI + Control UI Companion Home
默认 activities: forecast_15m, daily_anchor, arena(read-first)
默认日互动: 1 次可选 daily brief
```

**上线清单：**
- [ ] companion activation 路径打通
- [ ] `/buddy`、`/status`、`/activities`、`/checkin` 定义清楚
- [ ] Control UI Companion Home / Activities / History 可用
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
| Control UI / Skill 原型 | ✅ | 已有 dashboard / risk / network / skill runtime 基础 |
| Token 经济模型设计 | ✅ | 21M CLAW，减半曲线 |

### Q2 2026（4-6月）

| 功能 | 优先级 | 预计工时 |
|------|--------|---------|
| companion identity + state model | P0 | 1 周 |
| Skill 命令面调整（`/buddy` 等） | P0 | 1 周 |
| TUI 状态表达与 daily brief 提醒 | P0 | 1 周 |
| Control UI Companion Home | P0 | 2 周 |
| Activities / History / Rankings IA | P0 | 2 周 |
| runtime 状态同步与 API contract | P0 | 1 周 |
| reward timeline / explanation surfaces | P1 | 1 周 |

### Q3 2026（7-9月）

| 功能 | 优先级 | 预计工时 |
|------|--------|---------|
| 公开测试网 companion launch | P0 | 1 周 |
| Arena read surfaces / ranking surfaces | P0 | 2 周 |
| Review / Risk 用户可见子集 | P1 | 1 周 |
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

*本文档为 ClawChain 产品全案 v1.1，将随项目发展持续迭代。*

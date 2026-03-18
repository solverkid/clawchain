# ClawChain 挖矿机制改进设计文档

**版本**: 0.2  
**日期**: 2026-03-18  
**基于**: 8个项目机制研究 + ClawChain 白皮书

---

## 1. 研究总结

### 1.1 项目机制对比

| 项目 | 核心机制 | 吸引矿工 | 留住矿工 | 防作弊 | 冷启动 |
|------|---------|----------|----------|--------|--------|
| **Filecoin** | 存储证明 PoRep/PoSt | 区块奖励按存储算力分配 | 质押锁定+长期合约 | SNARK证明+质押slash | 空扇区(CC sector)可先挖 |
| **Render** | GPU渲染任务分发 | 闲置GPU变现 | 声誉分级(3 tier) | 任务验证+escrow | $1/RNDR 锚定降低波动 |
| **Bittensor** | AI subnet + Yuma共识 | 按ML输出质量发奖 | 256个subnet多赛道 | 验证者评分+相对排名 | subnet创建门槛低 |
| **Ritual** | AI推理oracle | 链上推理费用 | 多链支持扩大需求 | ZK-ML/TEE验证 | Infernet SDK易集成 |
| **io.net** | GPU算力聚合 | 90%成本优势吸引需求侧 | 递减通胀长期发放 | 硬件监控+fault tolerance | 矿场转型GPU供给 |
| **Gensyn** | ML训练验证 | 任何设备可参与 | RepOps确定性验证 | 链上challenge+经济惩罚 | RL Swarm 测试网 |
| **Grass** | 带宽数据采集 | 装浏览器插件即挖 | Points→Token转换 | ZK proof数据溯源 | 大规模空投(300万人) |
| **Koii** | 注意力证明 PoRT | 低门槛节点 | Docker容器化任务多样 | 渐进共识+slash | K2结算层 |

### 1.2 核心发现

**什么让矿工来？**
1. **低门槛** (Grass: 浏览器插件; Koii: Docker任务; Gensyn: 笔记本可参与)
2. **早期高回报** (Bittensor: 新subnet高APY; io.net: 8%初始通胀)
3. **空投/积分预期** (Grass: 300万人空投; Gensyn: RL Swarm积分)

**什么让矿工留？**
1. **声誉升级** (Render: 3 tier声誉; Filecoin: 存储算力越大越有优势)
2. **质押锁定** (Filecoin: 质押+7天解锁; Bittensor: 质押权重影响收益)
3. **任务多样性** (Bittensor: 40+个subnet; Koii: Docker任务框架)

**什么防作弊？**
1. **经济惩罚** (Filecoin: slash质押; Gensyn: 链上challenge经济惩罚)
2. **交叉验证** (Bittensor: Yuma共识多验证者; ClawChain已有: commit-reveal)
3. **确定性验证** (Gensyn: RepOps bit-level一致; 精确匹配类任务)

---

## 2. ClawChain 机制改进方案

### 2.1 早鸟奖励倍率 (Early Bird Multiplier) ⭐

**灵感**: Grass 空投、io.net 递减通胀

```
前 1000 个注册矿工: 3x 奖励倍率
前 5000 个注册矿工: 2x 奖励倍率
前 10000 个注册矿工: 1.5x 奖励倍率
之后: 1x 标准倍率

实现: 链上记录全局矿工注册序号
```

**效果**: 制造 FOMO，加速冷启动

### 2.2 每日签到奖励 (Daily Check-in Bonus) ⭐

**灵感**: Grass 持续在线积分、Koii 注意力证明

```
连续在线 1 天:  +0 bonus
连续在线 7 天:  +10% bonus
连续在线 30 天: +25% bonus
连续在线 90 天: +50% bonus

中断后重新计算
```

**效果**: 提高在线率和网络稳定性

### 2.3 任务难度分级 (Task Difficulty Tiers) ⭐

**灵感**: Render 3-tier 系统、Bittensor subnet 多样性

```
Tier 1 (基础): 数学计算、逻辑推理 → 奖励 1x
Tier 2 (中级): 情感分析、文本分类 → 奖励 2x
Tier 3 (高级): 文本摘要、翻译、创意写作 → 奖励 3x

矿工声誉 > 800: 可接 Tier 3
矿工声誉 > 600: 可接 Tier 2
所有矿工: 可接 Tier 1
```

**效果**: 激励矿工提升能力，高声誉矿工获得更多收益

### 2.4 防作弊增强

**新增: Spot Check 机制** (灵感: Bittensor Yuma共识)
- 10% 的挑战为 spot check (已知答案)
- 矿工不知道哪个是 spot check
- Spot check 答错: 声誉 -50

**新增: 新矿工冷启动期**
- 前 100 epoch: 奖励 50%
- 防止批量注册刷号

---

## 3. Token 经济改进 (以白皮书为准)

### 3.1 统一参数

| 参数 | 白皮书值 (权威) | 旧官网值 (错误) |
|------|----------------|-----------------|
| 总量 | 21,000,000 CLAW | ~~10亿~~ |
| Epoch 奖励 | 50 CLAW | ~~100 CLAW~~ |
| 减半周期 | 210,000 epoch (~4年) | ~~6个月~~ |
| 精度 | 6位小数 (uclaw) | 同 |

### 3.2 改进后的奖励分配

```
每 epoch 50 CLAW:
├── 矿工奖励:     30 CLAW (60%) → 按完成数+声誉加权
├── 验证者奖励:    10 CLAW (20%) → 按质押权重
└── 生态基金:       10 CLAW (20%) → 自动进入基金

矿工奖励加权公式:
  miner_share = (challenges_completed * reputation_weight * early_bird_multiplier * streak_bonus)
  actual_reward = miner_pool * miner_share / total_shares
```

---

## 4. 冷启动策略

### Phase 0: 测试网积分 (Pre-mainnet)
- 参与测试网挖矿累积积分
- 主网上线后积分 1:1 兑换 CLAW
- 参考: Gensyn RL Swarm, Grass 积分体系

### Phase 1: 早鸟红利 (Mainnet 0-6个月)
- 3x 奖励倍率 for 前1000矿工
- 创始团队跑 5+ 节点 bootstrapping
- 每日签到奖励开始计算

### Phase 2: 生态扩展 (6-12个月)
- 推荐奖励: 邀请新矿工获得其挖矿收益 5% (持续3个月)
- 开放 Task Marketplace (用户可发布付费任务)
- IBC 跨链桥接

---

## 5. 实现优先级

| 优先级 | 功能 | 复杂度 | 本次实现 |
|--------|------|--------|---------|
| P0 | 早鸟奖励倍率 | 低 | ✅ |
| P0 | 每日签到奖励 | 中 | ✅ |
| P0 | 任务难度分级 | 低 | ✅ |
| P1 | Spot Check | 中 | ✅ |
| P1 | 新矿工冷启动期 | 低 | ✅ |
| P2 | 推荐奖励 | 中 | 🔜 Phase 2 |
| P2 | Task Marketplace | 高 | 🔜 Phase 2 |

"""
ClawChain Mining Service — 挑战生成引擎
从 Go keeper.go 忠实翻译，支持所有挑战类型。
"""

import hashlib
import json
import random
import secrets
from datetime import datetime

# ─── 挑战类型 & 难度 ───

CHALLENGE_TYPES = [
    "text_summary", "sentiment", "translation", "classification",
    "entity_extraction", "format_convert", "math", "logic",
    "text_transform", "json_extract", "hash",
]

# Alpha task pool: deterministic-first mining.
# Only tasks with a single verifiable correct answer (or closed-set options)
# participate in reward-critical mining during Alpha.
# Free-form generative tasks (translation, text_summary) are excluded from
# Alpha mining to prevent Sybil attacks via non-deterministic majority voting.
ALPHA_TASK_POOL = [
    "math", "logic", "hash", "text_transform", "json_extract", "format_convert",
    "sentiment", "classification",
]

# Sentiment labels — closed set, exact match only
SENTIMENT_LABELS = ["positive", "negative", "neutral"]

# Classification labels — closed set, exact match only
CLASSIFICATION_LABELS = ["科技", "金融", "体育", "娱乐", "政治"]

TIER_MAP = {
    "math": 1, "logic": 1, "hash": 1, "text_transform": 1,
    "sentiment": 2, "classification": 2, "format_convert": 2, "json_extract": 2,
    "text_summary": 3, "translation": 3, "entity_extraction": 3,
}

# 生成时的加权（Alpha: deterministic-first）
TYPE_WEIGHTS = [
    ("math", 5),
    ("logic", 5),
    ("hash", 4),
    ("text_transform", 4),
    ("json_extract", 3),
    ("format_convert", 3),
    ("sentiment", 3),
    ("classification", 3),
]

# Spot check rate: 20% in Alpha (raised from 10% for stronger fraud detection)
ALPHA_SPOT_CHECK_RATE = 5  # 1-in-5 = 20%

# ─── 内容池（从 Go keeper.go 完整翻译）───

TEXT_SUMMARY_POOL = [
    "人工智能（Artificial Intelligence，简称AI）是计算机科学的一个分支，它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。该领域的研究包括机器人、语言识别、图像识别、自然语言处理和专家系统等。AI的核心问题包括建造能够跟人类似甚至超卓的推理、知识、规划、学习、交流、感知、移物、使用工具和操控机械的能力等。当前AI技术已在医疗诊断、金融分析、自动驾驶、智能客服等领域得到广泛应用。",
    "区块链是一种分布式数据存储、点对点传输、共识机制、加密算法等计算机技术的新型应用模式。本质上是一个去中心化的数据库，同时作为比特币的底层技术，是一串使用密码学方法相关联产生的数据块。每个数据块中包含了一批次比特币网络交易的信息，用于验证其信息的有效性和生成下一个区块。区块链技术的特点包括去中心化、开放性、自治性、信息不可篡改、匿名性等。目前在金融、供应链管理、数字版权、物联网等领域都有应用探索。",
    "量子计算是一种遵循量子力学规律调控量子信息单元进行计算的新型计算模式。传统计算机使用比特（0或1）作为信息的基本单位，而量子计算机使用量子比特（可以同时处于0和1的叠加态）。这使得量子计算机在处理某些特定问题时，理论上可以达到指数级的加速。量子计算在密码破解、药物研发、材料科学、优化问题等领域展现出巨大潜力。目前IBM、Google、中国科学技术大学等机构都在积极研发量子计算机，但距离大规模实用化还有很长的路要走。",
    "Web3是下一代互联网的愿景，它基于区块链技术，旨在创建一个去中心化的网络。与Web2（当前互联网）不同，Web3中用户拥有自己的数据和数字资产，不再依赖于中心化的平台。Web3的核心特征包括：去中心化身份（DID）、加密货币钱包、智能合约、去中心化应用（DApp）等。Web3有望改变社交媒体、游戏、金融、内容创作等多个领域，让用户真正成为互联网的主人而不是产品。然而，Web3也面临技术复杂度高、用户体验不佳、监管不明确等挑战。",
    "机器学习是人工智能的一个分支，它使计算机能够在没有明确编程的情况下学习。机器学习算法通过分析大量数据来识别模式，并据此做出预测或决策。主要分为监督学习、无监督学习和强化学习三大类。深度学习是机器学习的一个子集，它使用多层神经网络来处理复杂的数据模式。机器学习已经在图像识别、语音识别、推荐系统、自然语言处理等领域取得了突破性进展。随着算力提升和数据积累，机器学习的应用场景还在不断扩大，但也面临数据隐私、算法偏见等伦理挑战。",
]

SENTIMENT_POOL = [
    ("比特币突破历史新高，加密市场迎来牛市", "positive"),
    ("全球股市暴跌，投资者恐慌性抛售", "negative"),
    ("今天天气晴朗，适合出门散步", "positive"),
    ("项目进度延期，团队压力很大", "negative"),
    ("会议按计划进行，各方达成共识", "neutral"),
    ("产品获得用户高度评价，销量大增", "positive"),
    ("系统出现严重漏洞，数据泄露风险高", "negative"),
    ("公司宣布裁员计划，员工士气低落", "negative"),
    ("新技术发布，行业格局可能改变", "neutral"),
    ("研究取得重大突破，论文发表在顶级期刊", "positive"),
]

TRANSLATION_POOL = [
    ("The quick brown fox jumps over the lazy dog", "敏捷的棕色狐狸跳过懒狗"),
    ("Artificial intelligence is transforming the world", "人工智能正在改变世界"),
    ("Blockchain technology enables decentralized applications", "区块链技术使去中心化应用成为可能"),
    ("Machine learning algorithms can predict future trends", "机器学习算法可以预测未来趋势"),
    ("Cryptocurrency adoption is growing rapidly worldwide", "加密货币在全球范围内的采用正在快速增长"),
    ("Quantum computing promises exponential speedup", "量子计算承诺指数级加速"),
    ("Smart contracts automate agreement execution", "智能合约自动化协议执行"),
    ("Data privacy is a fundamental human right", "数据隐私是一项基本人权"),
    ("Cloud computing provides scalable infrastructure", "云计算提供可扩展的基础设施"),
    ("Open source software drives innovation", "开源软件推动创新"),
]

CLASSIFICATION_POOL = [
    ("OpenAI发布GPT-5模型，性能大幅提升", "科技"),
    ("美联储宣布加息25个基点，市场反应平淡", "金融"),
    ("世界杯决赛阿根廷夺冠，梅西圆梦", "体育"),
    ("新电影票房破10亿，刷新历史纪录", "娱乐"),
    ("联合国安理会通过新决议，呼吁停火", "政治"),
    ("SpaceX成功发射星际飞船，马斯克庆祝", "科技"),
    ("比特币价格突破10万美元，创历史新高", "金融"),
    ("NBA总决赛进入抢七，悬念丛生", "体育"),
    ("奥斯卡颁奖典礼落幕，最佳影片揭晓", "娱乐"),
    ("欧盟峰会讨论气候变化政策", "政治"),
    ("量子计算机实现新突破，算力提升百倍", "科技"),
    ("全球股市集体大涨，道指创新高", "金融"),
    ("奥运会中国代表团夺得金牌榜第一", "体育"),
    ("顶级歌手演唱会门票秒光", "娱乐"),
    ("G20峰会在京召开，讨论全球经济", "政治"),
]


# Challenge types that have a single deterministic correct answer
# In Alpha, sentiment and classification are closed-set with pre-committed answers,
# making them deterministic for verification purposes.
DETERMINISTIC_TYPES = {"math", "logic", "hash", "text_transform", "json_extract", "format_convert", "sentiment", "classification"}

# Challenge types that require subjective judgment (non-deterministic)
# These are NOT part of Alpha reward-critical mining.
NON_DETERMINISTIC_TYPES = {"translation", "text_summary", "entity_extraction"}


def compute_commitment(challenge_id: str, expected_answer: str, salt: str) -> str:
    """Compute SHA256 commitment: H(challenge_id || expected_answer || salt)"""
    payload = f"{challenge_id}{expected_answer}{salt}"
    return hashlib.sha256(payload.encode()).hexdigest()


def calc_num_challenges(active_miners: int) -> int:
    """max(1, min(active_miners/3, 10))"""
    if active_miners <= 0:
        return 1
    n = active_miners // 3
    return max(1, min(n, 10))


def _weighted_choice(rng, weights, exclude=None):
    """从加权列表中随机选一个（尽量排除 exclude 集合）"""
    exclude = exclude or set()
    candidates = [(t, w) for t, w in weights if t not in exclude]
    if not candidates:
        candidates = weights  # 全部用完就允许重复
    total = sum(w for _, w in candidates)
    roll = rng.randint(0, total - 1)
    cumulative = 0
    for t, w in candidates:
        cumulative += w
        if roll < cumulative:
            return t
    return candidates[-1][0]


def _generate_prompt(ctype: str, rng: random.Random):
    """根据类型生成 prompt + expected_answer"""
    if ctype == "text_summary":
        text = rng.choice(TEXT_SUMMARY_POOL)
        return f"将以下文章摘要为不超过50字：\n\n{text}", ""

    elif ctype == "sentiment":
        text, expected = rng.choice(SENTIMENT_POOL)
        return f"Classify the sentiment of the following text as exactly one of: positive, negative, neutral\n\nText: {text}", expected

    elif ctype == "translation":
        en, zh = rng.choice(TRANSLATION_POOL)
        return f"将以下英文翻译为中文：{en}", zh

    elif ctype == "classification":
        text, expected = rng.choice(CLASSIFICATION_POOL)
        return f"Classify the following text into exactly one category from: 科技, 金融, 体育, 娱乐, 政治\n\nText: {text}", expected

    elif ctype == "math":
        a = rng.randint(100, 999)
        b = rng.randint(100, 999)
        op = rng.choice(["+", "-", "*"])
        if op == "+":
            result = a + b
        elif op == "-":
            result = a - b
        else:
            result = a * b
        return f"计算 {a} {op} {b} 的结果", str(result)

    elif ctype == "logic":
        return "如果 A > B 且 B > C，那么 A 和 C 的关系是？(回答格式: A>C)", "A>C"

    elif ctype == "hash":
        words = ["hello", "world", "clawchain", "mining", "blockchain", "ai", "test", "crypto"]
        word = rng.choice(words)
        expected = hashlib.sha256(word.encode()).hexdigest()
        return f'计算字符串 "{word}" 的 SHA256 哈希值', expected

    elif ctype == "text_transform":
        phrases = ["hello world", "clawchain mining", "artificial intelligence", "blockchain technology"]
        phrase = rng.choice(phrases)
        ops = [("uppercase", "大写", phrase.upper()), ("reverse", "反转", phrase[::-1])]
        op_name_zh, op_label, expected = rng.choice(ops)
        return f'将文本 "{phrase}" 转换为{op_label}', expected

    elif ctype == "json_extract":
        samples = [
            ('{"name":"Alice","age":30,"city":"Beijing"}', "name", "Alice"),
            ('{"token":"CLAW","price":0.5,"supply":1000000}', "token", "CLAW"),
            ('{"miner":"claw1abc","rewards":500}', "rewards", "500"),
        ]
        json_str, field, expected = rng.choice(samples)
        return f"从以下 JSON 中提取 {field} 字段的值：{json_str}", expected

    elif ctype == "format_convert":
        return '将 JSON 转为 CSV: {"name":"Alice","age":30}', "name,age\nAlice,30"

    elif ctype == "entity_extraction":
        return (
            "提取人名和组织：Elon Musk announced that Tesla will invest $10 billion in AI research.",
            "",
        )

    else:
        a = rng.randint(1, 100)
        b = rng.randint(1, 100)
        return f"计算 {a} + {b} 的结果", str(a + b)


def generate_challenges(epoch: int, active_miners: int, seed: int = None):
    """
    生成一个 epoch 的全部挑战。
    返回 list[dict]，每个 dict 对应一个 Challenge。
    """
    num = calc_num_challenges(active_miners)

    if seed is None:
        seed = epoch
    rng = random.Random(seed)

    used_types = set()
    challenges = []

    # Filter TYPE_WEIGHTS to Alpha task pool only
    alpha_weights = [(t, w) for t, w in TYPE_WEIGHTS if t in ALPHA_TASK_POOL]

    for idx in range(num):
        ctype = _weighted_choice(rng, alpha_weights, exclude=used_types)
        used_types.add(ctype)

        prompt, expected = _generate_prompt(ctype, rng)
        tier = TIER_MAP.get(ctype, 1)

        # 20% spot check (Alpha hardening)
        is_spot_check = rng.randint(0, ALPHA_SPOT_CHECK_RATE - 1) == 0
        known_answer = ""
        if is_spot_check and expected:
            known_answer = expected
        elif is_spot_check and not expected:
            is_spot_check = False

        ch_id = f"ch-{epoch}-{idx}"
        salt = secrets.token_hex(16)
        commitment = compute_commitment(ch_id, expected, salt) if expected else ""

        ch = {
            "id": ch_id,
            "epoch": epoch,
            "type": ctype,
            "tier": tier,
            "prompt": prompt,
            "expected_answer": expected,
            "status": "pending",
            "is_spot_check": is_spot_check,
            "known_answer": known_answer,
            "salt": salt,
            "commitment": commitment,
            "created_at": datetime.utcnow().isoformat(),
        }
        challenges.append(ch)

    return challenges

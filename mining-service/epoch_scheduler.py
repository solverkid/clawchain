"""
ClawChain Mining Service — Epoch 调度器
每 10 分钟 = 1 epoch。
在 server.py 中作为后台线程运行。
"""

import threading
import time
import logging
from datetime import datetime, date, timedelta

from models import get_db, get_global, set_global, DB_PATH, migrate_db
from challenge_engine import generate_challenges
from rewards import (
    get_epoch_miner_pool,
    get_epoch_validator_pool,
    get_epoch_eco_fund,
    calculate_miner_reward,
)

logger = logging.getLogger("epoch_scheduler")

EPOCH_INTERVAL = 600  # 10 minutes


def get_current_epoch(db):
    """获取当前 epoch（从全局状态读取）"""
    val = get_global(db, "current_epoch", "0")
    return int(val)


def count_active_miners(db) -> int:
    row = db.execute(
        "SELECT COUNT(*) AS cnt FROM miners WHERE status='active'"
    ).fetchone()
    return row["cnt"] if row else 0


def settle_epoch(db, epoch: int):
    """
    结算指定 epoch 的所有挑战。
    1. 查找 epoch 的 pending/commit 挑战
    2. 对每个挑战：检查 submissions → 多数一致 → 计算奖励 → 更新矿工
    3. 未答的标 expired
    """
    challenges = db.execute(
        "SELECT * FROM challenges WHERE epoch=? AND status IN ('pending','commit')",
        (epoch,),
    ).fetchall()

    if not challenges:
        return

    # 本 epoch 挑战总数（用于奖励分摊）
    total_challenges = db.execute(
        "SELECT COUNT(*) AS cnt FROM challenges WHERE epoch=?", (epoch,)
    ).fetchone()["cnt"]
    if total_challenges < 1:
        total_challenges = 1

    for ch in challenges:
        ch_id = ch["id"]

        # 获取该挑战的所有提交
        subs = db.execute(
            "SELECT * FROM submissions WHERE challenge_id=? AND answer IS NOT NULL",
            (ch_id,),
        ).fetchall()

        if not subs:
            # 无人提交 → expired
            db.execute(
                "UPDATE challenges SET status='expired' WHERE id=?", (ch_id,)
            )
            continue

        # DEV 模式: 1 人即可结算；生产模式需 3 人
        required = 1  # 独立服务默认 DEV 模式

        if len(subs) < required:
            # 未达到结算条件，保持 pending
            continue

        # 构建答案分组
        answer_votes = {}  # normalized_answer -> [miner_addr]
        for s in subs:
            norm = s["answer"].strip().lower()
            answer_votes.setdefault(norm, []).append(s["miner_address"])

        is_spot = bool(ch["is_spot_check"])
        known = (ch["known_answer"] or "").strip().lower()

        # Spot check: 正确答案以 known_answer 为准
        if is_spot and known:
            majority_answer = known
            majority_miners = answer_votes.get(known, [])
        else:
            majority_answer = max(answer_votes, key=lambda k: len(answer_votes[k]))
            majority_miners = answer_votes[majority_answer]

        # 获取矿工信息用于奖励计算
        miner_pool = get_epoch_miner_pool(epoch)
        per_challenge_pool = max(miner_pool // total_challenges, 1)
        reward_per_miner = max(per_challenge_pool // len(majority_miners), 1) if majority_miners else 0

        is_spot = bool(ch["is_spot_check"])

        for addr in majority_miners:
            miner = db.execute(
                "SELECT * FROM miners WHERE address=?", (addr,)
            ).fetchone()
            if not miner:
                continue

            actual_reward = calculate_miner_reward(
                reward_per_miner,
                miner["registration_index"] or 0,
                miner["consecutive_days"] or 0,
                miner["challenges_completed"] or 0,
            )

            rep_delta = 10 if is_spot else 5

            # 更新 submission
            db.execute(
                "UPDATE submissions SET is_correct=1, reward_amount=? WHERE challenge_id=? AND miner_address=?",
                (actual_reward, ch_id, addr),
            )

            # 更新矿工统计 + 声誉
            db.execute(
                """UPDATE miners SET
                    challenges_completed = challenges_completed + 1,
                    total_rewards = total_rewards + ?,
                    last_active_day = ?,
                    reputation = MIN(reputation + ?, 1000),
                    consecutive_failures = 0
                WHERE address=?""",
                (actual_reward, date.today().isoformat(), rep_delta, addr),
            )

        # 惩罚不一致的矿工
        for norm_answer, addrs in answer_votes.items():
            if norm_answer != majority_answer:
                for addr in addrs:
                    db.execute(
                        "UPDATE submissions SET is_correct=0 WHERE challenge_id=? AND miner_address=?",
                        (ch_id, addr),
                    )

                    rep_penalty = 50 if is_spot else 20
                    miner = db.execute("SELECT * FROM miners WHERE address=?", (addr,)).fetchone()
                    if not miner:
                        continue

                    new_failures = (miner["consecutive_failures"] or 0) + 1
                    new_rep = (miner["reputation"] or 500) - rep_penalty
                    staked = miner["staked_amount"] if "staked_amount" in miner.keys() else 0
                    staked = staked or 0
                    slash_amount = 0

                    # Slashing: 3+ consecutive failures on spot checks → 10% stake
                    if is_spot and new_failures >= 3 and staked > 0:
                        slash_amount = staked // 10

                    if new_failures > 5:
                        new_rep = (miner["reputation"] or 500) - 500
                        if staked > 0:
                            slash_amount = staked // 2  # 50% slash

                    new_status = miner["status"]
                    suspended_at = None
                    if new_rep < 100 or new_failures > 5:
                        new_status = "suspended"
                        suspended_at = datetime.utcnow().isoformat()

                    db.execute(
                        """UPDATE miners SET
                            challenges_failed = challenges_failed + 1,
                            consecutive_failures = ?,
                            reputation = ?,
                            status = ?,
                            suspended_at = COALESCE(?, suspended_at),
                            staked_amount = MAX(COALESCE(staked_amount, 0) - ?, 0)
                        WHERE address=?""",
                        (new_failures, max(new_rep, 0), new_status, suspended_at, slash_amount, addr),
                    )

        # 标记挑战完成
        db.execute(
            "UPDATE challenges SET status='complete' WHERE id=?", (ch_id,)
        )

    db.commit()


def update_consecutive_days(db):
    """更新矿工连续在线天数"""
    today = date.today().isoformat()
    yesterday = date.fromordinal(date.today().toordinal() - 1).isoformat()

    # 今天活跃的矿工：last_active_day == today → 保持
    # 昨天活跃今天没活跃 → 不动（等今天活跃了再更新）
    # 断签超过1天 → 重置
    miners = db.execute("SELECT address, last_active_day, consecutive_days FROM miners WHERE status='active'").fetchall()
    for m in miners:
        last = m["last_active_day"]
        if last == today:
            continue  # 今天已更新
        elif last == yesterday:
            # 连续，等今天活跃时 +1
            pass
        elif last and last < yesterday:
            # 断签，重置
            db.execute(
                "UPDATE miners SET consecutive_days=0 WHERE address=?",
                (m["address"],),
            )
    db.commit()


def run_epoch_tick(db):
    """执行一次 epoch tick"""
    current_epoch = get_current_epoch(db)
    active_miners = count_active_miners(db)

    logger.info(f"Epoch tick: epoch={current_epoch}, active_miners={active_miners}")

    # 1. 结算上一个 epoch
    if current_epoch > 0:
        settle_epoch(db, current_epoch - 1)

    # 2. 过期更早的未结算挑战
    if current_epoch > 1:
        db.execute(
            "UPDATE challenges SET status='expired' WHERE epoch<? AND status IN ('pending','commit')",
            (current_epoch - 1,),
        )
        db.commit()

    # 3. 生成新 epoch 的挑战
    new_challenges = generate_challenges(current_epoch, active_miners)
    for ch in new_challenges:
        db.execute(
            """INSERT OR IGNORE INTO challenges (id, epoch, type, tier, prompt, expected_answer, status, is_spot_check, known_answer, salt, commitment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ch["id"], ch["epoch"], ch["type"], ch["tier"],
                ch["prompt"], ch["expected_answer"], ch["status"],
                1 if ch["is_spot_check"] else 0,
                ch["known_answer"], ch["salt"], ch["commitment"], ch["created_at"],
            ),
        )
    db.commit()

    # 4. 记录 epoch 奖励分配
    miner_pool = get_epoch_miner_pool(current_epoch)
    validator_pool = get_epoch_validator_pool(current_epoch)
    eco_fund = get_epoch_eco_fund(current_epoch)
    db.execute(
        "INSERT OR IGNORE INTO epoch_rewards (epoch, miner_pool, validator_pool, eco_fund) VALUES (?, ?, ?, ?)",
        (current_epoch, miner_pool, validator_pool, eco_fund),
    )
    db.commit()

    # 5. 更新连续在线天数
    update_consecutive_days(db)

    # 6. 递增 epoch
    set_global(db, "current_epoch", current_epoch + 1)

    logger.info(
        f"Epoch {current_epoch} done: generated {len(new_challenges)} challenges, "
        f"miner_pool={miner_pool}, validator_pool={validator_pool}, eco_fund={eco_fund}"
    )

    return current_epoch


def epoch_loop(db_path=None):
    """后台 epoch 调度循环"""
    db = get_db(db_path)
    migrate_db(db)
    logger.info("Epoch scheduler started")

    # 启动时立即执行一次
    run_epoch_tick(db)

    while True:
        time.sleep(EPOCH_INTERVAL)
        try:
            run_epoch_tick(db)
        except Exception as e:
            logger.error(f"Epoch tick error: {e}", exc_info=True)


def start_scheduler(db_path=None):
    """启动后台调度线程"""
    t = threading.Thread(target=epoch_loop, args=(db_path,), daemon=True)
    t.start()
    return t

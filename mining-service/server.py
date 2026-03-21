#!/usr/bin/env python3
"""
ClawChain Independent Mining Service
独立挖矿 HTTP 服务，SQLite 存储，与链进程解耦。
端口 1317（兼容 Skill 现有配置）。
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# 确保能 import 同目录模块
sys.path.insert(0, str(Path(__file__).parent))

from models import init_db, get_db, get_global, set_global, DB_PATH, migrate_db
from challenge_engine import (
    generate_challenges, calc_num_challenges, compute_commitment,
    DETERMINISTIC_TYPES, NON_DETERMINISTIC_TYPES, ALPHA_TASK_POOL,
)
from epoch_scheduler import compute_settlement_root
from rewards import (
    get_epoch_miner_pool,
    get_epoch_validator_pool,
    get_epoch_eco_fund,
    calculate_miner_reward,
    INITIAL_MINER_POOL,
)
from epoch_scheduler import start_scheduler, get_current_epoch, run_epoch_tick

# ─── 配置 ───

SERVER_VERSION = "0.2.0"
MIN_MINER_VERSION = "0.1.0"
DEFAULT_PORT = 1317
MAX_MINERS_PER_IP = 3
DEV_MODE = os.getenv("CLAWCHAIN_DEV", "1") == "1"
REQUIRED_SUBMISSIONS = 1 if DEV_MODE else 3
MIN_MAJORITY = 1 if DEV_MODE else 2
FAUCET_AMOUNT = 200_000_000  # 200 CLAW in uclaw

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("mining-service")

# 全局 DB 连接（per-thread 需要时可改为 thread-local）
_db = None


def get_shared_db():
    global _db
    if _db is None:
        _db = init_db()
    return _db


# ─── 请求处理器 ───

class MiningHandler(BaseHTTPRequestHandler):
    """HTTP handler for all mining API endpoints."""

    # 路由表
    GET_ROUTES = {
        "/clawchain/challenges/pending": "handle_get_pending",
        "/clawchain/stats": "handle_get_stats",
        "/clawchain/version": "handle_get_version",
        "/clawchain/anchors": "handle_get_anchors",
    }
    POST_ROUTES = {
        "/clawchain/challenge/submit": "handle_submit_answer",
        "/clawchain/challenge/commit": "handle_submit_commit",
        "/clawchain/challenge/reveal": "handle_submit_reveal",
        "/clawchain/miner/register": "handle_register_miner",
        "/clawchain/faucet": "handle_faucet",
    }

    def log_message(self, format, *args):
        """覆盖默认日志，用 logging 模块"""
        logger.info(f"{self.client_address[0]} - {format % args}")

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _error(self, msg, status=400):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(msg.encode("utf-8"))

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # 静态路由
        if path in self.GET_ROUTES:
            getattr(self, self.GET_ROUTES[path])()
            return

        # 动态路由: /clawchain/epoch/{N}/settlement
        m = re.match(r"^/clawchain/epoch/(\d+)/settlement$", path)
        if m:
            self.handle_get_epoch_settlement(int(m.group(1)))
            return

        # 动态路由: /clawchain/miner/{address}
        m = re.match(r"^/clawchain/miner/([^/]+)/stats$", path)
        if m:
            self.handle_get_miner_stats(m.group(1))
            return

        m = re.match(r"^/clawchain/miner/([^/]+)$", path)
        if m:
            self.handle_get_miner_info(m.group(1))
            return

        self._error("not found", 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in self.POST_ROUTES:
            try:
                body = self._read_body()
                getattr(self, self.POST_ROUTES[path])(body)
            except json.JSONDecodeError:
                self._error("invalid JSON", 400)
            except Exception as e:
                logger.error(f"POST {path} error: {e}", exc_info=True)
                self._error(f"internal error: {e}", 500)
            return

        self._error("not found", 404)

    # ═══════════════════════════════════════
    # GET /clawchain/challenges/pending
    # ═══════════════════════════════════════
    def handle_get_pending(self):
        db = get_shared_db()
        rows = db.execute(
            "SELECT * FROM challenges WHERE status IN ('pending', 'commit') ORDER BY epoch DESC, id"
        ).fetchall()

        challenges = []
        for r in rows:
            # 获取该挑战的提交（用于构建 reveals/commits 字段）
            subs = db.execute(
                "SELECT miner_address, commit_hash, answer FROM submissions WHERE challenge_id=?",
                (r["id"],),
            ).fetchall()

            commits = {}
            reveals = {}
            for s in subs:
                if s["commit_hash"]:
                    commits[s["miner_address"]] = s["commit_hash"]
                if s["answer"]:
                    reveals[s["miner_address"]] = s["answer"]

            # Determine verification mode for this challenge type
            ctype = r["type"]
            if ctype in DETERMINISTIC_TYPES:
                verification_mode = "deterministic"
            else:
                verification_mode = "server_trust"  # will become "majority_vote" with multi-validator

            challenges.append({
                "id": r["id"],
                "epoch": r["epoch"],
                "type": ctype,
                "tier": r["tier"],
                "prompt": r["prompt"],
                # SECURITY: expected_answer and known_answer are NEVER sent to miners
                "assignees": [],  # 公开挑战
                "status": r["status"],
                "created_height": 0,
                "commits": commits,
                "reveals": reveals,
                "is_spot_check": bool(r["is_spot_check"]),
                "commitment": r["commitment"] or "",
                "verification_mode": verification_mode,
            })

        self._json_response({"challenges": challenges})

    # ═══════════════════════════════════════
    # POST /clawchain/challenge/submit
    # ═══════════════════════════════════════
    def handle_submit_answer(self, body):
        ch_id = body.get("challenge_id", "")
        miner_addr = body.get("miner_address", "")
        answer = body.get("answer", "")

        if not ch_id or not miner_addr or not answer:
            self._error("challenge_id, miner_address, and answer are required", 400)
            return

        db = get_shared_db()

        # 检查矿工
        miner = db.execute("SELECT * FROM miners WHERE address=?", (miner_addr,)).fetchone()
        if not miner:
            self._error("miner not registered", 403)
            return
        if miner["status"] != "active":
            self._error("miner not active", 403)
            return

        # 检查挑战
        ch = db.execute("SELECT * FROM challenges WHERE id=?", (ch_id,)).fetchone()
        if not ch:
            self._error("challenge not found", 404)
            return

        # 防重复
        existing = db.execute(
            "SELECT id FROM submissions WHERE challenge_id=? AND miner_address=? AND answer IS NOT NULL",
            (ch_id, miner_addr),
        ).fetchone()
        if existing:
            self._error("already submitted", 409)
            return

        # 插入提交
        db.execute(
            "INSERT INTO submissions (challenge_id, miner_address, answer) VALUES (?, ?, ?)",
            (ch_id, miner_addr, answer),
        )
        db.commit()

        # 更新矿工活跃天
        db.execute(
            "UPDATE miners SET last_active_day=? WHERE address=?",
            (date.today().isoformat(), miner_addr),
        )
        db.commit()

        # 统计提交数
        sub_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM submissions WHERE challenge_id=? AND answer IS NOT NULL",
            (ch_id,),
        ).fetchone()["cnt"]

        # 尝试即时结算
        status = ch["status"]
        settle_result = None
        if sub_count >= REQUIRED_SUBMISSIONS:
            settle_result = self._try_settle_challenge(db, ch_id)
            status = settle_result["status"] if isinstance(settle_result, dict) else settle_result

        response = {
            "success": True,
            "submission_count": sub_count,
            "required_submissions": REQUIRED_SUBMISSIONS,
            "status": status,
            "message": "answer recorded, waiting for other miners to submit",
        }

        # After settlement, reveal answer + salt for miner verification
        if isinstance(settle_result, dict) and settle_result.get("settled"):
            ch_fresh = db.execute("SELECT * FROM challenges WHERE id=?", (ch_id,)).fetchone()
            ctype = ch_fresh["type"]
            response["verification"] = {
                "verification_mode": "deterministic" if ctype in DETERMINISTIC_TYPES else "server_trust",
                "commitment": ch_fresh["commitment"] or "",
                "revealed_answer": ch_fresh["expected_answer"] or "",
                "salt": ch_fresh["salt"] or "",
            }

        self._json_response(response)

    # ═══════════════════════════════════════
    # POST /clawchain/challenge/commit
    # ═══════════════════════════════════════
    def handle_submit_commit(self, body):
        ch_id = body.get("challenge_id", "")
        miner_addr = body.get("miner_address", "")
        commit_hash = body.get("commit_hash", "")

        if not ch_id or not miner_addr or not commit_hash:
            self._error("challenge_id, miner_address, and commit_hash are required", 400)
            return

        db = get_shared_db()

        # 检查矿工
        miner = db.execute("SELECT * FROM miners WHERE address=?", (miner_addr,)).fetchone()
        if not miner:
            self._error("miner not registered", 403)
            return
        if miner["status"] != "active":
            self._error("miner not active", 403)
            return

        # 检查挑战
        ch = db.execute("SELECT * FROM challenges WHERE id=?", (ch_id,)).fetchone()
        if not ch:
            self._error("challenge not found", 404)
            return
        if ch["status"] not in ("pending", "commit"):
            self._error(f"challenge not accepting commits (status: {ch['status']})", 409)
            return

        # 防重复
        existing = db.execute(
            "SELECT id FROM submissions WHERE challenge_id=? AND miner_address=? AND commit_hash IS NOT NULL",
            (ch_id, miner_addr),
        ).fetchone()
        if existing:
            self._error("already committed", 409)
            return

        # 插入 commit
        db.execute(
            "INSERT INTO submissions (challenge_id, miner_address, commit_hash) VALUES (?, ?, ?)",
            (ch_id, miner_addr, commit_hash),
        )
        # 更新挑战状态
        db.execute("UPDATE challenges SET status='commit' WHERE id=?", (ch_id,))
        db.commit()

        self._json_response({
            "success": True,
            "message": "commit recorded, please reveal your answer later",
            "status": "commit",
        })

    # ═══════════════════════════════════════
    # POST /clawchain/challenge/reveal
    # ═══════════════════════════════════════
    def handle_submit_reveal(self, body):
        ch_id = body.get("challenge_id", "")
        miner_addr = body.get("miner_address", "")
        answer = body.get("answer", "")
        nonce = body.get("nonce", "")

        if not ch_id or not miner_addr or not answer or not nonce:
            self._error("challenge_id, miner_address, answer, and nonce are required", 400)
            return

        db = get_shared_db()

        # 检查矿工
        if not db.execute("SELECT 1 FROM miners WHERE address=?", (miner_addr,)).fetchone():
            self._error("miner not registered", 403)
            return

        # 检查挑战
        ch = db.execute("SELECT * FROM challenges WHERE id=?", (ch_id,)).fetchone()
        if not ch:
            self._error("challenge not found", 404)
            return

        # 找到对应的 commit
        sub = db.execute(
            "SELECT * FROM submissions WHERE challenge_id=? AND miner_address=? AND commit_hash IS NOT NULL",
            (ch_id, miner_addr),
        ).fetchone()
        if not sub:
            self._error("no commit found for this miner, please commit first", 400)
            return

        # 验证 hash
        expected_hash = hashlib.sha256((answer + nonce).encode()).hexdigest()
        if expected_hash != sub["commit_hash"]:
            self._error("reveal does not match commit hash", 403)
            return

        # 防重复 reveal
        if sub["answer"] is not None:
            self._error("already revealed", 409)
            return

        # 更新 answer
        db.execute(
            "UPDATE submissions SET answer=?, nonce=? WHERE id=?",
            (answer, nonce, sub["id"]),
        )
        db.commit()

        # 更新矿工活跃天
        db.execute(
            "UPDATE miners SET last_active_day=? WHERE address=?",
            (date.today().isoformat(), miner_addr),
        )
        db.commit()

        # 统计 reveal 数
        sub_count = db.execute(
            "SELECT COUNT(*) AS cnt FROM submissions WHERE challenge_id=? AND answer IS NOT NULL",
            (ch_id,),
        ).fetchone()["cnt"]

        # 尝试结算
        status = ch["status"]
        settle_result = None
        if sub_count >= REQUIRED_SUBMISSIONS:
            settle_result = self._try_settle_challenge(db, ch_id)
            status = settle_result["status"] if isinstance(settle_result, dict) else settle_result

        response = {
            "success": True,
            "submission_count": sub_count,
            "required_submissions": REQUIRED_SUBMISSIONS,
            "status": status,
            "message": "reveal recorded",
        }

        # After settlement, reveal answer + salt for miner verification
        if isinstance(settle_result, dict) and settle_result.get("settled"):
            ch_fresh = db.execute("SELECT * FROM challenges WHERE id=?", (ch_id,)).fetchone()
            ctype = ch_fresh["type"]
            response["verification"] = {
                "verification_mode": "deterministic" if ctype in DETERMINISTIC_TYPES else "server_trust",
                "commitment": ch_fresh["commitment"] or "",
                "revealed_answer": ch_fresh["expected_answer"] or "",
                "salt": ch_fresh["salt"] or "",
            }

        self._json_response(response)

    # ═══════════════════════════════════════
    # GET /clawchain/version
    # ═══════════════════════════════════════
    def handle_get_version(self):
        self._json_response({
            "server_version": SERVER_VERSION,
            "min_miner_version": MIN_MINER_VERSION,
            "protocol": "clawchain-testnet-1",
        })

    # ═══════════════════════════════════════
    # POST /clawchain/miner/register
    # ═══════════════════════════════════════
    def handle_register_miner(self, body):
        address = body.get("address", "")
        name = body.get("name", "")
        miner_version = body.get("miner_version", "")

        if not address:
            self._error("address is required", 400)
            return

        # 基础地址格式验证
        if not address.startswith("claw1"):
            self._error("invalid address format", 400)
            return

        # Version compatibility check
        if miner_version and miner_version < MIN_MINER_VERSION:
            self._error(
                f"miner version {miner_version} is below minimum {MIN_MINER_VERSION}, please upgrade",
                400,
            )
            return

        db = get_shared_db()

        # Anti-Sybil: IP rate limit
        client_ip = self.client_address[0] if self.client_address else ""
        if client_ip:
            ip_count = db.execute(
                "SELECT COUNT(*) AS cnt FROM miners WHERE ip_address=?",
                (client_ip,),
            ).fetchone()["cnt"]
            if ip_count >= MAX_MINERS_PER_IP:
                self._error(
                    f"too many miners from this IP (max {MAX_MINERS_PER_IP})", 429
                )
                return

        # 检查已注册
        existing = db.execute("SELECT * FROM miners WHERE address=?", (address,)).fetchone()
        if existing:
            # 如果 suspended，检查是否可以恢复
            if existing["status"] == "suspended":
                suspended_at = existing["suspended_at"]
                if suspended_at:
                    from datetime import timedelta
                    suspended_time = datetime.fromisoformat(suspended_at)
                    cooldown_end = suspended_time + timedelta(hours=24)
                    if datetime.utcnow() < cooldown_end:
                        remaining = cooldown_end - datetime.utcnow()
                        hours_left = remaining.total_seconds() / 3600
                        self._error(
                            f"miner suspended, please wait {hours_left:.1f} hours before re-registering",
                            403,
                        )
                        return
                # 24h passed or no suspended_at — restore with reputation 200
                db.execute(
                    """UPDATE miners SET status='active', reputation=200,
                       consecutive_failures=0, suspended_at=NULL WHERE address=?""",
                    (address,),
                )
                db.commit()
                logger.info(f"Miner {address} restored from suspension with reputation 200")
                self._json_response({
                    "success": True,
                    "message": "miner restored from suspension (reputation reset to 200)",
                    "address": address,
                })
                return
            else:
                self._error("miner already registered", 409)
                return

        # 获取注册序号
        reg_count = int(get_global(db, "miner_count", "0")) + 1
        set_global(db, "miner_count", reg_count)

        # Progressive staking requirement
        stake_required = self._get_stake_requirement(db)
        staked_amount = 0
        if stake_required > 0:
            # For new miners, staking is deducted from faucet/future rewards
            # In testnet, we allow registration and track the stake debt
            staked_amount = 0  # Will be enforced when miner has rewards

        # 插入矿工
        db.execute(
            """INSERT INTO miners (address, name, registration_index, status, reputation, ip_address, staked_amount, staked_at)
            VALUES (?, ?, ?, 'active', 500, ?, ?, CURRENT_TIMESTAMP)""",
            (address, name or "miner", reg_count, client_ip, staked_amount),
        )
        db.commit()

        self._json_response({
            "success": True,
            "message": "miner registered successfully",
            "address": address,
            "registration_index": reg_count,
            "stake_required": stake_required,
        })

    # ═══════════════════════════════════════
    # GET /clawchain/miner/{address}
    # ═══════════════════════════════════════
    def handle_get_miner_info(self, address):
        db = get_shared_db()
        miner = db.execute("SELECT * FROM miners WHERE address=?", (address,)).fetchone()
        if not miner:
            self._error("miner not found", 404)
            return

        self._json_response({
            "address": miner["address"],
            "name": miner["name"],
            "status": miner["status"],
            "registration_index": miner["registration_index"],
            "challenges_completed": miner["challenges_completed"],
            "challenges_failed": miner["challenges_failed"],
            "total_rewards": miner["total_rewards"],
            "consecutive_days": miner["consecutive_days"],
            "last_active_day": miner["last_active_day"],
            "reputation": miner["reputation"],
            "consecutive_failures": miner["consecutive_failures"],
            "suspended_at": miner["suspended_at"],
            "faucet_claimed": miner["faucet_claimed"],
        })

    # ═══════════════════════════════════════
    # GET /clawchain/miner/{address}/stats
    # ═══════════════════════════════════════
    def handle_get_miner_stats(self, address):
        db = get_shared_db()
        miner = db.execute("SELECT * FROM miners WHERE address=?", (address,)).fetchone()
        if not miner:
            self._error("miner not found", 404)
            return

        completed = miner["challenges_completed"] or 0
        failed = miner["challenges_failed"] or 0
        total = completed + failed
        success_rate = (completed / total * 100) if total > 0 else 0.0
        total_rewards = miner["total_rewards"] or 0

        self._json_response({
            "address": address,
            "challenges_completed": completed,
            "challenges_failed": failed,
            "total_challenges": total,
            "success_rate": f"{success_rate:.2f}%",
            "total_rewards": total_rewards,
            "total_rewards_uclaw": f"{total_rewards} uclaw",
        })

    # ═══════════════════════════════════════
    # GET /clawchain/stats
    # ═══════════════════════════════════════
    def handle_get_stats(self):
        db = get_shared_db()

        total_challenges = db.execute("SELECT COUNT(*) AS cnt FROM challenges").fetchone()["cnt"]
        completed_challenges = db.execute(
            "SELECT COUNT(*) AS cnt FROM challenges WHERE status IN ('complete','reveal')"
        ).fetchone()["cnt"]
        active_miners = db.execute(
            "SELECT COUNT(*) AS cnt FROM miners WHERE status='active'"
        ).fetchone()["cnt"]
        total_rewards_row = db.execute(
            "SELECT COALESCE(SUM(total_rewards), 0) AS total FROM miners"
        ).fetchone()
        total_rewards_paid = total_rewards_row["total"]

        current_epoch = get_current_epoch(db)
        current_reward = get_epoch_miner_pool(current_epoch)

        # 验证者池和生态基金累计
        val_row = db.execute(
            "SELECT COALESCE(SUM(validator_pool), 0) AS total FROM epoch_rewards"
        ).fetchone()
        eco_row = db.execute(
            "SELECT COALESCE(SUM(eco_fund), 0) AS total FROM epoch_rewards"
        ).fetchone()
        validator_pool_total = val_row["total"]
        eco_fund_total = eco_row["total"]

        self._json_response({
            "total_challenges": total_challenges,
            "completed_challenges": completed_challenges,
            "active_miners": active_miners,
            "total_rewards_paid": total_rewards_paid,
            "total_rewards_uclaw": f"{total_rewards_paid} uclaw",
            "current_block_height": current_epoch * 100,  # 模拟 block height
            "current_block_reward": current_reward,
            "current_reward_uclaw": f"{current_reward} uclaw",
            "validator_pool_total": validator_pool_total,
            "validator_pool_uclaw": f"{validator_pool_total} uclaw",
            "eco_fund_total": eco_fund_total,
            "eco_fund_uclaw": f"{eco_fund_total} uclaw",
        })

    # ═══════════════════════════════════════
    # POST /clawchain/faucet
    # ═══════════════════════════════════════
    def handle_faucet(self, body):
        address = body.get("address", "")
        if not address:
            self._error("address is required", 400)
            return

        if not address.startswith("claw1"):
            self._error("invalid address format", 400)
            return

        db = get_shared_db()

        # 检查是否已领取
        miner = db.execute("SELECT faucet_claimed FROM miners WHERE address=?", (address,)).fetchone()
        if miner and miner["faucet_claimed"]:
            self._json_response({
                "success": False,
                "message": "faucet tokens already claimed",
            })
            return

        # 如果矿工不存在，也标记为已领取（在 global_state 中记录）
        faucet_key = f"faucet:{address}"
        if get_global(db, faucet_key):
            self._json_response({
                "success": False,
                "message": "faucet tokens already claimed",
            })
            return

        # 标记已领取
        set_global(db, faucet_key, "1")
        if miner is not None:
            db.execute("UPDATE miners SET faucet_claimed=1 WHERE address=?", (address,))
            db.commit()

        self._json_response({
            "success": True,
            "message": f"sent 200 CLAW (200,000,000 uclaw) to {address}",
            "amount": FAUCET_AMOUNT,
        })

    # ═══════════════════════════════════════
    # GET /clawchain/epoch/{N}/settlement
    # ═══════════════════════════════════════
    def handle_get_epoch_settlement(self, epoch_id):
        db = get_shared_db()

        # Check if anchor exists in DB
        anchor = db.execute(
            "SELECT * FROM epoch_anchors WHERE epoch_id=?", (epoch_id,)
        ).fetchone()

        if anchor:
            records = json.loads(anchor["records_json"]) if anchor["records_json"] else []
            self._json_response({
                "epoch_id": epoch_id,
                "settlement_root": anchor["settlement_root"],
                "anchor_type": anchor["anchor_type"],
                "tx_hash": anchor["tx_hash"],
                "records": records,
                "created_at": anchor["created_at"],
            })
            return

        # Compute on the fly if not anchored yet
        result = compute_settlement_root(db, epoch_id)
        if result is None or result[0] is None:
            self._error(f"no settlement data for epoch {epoch_id}", 404)
            return

        settlement_root, records = result
        self._json_response({
            "epoch_id": epoch_id,
            "settlement_root": settlement_root,
            "anchor_type": "computed",
            "tx_hash": None,
            "records": records,
        })

    # ═══════════════════════════════════════
    # GET /clawchain/anchors
    # ═══════════════════════════════════════
    def handle_get_anchors(self):
        db = get_shared_db()
        rows = db.execute(
            "SELECT epoch_id, settlement_root, anchor_type, tx_hash, created_at FROM epoch_anchors ORDER BY epoch_id DESC"
        ).fetchall()

        anchors = []
        for r in rows:
            anchors.append({
                "epoch_id": r["epoch_id"],
                "settlement_root": r["settlement_root"],
                "anchor_type": r["anchor_type"],
                "tx_hash": r["tx_hash"],
                "created_at": r["created_at"],
            })

        self._json_response({"anchors": anchors, "count": len(anchors)})

    # ═══════════════════════════════════════
    # 内部：即时结算
    # ═══════════════════════════════════════
    def _try_settle_challenge(self, db, ch_id):
        """尝试即时结算一道挑战，返回 {"status": str, "settled": bool}"""
        ch = db.execute("SELECT * FROM challenges WHERE id=?", (ch_id,)).fetchone()
        if not ch or ch["status"] == "complete":
            return {"status": ch["status"] if ch else "unknown", "settled": False}

        subs = db.execute(
            "SELECT * FROM submissions WHERE challenge_id=? AND answer IS NOT NULL",
            (ch_id,),
        ).fetchall()

        if len(subs) < REQUIRED_SUBMISSIONS:
            return {"status": ch["status"], "settled": False}

        # 构建答案分组
        answer_votes = {}
        for s in subs:
            norm = s["answer"].strip().lower()
            answer_votes.setdefault(norm, []).append(s["miner_address"])

        is_spot = bool(ch["is_spot_check"])
        known = (ch["known_answer"] or "").strip().lower()

        # Spot check: 正确答案以 known_answer 为准
        # 普通挑战: 正确答案以多数一致为准
        if is_spot and known:
            majority_answer = known
            majority_miners = answer_votes.get(known, [])
        else:
            majority_answer = max(answer_votes, key=lambda k: len(answer_votes[k]))
            majority_miners = answer_votes[majority_answer]

        if not is_spot and len(majority_miners) < MIN_MAJORITY:
            return {"status": ch["status"], "settled": False}

        # 结算！
        epoch = ch["epoch"]
        total_ch_in_epoch = db.execute(
            "SELECT COUNT(*) AS cnt FROM challenges WHERE epoch=?", (epoch,)
        ).fetchone()["cnt"]
        if total_ch_in_epoch < 1:
            total_ch_in_epoch = 1

        miner_pool = get_epoch_miner_pool(epoch)
        per_challenge_pool = max(miner_pool // total_ch_in_epoch, 1)
        reward_per_miner = max(per_challenge_pool // len(majority_miners), 1) if majority_miners else 0

        is_spot = bool(ch["is_spot_check"])

        for addr in majority_miners:
            miner = db.execute("SELECT * FROM miners WHERE address=?", (addr,)).fetchone()
            if not miner:
                continue

            actual_reward = calculate_miner_reward(
                reward_per_miner,
                miner["registration_index"] or 0,
                miner["consecutive_days"] or 0,
                miner["challenges_completed"] or 0,
            )

            # 声誉奖励：spot check 答对 +10，普通答对 +5
            rep_delta = 10 if is_spot else 5

            db.execute(
                "UPDATE submissions SET is_correct=1, reward_amount=? WHERE challenge_id=? AND miner_address=?",
                (actual_reward, ch_id, addr),
            )
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

        # 惩罚不一致
        for norm_answer, addrs in answer_votes.items():
            if norm_answer != majority_answer:
                for addr in addrs:
                    db.execute(
                        "UPDATE submissions SET is_correct=0 WHERE challenge_id=? AND miner_address=?",
                        (ch_id, addr),
                    )

                    # 声誉惩罚：spot check 答错 -50，普通答错 -20
                    rep_penalty = 50 if is_spot else 20

                    # 获取当前矿工信息，检查连续失败
                    miner = db.execute("SELECT * FROM miners WHERE address=?", (addr,)).fetchone()
                    if not miner:
                        continue

                    new_failures = (miner["consecutive_failures"] or 0) + 1
                    new_rep = (miner["reputation"] or 500) - rep_penalty
                    staked = miner["staked_amount"] or 0
                    slash_amount = 0

                    # Slashing: 3+ consecutive failures on spot checks → 10% stake
                    if is_spot and new_failures >= 3 and staked > 0:
                        slash_amount = staked // 10
                        logger.warning(f"Miner {addr} slashed 10% stake ({slash_amount} uclaw): {new_failures} consecutive spot-check failures")

                    # 连续答错 5 次以上 → 疑似作弊，-500 + 50% slash + suspended
                    if new_failures > 5:
                        new_rep = (miner["reputation"] or 500) - 500
                        if staked > 0:
                            slash_amount = staked // 2  # 50% slash
                        logger.warning(f"Miner {addr} suspected cheating: {new_failures} consecutive failures, slashed 50% stake")

                    new_status = miner["status"]
                    suspended_at = None
                    if new_rep < 100 or new_failures > 5:
                        new_status = "suspended"
                        suspended_at = datetime.utcnow().isoformat()
                        logger.warning(f"Miner {addr} suspended: rep={new_rep}, failures={new_failures}")

                    db.execute(
                        """UPDATE miners SET
                            challenges_failed = challenges_failed + 1,
                            consecutive_failures = ?,
                            reputation = ?,
                            status = ?,
                            suspended_at = COALESCE(?, suspended_at),
                            staked_amount = staked_amount - ?
                        WHERE address=?""",
                        (new_failures, max(new_rep, 0), new_status, suspended_at, slash_amount, addr),
                    )

        db.execute("UPDATE challenges SET status='complete' WHERE id=?", (ch_id,))
        db.commit()

        logger.info(f"Challenge {ch_id} settled: {len(majority_miners)} correct miners")
        return {"status": "complete", "settled": True}


    # ═══════════════════════════════════════
    # Internal: Progressive staking
    # ═══════════════════════════════════════
    def _get_stake_requirement(self, db) -> int:
        """Progressive stake requirement based on active miner count (uclaw)."""
        active = db.execute(
            "SELECT COUNT(*) AS cnt FROM miners WHERE status='active'"
        ).fetchone()["cnt"]
        if active < 1000:
            return 0
        elif active < 5000:
            return 10_000_000  # 10 CLAW
        else:
            return 100_000_000  # 100 CLAW


def get_current_epoch(db):
    val = get_global(db, "current_epoch", "0")
    return int(val)


# ─── 入口 ───

def main():
    parser = argparse.ArgumentParser(description="ClawChain Mining Service")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"HTTP port (default: {DEFAULT_PORT})")
    parser.add_argument("--db", type=str, default=None, help="SQLite database path")
    parser.add_argument("--no-scheduler", action="store_true", help="Disable epoch scheduler")
    args = parser.parse_args()

    # 初始化 DB
    if args.db:
        from models import DB_PATH as _
        import models
        models.DB_PATH = Path(args.db)

    db = init_db()
    migrate_db(db)
    global _db
    _db = db

    logger.info(f"Database initialized: {DB_PATH}")
    logger.info(f"DEV mode: {DEV_MODE}")
    logger.info(f"Required submissions: {REQUIRED_SUBMISSIONS}")

    # 启动 epoch 调度器
    if not args.no_scheduler:
        start_scheduler()
        logger.info("Epoch scheduler started (interval: 600s)")
    else:
        # 即使不启动调度器，也生成初始挑战
        epoch = get_current_epoch(db)
        active = db.execute("SELECT COUNT(*) AS cnt FROM miners WHERE status='active'").fetchone()["cnt"]
        challenges = generate_challenges(epoch, max(active, 1))
        for ch in challenges:
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
        logger.info(f"Generated {len(challenges)} initial challenges for epoch {epoch}")

    # 启动 HTTP 服务
    server = HTTPServer(("0.0.0.0", args.port), MiningHandler)
    logger.info(f"Mining service listening on http://0.0.0.0:{args.port}")
    logger.info("API endpoints:")
    logger.info("  GET  /clawchain/challenges/pending")
    logger.info("  POST /clawchain/challenge/submit")
    logger.info("  POST /clawchain/challenge/commit")
    logger.info("  POST /clawchain/challenge/reveal")
    logger.info("  POST /clawchain/miner/register")
    logger.info("  GET  /clawchain/miner/{address}")
    logger.info("  GET  /clawchain/version")
    logger.info("  GET  /clawchain/miner/{address}/stats")
    logger.info("  GET  /clawchain/stats")
    logger.info("  POST /clawchain/faucet")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()

"""
ClawChain Mining Service — 数据模型 & SQLite 初始化
"""

import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "mining.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS miners (
    address TEXT PRIMARY KEY,
    name TEXT,
    registration_index INTEGER,
    challenges_completed INTEGER DEFAULT 0,
    challenges_failed INTEGER DEFAULT 0,
    total_rewards INTEGER DEFAULT 0,
    consecutive_days INTEGER DEFAULT 0,
    last_active_day TEXT,
    reputation INTEGER DEFAULT 500,
    consecutive_failures INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    suspended_at TIMESTAMP,
    faucet_claimed INTEGER DEFAULT 0,
    staked_amount INTEGER DEFAULT 0,
    staked_at TIMESTAMP,
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS challenges (
    id TEXT PRIMARY KEY,
    epoch INTEGER,
    type TEXT,
    tier INTEGER DEFAULT 1,
    prompt TEXT,
    expected_answer TEXT,
    status TEXT DEFAULT 'pending',
    is_spot_check INTEGER DEFAULT 0,
    known_answer TEXT,
    salt TEXT,
    commitment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenge_id TEXT,
    miner_address TEXT,
    commit_hash TEXT,
    answer TEXT,
    nonce TEXT,
    is_correct INTEGER,
    reward_amount INTEGER DEFAULT 0,
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (challenge_id) REFERENCES challenges(id),
    FOREIGN KEY (miner_address) REFERENCES miners(address)
);

CREATE TABLE IF NOT EXISTS epoch_rewards (
    epoch INTEGER PRIMARY KEY,
    miner_pool INTEGER,
    validator_pool INTEGER,
    eco_fund INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS global_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS epoch_anchors (
    epoch_id INTEGER PRIMARY KEY,
    settlement_root TEXT NOT NULL,
    anchor_type TEXT DEFAULT 'local',
    tx_hash TEXT,
    records_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db(db_path=None):
    """获取 SQLite 连接（WAL 模式，支持并发读）"""
    path = db_path or DB_PATH
    db = sqlite3.connect(str(path), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db(db_path=None):
    """初始化数据库 schema"""
    db = get_db(db_path)
    db.executescript(SCHEMA)
    db.commit()
    return db


def migrate_db(db):
    """Add columns introduced after v0.1.0 (idempotent)."""
    migrations = [
        ("challenges", "salt", "ALTER TABLE challenges ADD COLUMN salt TEXT"),
        ("challenges", "commitment", "ALTER TABLE challenges ADD COLUMN commitment TEXT"),
        ("miners", "staked_amount", "ALTER TABLE miners ADD COLUMN staked_amount INTEGER DEFAULT 0"),
        ("miners", "staked_at", "ALTER TABLE miners ADD COLUMN staked_at TIMESTAMP"),
        ("miners", "ip_address", "ALTER TABLE miners ADD COLUMN ip_address TEXT"),
        ("miners", "auth_secret", "ALTER TABLE miners ADD COLUMN auth_secret TEXT"),
        ("miners", "public_key", "ALTER TABLE miners ADD COLUMN public_key TEXT"),
        ("miners", "last_nonce", "ALTER TABLE miners ADD COLUMN last_nonce INTEGER DEFAULT 0"),
    ]
    for table, col, sql in migrations:
        try:
            db.execute(f"SELECT {col} FROM {table} LIMIT 1")
        except Exception:
            db.execute(sql)
    db.commit()


def get_global(db, key, default=None):
    """读取全局状态"""
    row = db.execute("SELECT value FROM global_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_global(db, key, value):
    """设置全局状态"""
    db.execute(
        "INSERT OR REPLACE INTO global_state (key, value) VALUES (?, ?)",
        (key, str(value)),
    )
    db.commit()

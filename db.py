"""
本地 SQLite 数据库（移动端版本：路径自适应 Android/iOS/桌面）
"""
import os
import sys
import sqlite3
import time
import json
from typing import Optional, List, Dict, Any


def _get_db_dir() -> str:
    # Android: app storage
    if "android" in sys.platform or os.environ.get("ANDROID_ARGUMENT"):
        try:
            from android.storage import app_storage_path  # type: ignore
            d = app_storage_path()
            os.makedirs(d, exist_ok=True)
            return d
        except Exception:
            pass
    # 桌面：项目目录
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(d, exist_ok=True)
    return d


DB_PATH = os.path.join(_get_db_dir(), "accounts.db")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init_db():
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                email         TEXT UNIQUE,
                password_enc  TEXT DEFAULT '',
                token_id      TEXT DEFAULT '',
                token_key_enc TEXT DEFAULT '',
                user_name     TEXT DEFAULT '',
                balance       REAL DEFAULT 0,
                status        TEXT DEFAULT 'idle',
                last_refresh  INTEGER DEFAULT 0,
                note          TEXT DEFAULT '',
                created_at    INTEGER
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                order_id TEXT, order_goods_id INTEGER, order_goods_name TEXT,
                order_goods_price REAL, order_refund INTEGER, order_num INTEGER,
                order_price REAL, order_start_num INTEGER, order_end_num INTEGER,
                order_value TEXT, order_code INTEGER, order_card TEXT, order_date TEXT,
                raw_json TEXT, queried_at INTEGER,
                UNIQUE(account_id, order_id)
            );
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE INDEX IF NOT EXISTS idx_orders_account ON orders(account_id);
            """
        )


def upsert_account(email, password_enc, token_id, token_key_enc, note=""):
    now = int(time.time())
    with _conn() as c:
        row = c.execute("SELECT id FROM accounts WHERE email=?", (email,)).fetchone()
        if row:
            c.execute("UPDATE accounts SET password_enc=?, token_id=?, token_key_enc=?, note=? WHERE id=?",
                      (password_enc, token_id, token_key_enc, note, row["id"]))
            return row["id"]
        cur = c.execute("INSERT INTO accounts(email,password_enc,token_id,token_key_enc,note,created_at) VALUES(?,?,?,?,?,?)",
                        (email, password_enc, token_id, token_key_enc, note, now))
        return cur.lastrowid


def list_accounts():
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM accounts ORDER BY id ASC").fetchall()]


def get_account(account_id):
    with _conn() as c:
        r = c.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
        return dict(r) if r else None


def delete_account(account_id):
    with _conn() as c:
        c.execute("DELETE FROM orders WHERE account_id=?", (account_id,))
        c.execute("DELETE FROM accounts WHERE id=?", (account_id,))


def update_account_cache(account_id, user_name, balance, status="ok"):
    now = int(time.time())
    with _conn() as c:
        c.execute("UPDATE accounts SET user_name=?, balance=?, status=?, last_refresh=? WHERE id=?",
                  (user_name, balance, status, now, account_id))


def set_account_status(account_id, status):
    with _conn() as c:
        c.execute("UPDATE accounts SET status=? WHERE id=?", (status, account_id))


def update_account_token(account_id, token_id, token_key_enc):
    with _conn() as c:
        c.execute("UPDATE accounts SET token_id=?, token_key_enc=? WHERE id=?",
                  (token_id, token_key_enc, account_id))


def upsert_order(account_id, order):
    now = int(time.time())
    with _conn() as c:
        c.execute(
            """INSERT INTO orders(account_id, order_id, order_goods_id, order_goods_name,
               order_goods_price, order_refund, order_num, order_price, order_start_num,
               order_end_num, order_value, order_code, order_card, order_date, raw_json, queried_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(account_id, order_id) DO UPDATE SET
                order_goods_name=excluded.order_goods_name, order_code=excluded.order_code,
                order_card=excluded.order_card, order_date=excluded.order_date,
                order_end_num=excluded.order_end_num, raw_json=excluded.raw_json, queried_at=excluded.queried_at""",
            (account_id, order.get("orderId",""), order.get("orderGoodsId"), order.get("orderGoodsName"),
             order.get("orderGoodsPrice"), order.get("orderRefund"), order.get("orderNum"),
             order.get("orderPrice"), order.get("orderStartNum"), order.get("orderEndNum"),
             order.get("orderValue"), order.get("orderCode"), order.get("orderCard"),
             order.get("orderDate"), json.dumps(order, ensure_ascii=False), now))


def list_orders(account_id=None, limit=500):
    with _conn() as c:
        if account_id:
            rows = c.execute("SELECT * FROM orders WHERE account_id=? ORDER BY queried_at DESC LIMIT ?",
                            (account_id, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM orders ORDER BY queried_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


def get_setting(key, default=""):
    with _conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default


def set_setting(key, value):
    with _conn() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, value))

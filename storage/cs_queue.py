"""客服待回复队列（SQLite）：批量导入差评/私信 -> 待处理 -> 生成回复 -> 已回复/已忽略

- 与报告库、商品库共用 data/reports.db
- 每条记录：原文、评分、检测语言、回复、命中的模板、状态（待处理/已回复/已忽略）
"""
import os
import sqlite3
from datetime import datetime
from typing import List, Optional

from config.settings import settings
from utils.logger import logger

CS_STATUSES = ["待处理", "已回复", "已忽略"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS customer_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    rating INTEGER,
    language TEXT DEFAULT '',
    reply TEXT DEFAULT '',
    matched_template TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT '待处理',
    created_at TEXT NOT NULL,
    replied_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_cs_status ON customer_messages(status);
"""


class CsQueueStore:
    """客服待办队列存取"""

    def __init__(self, db_path: str = settings.REPORT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)) or ".", exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def add_many(self, items: List[dict]) -> int:
        """批量导入（items: [{content, rating?}]）"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._connect()
        n = 0
        try:
            for it in items:
                content = str(it.get("content") or "").strip()
                if not content:
                    continue
                rating = it.get("rating")
                conn.execute(
                    "INSERT INTO customer_messages (content, rating, status, created_at) VALUES (?,?,?,?)",
                    (content[:2000], int(rating) if rating else None, "待处理", now),
                )
                n += 1
            conn.commit()
        finally:
            conn.close()
        if n:
            logger.info(f"客服队列导入 {n} 条")
        return n

    def list(self, status: Optional[str] = None, limit: int = 100) -> dict:
        where, args = [], []
        if status:
            where.append("status=?")
            args.append(status)
        cond = (" WHERE " + " AND ".join(where)) if where else ""
        conn = self._connect()
        try:
            total = conn.execute(f"SELECT COUNT(*) FROM customer_messages{cond}", args).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM customer_messages{cond} ORDER BY id DESC LIMIT ?",
                args + [max(1, min(int(limit), 500))],
            ).fetchall()
            items = [dict(r) for r in rows]
        finally:
            conn.close()
        return {"items": items, "total": total}

    def stats(self) -> dict:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT status, COUNT(*) AS n FROM customer_messages GROUP BY status").fetchall()
        finally:
            conn.close()
        out = {s: 0 for s in CS_STATUSES}
        for r in rows:
            out[r["status"]] = r["n"]
        out["total"] = sum(out.values())
        return out

    def get(self, item_id: int) -> Optional[dict]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM customer_messages WHERE id=?", (int(item_id),)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def set_reply(self, item_id: int, reply: str, language: str = "", matched_template: str = "") -> bool:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._connect()
        try:
            cur = conn.execute(
                "UPDATE customer_messages SET reply=?, language=?, matched_template=?, replied_at=? WHERE id=?",
                (reply or "", language or "", matched_template or "", now, int(item_id)),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def set_status(self, item_id: int, status: str) -> bool:
        if status not in CS_STATUSES:
            raise ValueError(f"非法状态: {status}，可选 {'/'.join(CS_STATUSES)}")
        conn = self._connect()
        try:
            cur = conn.execute("UPDATE customer_messages SET status=? WHERE id=?", (status, int(item_id)))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


cs_queue = CsQueueStore()

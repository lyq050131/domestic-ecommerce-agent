"""商品库（SQLite）：把报告推荐的 Top 商品沉淀为可运营的商品池

- 同一商品（source_type|product_id）去重，重复推荐时更新分数与最近出现时间
- 支持状态流转：待投放 / 已投放 / 已排除 / 效果待观察
- 与报告库共用 data/reports.db，运营后台「商品库」卡片读写
"""
import os
import sqlite3
from datetime import datetime
from typing import List, Optional

from config.settings import settings
from utils.logger import logger

PRODUCT_STATUSES = ["待投放", "已投放", "已排除", "效果待观察"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_key TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    category TEXT,
    product_id TEXT NOT NULL,
    product_name TEXT,
    price REAL DEFAULT 0,
    sales_30d INTEGER DEFAULT 0,
    commission_rate REAL DEFAULT 0,
    coupon_amount REAL DEFAULT 0,
    score REAL DEFAULT 0,
    item_url TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT '待投放',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
CREATE INDEX IF NOT EXISTS idx_products_source ON products(source_type);
"""


class ProductStore:
    """商品池存取：去重入库 / 列表查询 / 状态统计 / 状态流转"""

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
        logger.info(f"商品库已就绪: {self.db_path}")

    def upsert_many(self, source_type: str, items: List[dict], category: str = "") -> int:
        """把推荐商品写入商品库（去重；保留用户已设置的状态，仅刷新数据与时间）"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = self._connect()
        n = 0
        try:
            for it in items:
                pid = str(it.get("product_id") or "").strip()
                if not pid:
                    continue
                key = f"{source_type}|{pid}"
                cat = category or str(it.get("category") or it.get("keyword") or "")[:100]
                score = float(it.get("hot_score") or it.get("promotion_score") or 0)
                conn.execute(
                    """INSERT INTO products
                       (product_key, source_type, category, product_id, product_name,
                        price, sales_30d, commission_rate, coupon_amount, score, item_url,
                        status, first_seen_at, last_seen_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?, '待投放', ?, ?)
                       ON CONFLICT(product_key) DO UPDATE SET
                         product_name=excluded.product_name,
                         category=excluded.category,
                         price=excluded.price,
                         sales_30d=excluded.sales_30d,
                         commission_rate=excluded.commission_rate,
                         coupon_amount=excluded.coupon_amount,
                         score=excluded.score,
                         item_url=excluded.item_url,
                         last_seen_at=excluded.last_seen_at""",
                    (
                        key, source_type, cat, pid,
                        str(it.get("product_name") or "")[:200],
                        round(float(it.get("price") or 0), 2),
                        int(it.get("sales_30d") or 0),
                        round(float(it.get("commission_rate") or 0), 2),
                        round(float(it.get("coupon_amount") or 0), 2),
                        round(score, 2),
                        str(it.get("item_url") or ""),
                        now, now,
                    ),
                )
                n += 1
            conn.commit()
        finally:
            conn.close()
        if n:
            logger.info(f"商品库写入 {n} 条（{source_type}）")
        return n

    def list_products(
        self,
        status: Optional[str] = None,
        source: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        where, args = [], []
        if status:
            where.append("status=?")
            args.append(status)
        if source:
            where.append("source_type=?")
            args.append(source)
        if q:
            where.append("(product_name LIKE ? OR category LIKE ?)")
            args += [f"%{q}%", f"%{q}%"]
        cond = (" WHERE " + " AND ".join(where)) if where else ""
        conn = self._connect()
        try:
            total = conn.execute(f"SELECT COUNT(*) FROM products{cond}", args).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM products{cond} ORDER BY last_seen_at DESC, score DESC LIMIT ? OFFSET ?",
                args + [max(1, min(int(limit), 500)), max(0, int(offset))],
            ).fetchall()
            items = [dict(r) for r in rows]
        finally:
            conn.close()
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def stats(self) -> dict:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT status, COUNT(*) AS n FROM products GROUP BY status").fetchall()
        finally:
            conn.close()
        out = {s: 0 for s in PRODUCT_STATUSES}
        for r in rows:
            out[r["status"]] = r["n"]
        out["total"] = sum(out.values())
        return out

    def set_status(self, product_id: int, status: str) -> bool:
        if status not in PRODUCT_STATUSES:
            raise ValueError(f"非法状态: {status}，可选 {'/'.join(PRODUCT_STATUSES)}")
        conn = self._connect()
        try:
            cur = conn.execute("UPDATE products SET status=? WHERE id=?", (status, int(product_id)))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


product_store = ProductStore()

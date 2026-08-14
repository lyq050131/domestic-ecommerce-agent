"""报告持久化（SQLite）：选品/投放报告落库 + 历史查询 + 趋势聚合

- 每次选品/投放分析结果自动写入 data/reports.db（本地零依赖）
- 摘要字段为 JSON，包含关键指标与 Top 商品（含淘宝推广链接 item_url）
- 趋势接口按日期聚合，供运营后台画趋势图
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional

from config.settings import settings
from storage.product_store import product_store
from utils.logger import logger

REPORT_DB_DIR = os.path.dirname(os.path.abspath(settings.REPORT_DB_PATH)) or "."
REPORT_DB_PATH = settings.REPORT_DB_PATH

# 每个报告类型的可聚合数值指标（趋势图用，取当日报告均值）
METRIC_KEYS = {
    "selection": ["total", "avg_price", "avg_sales", "avg_commission", "hot_count", "total_coupon"],
    "ad": ["total", "keywords", "avg_commission", "total_estimated_commission"],
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    summary TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_type_created ON reports(report_type, created_at);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ReportStore:
    """报告存取：落库 / 列表 / 详情 / 趋势"""

    def __init__(self, db_path: str = REPORT_DB_PATH):
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
        logger.info(f"报告库已就绪: {self.db_path}")

    # ---------- 写入 ----------
    def save_report(
        self,
        report_type: str,
        title: str,
        content: str,
        summary: dict,
        params: Optional[dict] = None,
    ) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT INTO reports (report_type, title, content, summary, params, created_at) VALUES (?,?,?,?,?,?)",
                (
                    report_type,
                    title,
                    content or "",
                    json.dumps(summary or {}, ensure_ascii=False),
                    json.dumps(params or {}, ensure_ascii=False),
                    _now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def save_selection_report(self, result: dict, params: Optional[dict] = None) -> int:
        """把选品 Agent 结果落库：摘要 + Top10 商品（含推广链接）"""
        df = result.get("competitor_data")
        summary = {"total": 0, "avg_price": 0, "avg_sales": 0, "avg_commission": 0,
                   "hot_count": 0, "total_coupon": 0}
        top_products = []
        if df is not None and not df.empty:
            df = df.copy()
            if "hot_score" not in df.columns:
                df["hot_score"] = 0
            top = df.nlargest(10, "hot_score")
            for _, row in top.iterrows():
                top_products.append({
                    "product_id": str(row.get("product_id", "")),
                    "product_name": str(row.get("product_name", "")),
                    "price": round(float(row.get("price", 0) or 0), 2),
                    "sales_30d": int(row.get("sales_30d", 0) or 0),
                    "commission_rate": round(float(row.get("commission_rate", 0) or 0), 2),
                    "coupon_amount": round(float(row.get("coupon_amount", 0) or 0), 2),
                    "hot_score": round(float(row.get("hot_score", 0) or 0), 2),
                    "item_url": str(row.get("item_url", "") or ""),
                })
            s = _safe_summary(df, ["price", "sales_30d", "commission_rate", "coupon_amount"])
            summary = {
                "total": int(len(df)),
                "avg_price": s["price"],
                "avg_sales": s["sales_30d"],
                "avg_commission": s["commission_rate"],
                "hot_count": int((df["hot_score"] >= 60).sum()) if "hot_score" in df.columns else 0,
                "total_coupon": round(float(df["coupon_amount"].sum()), 2) if "coupon_amount" in df.columns else 0,
            }
        summary["top_products"] = top_products
        product_store.upsert_many("selection", top_products, category=result.get("category") or "")
        if params is None:
            params = {
                "category": result.get("category"),
                "cat": result.get("cat"),
                "include_keywords": result.get("include_keywords"),
                "exclude_keywords": result.get("exclude_keywords"),
            }
        rid = self.save_report("selection", result.get("category") or "选品分析",
                             result.get("report") or "", summary, params)
        return rid, summary

    def save_ad_report(self, result: dict, params: Optional[dict] = None) -> int:
        """把投放优化 Agent 结果落库：摘要 + Top10 商品（含推广链接）"""
        promo = result.get("promotion_summary") or {}
        df = result.get("promotion_data")
        top_products = []
        if df is not None and not df.empty:
            df = df.copy()
            if "promotion_score" not in df.columns:
                df["promotion_score"] = 0
            top = df.nlargest(10, "promotion_score")
            for _, row in top.iterrows():
                top_products.append({
                    "product_id": str(row.get("product_id", "")),
                    "product_name": str(row.get("product_name", "")),
                    "keyword": str(row.get("keyword", "")),
                    "price": round(float(row.get("price", 0) or 0), 2),
                    "sales_30d": int(row.get("sales_30d", 0) or 0),
                    "commission_rate": round(float(row.get("commission_rate", 0) or 0), 2),
                    "promotion_score": round(float(row.get("promotion_score", 0) or 0), 2),
                    "item_url": str(row.get("item_url", "") or ""),
                })
        summary = {
            "total": int(promo.get("total", 0) or 0),
            "keywords": int(promo.get("keywords", 0) or 0),
            "avg_commission": round(float(promo.get("avg_commission", 0) or 0), 2),
            "total_estimated_commission": round(float(promo.get("total_estimated_commission", 0) or 0), 2),
        }
        summary["top_products"] = top_products
        product_store.upsert_many("ad", top_products)
        if params is None:
            params = {
                "keywords": result.get("request_keywords"),
                "top_n": result.get("request_top_n"),
                "order_days": result.get("request_order_days"),
            }
        rid = self.save_report("ad", "推广优化方案", result.get("optimization_strategy") or "", summary, params)
        return rid, summary

    # ---------- 查询 ----------
    def list_reports(self, report_type: Optional[str] = None, limit: int = 30) -> List[dict]:
        """历史列表（不含正文，含摘要）"""
        conn = self._connect()
        try:
            if report_type:
                rows = conn.execute(
                    "SELECT id, report_type, title, summary, created_at FROM reports "
                    "WHERE report_type=? ORDER BY id DESC LIMIT ?",
                    (report_type, max(1, min(int(limit), 200))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, report_type, title, summary, created_at FROM reports "
                    "ORDER BY id DESC LIMIT ?",
                    (max(1, min(int(limit), 200)),),
                ).fetchall()
            return [dict(r, summary=_parse_summary(r["summary"])) for r in rows]
        finally:
            conn.close()

    def get_report(self, report_id: int) -> Optional[dict]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, report_type, title, content, summary, params, created_at FROM reports WHERE id=?",
                (int(report_id),),
            ).fetchone()
            if not row:
                return None
            return dict(row, summary=_parse_summary(row["summary"]), params=_parse_summary(row["params"]))
        finally:
            conn.close()

    def latest_by_date(self, report_type: str, date: str) -> Optional[dict]:
        """某类型某天最近一条报告（不含正文）"""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, report_type, title, summary, created_at FROM reports "
                "WHERE report_type=? AND created_at LIKE ? ORDER BY id DESC LIMIT 1",
                (report_type, date + "%"),
            ).fetchone()
            if not row:
                return None
            return dict(row, summary=_parse_summary(row["summary"]))
        finally:
            conn.close()

    def trend(self, report_type: str, days: int = 30) -> List[dict]:
        """按日期聚合趋势（数值指标取当日报告均值）"""
        keys = METRIC_KEYS.get(report_type, [])
        start = (datetime.now() - timedelta(days=max(1, min(int(days), 365)))).strftime("%Y-%m-%d %H:%M:%S")
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT summary, created_at FROM reports WHERE report_type=? AND created_at >= ? ORDER BY created_at ASC",
                (report_type, start),
            ).fetchall()
        finally:
            conn.close()
        buckets: dict = {}
        for raw, ts in rows:
            s = _parse_summary(raw)
            if not s:
                continue
            date = ts[:10]
            bucket = buckets.setdefault(date, {"date": date, "runs": 0, "_sums": {}})
            bucket["runs"] += 1
            for k in keys:
                v = s.get(k)
                if isinstance(v, (int, float)):
                    bucket["_sums"][k] = bucket["_sums"].get(k, 0.0) + float(v)
        result = []
        for date in sorted(buckets):
            b = buckets[date]
            row = {"date": date, "runs": b["runs"]}
            for k in keys:
                if k in b["_sums"]:
                    row[k] = round(b["_sums"][k] / b["runs"], 2)
            result.append(row)
        return result


def _parse_summary(raw) -> dict:
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}


def _safe_summary(df, cols) -> dict:
    out = {}
    for c in cols:
        try:
            out[c] = round(float(df[c].mean()), 2) if len(df) else 0
        except Exception:
            out[c] = 0
    return out


report_store = ReportStore()

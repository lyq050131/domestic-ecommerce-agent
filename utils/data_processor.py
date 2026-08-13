"""数据处理与爆款指数计算（字段对齐淘宝客真实数据）"""
import re
from datetime import datetime
from typing import List, Optional

import pandas as pd

from utils.logger import logger


def filter_by_keywords(
    df: pd.DataFrame,
    column: str = "product_name",
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
) -> pd.DataFrame:
    """按关键词过滤商品标题，保证按品类抓取的精确性。

    - include：标题必须同时命中全部词（白名单），不传则不过滤；
    - exclude：标题命中任一词即剔除（黑名单），如"鼠标垫/电脑/笔记本"；
    - 该过滤用于淘宝关键词搜索结果的二次清洗：q 是搜索词，不保证 100% 同品类。
    """
    if df.empty:
        return df
    df = df.copy()
    include = [str(k).strip() for k in (include or []) if str(k).strip()]
    exclude = [str(k).strip() for k in (exclude or []) if str(k).strip()]
    titles = df[column].fillna("")
    mask = pd.Series(True, index=df.index)
    if include:
        mask &= titles.str.contains("|".join(map(re.escape, include)), case=False, regex=True, na=False)
    if exclude:
        mask &= ~titles.str.contains("|".join(map(re.escape, exclude)), case=False, regex=True, na=False)
    return df[mask].reset_index(drop=True)

REQUIRED_COLS = [
    "product_id", "product_name", "category", "price", "sales_30d",
    "commission_rate", "coupon_amount", "rating", "review_count", "is_hot",
]


def _safe_norm(series: pd.Series) -> pd.Series:
    """归一化到 [0,1]；全同取值或空数据时返回中性 0.5，避免除零"""
    if series is None or len(series) == 0:
        return pd.Series(dtype=float)
    span = series.max() - series.min()
    if span == 0 or pd.isna(span):
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - series.min()) / span


class DataProcessor:
    """数据处理工具：清洗 -> 爆款指数 -> 摘要"""

    def __init__(self):
        logger.info("数据处理工具初始化完成")

    def clean_product_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗商品数据：补列、去重、过滤异常价格、填充缺失值"""
        logger.info(f"清洗商品数据，原始行数: {len(df)}")
        if df.empty:
            return df
        df = df.copy()
        for col in REQUIRED_COLS:
            if col not in df.columns:
                df[col] = "" if col == "product_name" else 0
        df = df.drop_duplicates(subset=["product_id"])
        df = df[(df["price"] > 0) & (df["price"] < 100000)]
        df["sales_30d"] = df["sales_30d"].fillna(0).astype(int)
        df["commission_rate"] = df["commission_rate"].fillna(0).astype(float)
        df["coupon_amount"] = df["coupon_amount"].fillna(0).astype(float)
        # 淘宝物料接口不返回评分/评论数：评分取中性值 4.5，避免爆款指数失真
        df["rating"] = df["rating"].fillna(4.5).astype(float)
        df["review_count"] = df["review_count"].fillna(0).astype(int)
        logger.info(f"清洗完成，剩余行数: {len(df)}")
        return df

    def calculate_hot_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """爆款指数：月销 40% + 佣金率 30% + 优惠力度 15% + 评分 15%
        相比 v2（销量/评分/评论）更适配淘宝客真实字段：销量、佣金率、优惠券均为真实数据。"""
        if df.empty:
            return df
        df = df.copy()
        df["sales_norm"] = _safe_norm(df["sales_30d"])
        df["commission_norm"] = _safe_norm(df["commission_rate"])
        df["coupon_norm"] = _safe_norm(df["coupon_amount"])
        df["rating_norm"] = _safe_norm(df["rating"])
        df["hot_score"] = (
            df["sales_norm"] * 0.4
            + df["commission_norm"] * 0.3
            + df["coupon_norm"] * 0.15
            + df["rating_norm"] * 0.15
        ) * 100
        df["hot_score"] = df["hot_score"].round(2)
        df["is_hot"] = df["hot_score"] >= 60
        return df

    def summarize_products(self, df: pd.DataFrame) -> dict:
        """选品数据摘要（用于报告数据展示）"""
        if df.empty:
            return {"total": 0, "avg_price": 0, "avg_sales": 0, "avg_commission": 0,
                    "hot_count": 0, "total_coupon": 0}
        return {
            "total": len(df),
            "avg_price": round(float(df["price"].mean()), 2),
            "avg_sales": int(df["sales_30d"].mean()),
            "avg_commission": round(float(df["commission_rate"].mean()), 2),
            "hot_count": int(df["is_hot"].sum()),
            "total_coupon": round(float(df["coupon_amount"].sum()), 2),
        }

    def summarize_promotion(self, df: pd.DataFrame) -> dict:
        """推广数据摘要（用于报告数据展示）"""
        if df.empty:
            return {"total": 0, "keywords": 0, "avg_commission": 0,
                    "total_estimated_commission": 0, "top_keywords": []}
        top_kw = (df.groupby("keyword")["promotion_score"].mean()
                  .sort_values(ascending=False).head(5))
        return {
            "total": len(df),
            "keywords": int(df["keyword"].nunique()),
            "avg_commission": round(float(df["commission_rate"].mean()), 2),
            "total_estimated_commission": round(float(df["estimated_commission"].sum()), 2),
            "top_keywords": [{"keyword": k, "score": round(float(v), 2)} for k, v in top_kw.items()],
        }

    def format_top_products(self, df: pd.DataFrame, top_n: int = 5) -> str:
        """格式化 Top 商品明细"""
        cols = ["product_name", "price", "sales_30d", "commission_rate",
                "estimated_commission", "hot_score"]
        cols = [c for c in cols if c in df.columns]
        if df.empty:
            return "（暂无商品数据）"
        return df.nlargest(top_n, "hot_score")[cols].to_string(index=False)

    def generate_daily_report(self, product_df: pd.DataFrame) -> dict:
        """日报摘要（可扩展输出到 data/output）"""
        summary = self.summarize_products(product_df)
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "product_summary": summary,
        }


data_processor = DataProcessor()
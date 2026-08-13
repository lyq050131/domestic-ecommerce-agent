"""竞品/商品数据抓取：淘宝客真实 API（真实店铺运营模式）

真实模式是唯一数据源：调用 taobao.tbk.dg.material.optional.upgrade 物料搜索升级版，
返回真实商品价格、月销、佣金率、优惠券数据；接口失败直接抛出异常，绝不伪造数据。

按品类抓取的精确性由"三层机制"保证：
1. 请求层：q=品类关键词 + 可选 cat=淘宝商品类目ID；
2. 过滤层：标题白名单（必须命中品类核心词）+ 黑名单（剔除近义词/套装/相邻品类噪声）；
3. 复核层：DeepSeek 在报告中识别并标注类目异常商品。
"""
import os
import random
from datetime import datetime
from typing import List, Optional

import pandas as pd

from config.settings import settings
from crawlers.taobao_client import taobao_client
from utils.data_processor import filter_by_keywords
from utils.logger import logger

FIELDS = [
    "product_id", "product_name", "category", "price", "original_price",
    "coupon_amount", "coupon_start_fee", "sales_30d", "commission_rate",
    "estimated_commission", "shop_title", "item_url", "seller_type",
    "rating", "review_count", "is_hot", "data_source",
]


class CompetitorCrawler:
    """竞品数据爬虫（真实淘宝客数据源，支持品类精确过滤）"""

    def __init__(self) -> None:
        self.product_categories = [
            "无线蓝牙耳机", "智能手表", "便携充电宝", "运动手环", "蓝牙音箱",
            "手机壳", "数据线", "手机支架", "无线充电器", "降噪耳机",
        ]
        self._ensure_dirs()
        logger.info("竞品数据爬虫初始化完成（真实淘宝客数据源）")

    @staticmethod
    def _ensure_dirs() -> None:
        for path in ("data/raw", "data/processed", "data/output", "logs"):
            os.makedirs(path, exist_ok=True)

    def crawl_competitor_products(
        self,
        category: Optional[str] = None,
        count: int = 20,
        cat: Optional[str] = None,
        include_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """按品类抓取淘宝客真实商品数据（按销量排序）。

        参数说明：
        - category: 品类关键词（作为 q 与默认标题白名单）
        - cat: 淘宝商品类目ID（如鼠标类目 50006001），可显著提升精确性
        - include_keywords: 标题必须命中的白名单词，默认 [category]
        - exclude_keywords: 标题命中即剔除的黑名单词（如鼠标场景：["鼠标垫","电脑","笔记本","键盘"]）
        """
        if not settings.taobao_configured:
            raise RuntimeError(
                "未配置淘宝客三要素（TAOBAO_APP_KEY / TAOBAO_APP_SECRET / TAOBAO_ADZONE_ID），无法抓取真实数据"
            )
        logger.info(f"调用淘宝客物料搜索，品类: {category or '默认'}, 目标条数: {count}, 类目ID: {cat or '无'}")
        keyword = category or random.choice(self.product_categories)
        page_size = min(max(int(count), 1), 100)

        items = taobao_client.search_material(
            keyword, page_no=1, page_size=page_size, sort="total_sales_des", cat=cat
        )
        records = [taobao_client.parse_material_item(item) for item in items]
        df = pd.DataFrame(records, columns=FIELDS) if records else pd.DataFrame(columns=FIELDS)
        if df.empty:
            logger.warning(f"淘宝接口返回空结果（关键词 [{keyword}] 可能无联盟商品），请更换关键词后重试")
            self._save(df, prefix="competitor")
            return df

        df = self._apply_category_filter(df, keyword, include_keywords, exclude_keywords)
        self._save(df, prefix="competitor")
        logger.info(f"✅ 竞品数据就绪：{len(df)} 条（真实淘宝客数据，品类过滤后）")
        return df

    @staticmethod
    def _apply_category_filter(
        df: pd.DataFrame,
        category: str,
        include_keywords: Optional[List[str]],
        exclude_keywords: Optional[List[str]],
    ) -> pd.DataFrame:
        """标题关键词过滤：白名单全命中才保留，黑名单命中即剔除"""
        before = len(df)
        include = [k.strip() for k in (include_keywords or []) if k.strip()] or ([category] if category else None)
        filtered = filter_by_keywords(df, "product_name", include=include, exclude=exclude_keywords)
        if len(filtered) < before:
            logger.info(
                f"按品类过滤：{before} → {len(filtered)} 条（include={include}, exclude={exclude_keywords}）"
            )
        if filtered.empty:
            logger.warning("按品类过滤后无符合条件商品，建议调整品类关键词或 include/exclude 词")
        return filtered

    def _save(self, df: pd.DataFrame, prefix: str) -> None:
        if df.empty:
            return
        filename = f"data/raw/{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        logger.info(f"数据已保存到: {filename}")


competitor_crawler = CompetitorCrawler()
"""推广/投放数据抓取：淘宝客真实商品推广数据 + 可选订单数据（真实店铺运营模式）

说明：
- 淘宝客没有"广告投放"接口；本模块用「商品推广数据」驱动投放分析：
  按关键词搜索淘宝联盟推广商品，以 佣金率 × 月销量 估算推广潜力分。
- 订单结算数据（taobao.tbk.order.details.get）为付费接口，默认关闭。
"""
import os
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd

from config.settings import settings
from crawlers.taobao_client import taobao_client
from utils.data_processor import filter_by_keywords
from utils.logger import logger

PROMO_FIELDS = [
    "keyword", "product_id", "product_name", "category", "price",
    "sales_30d", "commission_rate", "estimated_commission", "coupon_amount",
    "shop_title", "item_url", "promotion_score", "data_source",
]

ORDER_FIELDS = [
    "order_id", "item_title", "num_iid", "total_fee", "commission",
    "order_status", "pay_time", "data_source",
]


class AdDataCrawler:
    """推广数据抓取（真实淘宝客数据源）"""

    def __init__(self) -> None:
        self.default_keywords = [
            "无线蓝牙耳机", "智能手表", "便携充电宝", "运动手环",
            "蓝牙音箱", "手机壳", "数据线", "手机支架", "无线充电器", "降噪耳机",
        ]
        os.makedirs("data/raw", exist_ok=True)
        logger.info("推广数据抓取器初始化完成（真实淘宝客数据源）")

    # ---------- 商品推广数据 ----------
    def fetch_promotion_data(
        self,
        keywords: Optional[List[str]] = None,
        top_n: int = 15,
        include_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """按关键词抓取淘宝联盟推广商品，计算推广潜力分（佣金率 × 月销）。

        include_keywords / exclude_keywords：标题白名单/黑名单过滤，
        默认白名单为该关键词本身，避免跨品类商品污染潜力分。
        """
        if not settings.taobao_configured:
            raise RuntimeError(
                "未配置淘宝客三要素（TAOBAO_APP_KEY / TAOBAO_APP_SECRET / TAOBAO_ADZONE_ID），无法抓取真实数据"
            )
        kw_list = [k.strip() for k in (keywords or self.default_keywords) if k.strip()]
        if not kw_list:
            raise ValueError("keywords 不能为空")
        records: List[dict] = []
        for kw in kw_list:
            records.extend(self._fetch_taobao_keyword(kw, top_n, include_keywords, exclude_keywords))
        df = pd.DataFrame(records, columns=PROMO_FIELDS) if records else pd.DataFrame(columns=PROMO_FIELDS)
        if not df.empty:
            df["promotion_score"] = (df["commission_rate"] * df["sales_30d"]).round(2)
            df = df.sort_values("promotion_score", ascending=False).reset_index(drop=True)
        filename = f"data/raw/promotion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        if not df.empty:
            df.to_csv(filename, index=False, encoding="utf-8-sig")
        logger.info(f"✅ 推广数据就绪：{len(df)} 条（真实淘宝客数据）")
        return df

    def _fetch_taobao_keyword(
        self,
        keyword: str,
        top_n: int,
        include_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
    ) -> List[dict]:
        items = taobao_client.search_material(
            keyword, page_no=1, page_size=min(max(int(top_n), 1), 100), sort="total_sales_des"
        )
        rows = []
        for item in items[:top_n]:
            parsed = taobao_client.parse_material_item(item)
            rows.append({
                "keyword": keyword,
                "product_id": parsed["product_id"],
                "product_name": parsed["product_name"],
                "category": parsed["category"],
                "price": parsed["price"],
                "sales_30d": parsed["sales_30d"],
                "commission_rate": parsed["commission_rate"],
                "estimated_commission": parsed["estimated_commission"],
                "coupon_amount": parsed["coupon_amount"],
                "shop_title": parsed["shop_title"],
                "item_url": parsed["item_url"],
                "promotion_score": 0.0,  # 稍后统一计算
                "data_source": "taobao",
            })
        df = pd.DataFrame(rows, columns=PROMO_FIELDS) if rows else pd.DataFrame(columns=PROMO_FIELDS)
        # 白名单默认=该关键词本身，黑名单可剔除跨品类噪声
        include = [k.strip() for k in (include_keywords or []) if k.strip()] or [keyword]
        filtered = filter_by_keywords(df, "product_name", include=include, exclude=exclude_keywords)
        if len(filtered) < len(df):
            logger.info(f"关键词 [{keyword}] 按品类过滤：{len(df)} → {len(filtered)} 条")
        return filtered.to_dict("records")

    # ---------- 订单结算数据（可选，付费接口） ----------
    def fetch_order_data(self, days: int = 7) -> pd.DataFrame:
        """拉取最近 N 天订单结算数据（需联盟佣金权限 + 商家 OAuth）。"""
        if not settings.TAOBAO_ORDER_ENABLED:
            logger.warning("订单数据未开启（TAOBAO_ORDER_ENABLED=false），跳过")
            return pd.DataFrame(columns=ORDER_FIELDS)
        token = settings.TAOBAO_ACCESS_TOKEN
        if not token:
            logger.warning("未配置 TAOBAO_ACCESS_TOKEN，无法拉取订单，跳过")
            return pd.DataFrame(columns=ORDER_FIELDS)
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_time = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        data = taobao_client._request(
            "taobao.tbk.order.details.get",
            {
                "start_time": start_time,
                "end_time": end_time,
                "page_no": 1,
                "page_size": 20,
                "order_scene": "1",
            },
            session=token,
        )
        results = ((data.get("results") or {}).get("publisher_order_dto")) or []
        records = [{
            "order_id": r.get("trade_id") or "",
            "item_title": r.get("item_title") or "",
            "num_iid": r.get("num_iid") or "",
            "total_fee": float(r.get("total_fee") or 0),
            "commission": float(r.get("pub_share_fee") or 0),
            "order_status": r.get("tk_status") or "",
            "pay_time": r.get("tb_paid_time") or "",
            "data_source": "taobao",
        } for r in results]
        logger.info(f"✅ 订单数据拉取完成：{len(records)} 条")
        return pd.DataFrame(records, columns=ORDER_FIELDS)


ad_data_crawler = AdDataCrawler()
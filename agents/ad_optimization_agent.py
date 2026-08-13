"""投放优化 Agent：淘宝客真实商品推广数据 + 历史策略（RAG 可选）→ 推广优化方案 → 闭环回流"""
from typing import List, Optional

import pandas as pd

from agents.base_agent import BaseAgent
from crawlers.ad_data_crawler import ad_data_crawler
from retrieval.vector_store import vector_store
from retrieval.mobius_loop import mobius_loop
from utils.data_processor import data_processor
from utils.logger import logger


class AdOptimizationAgent(BaseAgent):
    """投放优化 Agent

    说明：淘宝客没有广告投放接口，本模块用「商品推广数据」驱动：
    按关键词搜索淘宝联盟推广商品，以 佣金率 × 月销量 的推广潜力分做投放/选词优化。
    """

    def __init__(self):
        super().__init__("投放优化Agent")

    def optimize_campaigns(
        self,
        keywords: Optional[List[str]] = None,
        top_n: int = 15,
        order_days: int = 7,
        exclude_keywords: Optional[List[str]] = None,
    ) -> dict:
        """推广优化。exclude_keywords：标题黑名单，剔除跨品类噪声商品。"""
        logger.info("========== 开始推广/投放优化分析 ==========")

        logger.info("[步骤1/4] 获取淘宝客真实商品推广数据（含品类过滤）...")
        promo_df = ad_data_crawler.fetch_promotion_data(keywords, top_n=top_n, exclude_keywords=exclude_keywords)
        order_df = ad_data_crawler.fetch_order_data(days=order_days)

        logger.info("[步骤2/4] RAG 检索历史投放策略...")
        historical = self._search_historical()

        logger.info("[步骤3/4] 生成推广优化方案（DeepSeek）...")
        strategy = self._generate_optimization_strategy(promo_df, order_df, historical)

        logger.info("[步骤4/4] 自反馈闭环回流...")
        summary = data_processor.summarize_promotion(promo_df)
        feedback_result = mobius_loop.feedback_ad_strategy(
            strategy_name=f"推广优化_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}",
            strategy_content=strategy,
            roi_data={
                "total_products": summary["total"],
                "avg_commission": summary["avg_commission"],
                "total_estimated_commission": summary["total_estimated_commission"],
                "orders_count": len(order_df),
            },
            metadata={"data_source": "taobao"},
        )

        logger.info("========== 推广/投放优化分析完成 ==========")
        return {
            "promotion_data": promo_df,
            "order_data": order_df,
            "historical_strategies": historical,
            "optimization_strategy": strategy,
            "promotion_summary": summary,
            "feedback_success": feedback_result,
            "data_source": "taobao",
        }

    def _search_historical(self) -> str:
        search_results = vector_store.search(
            collection_name="ad_strategies",
            query="广告优化 ROI提升 投放策略 关键词优化 佣金",
            n_results=5,
        )
        if not search_results["documents"][0]:
            return "（暂无历史策略数据，本次为首次优化）"
        return "".join(f"\n--- 历史策略 {i + 1} ---\n{doc}\n" for i, doc in enumerate(search_results["documents"][0]))

    def _generate_optimization_strategy(self, promo_df: pd.DataFrame, order_df: pd.DataFrame, historical: str) -> str:
        summary = data_processor.summarize_promotion(promo_df)
        top_kw_text = "；".join(f"{k['keyword']}（潜力分 {k['score']}）" for k in summary["top_keywords"]) or "暂无"
        top_products = ""
        if not promo_df.empty:
            cols = ["keyword", "product_name", "price", "sales_30d", "commission_rate", "promotion_score"]
            cols = [c for c in cols if c in promo_df.columns]
            top_products = promo_df.nlargest(5, "promotion_score")[cols].to_string(index=False)

        prompt = f"""请你作为资深电商推广专家，基于以下淘宝客真实推广数据生成一份专业的推广优化方案。

【数据来源】淘宝客物料搜索真实数据（佣金率 × 月销 = 推广潜力分）

【推广数据概览】
- 推广商品总数：{summary['total']} 款，关键词数：{summary['keywords']}
- 平均佣金率：{summary['avg_commission']}%
- 累计预估佣金：¥{summary['total_estimated_commission']}
- 订单结算数据：{len(order_df)} 条（未开启/无数据时请说明以预估为主）

【高潜力关键词（佣金率×月销）】
{top_kw_text}

【Top5 推广商品（推广潜力分排序）】
{top_products}

【历史优化策略（RAG 检索结果）】
{historical}

请按照以下结构生成优化方案：
## 一、投放现状诊断
## 二、关键词优化策略（高潜力如何放大 / 低潜力如何处理 / 新词挖掘）
## 三、预算分配优化（向高潜力关键词/商品倾斜）
## 四、推广策略迭代（结合历史策略的本次迭代方向）
## 五、预期效果（预估佣金提升幅度与指标，说明以联盟结算为准）

请用中文回答，内容要专业、具体、可执行，每个建议都要有数据支撑。"""

        system_prompt = "你是一位拥有8年电商推广经验的专家，精通淘宝联盟/淘宝客选品推广、佣金优化与关键词策略，能够给出数据驱动的可执行推广方案。"

        return self.call_llm(prompt, system_prompt)


ad_optimization_agent = AdOptimizationAgent()
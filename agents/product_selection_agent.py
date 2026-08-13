"""选品 Agent：真实淘宝客数据 + 历史爆款经验（RAG 可选）→ 选品分析报告 → 闭环回流"""
from typing import List, Optional

import pandas as pd

from agents.base_agent import BaseAgent
from crawlers.competitor_crawler import competitor_crawler
from retrieval.vector_store import vector_store
from retrieval.mobius_loop import mobius_loop
from utils.data_processor import data_processor
from utils.logger import logger


class ProductSelectionAgent(BaseAgent):
    """选品 Agent：基于淘宝客真实商品数据生成选品分析报告"""

    def __init__(self):
        super().__init__("选品Agent")

    def analyze_category(
        self,
        category: str,
        count: int = 20,
        cat: Optional[str] = None,
        include_keywords: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
    ) -> dict:
        """选品分析。

        - cat: 淘宝商品类目ID（如鼠标类目），提升按品类抓取精确性
        - include_keywords: 标题白名单（默认 [category]）
        - exclude_keywords: 标题黑名单（如 ["鼠标垫", "电脑", "笔记本"]）
        """
        logger.info(f"========== 开始选品分析: {category} ==========")

        logger.info("[步骤1/4] 获取淘宝客真实商品数据（含品类过滤）...")
        raw_df = competitor_crawler.crawl_competitor_products(
            category, count=count, cat=cat,
            include_keywords=include_keywords, exclude_keywords=exclude_keywords,
        )
        df = data_processor.clean_product_data(raw_df)
        df = data_processor.calculate_hot_score(df)

        logger.info("[步骤2/4] RAG 检索历史爆款经验...")
        historical_insights = self._search_historical(category)

        logger.info("[步骤3/4] 生成选品分析报告（DeepSeek）...")
        report = self._generate_selection_report(category, df, historical_insights)

        logger.info("[步骤4/4] 自反馈闭环回流...")
        feedback_result = mobius_loop.feedback_product_insight(
            product_name=category,
            report_content=report,
            metadata={"category": category, "data_source": "taobao"},
        )

        logger.info(f"========== 选品分析完成: {category} ==========")
        return {
            "category": category,
            "competitor_data": df,
            "historical_insights": historical_insights,
            "report": report,
            "feedback_success": feedback_result,
            "data_source": "taobao",
            "cat": cat,
            "include_keywords": include_keywords,
            "exclude_keywords": exclude_keywords,
        }

    def _search_historical(self, category: str) -> str:
        search_results = vector_store.search(
            collection_name="hot_products",
            query=f"{category} 爆款 选品 特征 经验",
            n_results=5,
        )
        if not search_results["documents"][0]:
            return "（暂无历史爆款数据，本次为首次分析）"
        return "".join(f"\n--- 历史经验 {i + 1} ---\n{doc}\n" for i, doc in enumerate(search_results["documents"][0]))

    def _generate_selection_report(self, category: str, df: pd.DataFrame, historical_insights: str) -> str:
        stats = data_processor.summarize_products(df)
        top_products = data_processor.format_top_products(df, top_n=5)

        prompt = f"""请你作为资深电商选品专家，基于以下淘宝客真实商品数据生成一份专业的选品分析报告。

【分析品类】{category}
【数据来源】淘宝客物料搜索升级版（taobao.tbk.dg.material.optional.upgrade）真实数据

【商品数据摘要】
- 竞品总数：{stats['total']} 款
- 均价：¥{stats['avg_price']}，平均月销：{stats['avg_sales']} 件
- 平均佣金率：{stats['avg_commission']}%，优惠券总额：¥{stats['total_coupon']}
- 爆款数量：{stats['hot_count']} 款（hot_score ≥ 60，权重：月销40%+佣金率30%+优惠15%+评分15%）

【Top5 爆款商品（hot_score 排序）】
{top_products}

【历史爆款经验（RAG 检索结果）】
{historical_insights}

请按照以下结构生成报告：
## 一、品类概述
## 二、竞品数据分析（价格带 / 销量分布 / 佣金与优惠 / 爆款共性）
## 三、选品机会识别（3-5 个机会点）
## 四、风险评估
## 五、选品建议（推荐价格带 / 差异化方向 / 佣金策略 / 入市节奏）

请用中文回答，内容要专业、具体、有数据支撑。"""

        system_prompt = "你是一位拥有10年国内电商选品经验的专家，精通淘宝联盟/淘宝客推广逻辑、竞品研究与数据驱动选品，能够给出专业、可执行的选品建议。"

        return self.call_llm(prompt, system_prompt)

    def batch_analyze(self, categories: list) -> list:
        results = []
        for cat in categories:
            try:
                results.append(self.analyze_category(cat))
            except Exception as e:
                logger.error(f"分析品类 {cat} 时出错: {e}")
                results.append({"category": cat, "error": str(e)})
        return results


product_selection_agent = ProductSelectionAgent()
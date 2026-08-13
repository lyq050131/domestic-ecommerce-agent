"""自反馈闭环：质量门控 → 去重 → 向量回流 → 容量控制"""
from typing import Any, Dict
from datetime import datetime
import uuid

from config.settings import settings
from retrieval.vector_store import vector_store
from retrieval.quality_gate import quality_gate
from utils.logger import logger


class MobiusLoop:
    """自反馈闭环：质量门控 → 去重 → 向量回流 → 容量控制

    未启用向量库时自动退化为"只统计不回流"，业务流程不受影响。
    """

    def __init__(self):
        self.loop_count = 0
        logger.info("✅ 自反馈闭环系统初始化完成")

    def _is_duplicate(self, collection_name: str, text: str, threshold: float = 0.12) -> bool:
        """相似度去重：与库中已有文档距离过近则视为重复，不再入库。"""
        try:
            results = vector_store.search(collection_name, text, n_results=1)
            documents = results["documents"][0]
            distances = results.get("distances", [[1.0]])[0]
            if documents and distances and distances[0] < threshold:
                logger.info(f"[自反馈闭环] 检测到重复内容（距离 {distances[0]:.4f}），跳过回流")
                return True
        except Exception as e:
            logger.warning(f"[自反馈闭环] 去重检查失败，继续流程: {e}")
        return False

    def _enforce_capacity(self, collection_name: str) -> None:
        """容量上限：超过 MAX_DOCS_PER_COLLECTION 时删除最旧的文档。"""
        try:
            count = vector_store.count_documents(collection_name)
            max_docs = settings.MAX_DOCS_PER_COLLECTION
            if count <= max_docs:
                return
            overflow = count - max_docs
            collection = vector_store.get_collection(collection_name)
            if collection is None:
                return
            data = collection.get(limit=overflow)
            ids = data.get("ids") or []
            if ids:
                collection.delete(ids=ids)
                logger.info(f"[自反馈闭环] 集合 [{collection_name}] 超过上限，清理最旧 {len(ids)} 条")
        except Exception as e:
            logger.warning(f"[自反馈闭环] 容量清理失败: {e}")

    def _build_doc(self, doc_id: str, content: str, meta: Dict) -> bool:
        """统一入库入口：去重 → 写入 → 容量控制，返回是否入库成功"""
        collection = meta["collection"]
        if self._is_duplicate(collection, content):
            return False
        vector_store.add_documents(
            collection_name=collection,
            documents=[content],
            metadatas=[meta],
            ids=[doc_id],
        )
        self._enforce_capacity(collection)
        self.loop_count += 1
        return True

    def feedback_product_insight(self, product_name: str, report_content: str, metadata: Dict[str, Any] = None) -> bool:
        """选品结果回流"""
        logger.info(f"[自反馈闭环] 开始回流选品洞察: {product_name}")
        passed, score, _ = quality_gate.evaluate_product_report(report_content)
        if not passed:
            logger.warning(f"[自反馈闭环] 质量未通过门槛 ({score:.2f} < {quality_gate.threshold})，不回流")
            return False

        doc_id = f"product_{uuid.uuid4().hex[:8]}"
        document = f"""【商品名称】{product_name}
【选品分析报告】
{report_content}
【质量评分】{score:.2f}
【回流时间】{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

        meta = {
            "collection": "hot_products",
            "type": "product_selection",
            "product_name": product_name,
            "quality_score": score,
            "created_at": datetime.now().isoformat(),
            "loop_iteration": self.loop_count,
        }
        if metadata:
            meta.update(metadata)

        ok = self._build_doc(doc_id, document, meta)
        if ok:
            logger.info(f"[自反馈闭环] ✅ 选品洞察回流成功！当前闭环迭代次数: {self.loop_count}")
        return ok

    def feedback_ad_strategy(self, strategy_name: str, strategy_content: str, roi_data: Dict = None, metadata: Dict[str, Any] = None) -> bool:
        """投放策略回流"""
        logger.info(f"[自反馈闭环] 开始回流投放策略: {strategy_name}")
        passed, score, _ = quality_gate.evaluate_ad_strategy(strategy_content)
        if not passed:
            logger.warning(f"[自反馈闭环] 投放策略质量未通过，不回流")
            return False

        doc_id = f"ad_{uuid.uuid4().hex[:8]}"
        document = f"""【策略名称】{strategy_name}
【投放优化方案】
{strategy_content}
【ROI数据】{roi_data if roi_data else '暂无'}
【质量评分】{score:.2f}
【回流时间】{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

        meta = {
            "collection": "ad_strategies",
            "type": "ad_optimization",
            "strategy_name": strategy_name,
            "quality_score": score,
            "created_at": datetime.now().isoformat(),
            "loop_iteration": self.loop_count,
        }
        if metadata:
            meta.update(metadata)

        ok = self._build_doc(doc_id, document, meta)
        if ok:
            logger.info(f"[自反馈闭环] ✅ 投放策略回流成功！当前闭环迭代次数: {self.loop_count}")
        return ok

    def feedback_customer_reply(self, question_type: str, reply_content: str, language: str = "zh", metadata: Dict[str, Any] = None) -> bool:
        """客服回复回流（按回复语言走对应质量门控）"""
        logger.info(f"[自反馈闭环] 开始回流客服回复模板: {question_type}")
        passed, score, _ = quality_gate.evaluate_customer_reply(reply_content, language=language)
        if not passed:
            logger.warning(f"[自反馈闭环] 客服回复质量未通过，不回流")
            return False

        doc_id = f"faq_{uuid.uuid4().hex[:8]}"
        document = f"""【问题类型】{question_type}
【语言】{language}
【回复模板】
{reply_content}
【质量评分】{score:.2f}
【回流时间】{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

        meta = {
            "collection": "faqs",
            "type": "customer_service",
            "question_type": question_type,
            "language": language,
            "quality_score": score,
            "created_at": datetime.now().isoformat(),
            "loop_iteration": self.loop_count,
        }
        if metadata:
            meta.update(metadata)

        ok = self._build_doc(doc_id, document, meta)
        if ok:
            logger.info(f"[自反馈闭环] ✅ 客服回复回流成功！当前闭环迭代次数: {self.loop_count}")
        return ok

    def get_loop_stats(self) -> Dict:
        return {
            "total_loops": self.loop_count,
            "hot_products_count": vector_store.count_documents("hot_products"),
            "ad_strategies_count": vector_store.count_documents("ad_strategies"),
            "faqs_count": vector_store.count_documents("faqs"),
        }


mobius_loop = MobiusLoop()
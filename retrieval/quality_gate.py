"""质量门控：多维度启发式评分，低于阈值的结果不回流知识库（语言感知）"""
from typing import Dict, Tuple

from config.settings import settings
from utils.logger import logger

# 多语言关键词表
LANG_KEYWORDS = {
    "zh": {
        "polite": ["您好", "抱歉", "感谢", "理解", "请"],
        "solution": ["解决", "方案", "处理", "补偿", "退货", "退款"],
    },
    "en": {
        "polite": ["sorry", "thank", "appreciate", "understand", "please"],
        "solution": ["solution", "resolve", "refund", "replacement", "return", "compensation"],
    },
    "es": {
        "polite": ["lo siento", "gracias", "entend", "por favor"],
        "solution": ["solución", "reembolso", "reemplazo", "devolución", "compensación"],
    },
    "fr": {
        "polite": ["désolé", "merci", "compren", "s'il vous plaît"],
        "solution": ["solution", "remboursement", "remplacement", "retour", "compensation"],
    },
    "de": {
        "polite": ["entschuldig", "danke", "versteh", "bitte"],
        "solution": ["lösung", "erstattung", "ersatz", "rückgabe", "entschädigung"],
    },
    "ja": {
        "polite": ["申し訳", "ありがとう", "ご理解", "お願い"],
        "solution": ["解決", "返金", "交換", "返品", "補償"],
    },
    "ko": {
        "polite": ["죄송", "감사", "이해", "부탁"],
        "solution": ["해결", "환불", "교환", "반품", "보상"],
    },
    "pt": {
        "polite": ["desculpe", "obrigado", "entend", "por favor"],
        "solution": ["solução", "reembolso", "troca", "devolução", "compensação"],
    },
    "ru": {
        "polite": ["извините", "спасибо", "понимаю", "пожалуйста"],
        "solution": ["решение", "возврат", "замена", "компенсация"],
    },
    "ar": {
        "polite": ["آسف", "شكرا", "أفهم", "من فضلك"],
        "solution": ["حل", "استرداد", "استبدال", "إرجاع", "تعويض"],
    },
}
DEFAULT_LANG = "en"


class QualityGate:
    """质量门控：多维度启发式评分，低于阈值的结果不回流知识库"""

    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold

    def evaluate_product_report(self, report: str) -> Tuple[bool, float, Dict]:
        """选品报告质量：数据完整性 / 分析深度 / 结构 / 长度"""
        scores = {}

        data_keywords = ["价格", "销量", "评分", "评论", "竞品", "趋势", "佣金"]
        scores["data_completeness"] = sum(1 for kw in data_keywords if kw in report) / len(data_keywords)

        analysis_keywords = ["对比", "分析", "建议", "优势", "劣势", "机会", "风险"]
        scores["analysis_depth"] = sum(1 for kw in analysis_keywords if kw in report) / len(analysis_keywords)

        structure_keywords = ["概述", "数据", "结论", "建议"]
        scores["structure"] = sum(1 for kw in structure_keywords if kw in report) / len(structure_keywords)

        report_length = len(report)
        if 500 <= report_length <= 5000:
            scores["length"] = 1.0
        elif 200 <= report_length < 500:
            scores["length"] = 0.6
        else:
            scores["length"] = 0.3

        weights = {"data_completeness": 0.35, "analysis_depth": 0.35, "structure": 0.15, "length": 0.15}
        total_score = sum(scores[k] * weights[k] for k in scores)
        passed = total_score >= self.threshold

        logger.info(f"选品报告质量评估 - 总分: {total_score:.2f}, 是否通过: {passed}")
        logger.info(f"详细评分: {scores}")
        return passed, total_score, scores

    def evaluate_ad_strategy(self, strategy: str) -> Tuple[bool, float, Dict]:
        """投放策略质量：ROI 关注度 / 可执行性 / 数据支撑"""
        scores = {}

        roi_keywords = ["ROI", "投产比", "转化率", "点击率", "CPC", "CPA", "佣金"]
        scores["roi_focus"] = sum(1 for kw in roi_keywords if kw in strategy) / len(roi_keywords)

        action_keywords = ["调整", "优化", "增加", "减少", "暂停", "测试"]
        scores["actionability"] = sum(1 for kw in action_keywords if kw in strategy) / len(action_keywords)

        data_keywords = ["数据", "对比", "提升", "下降", "趋势"]
        scores["data_support"] = sum(1 for kw in data_keywords if kw in strategy) / len(data_keywords)

        weights = {"roi_focus": 0.4, "actionability": 0.35, "data_support": 0.25}
        total_score = sum(scores[k] * weights[k] for k in scores)
        passed = total_score >= self.threshold

        logger.info(f"投放策略质量评估 - 总分: {total_score:.2f}, 通过: {passed}")
        return passed, total_score, scores

    def evaluate_customer_reply(self, reply: str, language: str = "zh") -> Tuple[bool, float, Dict]:
        """客服回复质量：礼貌性 / 解决性 / 长度（按语言匹配关键词）"""
        kw = LANG_KEYWORDS.get(language, LANG_KEYWORDS[DEFAULT_LANG])
        reply_lower = reply.lower()
        scores = {}

        polite_count = sum(1 for k in kw["polite"] if k in reply_lower)
        scores["politeness"] = min(polite_count / 3, 1.0)

        solution_count = sum(1 for k in kw["solution"] if k in reply_lower)
        scores["solution"] = min(solution_count / 2, 1.0)

        reply_len = len(reply)
        scores["length"] = 1.0 if 50 <= reply_len <= 500 else 0.5

        weights = {"politeness": 0.3, "solution": 0.5, "length": 0.2}
        total_score = sum(scores[k] * weights[k] for k in scores)
        passed = total_score >= self.threshold

        logger.info(f"客服回复质量评估（语言: {language}）- 总分: {total_score:.2f}, 通过: {passed}")
        return passed, total_score, scores


quality_gate = QualityGate(threshold=settings.QUALITY_THRESHOLD)
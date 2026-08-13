"""多语言客服 Agent：预置模板 + DeepSeek 个性化回复（真实店铺运营模式）

工作方式：
1. 先用预置 FAQ 模板命中（比价/物流/尺码/破损/退换等），锁定业务口径；
2. 由 DeepSeek 结合评论/私信细节在模板基础上做个性化回复；
3. 优质回复经质量门控回流知识库（可选，RAG 未启用时自动跳过）。
"""
import json
import os
from pathlib import Path
from typing import List, Optional

from agents.base_agent import BaseAgent
from config.settings import settings
from retrieval.vector_store import vector_store
from retrieval.mobius_loop import mobius_loop
from utils.translator import translator
from utils.logger import logger

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CustomerServiceAgent(BaseAgent):
    """多语言客服 Agent（模板锁定口径 + DeepSeek 个性化）"""

    def __init__(self):
        super().__init__("多语言客服Agent")
        self.templates = self._load_templates()

    # ---------- 模板加载 ----------
    def _load_templates(self) -> List[dict]:
        path = settings.REPLY_TEMPLATES_PATH
        if not os.path.isabs(path):
            path = str(PROJECT_ROOT / path)
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            templates = data.get("templates", [])
            logger.info(f"✅ 客服模板加载完成: {len(templates)} 条")
            return templates
        except Exception as e:
            logger.warning(f"客服模板加载失败（将仅依赖 LLM）: {e}")
            return []

    def _match_template(self, text: str, rating: Optional[int] = None) -> Optional[dict]:
        """关键词匹配模板；低分优先差评模板，高分优先好评模板"""
        if rating is not None and rating <= 2:
            for t in self.templates:
                if t.get("id") == "bad_review":
                    return t
        if rating is not None and rating >= 4:
            for t in self.templates:
                if t.get("id") == "praise":
                    return t
        text_lower = text.lower()
        best, best_hits = None, 0
        for t in self.templates:
            hits = sum(1 for kw in t.get("keywords", []) if kw.lower() in text_lower)
            if hits > best_hits:
                best, best_hits = t, hits
        return best if best_hits > 0 else None

    def _template_reply(self, template: dict, language: str) -> str:
        """按语言取模板回复；模板缺该语言时先取中文再翻译"""
        for key in ("reply_" + language, "reply_zh", "reply_en"):
            if template.get(key):
                return template[key]
        if template.get("reply_zh"):
            return translator.translate(template["reply_zh"], target_lang=language)
        return ""

    # ---------- 评论处理 ----------
    def handle_review(self, review_content: str, rating: int, language: str = "auto") -> dict:
        logger.info(f"========== 开始处理用户评论（评分: {rating}星） ==========")
        detected_lang = translator.detect_language(review_content) if language == "auto" else language
        logger.info(f"[步骤1/5] 检测到语言: {detected_lang}")

        template = self._match_template(review_content, rating)
        logger.info(f"[步骤2/5] 模板命中: {template.get('scenario') if template else '无（走 LLM 生成）'}")

        logger.info("[步骤3/5] RAG 检索 FAQ 参考...")
        similar_faqs = self._search_faqs(review_content)

        logger.info("[步骤4/5] 生成客服回复（DeepSeek）...")
        template_reply = self._template_reply(template, detected_lang) if template else ""
        reply = self._generate_reply(review_content, rating, detected_lang, similar_faqs, template_reply)

        logger.info("[步骤5/5] 质量门控 + 自反馈闭环回流...")
        q_type = "差评回复" if rating <= 2 else ("中评回复" if rating == 3 else "好评回复")
        feedback_result = mobius_loop.feedback_customer_reply(
            question_type=q_type, reply_content=reply, language=detected_lang,
        )

        logger.info("========== 评论处理完成 ==========")
        return {
            "original_review": review_content,
            "rating": rating,
            "detected_language": detected_lang,
            "matched_template": template.get("scenario") if template else None,
            "similar_faqs": similar_faqs,
            "reply": reply,
            "feedback_success": feedback_result,
        }

    # ---------- 私信处理 ----------
    def handle_message(self, message: str, language: str = "auto") -> dict:
        logger.info("========== 开始处理用户私信 ==========")
        detected_lang = translator.detect_language(message) if language == "auto" else language

        template = self._match_template(message)
        similar_faqs = self._search_faqs(message)
        template_reply = self._template_reply(template, detected_lang) if template else ""
        reply = self._generate_message_reply(message, detected_lang, similar_faqs, template_reply)

        feedback_result = mobius_loop.feedback_customer_reply(
            question_type="私信咨询", reply_content=reply, language=detected_lang,
        )

        return {
            "original_message": message,
            "detected_language": detected_lang,
            "matched_template": template.get("scenario") if template else None,
            "reply": reply,
            "feedback_success": feedback_result,
        }

    def _search_faqs(self, text: str) -> str:
        search_results = vector_store.search(collection_name="faqs", query=text, n_results=3)
        if not search_results["documents"][0]:
            return "（暂无相关FAQ模板）"
        return "".join(f"\n--- 相似FAQ {i + 1} ---\n{doc}\n" for i, doc in enumerate(search_results["documents"][0]))

    # ---------- LLM 生成（模板作为业务口径基准） ----------
    def _generate_reply(self, review: str, rating: int, language: str, similar_faqs: str, template_reply: str) -> str:
        lang_name = translator.supported_languages.get(language, "英语")
        if rating <= 2:
            review_type, tone = "差评", "诚恳道歉，积极解决问题"
        elif rating == 3:
            review_type, tone = "中评", "感谢反馈，了解改进方向"
        else:
            review_type, tone = "好评", "感谢支持，邀请复购"

        if template_reply:
            prompt = f"""你是专业电商客服。请基于以下【模板回复】为用户{review_type}生成最终回复：
- 保持模板的核心承诺与合规表述不变，结合评论细节做个性化润色
- 使用{lang_name}回复，语气{tone}，50-200字
- 直接输出回复内容，不要任何前缀

【用户评论】{review}
【评分】{rating}星
【模板回复】{template_reply}"""
            system_prompt = "你是一位经验丰富的电商客服主管，擅长在合规模板基础上做个性化回复。"
            return self.call_llm(prompt, system_prompt, temperature=0.6)

        prompt = f"""请你作为专业电商客服，为以下用户{review_type}生成回复。

【用户评论】{review}
【评论评分】{rating} 星
【回复语言】{lang_name}
【回复语气】{tone}

【相似FAQ和历史回复（RAG 检索结果）】
{similar_faqs}

要求：
1. 用{lang_name}回复
2. 语气真诚、专业
3. 长度控制在50-200字
4. {review_type}要表达歉意（如适用）并提出解决方案
5. 不要使用模板化的套话，要自然
6. 可以参考相似FAQ中的回复风格，但不要直接复制

请直接输出回复内容，不要加任何前缀或解释。"""

        system_prompt = "你是一位经验丰富的多语言电商客服主管，精通客户沟通，能够用恰当的语气回复客户并维护品牌形象。"
        return self.call_llm(prompt, system_prompt)

    def _generate_message_reply(self, message: str, language: str, similar_faqs: str, template_reply: str) -> str:
        lang_name = translator.supported_languages.get(language, "英语")

        if template_reply:
            prompt = f"""你是专业电商客服。请基于以下【模板回复】回答用户私信：
- 保持模板核心承诺不变，结合私信细节做个性化润色
- 使用{lang_name}回复，50-300字
- 直接输出回复内容，不要任何前缀

【用户私信】{message}
【模板回复】{template_reply}"""
            system_prompt = "你是一位专业的电商客服，擅长在合规模板基础上做个性化回答。"
            return self.call_llm(prompt, system_prompt, temperature=0.6)

        prompt = f"""请你作为专业电商客服，回复以下用户私信。

【用户私信】{message}
【回复语言】{lang_name}
【相似FAQ（RAG 检索结果）】{similar_faqs}

要求：
1. 用{lang_name}回复
2. 语气友好、专业、有帮助
3. 直接回答用户问题
4. 长度控制在50-300字
5. 常见问题参考FAQ中的回答

请直接输出回复内容，不要加任何前缀或解释。"""

        system_prompt = "你是一位专业的电商客服，精通多语言沟通，能够快速准确地回答客户问题。"
        return self.call_llm(prompt, system_prompt)

    def batch_handle_reviews(self, reviews: list) -> list:
        results = []
        for review in reviews:
            try:
                results.append(self.handle_review(
                    review_content=review["content"],
                    rating=review["rating"],
                    language=review.get("language", "auto"),
                ))
            except Exception as e:
                logger.error(f"处理评论出错: {e}")
                results.append({"error": str(e), "review": review})
        return results


customer_service_agent = CustomerServiceAgent()
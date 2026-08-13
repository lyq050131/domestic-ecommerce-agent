"""Agent 基类：统一封装 DeepSeek LLM 调用（OpenAI 兼容协议）

真实店铺运营模式：DeepSeek Key 为必填。配置校验由入口（settings.validate）
统一提示；此处未配置时在调用阶段抛出明确错误，避免误导性输出。
"""
from openai import OpenAI

from config.settings import settings
from utils.logger import logger


class BaseAgent:
    """Agent 基类：统一封装 LLM 调用（OpenAI 兼容协议，DeepSeek）"""

    def __init__(self, name: str) -> None:
        self.name = name
        if settings.llm_configured:
            self.client = OpenAI(
                api_key=settings.LLM_API_KEY,
                base_url=settings.LLM_BASE_URL,
                timeout=settings.LLM_TIMEOUT,
            )
            llm_status = f"已配置 {settings.LLM_MODEL}"
        else:
            self.client = None
            llm_status = "未配置（入口启动校验会提示）"
        logger.info(f"[{name}] Agent 初始化完成（LLM: {llm_status}）")

    def call_llm(
        self,
        prompt: str,
        system_prompt: str = "你是一个专业的电商运营专家。",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """调用 DeepSeek 大模型；未配置或失败时抛出明确错误。"""
        if self.client is None:
            raise RuntimeError(f"[{self.name}] 未配置 DeepSeek API Key（LLM_API_KEY），请检查 .env")
        try:
            response = self.client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            result = (response.choices[0].message.content or "").strip()
            logger.debug(f"[{self.name}] LLM 调用成功，输出长度: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"[{self.name}] LLM 调用失败: {e}")
            raise
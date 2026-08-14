"""全局配置：所有 Key 一律从 .env 读取，代码中不写死任何密钥

v3.1（真实店铺运营版）：不再提供模拟数据模式，
淘宝客三要素与 DeepSeek Key 为硬性要求，缺失时启动即报错。
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """全局配置类"""

    # ===== LLM 配置（DeepSeek，OpenAI 兼容协议，必填） =====
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))

    # ===== 淘宝开放平台（淘宝客/淘宝联盟）配置，三要素必填 =====
    TAOBAO_APP_KEY: str = os.getenv("TAOBAO_APP_KEY", "")
    TAOBAO_APP_SECRET: str = os.getenv("TAOBAO_APP_SECRET", "")
    # 推广位 ID：取阿里妈妈 PID（mm_站点_广告位_推广）的最后一段数字
    TAOBAO_ADZONE_ID: str = os.getenv("TAOBAO_ADZONE_ID", "")
    TAOBAO_GATEWAY: str = os.getenv("TAOBAO_GATEWAY", "https://eco.taobao.com/router/rest")
    # 签名方式：md5 / hmac（HMAC-MD5）/ hmac-sha256（HMAC-SHA256）
    TAOBAO_SIGN_METHOD: str = os.getenv("TAOBAO_SIGN_METHOD", "md5")
    TAOBAO_PAGE_SIZE: int = int(os.getenv("TAOBAO_PAGE_SIZE", "20"))
    # 订单明细接口（taobao.tbk.order.details.get）：需联盟佣金结算资格（付费）+ 商家 OAuth，默认关闭
    TAOBAO_ORDER_ENABLED: bool = os.getenv("TAOBAO_ORDER_ENABLED", "false").lower() == "true"
    TAOBAO_ACCESS_TOKEN: str = os.getenv("TAOBAO_ACCESS_TOKEN", "")

    # ===== Embedding 配置（本地免费，可选） =====
    EMBEDDING_ENABLED: bool = os.getenv("EMBEDDING_ENABLED", "true").lower() == "true"
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    EMBEDDING_DEVICE: str = os.getenv("EMBEDDING_DEVICE", "cpu")

    # ===== 向量数据库（可选，未安装依赖时自动降级为无 RAG） =====
    VECTOR_DB_PATH: str = os.getenv("VECTOR_DB_PATH", "./data/vector_db")
    VECTOR_COLLECTION_HOT_PRODUCTS: str = os.getenv("VECTOR_COLLECTION_HOT_PRODUCTS", "hot_products")
    VECTOR_COLLECTION_AD_STRATEGIES: str = os.getenv("VECTOR_COLLECTION_AD_STRATEGIES", "ad_strategies")
    VECTOR_COLLECTION_FAQ: str = os.getenv("VECTOR_COLLECTION_FAQ", "faqs")

    # ===== 爬取与重试 =====
    CRAWLER_DELAY: int = int(os.getenv("CRAWLER_DELAY", "1"))
    CRAWLER_MAX_RETRIES: int = int(os.getenv("CRAWLER_MAX_RETRIES", "3"))

    # ===== 自反馈闭环 =====
    QUALITY_THRESHOLD: float = float(os.getenv("QUALITY_THRESHOLD", "0.75"))
    AUTO_FEEDBACK: bool = os.getenv("AUTO_FEEDBACK", "true").lower() == "true"
    MAX_DOCS_PER_COLLECTION: int = int(os.getenv("MAX_DOCS_PER_COLLECTION", "200"))

    # ===== 客服模板 =====
    REPLY_TEMPLATES_PATH: str = os.getenv("REPLY_TEMPLATES_PATH", "./data/templates/reply_templates.json")

    # ===== 报告落库与每日定时任务 =====
    REPORT_DB_PATH: str = os.getenv("REPORT_DB_PATH", "./data/reports.db")
    AUTO_REPORT_ENABLED: bool = os.getenv("AUTO_REPORT_ENABLED", "true").lower() == "true"
    AUTO_REPORT_TIME: str = os.getenv("AUTO_REPORT_TIME", "09:30")          # 每天自动运行时刻 HH:MM
    AUTO_REPORT_CATEGORY: str = os.getenv("AUTO_REPORT_CATEGORY", "无线蓝牙耳机")
    AUTO_REPORT_COUNT: int = int(os.getenv("AUTO_REPORT_COUNT", "20"))
    AUTO_REPORT_AD_TOP_N: int = int(os.getenv("AUTO_REPORT_AD_TOP_N", "15"))

    # ===== 钉钉机器人日报推送（可选：配置 DINGTALK_WEBHOOK_URL 后每日报告自动推送到钉钉群） =====
    DINGTALK_ENABLED: bool = os.getenv("DINGTALK_ENABLED", "true").lower() == "true"
    DINGTALK_WEBHOOK_URL: str = os.getenv("DINGTALK_WEBHOOK_URL", "")      # 钉钉自定义机器人 Webhook 地址
    DINGTALK_SECRET: str = os.getenv("DINGTALK_SECRET", "")                 # 机器人加签密钥（未启用加签可留空）
    DINGTALK_KEYWORD: str = os.getenv("DINGTALK_KEYWORD", "运营")           # 机器人「自定义关键词」安全设置的关键词，推送会自动带上

    # ===== Web 后台访问令牌（可选） =====
    # 留空=本机直连不鉴权；配置后 Web 后台需登录，API 需带 Authorization: Bearer <令牌>
    WEB_ACCESS_TOKEN: str = os.getenv("WEB_ACCESS_TOKEN", "")
    VERSION: str = "3.1.0"

    @property
    def taobao_configured(self) -> bool:
        """是否已配置完整的淘宝客三要素"""
        return bool(self.TAOBAO_APP_KEY and self.TAOBAO_APP_SECRET and self.TAOBAO_ADZONE_ID)

    @property
    def llm_configured(self) -> bool:
        return bool(self.LLM_API_KEY)

    def validate(self) -> None:
        """启动前校验：真实店铺运营模式，淘宝三要素与 DeepSeek Key 必填"""
        missing = []
        if not self.taobao_configured:
            missing.append("淘宝客三要素（TAOBAO_APP_KEY / TAOBAO_APP_SECRET / TAOBAO_ADZONE_ID）")
        if not self.llm_configured:
            missing.append("DeepSeek API Key（LLM_API_KEY）")
        if missing:
            raise RuntimeError(
                "真实店铺运营模式缺少必要配置：" + "、".join(missing)
                + "。请参考 .env.example 填写 .env 后重试。"
                + "（淘宝三要素获取：淘宝开放平台 AppKey/AppSecret + 阿里妈妈推广位 PID 末段）"
            )


settings = Settings()
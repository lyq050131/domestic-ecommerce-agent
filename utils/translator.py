"""多语言翻译与检测工具（依赖缺失时自动降级为原文返回）"""
try:
    from deep_translator import GoogleTranslator
    from langdetect import detect as _detect
    from langdetect import DetectorFactory

    DetectorFactory.seed = 0  # 固定随机种子，保证检测结果可复现
    TRANSLATE_AVAILABLE = True
except Exception:  # pragma: no cover
    GoogleTranslator = None
    _detect = None
    TRANSLATE_AVAILABLE = False

from utils.logger import logger

# deep-translator 需要的目标语言名称
LANG_MAP = {
    "zh": "chinese (simplified)",
    "zh-cn": "chinese (simplified)",
    "en": "english",
    "es": "spanish",
    "fr": "french",
    "de": "german",
    "ja": "japanese",
    "ko": "korean",
    "pt": "portuguese",
    "ru": "russian",
    "ar": "arabic",
}


class TranslationTool:
    """多语言翻译与检测工具"""

    def __init__(self):
        self.supported_languages = {
            "zh": "中文", "en": "英语", "es": "西班牙语", "fr": "法语",
            "de": "德语", "ja": "日语", "ko": "韩语", "pt": "葡萄牙语",
            "ru": "俄语", "ar": "阿拉伯语",
        }
        logger.info(f"翻译工具初始化完成（可用: {TRANSLATE_AVAILABLE}，支持 {len(self.supported_languages)} 种语言）")

    def translate(self, text: str, target_lang: str = "en", source_lang: str = "auto") -> str:
        """翻译文本，失败或不可用时返回原文"""
        if not TRANSLATE_AVAILABLE:
            return text
        try:
            target = LANG_MAP.get(target_lang.lower(), "english")
            source = LANG_MAP.get(source_lang.lower(), "auto")
            result = GoogleTranslator(source=source, target=target).translate(text)
            return result or text
        except Exception as e:
            logger.error(f"翻译失败: {e}")
            return text

    def detect_language(self, text: str) -> str:
        """检测语言，失败时默认 zh（本项目以中文业务为主）"""
        if not TRANSLATE_AVAILABLE:
            return "zh"
        try:
            code = _detect(text).lower()
            code = "zh" if code.startswith("zh") else code
            return code if code in self.supported_languages else "en"
        except Exception as e:
            logger.error(f"语言检测失败: {e}")
            return "zh"


translator = TranslationTool()
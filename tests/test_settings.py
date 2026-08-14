# -*- coding: utf-8 -*-
from config.settings import settings


def test_defaults_present():
    assert settings.LLM_MODEL
    assert settings.TAOBAO_GATEWAY.startswith("https://")
    assert settings.VERSION


def test_configured_flags_are_booleans():
    assert isinstance(settings.taobao_configured, bool)
    assert isinstance(settings.llm_configured, bool)
    assert settings.TAOBAO_ORDER_ENABLED in (True, False)
    assert settings.DINGTALK_ENABLED in (True, False)

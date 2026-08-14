"""运营设置：读取 + 写入 .env（重启生效）"""
import os

from dotenv import set_key
from fastapi import APIRouter, HTTPException

from api.schemas import SettingsUpdateRequest
from config.settings import settings
from notify.dingtalk import dingtalk
from utils.logger import logger

router = APIRouter(tags=["设置"])

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")


@router.get("/api/v1/settings", summary="运营设置（不含密钥）")
async def get_settings():
    return {"code": 0, "message": "success", "data": {
        "auto_report_enabled": settings.AUTO_REPORT_ENABLED,
        "auto_report_time": settings.AUTO_REPORT_TIME,
        "auto_report_category": settings.AUTO_REPORT_CATEGORY,
        "auto_report_count": settings.AUTO_REPORT_COUNT,
        "auto_report_ad_top_n": settings.AUTO_REPORT_AD_TOP_N,
        "dingtalk_enabled": settings.DINGTALK_ENABLED,
        "dingtalk_configured": dingtalk.configured,
    }}


@router.put("/api/v1/settings", summary="保存运营设置（写入 .env，重启后生效）")
async def update_settings(request: SettingsUpdateRequest):
    mapping = {
        "auto_report_enabled": "AUTO_REPORT_ENABLED",
        "auto_report_time": "AUTO_REPORT_TIME",
        "auto_report_category": "AUTO_REPORT_CATEGORY",
        "auto_report_count": "AUTO_REPORT_COUNT",
        "auto_report_ad_top_n": "AUTO_REPORT_AD_TOP_N",
        "dingtalk_enabled": "DINGTALK_ENABLED",
    }
    updated = []
    data = request.dict(exclude_none=True)
    try:
        for key, env_name in mapping.items():
            if key in data:
                set_key(ENV_PATH, env_name, str(data[key]))
                updated.append(env_name)
        if data.get("dingtalk_webhook") is not None and str(data["dingtalk_webhook"]).strip():
            set_key(ENV_PATH, "DINGTALK_WEBHOOK_URL", str(data["dingtalk_webhook"]).strip())
            updated.append("DINGTALK_WEBHOOK_URL")
        if data.get("dingtalk_secret") is not None and str(data["dingtalk_secret"]).strip():
            set_key(ENV_PATH, "DINGTALK_SECRET", str(data["dingtalk_secret"]).strip())
            updated.append("DINGTALK_SECRET")
    except Exception as e:
        logger.error(f"保存设置失败: {e}")
        raise HTTPException(status_code=500, detail="写入 .env 失败，请查看服务日志")
    return {"code": 0, "message": "success", "data": {
        "saved": True, "updated": updated, "restart_required": True,
        "hint": "设置已写入 .env，重启服务后生效",
    }}

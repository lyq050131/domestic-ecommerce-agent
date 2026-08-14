"""系统状态与健康检查"""
from fastapi import APIRouter

from config.settings import settings
from notify.dingtalk import dingtalk

router = APIRouter(tags=["系统"])


@router.get("/api/v1/system/status", summary="系统状态（不含任何密钥）")
async def system_status():
    return {
        "code": 0, "message": "success",
        "data": {
            "version": settings.VERSION,
            "data_source": "taobao",
            "taobao_configured": settings.taobao_configured,
            "llm_configured": settings.llm_configured,
            "order_api_enabled": settings.TAOBAO_ORDER_ENABLED,
            "auto_report_enabled": settings.AUTO_REPORT_ENABLED,
            "auto_report_time": settings.AUTO_REPORT_TIME,
            "report_db": "data/reports.db",
            "dingtalk_configured": dingtalk.configured,
        },
    }


@router.get("/health", summary="健康检查", include_in_schema=False)
async def health_check():
    return {"status": "healthy", "version": settings.VERSION}

"""历史报告：列表 / 趋势 / 详情"""
from fastapi import APIRouter, HTTPException, Query

from storage.report_store import report_store
from utils.logger import logger

router = APIRouter(tags=["报告"])


@router.get("/api/v1/reports", summary="历史报告列表")
async def list_reports(report_type: str = Query(None, alias="type"), limit: int = 30):
    try:
        return {"code": 0, "message": "success", "data": report_store.list_reports(report_type, limit)}
    except Exception as e:
        logger.error(f"获取历史报告失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@router.get("/api/v1/reports/trend", summary="报告趋势（按日期聚合）")
async def get_report_trend(report_type: str = Query("selection", alias="type"), days: int = 30):
    try:
        return {"code": 0, "message": "success", "data": report_store.trend(report_type, days)}
    except Exception as e:
        logger.error(f"获取报告趋势失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@router.get("/api/v1/reports/{report_id}", summary="报告详情")
async def get_report_detail(report_id: int):
    try:
        report = report_store.get_report(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="报告不存在")
        return {"code": 0, "message": "success", "data": report}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取报告详情失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")

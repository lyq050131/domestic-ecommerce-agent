"""今日运营总览与闭环统计"""
from datetime import datetime

from fastapi import APIRouter, HTTPException

from retrieval.mobius_loop import mobius_loop
from storage.product_store import product_store
from storage.report_store import report_store
from utils.logger import logger

router = APIRouter(tags=["总览"])


@router.get("/api/v1/loop/stats", summary="闭环系统统计")
async def get_loop_stats():
    try:
        return {"code": 0, "message": "success", "data": mobius_loop.get_loop_stats()}
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@router.get("/api/v1/dashboard/summary", summary="今日运营总览")
async def dashboard_summary():
    """总览：今日报告摘要 + 商品库待办 + 近7天趋势 + 闭环统计"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        return {
            "code": 0, "message": "success",
            "data": {
                "today": {
                    "selection": report_store.latest_by_date("selection", today),
                    "ad": report_store.latest_by_date("ad", today),
                },
                "products_stats": product_store.stats(),
                "trend": {
                    "selection": report_store.trend("selection", 7),
                    "ad": report_store.trend("ad", 7),
                },
                "loop_stats": mobius_loop.get_loop_stats(),
            },
        }
    except Exception as e:
        logger.error(f"获取运营总览失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")

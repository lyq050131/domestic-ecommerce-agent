"""推广/投放优化"""
from fastapi import APIRouter, HTTPException

from agents.ad_optimization_agent import ad_optimization_agent
from api.schemas import AdOptimizationRequest
from storage.report_store import report_store
from utils.logger import logger

router = APIRouter(tags=["投放"])


@router.post("/api/v1/ad/optimize", summary="推广/投放优化")
async def optimize_ads(request: AdOptimizationRequest):
    try:
        result = ad_optimization_agent.optimize_campaigns(
            keywords=request.keywords, top_n=request.top_n,
            order_days=request.order_days, exclude_keywords=request.exclude_keywords,
        )
        report_id, summary = report_store.save_ad_report(
            result,
            params={"keywords": request.keywords, "top_n": request.top_n, "order_days": request.order_days},
        )
        return {
            "code": 0, "message": "success",
            "data": {
                "strategy": result["optimization_strategy"],
                "promotion_summary": result["promotion_summary"],
                "feedback_success": result["feedback_success"],
                "data_source": result["data_source"],
                "report_id": report_id,
                "top_products": summary.get("top_products", []),
            },
        }
    except Exception as e:
        logger.error(f"投放优化失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")

"""选品分析"""
from fastapi import APIRouter, HTTPException

from agents.product_selection_agent import product_selection_agent
from api.schemas import ProductSelectionRequest
from storage.report_store import report_store
from utils.logger import logger

router = APIRouter(tags=["选品"])


@router.post("/api/v1/selection/analyze", summary="选品分析")
async def analyze_product_selection(request: ProductSelectionRequest):
    try:
        result = product_selection_agent.analyze_category(
            request.category, count=request.count, cat=request.cat,
            include_keywords=request.include_keywords, exclude_keywords=request.exclude_keywords,
        )
        report_id, summary = report_store.save_selection_report(
            result,
            params={
                "category": request.category,
                "count": request.count,
                "cat": request.cat,
                "include_keywords": request.include_keywords,
                "exclude_keywords": request.exclude_keywords,
            },
        )
        return {
            "code": 0, "message": "success",
            "data": {
                "category": result["category"],
                "report": result["report"],
                "feedback_success": result["feedback_success"],
                "data_source": result["data_source"],
                "competitor_count": len(result["competitor_data"]),
                "report_id": report_id,
                "top_products": summary.get("top_products", []),
                "cat": result.get("cat"),
                "include_keywords": result.get("include_keywords"),
                "exclude_keywords": result.get("exclude_keywords"),
            },
        }
    except Exception as e:
        logger.error(f"选品分析失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")

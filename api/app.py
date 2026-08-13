"""国内电商店铺自动化运营智能体 v3.1 - FastAPI 服务（真实店铺运营版）"""
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from config.settings import settings
from agents.product_selection_agent import product_selection_agent
from agents.ad_optimization_agent import ad_optimization_agent
from agents.customer_service_agent import customer_service_agent
from retrieval.mobius_loop import mobius_loop
from utils.logger import logger

app = FastAPI(
    title="国内电商店铺自动化运营智能体 API",
    description="接入真实淘宝平台（淘宝客 API）+ DeepSeek 大模型的电商运营智能体（v3.1 真实店铺运营版）",
    version="3.1.0",
)


class ProductSelectionRequest(BaseModel):
    category: str
    count: Optional[int] = 20
    cat: Optional[str] = None                 # 淘宝商品类目ID，提升按品类抓取精确性
    include_keywords: Optional[list] = None   # 标题白名单（默认 [category]）
    exclude_keywords: Optional[list] = None   # 标题黑名单（如 ["鼠标垫","电脑","笔记本"]）


class AdOptimizationRequest(BaseModel):
    keywords: Optional[list] = None
    top_n: Optional[int] = 15
    order_days: Optional[int] = 7
    exclude_keywords: Optional[list] = None   # 标题黑名单，剔除跨品类噪声商品


class ReviewRequest(BaseModel):
    content: str
    rating: int
    language: Optional[str] = "auto"


class MessageRequest(BaseModel):
    content: str
    language: Optional[str] = "auto"


@app.post("/api/v1/selection/analyze", summary="选品分析")
async def analyze_product_selection(request: ProductSelectionRequest):
    try:
        result = product_selection_agent.analyze_category(
            request.category, count=request.count, cat=request.cat,
            include_keywords=request.include_keywords, exclude_keywords=request.exclude_keywords,
        )
        return {
            "code": 0, "message": "success",
            "data": {
                "category": result["category"],
                "report": result["report"],
                "feedback_success": result["feedback_success"],
                "data_source": result["data_source"],
                "competitor_count": len(result["competitor_data"]),
                "cat": result.get("cat"),
                "include_keywords": result.get("include_keywords"),
                "exclude_keywords": result.get("exclude_keywords"),
            },
        }
    except Exception as e:
        logger.error(f"选品分析失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/ad/optimize", summary="推广/投放优化")
async def optimize_ads(request: AdOptimizationRequest):
    try:
        result = ad_optimization_agent.optimize_campaigns(
            keywords=request.keywords, top_n=request.top_n,
            order_days=request.order_days, exclude_keywords=request.exclude_keywords,
        )
        return {
            "code": 0, "message": "success",
            "data": {
                "strategy": result["optimization_strategy"],
                "promotion_summary": result["promotion_summary"],
                "feedback_success": result["feedback_success"],
                "data_source": result["data_source"],
            },
        }
    except Exception as e:
        logger.error(f"投放优化失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/cs/review", summary="评论回复")
async def handle_review(request: ReviewRequest):
    try:
        result = customer_service_agent.handle_review(request.content, request.rating, request.language)
        return {
            "code": 0, "message": "success",
            "data": {
                "reply": result["reply"],
                "detected_language": result["detected_language"],
                "matched_template": result.get("matched_template"),
                "feedback_success": result["feedback_success"],
            },
        }
    except Exception as e:
        logger.error(f"评论处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/cs/message", summary="私信回复")
async def handle_message(request: MessageRequest):
    try:
        result = customer_service_agent.handle_message(request.content, request.language)
        return {
            "code": 0, "message": "success",
            "data": {
                "reply": result["reply"],
                "detected_language": result["detected_language"],
                "matched_template": result.get("matched_template"),
                "feedback_success": result["feedback_success"],
            },
        }
    except Exception as e:
        logger.error(f"私信处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/loop/stats", summary="闭环系统统计")
async def get_loop_stats():
    try:
        return {"code": 0, "message": "success", "data": mobius_loop.get_loop_stats()}
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/system/status", summary="系统状态（不含任何密钥）")
async def system_status():
    return {
        "code": 0, "message": "success",
        "data": {
            "version": "3.1.0",
            "data_source": "taobao",
            "taobao_configured": settings.taobao_configured,
            "llm_configured": settings.llm_configured,
            "order_api_enabled": settings.TAOBAO_ORDER_ENABLED,
        },
    }


@app.get("/health", summary="健康检查")
async def health_check():
    return {"status": "healthy", "version": "3.1.0"}


@app.get("/", summary="首页")
async def root():
    return {
        "name": "国内电商店铺自动化运营智能体",
        "version": "3.1.0",
        "core_idea": "真实淘宝数据 + DeepSeek 大模型 + 自反馈闭环（RAG + 质量门控 + 向量回流）",
        "modules": ["选品Agent", "投放优化Agent", "多语言客服Agent", "数据闭环系统"],
        "docs": "/docs",
        "status": "/api/v1/system/status",
    }
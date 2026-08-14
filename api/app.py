"""国内电商店铺自动化运营智能体 v3.1 - FastAPI 服务（真实店铺运营版）"""
import os
import sys
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config.settings import settings
from agents.product_selection_agent import product_selection_agent
from agents.ad_optimization_agent import ad_optimization_agent
from agents.customer_service_agent import customer_service_agent
from retrieval.mobius_loop import mobius_loop
from utils.logger import logger
from contextlib import asynccontextmanager

from api.scheduler import daily_scheduler
from storage.report_store import report_store
from storage.product_store import product_store
from notify.dingtalk import dingtalk

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时拉起每日定时任务，退出时停止"""
    daily_scheduler.start()
    yield
    daily_scheduler.stop()


app = FastAPI(
    title="国内电商店铺自动化运营智能体 API",
    description="接入真实淘宝平台（淘宝客 API）+ DeepSeek 大模型的电商运营智能体（v3.1 真实店铺运营版）",
    version="3.1.0",
    lifespan=lifespan,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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


class ProductStatusRequest(BaseModel):
    status: str


@app.post("/api/v1/selection/analyze", summary="选品分析")
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/ad/optimize", summary="推广/投放优化")
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


@app.get("/api/v1/reports", summary="历史报告列表")
async def list_reports(report_type: Optional[str] = Query(None, alias="type"), limit: int = 30):
    try:
        return {"code": 0, "message": "success", "data": report_store.list_reports(report_type, limit)}
    except Exception as e:
        logger.error(f"获取历史报告失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/reports/trend", summary="报告趋势（按日期聚合）")
async def get_report_trend(report_type: str = Query("selection", alias="type"), days: int = 30):
    try:
        return {"code": 0, "message": "success", "data": report_store.trend(report_type, days)}
    except Exception as e:
        logger.error(f"获取报告趋势失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/reports/{report_id}", summary="报告详情")
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
            "auto_report_enabled": settings.AUTO_REPORT_ENABLED,
            "auto_report_time": settings.AUTO_REPORT_TIME,
            "report_db": "data/reports.db",
            "dingtalk_configured": dingtalk.configured,
        },
    }


@app.get("/api/v1/dashboard/summary", summary="今日运营总览")
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/products", summary="商品库列表")
async def list_products(
    status: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    try:
        data = product_store.list_products(status, source, q, limit, offset)
        data["stats"] = product_store.stats()
        return {"code": 0, "message": "success", "data": data}
    except Exception as e:
        logger.error(f"获取商品库失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/v1/products/{product_id}", summary="更新商品状态")
async def update_product_status(product_id: int, request: ProductStatusRequest):
    try:
        ok = product_store.set_status(product_id, request.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="商品不存在")
    return {"code": 0, "message": "success", "data": {"id": product_id, "status": request.status}}


@app.post("/api/v1/notify/test", summary="钉钉推送测试")
async def notify_test():
    """发送一条测试消息到钉钉群，验证 Webhook 配置（不返回任何密钥）"""
    if not dingtalk.configured:
        raise HTTPException(
            status_code=400,
            detail="未配置钉钉机器人：请在 .env 设置 DINGTALK_WEBHOOK_URL（机器人安全设置若为加签，还需 DINGTALK_SECRET），保存后重启服务",
        )
    ok = dingtalk.send_markdown(
        "✅ 钉钉推送测试",
        "## ✅ 钉钉推送测试成功\n\n本消息来自国内电商运营智能体，说明 Webhook 配置正确。\n> 每日定时报告完成后将自动推送运营日报到本群。",
    )
    if not ok:
        raise HTTPException(status_code=502, detail="钉钉推送失败，请检查 Webhook 地址、加签密钥与网络（详情见日志）")
    return {"code": 0, "message": "success", "data": {"sent": True}}


@app.get("/health", summary="健康检查")
async def health_check():
    return {"status": "healthy", "version": "3.1.0"}


@app.get("/", summary="运营后台首页", include_in_schema=False)
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))

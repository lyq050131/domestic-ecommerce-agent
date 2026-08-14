"""国内电商店铺自动化运营智能体 v3.1 - FastAPI 服务（真实店铺运营版）"""
import os
import sys
from datetime import datetime
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
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
from storage.cs_queue import cs_queue
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
    version=settings.VERSION,
    lifespan=lifespan,
)


# ---------- 访问令牌鉴权（可选） ----------
@app.middleware("http")
async def access_auth_middleware(request: Request, call_next):
    """配置 WEB_ACCESS_TOKEN 后，所有 /api/v1/* 需带 Authorization: Bearer <令牌>。
    /api/v1/auth/*（登录本身）与 /health、静态页面不拦截。
    """
    if settings.WEB_ACCESS_TOKEN:
        path = request.url.path
        if path.startswith("/api/v1/") and not path.startswith("/api/v1/auth/"):
            auth = request.headers.get("authorization", "")
            if auth != f"Bearer {settings.WEB_ACCESS_TOKEN}":
                return JSONResponse(status_code=401, content={"code": 401, "message": "未授权：请输入访问令牌登录", "data": None})
    return await call_next(request)


# ---------- 统一错误处理 ----------
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """业务/参数错误：按原状态码返回，不泄露内部堆栈"""
    return JSONResponse(status_code=exc.status_code, content={"code": exc.status_code, "message": exc.detail, "data": None})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": 422, "message": "参数校验失败，请检查请求体", "data": None})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理异常 {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"code": 500, "message": "服务器内部错误，请查看服务日志", "data": None})

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


class CSQueueItem(BaseModel):
    content: str
    rating: Optional[int] = None


class CSQueueRequest(BaseModel):
    items: List[CSQueueItem]


class CSQueueStatusRequest(BaseModel):
    status: str


class AutoLaunchRequest(BaseModel):
    category: Optional[str] = None          # 品类（默认取定时任务配置）
    top_n: Optional[int] = 10               # 推广链接清单条数（1-20）
    push_dingtalk: Optional[bool] = True    # 是否推送钉钉清单


class SettingsUpdateRequest(BaseModel):
    auto_report_enabled: Optional[bool] = None
    auto_report_time: Optional[str] = None
    auto_report_category: Optional[str] = None
    auto_report_count: Optional[int] = None
    auto_report_ad_top_n: Optional[int] = None
    dingtalk_enabled: Optional[bool] = None
    dingtalk_webhook: Optional[str] = None
    dingtalk_secret: Optional[str] = None


class LoginRequest(BaseModel):
    token: str


@app.post("/api/v1/auth/login", summary="登录（输入访问令牌）")
async def login(request: LoginRequest):
    """校验访问令牌：与 .env 的 WEB_ACCESS_TOKEN 一致则登录成功（前端存 localStorage）。"""
    if not settings.WEB_ACCESS_TOKEN:
        return {"code": 0, "message": "success", "data": {"enabled": False}}
    if request.token and request.token == settings.WEB_ACCESS_TOKEN:
        return {"code": 0, "message": "success", "data": {"enabled": True}}
    raise HTTPException(status_code=401, detail="令牌不正确")


@app.get("/api/v1/auth/status", summary="登录状态（是否启用访问令牌）")
async def auth_status():
    return {"code": 0, "message": "success", "data": {"enabled": bool(settings.WEB_ACCESS_TOKEN)}}


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
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


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
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


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
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


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
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@app.get("/api/v1/loop/stats", summary="闭环系统统计")
async def get_loop_stats():
    try:
        return {"code": 0, "message": "success", "data": mobius_loop.get_loop_stats()}
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@app.get("/api/v1/reports", summary="历史报告列表")
async def list_reports(report_type: Optional[str] = Query(None, alias="type"), limit: int = 30):
    try:
        return {"code": 0, "message": "success", "data": report_store.list_reports(report_type, limit)}
    except Exception as e:
        logger.error(f"获取历史报告失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@app.get("/api/v1/reports/trend", summary="报告趋势（按日期聚合）")
async def get_report_trend(report_type: str = Query("selection", alias="type"), days: int = 30):
    try:
        return {"code": 0, "message": "success", "data": report_store.trend(report_type, days)}
    except Exception as e:
        logger.error(f"获取报告趋势失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


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
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@app.get("/api/v1/system/status", summary="系统状态（不含任何密钥）")
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
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


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
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@app.patch("/api/v1/products/{product_id}", summary="更新商品状态")
async def update_product_status(product_id: int, request: ProductStatusRequest):
    try:
        ok = product_store.set_status(product_id, request.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="商品不存在")
    return {"code": 0, "message": "success", "data": {"id": product_id, "status": request.status}}


@app.post("/api/v1/cs/queue", summary="客服队列批量导入")
async def add_cs_queue(request: CSQueueRequest):
    """批量导入差评/私信（单次最多 50 条），进入待处理队列"""
    if not request.items:
        raise HTTPException(status_code=400, detail="items 不能为空")
    if len(request.items) > 50:
        raise HTTPException(status_code=400, detail="单次最多导入 50 条")
    n = cs_queue.add_many([{"content": it.content, "rating": it.rating} for it in request.items])
    return {"code": 0, "message": "success", "data": {"added": n}}


@app.get("/api/v1/cs/queue", summary="客服队列列表")
async def list_cs_queue(status: Optional[str] = None, limit: int = 100):
    try:
        data = cs_queue.list(status, limit)
        data["stats"] = cs_queue.stats()
        return {"code": 0, "message": "success", "data": data}
    except Exception as e:
        logger.error(f"获取客服队列失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@app.post("/api/v1/cs/queue/{item_id}/reply", summary="生成客服回复")
async def reply_cs_queue(item_id: int, language: str = "auto"):
    item = cs_queue.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="记录不存在")
    try:
        if item["rating"]:
            result = customer_service_agent.handle_review(item["content"], item["rating"], language)
        else:
            result = customer_service_agent.handle_message(item["content"], language)
        cs_queue.set_reply(item_id, result["reply"], result["detected_language"], result.get("matched_template"))
        cs_queue.set_status(item_id, "已回复")
        return {"code": 0, "message": "success", "data": {
            "id": item_id, "reply": result["reply"],
            "detected_language": result["detected_language"],
            "matched_template": result.get("matched_template"),
        }}
    except Exception as e:
        logger.error(f"生成客服回复失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@app.patch("/api/v1/cs/queue/{item_id}", summary="客服队列状态更新（忽略等）")
async def update_cs_queue(item_id: int, request: CSQueueStatusRequest):
    try:
        ok = cs_queue.set_status(item_id, request.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"code": 0, "message": "success", "data": {"id": item_id, "status": request.status}}


@app.get("/api/v1/settings", summary="运营设置（不含密钥）")
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


@app.put("/api/v1/settings", summary="保存运营设置（写入 .env，重启后生效）")
async def update_settings(request: SettingsUpdateRequest):
    from dotenv import set_key
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
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
                set_key(env_path, env_name, str(data[key]))
                updated.append(env_name)
        if data.get("dingtalk_webhook") is not None and str(data["dingtalk_webhook"]).strip():
            set_key(env_path, "DINGTALK_WEBHOOK_URL", str(data["dingtalk_webhook"]).strip())
            updated.append("DINGTALK_WEBHOOK_URL")
        if data.get("dingtalk_secret") is not None and str(data["dingtalk_secret"]).strip():
            set_key(env_path, "DINGTALK_SECRET", str(data["dingtalk_secret"]).strip())
            updated.append("DINGTALK_SECRET")
    except Exception as e:
        logger.error(f"保存设置失败: {e}")
        raise HTTPException(status_code=500, detail="写入 .env 失败，请查看服务日志")
    return {"code": 0, "message": "success", "data": {
        "saved": True, "updated": updated, "restart_required": True,
        "hint": "设置已写入 .env，重启服务后生效",
    }}


@app.post("/api/v1/auto/launch", summary="自动投放（一键流水线）")
async def auto_launch(request: AutoLaunchRequest):
    """自动投放流水线：选品+投放分析 → 报告/商品落库 → 汇总推广链接清单 → 钉钉推送。
    合规边界：只生成可投放的推广链接清单，不自动下单、不自动发布，由运营者确认后投放。
    """
    category = (request.category or "").strip() or settings.AUTO_REPORT_CATEGORY
    top_n = max(1, min(int(request.top_n or 10), 20))
    try:
        logger.info("========== 自动投放流水线开始 ==========")
        # 1) 选品分析 + 落库
        sel_result = product_selection_agent.analyze_category(
            category, count=settings.AUTO_REPORT_COUNT
        )
        rid_sel, sel_summary = report_store.save_selection_report(
            sel_result, params={"category": category, "count": settings.AUTO_REPORT_COUNT}
        )
        # 2) 投放优化 + 落库
        ad_result = ad_optimization_agent.optimize_campaigns(top_n=settings.AUTO_REPORT_AD_TOP_N)
        rid_ad, ad_summary = report_store.save_ad_report(
            ad_result, params={"top_n": settings.AUTO_REPORT_AD_TOP_N}
        )
        # 3) 汇总推广链接（按 item_url 去重）
        links, seen = [], set()
        for source, tops in (
            ("选品", sel_summary.get("top_products") or []),
            ("投放", ad_summary.get("top_products") or []),
        ):
            for p in tops:
                url = p.get("item_url") or ""
                if not url or url in seen:
                    continue
                seen.add(url)
                links.append({
                    "product_name": p.get("product_name") or "",
                    "price": p.get("price") or 0,
                    "sales_30d": p.get("sales_30d") or 0,
                    "commission_rate": p.get("commission_rate") or 0,
                    "score": round(float(p.get("hot_score") or p.get("promotion_score") or 0), 2),
                    "item_url": url,
                    "source": source,
                })
                if len(links) >= top_n:
                    break
        # 4) 钉钉推送清单
        sent = False
        if request.push_dingtalk:
            sent = dingtalk.send_launch_links(datetime.now().strftime("%Y-%m-%d"), category, links)
        logger.info("========== 自动投放流水线完成 ==========")
        links_by_source = {"选品": [], "投放": []}
        for l in links:
            links_by_source.setdefault(l["source"], []).append(l)
        return {"code": 0, "message": "success", "data": {
            "category": category,
            "report_ids": {"selection": rid_sel, "ad": rid_ad},
            "links": links,
            "links_by_source": links_by_source,
            "link_count": len(links),
            "dingtalk_sent": sent,
        }}
    except Exception as e:
        logger.error(f"自动投放失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


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
    return {"status": "healthy", "version": settings.VERSION}


@app.get("/", summary="运营后台首页", include_in_schema=False)
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
async def not_found_route(full_path: str):
    """兜底路由：未匹配接口统一返回 404 JSON（与全局错误格式一致）"""
    raise HTTPException(status_code=404, detail=f"接口不存在: /{full_path}")

"""自动投放流水线：同步接口 + 异步任务（后台线程执行，前端轮询）"""
from datetime import datetime

from fastapi import APIRouter, HTTPException

from agents.ad_optimization_agent import ad_optimization_agent
from agents.product_selection_agent import product_selection_agent
from api.schemas import AutoLaunchRequest
from api.task_manager import task_manager
from config.settings import settings
from notify.dingtalk import dingtalk
from storage.report_store import report_store
from utils.logger import logger

router = APIRouter(tags=["自动投放"])


def run_auto_launch(request: AutoLaunchRequest, progress_cb=None) -> dict:
    """自动投放流水线（同步执行，供同步接口与后台任务复用）。
    合规边界：只生成可投放的推广链接清单，不自动下单、不自动发布，由运营者确认后投放。
    """
    category = (request.category or "").strip() or settings.AUTO_REPORT_CATEGORY
    top_n = max(1, min(int(request.top_n or 10), 20))

    def cb(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    logger.info("========== 自动投放流水线开始 ==========")
    cb("正在执行选品分析（抓取淘宝真实数据 + DeepSeek 报告）…")
    sel_result = product_selection_agent.analyze_category(
        category, count=settings.AUTO_REPORT_COUNT
    )
    rid_sel, sel_summary = report_store.save_selection_report(
        sel_result, params={"category": category, "count": settings.AUTO_REPORT_COUNT}
    )

    cb("选品分析完成，正在执行投放优化…")
    ad_result = ad_optimization_agent.optimize_campaigns(top_n=settings.AUTO_REPORT_AD_TOP_N)
    rid_ad, ad_summary = report_store.save_ad_report(
        ad_result, params={"top_n": settings.AUTO_REPORT_AD_TOP_N}
    )

    cb("投放优化完成，正在汇总推广链接清单…")
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

    cb("正在推送钉钉清单…")
    sent = False
    if request.push_dingtalk:
        sent = dingtalk.send_launch_links(datetime.now().strftime("%Y-%m-%d"), category, links)
    logger.info("========== 自动投放流水线完成 ==========")
    links_by_source = {"选品": [], "投放": []}
    for l in links:
        links_by_source.setdefault(l["source"], []).append(l)
    return {
        "category": category,
        "report_ids": {"selection": rid_sel, "ad": rid_ad},
        "links": links,
        "links_by_source": links_by_source,
        "link_count": len(links),
        "dingtalk_sent": sent,
    }


@router.post("/api/v1/auto/launch", summary="自动投放（同步，约2-3分钟）")
async def auto_launch_sync(request: AutoLaunchRequest):
    """同步版本：请求期间阻塞约 2-3 分钟（兼容旧调用方）。推荐使用 /auto/launch/async。"""
    try:
        return {"code": 0, "message": "success", "data": run_auto_launch(request)}
    except Exception as e:
        logger.error(f"自动投放失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@router.post("/api/v1/auto/launch/async", summary="自动投放（异步任务，推荐）")
async def auto_launch_async(request: AutoLaunchRequest):
    """提交后台任务立即返回 task_id，用 GET /api/v1/tasks/{task_id} 轮询进度与结果。"""
    tid = task_manager.submit("自动投放", run_auto_launch, request)
    return {"code": 0, "message": "success", "data": {"task_id": tid, "name": "自动投放", "status": "running"}}


@router.get("/api/v1/tasks/{task_id}", summary="查询后台任务状态")
async def get_task(task_id: str):
    t = task_manager.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"code": 0, "message": "success", "data": t}

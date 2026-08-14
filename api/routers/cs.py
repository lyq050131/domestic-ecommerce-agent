"""多语言客服：评论/私信回复 + 待回复队列"""
from fastapi import APIRouter, HTTPException

from agents.customer_service_agent import customer_service_agent
from api.schemas import CSQueueRequest, CSQueueStatusRequest, MessageRequest, ReviewRequest
from storage.cs_queue import cs_queue
from utils.logger import logger

router = APIRouter(tags=["客服"])


@router.post("/api/v1/cs/review", summary="评论回复")
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


@router.post("/api/v1/cs/message", summary="私信回复")
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


@router.post("/api/v1/cs/queue", summary="客服队列批量导入")
async def add_cs_queue(request: CSQueueRequest):
    """批量导入差评/私信（单次最多 50 条），进入待处理队列"""
    if not request.items:
        raise HTTPException(status_code=400, detail="items 不能为空")
    if len(request.items) > 50:
        raise HTTPException(status_code=400, detail="单次最多导入 50 条")
    n = cs_queue.add_many([{"content": it.content, "rating": it.rating} for it in request.items])
    return {"code": 0, "message": "success", "data": {"added": n}}


@router.get("/api/v1/cs/queue", summary="客服队列列表")
async def list_cs_queue(status: str = None, limit: int = 100):
    try:
        data = cs_queue.list(status, limit)
        data["stats"] = cs_queue.stats()
        return {"code": 0, "message": "success", "data": data}
    except Exception as e:
        logger.error(f"获取客服队列失败: {e}")
        raise HTTPException(status_code=500, detail="执行失败，请查看服务日志")


@router.post("/api/v1/cs/queue/{item_id}/reply", summary="生成客服回复")
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


@router.patch("/api/v1/cs/queue/{item_id}", summary="客服队列状态更新（忽略等）")
async def update_cs_queue(item_id: int, request: CSQueueStatusRequest):
    try:
        ok = cs_queue.set_status(item_id, request.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"code": 0, "message": "success", "data": {"id": item_id, "status": request.status}}

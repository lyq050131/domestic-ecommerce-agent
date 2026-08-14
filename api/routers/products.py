"""商品库：列表 + 状态流转"""
from fastapi import APIRouter, HTTPException

from api.schemas import ProductStatusRequest
from storage.product_store import product_store
from utils.logger import logger

router = APIRouter(tags=["商品库"])


@router.get("/api/v1/products", summary="商品库列表")
async def list_products(
    status: str = None,
    source: str = None,
    q: str = None,
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


@router.patch("/api/v1/products/{product_id}", summary="更新商品状态")
async def update_product_status(product_id: int, request: ProductStatusRequest):
    try:
        ok = product_store.set_status(product_id, request.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="商品不存在")
    return {"code": 0, "message": "success", "data": {"id": product_id, "status": request.status}}

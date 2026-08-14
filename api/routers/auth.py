"""认证：访问令牌登录"""
from fastapi import APIRouter, HTTPException

from api.schemas import LoginRequest
from config.settings import settings

router = APIRouter(tags=["认证"])


@router.post("/api/v1/auth/login", summary="登录（输入访问令牌）")
async def login(request: LoginRequest):
    """校验访问令牌：与 .env 的 WEB_ACCESS_TOKEN 一致则登录成功（前端存 localStorage）。"""
    if not settings.WEB_ACCESS_TOKEN:
        return {"code": 0, "message": "success", "data": {"enabled": False}}
    if request.token and request.token == settings.WEB_ACCESS_TOKEN:
        return {"code": 0, "message": "success", "data": {"enabled": True}}
    raise HTTPException(status_code=401, detail="令牌不正确")


@router.get("/api/v1/auth/status", summary="登录状态（是否启用访问令牌）")
async def auth_status():
    return {"code": 0, "message": "success", "data": {"enabled": bool(settings.WEB_ACCESS_TOKEN)}}

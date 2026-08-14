"""国内电商店铺自动化运营智能体 v3.1 - FastAPI 服务（真实店铺运营版）

入口模块：应用组装（生命周期 / 鉴权中间件 / 统一错误处理 / 路由挂载）。
业务路由按域拆分在 api/routers/ 下；请求模型见 api/schemas.py。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routers import (
    ad,
    auth,
    cs,
    dashboard,
    launch,
    notify,
    products,
    reports,
    selection,
    settings as settings_router,
    system,
)
from api.scheduler import daily_scheduler
from config.settings import settings
from utils.logger import logger


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

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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
    """业务/参数错误：按原状态码返回统一 JSON，不泄露内部堆栈"""
    return JSONResponse(status_code=exc.status_code, content={"code": exc.status_code, "message": exc.detail, "data": None})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": 422, "message": "参数校验失败，请检查请求体", "data": None})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理异常 {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"code": 500, "message": "服务器内部错误，请查看服务日志", "data": None})


# ---------- 业务路由 ----------
for _router in (auth, system, dashboard, selection, ad, cs, products, reports, settings_router, launch, notify):
    app.include_router(_router.router)


# ---------- 首页 ----------
@app.get("/", summary="运营后台首页", include_in_schema=False)
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ---------- 兜底 404（统一 JSON 格式） ----------
@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
async def not_found_route(full_path: str):
    raise HTTPException(status_code=404, detail=f"接口不存在: /{full_path}")

"""API 请求模型（Pydantic）"""
from typing import List, Optional

from pydantic import BaseModel


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

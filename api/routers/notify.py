"""钉钉推送测试"""
from fastapi import APIRouter, HTTPException

from notify.dingtalk import dingtalk

router = APIRouter(tags=["钉钉"])


@router.post("/api/v1/notify/test", summary="钉钉推送测试")
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

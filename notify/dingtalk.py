"""钉钉机器人日报推送（markdown 消息，可选加签）

- Webhook 地址在 .env 配置：DINGTALK_WEBHOOK_URL（自定义机器人）
- 安全设置若为「加签」，配置 DINGTALK_SECRET 后自动计算签名
- 未配置 Webhook 时所有推送自动跳过并记日志，不影响主流程
"""
import base64
import hashlib
import hmac
import time
import urllib.parse
from datetime import datetime
from typing import Optional

import requests

from config.settings import settings
from utils.logger import logger


class DingTalkNotifier:
    """钉钉自定义机器人推送器"""

    def __init__(self):
        self.webhook_url = settings.DINGTALK_WEBHOOK_URL.strip()
        self.secret = settings.DINGTALK_SECRET.strip()
        self.enabled_flag = settings.DINGTALK_ENABLED

    @property
    def configured(self) -> bool:
        return bool(self.enabled_flag and self.webhook_url)

    def _signed_url(self) -> str:
        """加签：timestamp + '\n' + secret 做 HMAC-SHA256，追加到 webhook"""
        if not self.secret:
            return self.webhook_url
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(self.secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        sep = "&" if "?" in self.webhook_url else "?"
        return f"{self.webhook_url}{sep}timestamp={timestamp}&sign={sign}"

    def send_markdown(self, title: str, text: str) -> bool:
        """发送 markdown 消息；失败记日志并返回 False（不抛异常）"""
        if not self.configured:
            logger.warning("钉钉机器人未配置（DINGTALK_WEBHOOK_URL 为空或 DINGTALK_ENABLED=false），跳过推送")
            return False
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title[:64], "text": text},
        }
        try:
            resp = requests.post(self._signed_url(), json=payload, timeout=10)
            body = resp.json()
            if resp.status_code == 200 and body.get("errcode") == 0:
                logger.info(f"✅ 钉钉日报已推送（title={title[:30]}）")
                return True
            logger.error(f"钉钉推送失败: HTTP {resp.status_code}，errcode={body.get('errcode')}，errmsg={body.get('errmsg')}")
            return False
        except Exception as e:
            logger.error(f"钉钉推送异常: {e}")
            return False

    def send_daily_digest(self, date_str: str, selection: Optional[dict] = None, ad: Optional[dict] = None) -> bool:
        """发送每日运营日报摘要。selection/ad 形如 {"title": ..., "summary": {...}}"""
        text = build_daily_digest(date_str, selection, ad)
        return self.send_markdown(f"📊 电商运营日报 {date_str}", text)


def _int_num(v) -> str:
    """取整（用于平均月销等）"""
    try:
        return str(int(round(float(v or 0))))
    except Exception:
        return str(v or 0)


def _fmt_num(v) -> str:
    try:
        n = float(v or 0)
        return str(int(n)) if n == int(n) else f"{n:g}"
    except Exception:
        return str(v or 0)


def build_daily_digest(date_str: str, selection: Optional[dict] = None, ad: Optional[dict] = None) -> str:
    """把选品/投放摘要拼成钉钉 markdown 日报文本（钉钉 markdown 不支持表格，用列表）"""
    lines = [f"## 📊 电商运营日报（{date_str}）", ""]
    if selection:
        s = selection.get("summary") or {}
        top = s.get("top_products") or []
        lines += [
            "### 🎯 选品分析",
            f"- 品类：**{selection.get('title') or '-'}** ｜ 样本 {s.get('total', 0)} 款",
            f"- 平均月销 {_int_num(s.get('avg_sales'))} ｜ 平均佣金率 {_fmt_num(s.get('avg_commission'))}% ｜ 爆款 {s.get('hot_count', 0)} 款",
            "- **Top 推荐（佣金率 × 月销）**：",
        ]
        if top:
            for i, p in enumerate(top[:3], 1):
                name = (p.get("product_name") or "")[:22]
                url = p.get("item_url") or ""
                link = f"[{name}]({url})" if url else name
                lines.append(f"  {i}. {link} ｜ ¥{_fmt_num(p.get('price'))} / 月销{_fmt_num(p.get('sales_30d'))} / 佣金{_fmt_num(p.get('commission_rate'))}%")
        else:
            lines.append("  （本次无商品明细）")
        lines.append("")
    if ad:
        s = ad.get("summary") or {}
        top = s.get("top_products") or []
        lines += [
            "### 📈 投放优化",
            f"- 商品 {s.get('total', 0)} 款 ｜ 关键词 {s.get('keywords', 0)} 个",
            f"- 平均佣金率 {_fmt_num(s.get('avg_commission'))}% ｜ 累计预估佣金 **¥{_fmt_num(s.get('total_estimated_commission'))}**",
            "- **Top 商品（推广潜力分）**：",
        ]
        if top:
            for i, p in enumerate(top[:3], 1):
                name = (p.get("product_name") or "")[:22]
                url = p.get("item_url") or ""
                link = f"[{name}]({url})" if url else name
                kw = p.get("keyword") or ""
                lines.append(f"  {i}. {link} ｜ ¥{_fmt_num(p.get('price'))} / 潜力分{_fmt_num(p.get('promotion_score'))}" + (f" / 词[{kw}]" if kw else ""))
        else:
            lines.append("  （本次无商品明细）")
        lines.append("")
    lines += [
        "> 完整报告见本地运营后台 http://127.0.0.1:8000/",
        "",
    ]
    return "\n".join(lines)


dingtalk = DingTalkNotifier()

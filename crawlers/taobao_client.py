"""淘宝客开放平台客户端（TOP 网关）

物料搜索使用升级版接口 taobao.tbk.dg.material.optional.upgrade，
需在淘宝联盟开放平台申请权限包「淘宝客【推广者】商品物料获取」（scope 27939）。
所有密钥一律从 .env 读取，本文件不写死任何 Key。
"""
import hashlib
import hmac
import time
from typing import Any, Dict, List, Optional

import requests

from config.settings import settings
from utils.logger import logger


class TaobaoClient:
    """淘宝客 TOP 网关客户端：签名 + 请求 + 物料搜索 + 字段解析"""

    def __init__(self) -> None:
        self.app_key = settings.TAOBAO_APP_KEY
        self.app_secret = settings.TAOBAO_APP_SECRET
        self.adzone_id = settings.TAOBAO_ADZONE_ID
        self.gateway = settings.TAOBAO_GATEWAY
        self.sign_method = settings.TAOBAO_SIGN_METHOD.lower()
        self.timeout = int(settings.LLM_TIMEOUT)
        self.max_retries = max(1, int(settings.CRAWLER_MAX_RETRIES))

    # ---------- 配置 ----------
    @property
    def configured(self) -> bool:
        """是否已配置淘宝客三要素"""
        return bool(self.app_key and self.app_secret and self.adzone_id)

    # ---------- 签名 ----------
    def _sign(self, params: Dict[str, str]) -> str:
        """TOP 官方签名算法。

        md5 模式：secret + 参数升序拼接(key+value) + secret -> MD5 -> 大写十六进制
        hmac 模式：以 secret 为密钥，对参数拼接串做 HMAC-MD5 / HMAC-SHA256
        """
        sorted_params = "".join(f"{k}{params[k]}" for k in sorted(params))
        if self.sign_method == "md5":
            raw = self.app_secret + sorted_params + self.app_secret
            return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()
        if self.sign_method == "hmac-sha256":
            return hmac.new(
                self.app_secret.encode("utf-8"),
                sorted_params.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest().upper()
        # 默认 hmac（HMAC-MD5）
        return hmac.new(
            self.app_secret.encode("utf-8"),
            sorted_params.encode("utf-8"),
            hashlib.md5,
        ).hexdigest().upper()

    # ---------- 请求 ----------
    def _request(
        self,
        method: str,
        biz_params: Dict[str, Any],
        session: Optional[str] = None,
        retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """发起 TOP 网关请求（GET），自动重试并统一解析错误。"""
        params: Dict[str, str] = {
            "method": method,
            "app_key": self.app_key,
            "sign_method": self.sign_method,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "format": "json",
            "v": "2.0",
        }
        if session:
            params["session"] = session
        params.update({k: str(v) for k, v in biz_params.items() if v is not None and str(v) != ""})
        params["sign"] = self._sign(params)

        attempts = retries or self.max_retries
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                resp = requests.get(self.gateway, params=params, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                if "error_response" in data:
                    err = data["error_response"]
                    raise RuntimeError(
                        f"淘宝API错误 [{method}] code={err.get('code')} "
                        f"msg={err.get('msg')} sub_msg={err.get('sub_msg')}"
                    )
                return data
            except Exception as e:  # noqa: BLE001
                last_error = e
                logger.warning(f"淘宝请求失败（第 {attempt}/{attempts} 次）: {e}")
                if attempt < attempts:
                    time.sleep(attempt * 1.0)
        raise RuntimeError(f"淘宝API请求失败: {last_error}")

    # ---------- 物料搜索 ----------
    def search_material(
        self,
        keyword: str,
        page_no: int = 1,
        page_size: Optional[int] = None,
        sort: str = "total_sales_des",
        has_coupon: bool = False,
        need_free_shipment: bool = False,
        cat: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """taobao.tbk.dg.material.optional.upgrade 物料搜索升级版（scope 27939）。

        真实返回包在 tbk_dg_material_optional_upgrade_response 内，需先解包。
        """
        if not self.configured:
            raise RuntimeError("未配置淘宝客三要素（TAOBAO_APP_KEY / TAOBAO_APP_SECRET / TAOBAO_ADZONE_ID）")
        page_size = page_size or settings.TAOBAO_PAGE_SIZE
        biz: Dict[str, Any] = {
            "q": keyword,
            "adzone_id": self.adzone_id,
            "material_id": "80309",  # 官方默认通用物料库
            "page_no": page_no,
            "page_size": min(max(int(page_size), 1), 100),
            "sort": sort,
        }
        if has_coupon:
            biz["has_coupon"] = "true"
        if need_free_shipment:
            biz["need_free_shipment"] = "true"
        if cat:
            biz["cat"] = str(cat)  # 商品类目ID，可显著提升按品类抓取的精确性

        data = self._request("taobao.tbk.dg.material.optional.upgrade", biz)
        resp = data.get("tbk_dg_material_optional_upgrade_response") or data
        items = ((resp.get("result_list") or {}).get("map_data")) or []
        logger.info(
            f"淘宝物料搜索升级版 [{keyword}] 第 {page_no} 页返回 {len(items)} 条"
            f"（total_results={resp.get('total_results')}）"
        )
        return items

    # ---------- 字段解析 ----------
    @staticmethod
    def _path_list(path_raw: Any) -> List[Dict[str, Any]]:
        """兼容到手价优惠路径的两种真实结构：数组 或 {"final_promotion_path_map_data":[...]}"""
        if isinstance(path_raw, dict):
            return path_raw.get("final_promotion_path_map_data") or []
        if isinstance(path_raw, list):
            return path_raw
        return []

    def parse_material_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """升级版接口嵌套字段对齐 + 佣金换算。

        升级版返回结构（docId=62201）：
        - item_basic_info: title / volume(30天销量) / category_name / shop_title / user_type
        - price_promotion_info: reserve_price(划线价) / zk_final_price(售价)
        - income_info.commission_rate: 百分比（如 "55" = 55%），非旧版万分比
        - publish_info.click_url: 推广链接
        - 商品券金额：final_promotion_path_list 中 promotion_title=="商品券" 的 promotion_fee 累加
        """
        basic = item.get("item_basic_info") or {}
        price_info = item.get("price_promotion_info") or {}
        income_info = item.get("income_info") or {}
        publish_info = item.get("publish_info") or {}

        price = float(
            price_info.get("zk_final_price")
            or price_info.get("final_promotion_price")
            or item.get("zk_final_price")
            or 0
        )
        original_price = float(price_info.get("reserve_price") or item.get("reserve_price") or price or 0)

        # 商品券金额：到手价路径中 "商品券" 优惠金额累加（升级版无顶层 coupon_amount）
        coupon_amount = float(item.get("coupon_amount") or 0)
        for promo in self._path_list(price_info.get("final_promotion_path_list")):
            if str(promo.get("promotion_title") or "") == "商品券":
                coupon_amount += float(promo.get("promotion_fee") or 0)

        # 销量：volume（30天销量）实测恒为 0，改用 tk_total_sales（淘客30天推广量）作为销量代理
        volume = int(basic.get("volume") or item.get("volume") or 0)
        if volume <= 0:
            volume = int(float(basic.get("tk_total_sales") or 0))

        # 佣金/收入比率：实测 income_info.commission_rate 常为空，主用 publish_info.income_rate（%）
        # 兼容两种口径：百分比（如 55 = 55%）与万分比（>100 时折算）
        commission_rate_raw = float(
            income_info.get("commission_rate")
            or publish_info.get("income_rate")
            or item.get("commission_rate")
            or 0
        )
        if commission_rate_raw > 100:
            commission_rate_raw = commission_rate_raw / 100.0
        commission_rate_percent = round(commission_rate_raw, 2)

        base_price = price if price > 0 else original_price
        estimated_commission = (
            round(base_price * commission_rate_percent / 100.0, 2) if base_price > 0 else 0.0
        )

        click_url = publish_info.get("click_url") or item.get("item_url") or item.get("click_url") or ""
        if click_url.startswith("//"):
            click_url = "https:" + click_url

        seller_type = basic.get("user_type")
        if seller_type is None:
            seller_type = item.get("user_type")

        return {
            "product_id": str(item.get("item_id") or item.get("num_iid") or ""),
            "product_name": basic.get("title") or item.get("title") or "",
            "category": basic.get("category_name") or item.get("category_name") or "",
            "price": round(price, 2),
            "original_price": round(original_price, 2),
            "coupon_amount": round(coupon_amount, 2),
            "coupon_start_fee": round(float(item.get("coupon_start_fee") or 0), 2),
            "sales_30d": volume,
            "commission_rate": commission_rate_percent,
            "estimated_commission": estimated_commission,
            "shop_title": basic.get("shop_title") or item.get("shop_title") or "",
            "item_url": click_url,
            "seller_type": seller_type,
            "rating": None,  # 淘宝物料接口不返回评分/评论数，由 DataProcessor 取中性值
            "review_count": 0,
            "is_hot": False,  # 由 DataProcessor 统一计算
            "data_source": "taobao",
        }


taobao_client = TaobaoClient()
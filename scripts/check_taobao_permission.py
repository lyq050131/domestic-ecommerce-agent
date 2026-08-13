# -*- coding: utf-8 -*-
"""淘宝物料搜索权限一键自检

用法:
    .venv\\Scripts\\python.exe scripts\\check_taobao_permission.py

- 成功: 打印权限 OK 与样例商品字段
- 失败(code=11): 打印当前已拥有 scope 列表与缺失的 27939 申请指引
"""
import os
import re
import sys

# 确保能导入项目根目录下的包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from crawlers.taobao_client import TaobaoClient


def main() -> int:
    client = TaobaoClient()
    if not client.configured:
        print("未配置淘宝客三要素，请先在 .env 填写 TAOBAO_APP_KEY / TAOBAO_APP_SECRET / TAOBAO_ADZONE_ID")
        return 1

    print("正在探测升级版物料搜索接口 taobao.tbk.dg.material.optional.upgrade（APPKEY=%s）..." % client.app_key)
    biz = {
        "q": "无线蓝牙耳机",
        "adzone_id": client.adzone_id,
        "material_id": "80309",
        "page_no": 1,
        "page_size": 3,
        "sort": "total_sales_des",
    }
    try:
        data = client._request("taobao.tbk.dg.material.optional.upgrade", biz, retries=1)
    except RuntimeError as e:
        msg = str(e)
        if "code=11" in msg:
            scopes = re.search(r"sub_msg=scope ids is ([\d\s]+)", msg)
            have = scopes.group(1).strip().split() if scopes else []
            print("[X] 权限尚未生效：升级版物料搜索接口返回 ISV权限不足（code=11）。")
            print("    当前 APPKEY 已拥有的权限包 scope：" + ("、".join(have) if have else "未知"))
            print("    缺少：27939「淘宝客【推广者】商品物料获取」。")
            print()
            print("申请步骤：")
            print("  1. 登录淘宝联盟开放平台：https://union.alimama.com （用申请 APPKEY 的同一账号）；")
            print("  2. 进入【功能中心】→ 选择权限包/能力列表；")
            print("  3. 找到「淘宝客【推广者】商品物料获取」（scope 27939）→ 选择当前 APPKEY 提交申请；")
            print("  4. 等待审核通过（个人媒体一般即时-1个工作日），通过后再运行本脚本复核。")
            print("  注意：权限必须开通在 .env 中 TAOBAO_APP_KEY 对应的同一个 APPKEY 上。")
        else:
            print("[X] 探测失败：%s" % msg)
        return 2

    resp = data.get("tbk_dg_material_optional_upgrade_response") or data
    items = ((resp.get("result_list") or {}).get("map_data")) or []
    if not items:
        print("[OK] 权限已生效，但该关键词暂无联盟商品（可换关键词重试）。")
        return 0
    print("[OK] 权限已生效，返回 %d 条商品。样例：" % len(items))
    for item in items[:3]:
        parsed = client.parse_material_item(item)
        print("  - %s | ￥%s | 月销%s | 佣金%s%% | 券￥%s | %s" % (
            parsed["product_name"], parsed["price"], parsed["sales_30d"],
            parsed["commission_rate"], parsed["coupon_amount"], parsed["shop_title"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
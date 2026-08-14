# -*- coding: utf-8 -*-
import pytest

from storage.product_store import ProductStore
from storage.cs_queue import CsQueueStore


def test_product_store_upsert_dedup_and_status(tmp_path):
    store = ProductStore(db_path=str(tmp_path / "test.db"))
    items = [
        {"product_id": "1", "product_name": "商品A", "price": 10, "sales_30d": 100,
         "commission_rate": 5, "hot_score": 88, "item_url": "http://x/1"},
        {"product_id": "1", "product_name": "商品A2", "price": 11, "sales_30d": 120,
         "commission_rate": 6, "hot_score": 90, "item_url": "http://x/1"},
    ]
    assert store.upsert_many("selection", items, category="耳机") == 2
    data = store.list_products(limit=10, offset=0)
    assert data["total"] == 1  # 按 product_key 去重
    assert data["items"][0]["product_name"] == "商品A2"
    pid = data["items"][0]["id"]
    store.set_status(pid, "已投放")
    assert store.list_products(status="已投放")["total"] == 1
    with pytest.raises(ValueError):
        store.set_status(pid, "非法状态")


def test_cs_queue_roundtrip(tmp_path):
    q = CsQueueStore(db_path=str(tmp_path / "cs.db"))
    assert q.add_many([{"content": "差评", "rating": 1}, {"content": "   "}]) == 1
    data = q.list(limit=10)
    assert data["total"] == 1
    item = data["items"][0]
    assert q.set_reply(item["id"], "回复内容", "zh", "模板A") is True
    assert q.set_status(item["id"], "已回复") is True
    got = q.get(item["id"])
    assert got["status"] == "已回复"
    assert got["reply"] == "回复内容"

# -*- coding: utf-8 -*-
import pytest
from fastapi.testclient import TestClient

import api.app as app_module
from api.app import app


@pytest.fixture
def client(monkeypatch):
    # mock 外部依赖：淘宝 / DeepSeek / 报告落库 / 钉钉，避免真实付费调用
    def fake_analyze(category, count=20, cat=None, include_keywords=None, exclude_keywords=None):
        return {
            "category": category,
            "report": "## 一、品类概述\n测试报告",
            "feedback_success": True,
            "data_source": "taobao",
            "competitor_data": [{"product_name": "测试商品"}],
            "cat": cat,
            "include_keywords": include_keywords,
            "exclude_keywords": exclude_keywords,
        }

    def fake_optimize(keywords=None, top_n=15, order_days=7, exclude_keywords=None):
        return {
            "optimization_strategy": "## 一、投放现状诊断\n测试方案",
            "promotion_summary": {"total": 1, "avg_commission": 5, "total_estimated_commission": 10},
            "feedback_success": True,
            "data_source": "taobao",
        }

    def fake_save_selection(result, params=None):
        return 1001, {"top_products": [
            {"product_id": "p1", "product_name": "商品1", "item_url": "http://x/1", "hot_score": 88}]}

    def fake_save_ad(result, params=None):
        return 1002, {"top_products": [
            {"product_id": "p2", "product_name": "商品2", "item_url": "http://x/2", "promotion_score": 90}]}

    monkeypatch.setattr(app_module.product_selection_agent, "analyze_category", fake_analyze)
    monkeypatch.setattr(app_module.ad_optimization_agent, "optimize_campaigns", fake_optimize)
    monkeypatch.setattr(app_module.report_store, "save_selection_report", fake_save_selection)
    monkeypatch.setattr(app_module.report_store, "save_ad_report", fake_save_ad)
    monkeypatch.setattr(app_module.dingtalk, "send_launch_links", lambda *a, **k: False)
    with TestClient(app) as c:
        yield c


def test_system_status(client):
    r = client.get("/api/v1/system/status")
    assert r.status_code == 200
    d = r.json()
    assert d["code"] == 0
    assert d["data"]["version"] == app_module.settings.VERSION


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["version"] == app_module.settings.VERSION


def test_auth_required_when_token_configured(client, monkeypatch):
    monkeypatch.setattr(app_module.settings, "WEB_ACCESS_TOKEN", "test-token")
    assert client.get("/api/v1/system/status").status_code == 401
    assert client.get("/api/v1/system/status", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.get("/api/v1/system/status", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200


def test_login_flow(client, monkeypatch):
    monkeypatch.setattr(app_module.settings, "WEB_ACCESS_TOKEN", "test-token")
    assert client.post("/api/v1/auth/login", json={"token": "bad"}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"token": "test-token"})
    assert r.status_code == 200 and r.json()["code"] == 0


def test_selection_analyze(client):
    r = client.post("/api/v1/selection/analyze", json={"category": "无线蓝牙耳机"})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["report_id"] == 1001
    assert d["top_products"]


def test_auto_launch_links_by_source(client):
    r = client.post("/api/v1/auto/launch", json={"category": "耳机", "top_n": 5, "push_dingtalk": False})
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["link_count"] >= 1
    assert "选品" in d["links_by_source"] and "投放" in d["links_by_source"]


def test_products_list_shape(client):
    r = client.get("/api/v1/products?limit=10&offset=0")
    assert r.status_code == 200
    d = r.json()["data"]
    assert "items" in d and "total" in d and "stats" in d


def test_unknown_route_returns_json_error(client):
    r = client.get("/api/v1/not_exist")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == 404 and "data" in body

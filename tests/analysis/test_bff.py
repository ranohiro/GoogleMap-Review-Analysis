"""BFF API エンドポイントのテスト (test_bff.py)"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.server import create_app


@pytest.fixture
def client(mock_env):
    """BFF API テスト用クライアント。"""
    app = create_app()
    return TestClient(app)


def test_health_check(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_meta_endpoint(client):
    res = client.get("/api/meta")
    assert res.status_code == 200
    data = res.json()
    assert data["prompt_version"] == "aspect_v1"
    assert "taste" in data["aspects"]
    assert data["total_reviews"] == 25
    assert data["tagged_reviews"] == 20
    assert data["has_tagged_data"] is True


def test_filters_options(client):
    res = client.get("/api/filters/options")
    assert res.status_code == 200
    data = res.json()
    assert len(data["stores"]) >= 2
    assert "赤から" in data["brands"]
    assert "ja" in data["languages"]


def test_overview_endpoint(client):
    res = client.post("/api/overview", json={})
    assert res.status_code == 200
    data = res.json()
    assert "prefectures" in data
    assert "scatter" in data
    assert data["summary"]["total_stores"] >= 3
    # 散布図データに reviews_count と rating が含まれる
    s0 = data["scatter"][0]
    assert "reviews_count" in s0
    assert "rating" in s0
    assert "store_name" in s0


def test_aspects_endpoint(client):
    res = client.post("/api/aspects", json={})
    assert res.status_code == 200
    data = res.json()
    assert data["has_tagged_data"] is True
    aspects = data["aspects"]
    assert len(aspects) == 7
    # 各観点レコードの検証
    a0 = aspects[0]
    assert "mention_rate" in a0
    assert "avg_sentiment" in a0
    assert "net_sentiment" in a0
    assert "neg_rate" in a0
    assert "is_reference" in a0


def test_subtopics_endpoint(client):
    res = client.post(
        "/api/aspects/subtopics",
        json={"aspect": "taste", "sentiment": "pos", "k": 5},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["aspect"] == "taste"
    assert isinstance(data["subtopics"], list)


def test_low_rating_endpoint(client):
    res = client.post("/api/low-rating", json={})
    assert res.status_code == 200
    data = res.json()
    assert "drivers" in data
    assert "aspect_evidence" in data
    d0 = data["drivers"][0]
    assert "lift" in d0
    assert "low_negs" in d0


def test_reviews_search_and_pii(client):
    res = client.post(
        "/api/reviews",
        json={"page": 1, "page_size": 10},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 25
    assert len(data["reviews"]) == 10
    # PII が含まれていないことの検証
    r0 = data["reviews"][0]
    assert "reviewer_name" not in r0
    assert "reviewer_id" not in r0
    assert "review_uid" in r0
    assert "review_text" in r0
    assert "aspects" in r0


def test_reviews_csv_export(client):
    res = client.post("/api/reviews/export", json={})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    content = res.content.decode("utf-8-sig")
    assert "review_uid" in content
    assert "review_text" in content
    # PII 列が CSV に出力されていないこと
    assert "reviewer_name" not in content
    assert "reviewer_id" not in content


def test_compare_endpoint(client):
    res = client.post(
        "/api/compare",
        json={"metric": "mention_rate", "use_shrinkage": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert "stores" in data
    assert "aspects" in data
    assert "matrix" in data
    assert "reply_rates" in data


def test_trends_endpoint(client):
    res = client.post(
        "/api/trends",
        json={"exclude_estimated": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert "monthly" in data
    assert "excluded_estimated_count" in data


def test_static_assets(client):
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "text/html" in res_index.headers["content-type"]
    assert "口コミ分析ツール" in res_index.text

    res_css = client.get("/static/css/style.css")
    assert res_css.status_code == 200

    res_app_js = client.get("/static/js/app.js")
    assert res_app_js.status_code == 200

    res_charts_js = client.get("/static/js/charts.js")
    assert res_charts_js.status_code == 200

"""API プロバイダのデータマッピングテスト (test_mapping.py)"""
from __future__ import annotations

import pandas as pd
import pytest

from src.api.base import Target
from src.api.providers import apify
from src.api import targets
from src.api.writer import RAW_COLUMNS, write_raw_csv


def test_targets_resolution():
    t_all = targets.get_targets()
    assert len(t_all) >= 10

    t_store2 = targets.get_target_by_key("store_2")
    assert t_store2.store_key == "store_2"
    assert "つくば" in t_store2.store_name

    with pytest.raises(ValueError):
        targets.get_target_by_key("store_9999")


def test_apify_to_rows_mapping():
    target = Target(
        store_key="store_10",
        store_name="赤から 新潟万代シティ店",
        url="https://maps.test/store10",
        place_id="ChIJSUSnZgzJ9F8RWQJn7nWhTeE",
    )

    mock_record = {
        "reviewId": "Ci9DQU_mock_id",
        "name": "テスト太郎",
        "reviewerId": "1234567890",
        "isLocalGuide": True,
        "reviewerNumberOfReviews": 15,
        "stars": 4,
        "text": "鍋がとても美味しかったです。",
        "publishedAtDate": "2026-10-06T12:09:54.000Z", # UTC 12:09 -> JST 21:09
        "publishAt": "3 週間前",
        "responseFromOwnerText": "ご来店ありがとうございます。",
        "responseFromOwnerDate": "2026-10-07T01:00:00.000Z", # UTC 01:00 -> JST 10:00
    }

    rows = apify.to_rows([mock_record], target)
    assert len(rows) == 1
    r = rows[0]

    assert r["store_name"] == "赤から 新潟万代シティ店"
    assert r["review_id"] == "Ci9DQU_mock_id"
    assert r["reviewer_name"] == "テスト太郎"
    assert r["is_local_guide"] is True
    assert r["reviewer_review_count"] == 15
    assert r["rating"] == 4
    assert r["review_text"] == "鍋がとても美味しかったです。"
    assert r["post_time"] == "2026-10-06 21:09:54"
    assert r["relative_time"] == "3 週間前"
    assert r["owner_reply"] == "ご来店ありがとうございます。"
    assert r["owner_reply_time"] == "2026-10-07 10:00:00"
    assert r["source_url"] == target.url


def test_write_raw_csv(tmp_path):
    target = Target(
        store_key="store_test",
        store_name="テスト店舗",
        url="https://maps.test",
    )
    rows = [{
        "store_name": "テスト店舗",
        "review_id": "rev_01",
        "reviewer_name": "User A",
        "reviewer_id": "1",
        "is_local_guide": False,
        "reviewer_review_count": 2,
        "reviewer_attributes": "",
        "rating": 5,
        "review_text": "Good",
        "post_time": "2026-10-01 12:00:00",
        "updated_time": "",
        "relative_time": "1日前",
        "owner_reply": "",
        "owner_reply_time": "",
        "source_url": "https://maps.test",
    }]

    out = write_raw_csv(rows, target, output_dir=str(tmp_path))
    assert out.endswith(".csv")

    df = pd.read_csv(out, encoding="utf-8-sig")
    assert list(df.columns) == RAW_COLUMNS
    assert len(df) == 1
    assert df["review_id"].iloc[0] == "rev_01"

"""データ読み込みモジュールのテスト (test_load.py)"""
from __future__ import annotations

import os
import pandas as pd
import pytest

from src.analysis import load


def test_pii_columns_are_dropped(mock_env):
    """個人特定情報 (reviewer_name, reviewer_id, reviewer_attributes) が除外されていることを検証。"""
    df = load.load_reviews()
    assert not df.empty
    assert "reviewer_name" not in df.columns
    assert "reviewer_id" not in df.columns
    assert "reviewer_attributes" not in df.columns
    assert "review_uid" in df.columns
    assert "review_text" in df.columns


def test_store_key_assignment(mock_env):
    """store_id から店舗マスタの store_key が付与されることを検証。"""
    df = load.load_reviews()
    assert "store_key" in df.columns
    # mock_store_1 は store_1 にマッピングされる
    sub1 = df[df["store_id"] == "mock_store_1"]
    assert (sub1["store_key"] == "store_1").all()

    # mock_store_2 は store_2 にマッピングされる
    sub2 = df[df["store_id"] == "mock_store_2"]
    assert (sub2["store_key"] == "store_2").all()


def test_fallback_when_tagged_missing(isolated_env):
    """reviews_tagged.parquet が存在しない場合、reviews.parquet を読み込み llm_tagged=False になることを検証。"""
    data_dir = isolated_env["data_dir"]
    tagged_file = os.path.join(data_dir, "reviews_tagged.parquet")
    if os.path.exists(tagged_file):
        os.remove(tagged_file)

    df = load.load_reviews()
    assert not df.empty
    assert "llm_tagged" in df.columns
    assert (df["llm_tagged"] == False).all()
    assert "taste_mentioned" in df.columns
    assert (df["taste_mentioned"] == False).all()


def test_places_matching(mock_env):
    """店舗一覧と店舗マスタの結合（place_id 一致 -> 店名一致 -> マスタ外）を検証。"""
    places = load.load_places()
    assert not places.empty
    assert "in_master" in places.columns
    assert "store_key" in places.columns

    # 1. placeId で一致 (架空赤から 渋谷店 -> store_1)
    p_shibuya = places[places["store_name"] == "架空赤から 渋谷店"].iloc[0]
    assert p_shibuya["in_master"] == True
    assert p_shibuya["store_key"] == "store_1"

    # 2. 店名で一致 (架空赤から 池袋店: place_idがマスタ側で空 -> store_3)
    p_ikebukuro = places[places["store_name"] == "架空赤から 池袋店"].iloc[0]
    assert p_ikebukuro["in_master"] == True
    assert p_ikebukuro["store_key"] == "store_3"

    # 3. マスタ外店舗 (横浜西口店、名古屋駅前店)
    p_yokohama = places[places["store_name"] == "架空赤から 横浜西口店"].iloc[0]
    assert p_yokohama["in_master"] == False
    assert pd.isna(p_yokohama["store_key"])


def test_load_all(mock_env):
    """load_all が Dataset を正しく返すことを検証。"""
    ds = load.load_all()
    assert isinstance(ds, load.Dataset)
    assert not ds.reviews.empty
    assert not ds.aspects.empty
    assert not ds.places.empty
    assert ds.metadata["prompt_version"] == "aspect_v1"
    # 口コミが収集されている店舗 (store_1, store_2) の has_reviews が True
    places = ds.places
    shibuya = places[places["store_key"] == "store_1"].iloc[0]
    assert shibuya["has_reviews"] == True

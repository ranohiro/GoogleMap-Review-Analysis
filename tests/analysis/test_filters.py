"""フィルタリングモジュールのテスト (test_filters.py)"""
from __future__ import annotations

import pandas as pd
import pytest

from src.analysis import filters, load


def test_filter_by_store(mock_env):
    df = load.load_reviews()
    f1 = filters.apply(df, stores=["store_1"])
    assert (f1["store_key"] == "store_1").all()
    assert len(f1) == 15

    f2 = filters.apply(df, stores=["store_2"])
    assert (f2["store_key"] == "store_2").all()
    assert len(f2) == 10


def test_filter_by_ratings(mock_env):
    df = load.load_reviews()
    f = filters.apply(df, ratings=[1, 2])
    assert set(f["rating"].unique()).issubset({1, 2})


def test_filter_by_languages(mock_env):
    df = load.load_reviews()
    f_en = filters.apply(df, languages=["en"])
    assert (f_en["language"] == "en").all()
    assert len(f_en) == 2


def test_filter_by_has_text(mock_env):
    df = load.load_reviews()
    f_text = filters.apply(df, has_text=True)
    assert (f_text["has_text"] == True).all()
    assert len(f_text) == 20

    f_no_text = filters.apply(df, has_text=False)
    assert (f_no_text["has_text"] == False).all()
    assert len(f_no_text) == 5


def test_filter_by_exclude_estimated_time(mock_env):
    df = load.load_reviews()
    f = filters.apply(df, exclude_estimated_time=True)
    assert (f["time_is_estimated"] == False).all()


def test_filter_by_query(mock_env):
    df = load.load_reviews()
    f = filters.apply(df, query="呼び出しボタン")
    assert len(f) >= 2
    for text in f["review_text"]:
        assert "呼び出しボタン" in text


def test_filter_by_aspect_and_sentiment(mock_env):
    df = load.load_reviews()
    # service 観点に言及があり、かつ否定的な口コミ
    f = filters.apply(df, aspect="service", sentiment_filter="neg")
    assert (f["service_neg"] == 1.0).all()
    assert len(f) > 0

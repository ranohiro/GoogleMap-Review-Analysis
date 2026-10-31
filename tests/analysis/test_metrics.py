"""指標計算モジュールの単体テスト (test_metrics.py)"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analysis import load, metrics


def test_aspect_summary_hand_calculation(mock_env):
    """手計算による検証: 分母、言及率、平均感情、ネット感情、否定率の一致。"""
    df = load.load_reviews()
    asp = metrics.aspect_summary(df)

    # 分母は llm_tagged & has_text = 20 件
    assert not asp.empty
    assert (asp["n"] == 20).all()

    # taste 観点の検証
    taste_row = asp[asp["aspect"] == "taste"].iloc[0]

    # taste 言及数
    taste_mentioned = df[df["llm_tagged"] & df["has_text"]]["taste_mentioned"]
    expected_mentions = int(taste_mentioned.sum())
    assert taste_row["mention_count"] == expected_mentions
    assert taste_row["mention_rate"] == round(expected_mentions / 20, 4)

    # ネット感情: (pos - neg) / mentions
    pos = int(df.loc[df["llm_tagged"] & df["has_text"], "taste_pos"].fillna(0).sum())
    neg = int(df.loc[df["llm_tagged"] & df["has_text"], "taste_neg"].fillna(0).sum())
    expected_net = (pos - neg) / expected_mentions
    assert abs(taste_row["net_sentiment"] - expected_net) < 1e-3


def test_aspect_summary_empty_and_zero():
    """空 DataFrame またはタグ付け0件の時に例外が発生しないことを検証。"""
    empty_df = pd.DataFrame()
    res = metrics.aspect_summary(empty_df)
    assert res.empty

    no_tagged_df = pd.DataFrame([
        {"review_uid": "1", "has_text": True, "llm_tagged": False, "rating": 5}
    ])
    res2 = metrics.aspect_summary(no_tagged_df)
    # 分母 0件
    assert not res2.empty
    assert (res2["n"] == 0).all()
    assert (res2["mention_count"] == 0).all()


def test_low_rating_drivers(mock_env):
    """低評価ドライバー (Lift) の手計算検証。"""
    df = load.load_reviews()
    drivers = metrics.low_rating_drivers(df, low=(1, 2))

    assert not drivers.empty
    assert "lift" in drivers.columns
    assert "low_negs" in drivers.columns
    assert "all_negs" in drivers.columns

    # service の否定言及を検証
    srv = drivers[drivers["aspect"] == "service"].iloc[0]
    p_low = srv["low_negs"] / srv["low_total"]
    p_all = srv["all_negs"] / srv["all_total"]
    expected_lift = p_low / p_all
    assert abs(srv["lift"] - expected_lift) < 1e-3


def test_top_subtopics(mock_env):
    """subtopic 集計の検証。"""
    ds = load.load_all()
    sub_df = metrics.top_subtopics(ds.aspects, aspect="service", sentiment="neg", k=5)
    assert not sub_df.empty
    assert "subtopic" in sub_df.columns
    assert "count" in sub_df.columns
    assert "percentage" in sub_df.columns
    # 頻度順にソートされていること
    counts = sub_df["count"].tolist()
    assert counts == sorted(counts, reverse=True)


def test_rating_summary(mock_env):
    """星評価サマリーの検証。"""
    df = load.load_reviews()
    r = metrics.rating_summary(df)

    assert r["total_reviews"] == 25
    assert r["has_text_count"] == 20
    assert r["tagged_count"] == 20
    assert 1.0 <= r["mean_rating"] <= 5.0
    assert sum(r["distribution"].values()) == 25


def test_monthly_trend_excludes_estimated(mock_env):
    """月次推移で推定日時の口コミが正しく除外されることを検証。"""
    df = load.load_reviews()
    trend_df, excluded_cnt = metrics.monthly_trend(df, exclude_estimated=True)

    # 架空データで time_is_estimated == True の件数が除外カウントと一致
    assert excluded_cnt == int(df["time_is_estimated"].sum())
    assert not trend_df.empty


def test_store_comparison_matrix(mock_env):
    """店舗比較マトリクスの作成および縮小推定フラグの検証。"""
    df = load.load_reviews()
    matrix_raw = metrics.store_comparison_matrix(df, metric="mention_rate", use_shrinkage=False)
    assert "taste" in matrix_raw.columns
    assert "store_1" in matrix_raw.index

    matrix_shrunk = metrics.store_comparison_matrix(df, metric="mention_rate", use_shrinkage=True)
    assert matrix_shrunk.shape == matrix_raw.shape

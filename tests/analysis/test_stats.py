"""統計計算モジュールの単体テスト (test_stats.py)"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analysis.stats import (
    MIN_N,
    bootstrap_ci,
    bootstrap_lift_ci,
    is_reference_sample,
    shrinkage_estimation,
    wilson_score_interval,
)


def test_is_reference_sample():
    assert is_reference_sample(0) is True
    assert is_reference_sample(19) is True
    assert is_reference_sample(20) is False
    assert is_reference_sample(100) is False


def test_wilson_score_interval_edges():
    # n = 0 のとき
    low, upp = wilson_score_interval(0, 0)
    assert low == 0.0 and upp == 0.0

    # count = 0, n > 0 のとき
    low, upp = wilson_score_interval(0, 50)
    assert low == 0.0
    assert 0.0 < upp < 0.1

    # count = n, n > 0 のとき
    low, upp = wilson_score_interval(50, 50)
    assert 0.9 < low < 1.0
    assert upp == 1.0


def test_wilson_score_interval_values():
    # 50/100 = 0.5 の95%区間
    low, upp = wilson_score_interval(50, 100)
    assert 0.39 < low < 0.41
    assert 0.59 < upp < 0.61
    assert low < 0.5 < upp


def test_bootstrap_ci():
    # 空配列
    low, upp = bootstrap_ci([])
    assert np.isnan(low) and np.isnan(upp)

    # 1要素
    low, upp = bootstrap_ci([4.0])
    assert low == 4.0 and upp == 4.0

    # 全て同一値
    low, upp = bootstrap_ci([3.0, 3.0, 3.0, 3.0])
    assert low == 3.0 and upp == 3.0

    # 一般データ
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    low, upp = bootstrap_ci(data, random_state=42)
    assert 1.0 <= low <= 3.0
    assert 3.0 <= upp <= 5.0
    assert low <= upp


def test_bootstrap_lift_ci():
    # 0件のケース
    low, upp = bootstrap_lift_ci(0, 10, 0, 50)
    assert np.isnan(low) and np.isnan(upp)

    # 低評価 10件中5件否定、全体 50件中10件否定
    # p_low = 0.5, p_all = 0.2 -> Lift = 2.5
    low, upp = bootstrap_lift_ci(low_negs=5, low_total=10, all_negs=10, all_total=50)
    assert not np.isnan(low)
    assert not np.isnan(upp)
    assert low < 2.5 < upp


def test_shrinkage_estimation():
    # 店舗A: 1/1 (100%), 店舗B: 10/100 (10%), 店舗C: 5/50 (10%)
    # 全体平均は 16/151 ≈ 10.6%
    # 店舗A (n=1) は全体平均(10.6%)近くに強く縮小されるべき
    df = pd.DataFrame([
        {"store": "A", "count": 1, "n": 1},
        {"store": "B", "count": 10, "n": 100},
        {"store": "C", "count": 5, "n": 50},
    ])
    shrunk = shrinkage_estimation(df, count_col="count", n_col="n", prior_weight=10.0)

    # 店舗Aの元レートは 1.0 だが、縮小後は大幅に低下して全体平均(約0.1)に近づく
    assert shrunk.iloc[0] < 0.3
    # 店舗B (n=100) はデータ量が多いため元レート(0.10)に近い
    assert abs(shrunk.iloc[1] - 0.10) < 0.02

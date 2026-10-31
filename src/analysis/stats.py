"""統計計算・信頼区間・縮小推定モジュール。

- Wilson score interval: 割合の95%信頼区間（言及率・否定率・本文あり率・返信率）
- Bootstrap CI: 平均（星・感情）およびLiftの95%信頼区間
- Empirical Bayes shrinkage: ベータ二項分布による縮小推定（店舗比較用）
- MIN_N = 20: 参考値判定のしきい値
"""
from __future__ import annotations

from typing import Callable, Sequence, Tuple
import numpy as np
import pandas as pd

MIN_N: int = 20
Z_95: float = 1.959963984540054  # 95% 信頼区間の z 値 (alpha=0.05)


def is_reference_sample(n: int, min_n: int = MIN_N) -> bool:
    """分母 n が min_n 未満の場合、参考値（True）と判定する。"""
    return int(n) < min_n


def wilson_score_interval(
    count: int,
    n: int,
    confidence: float = 0.95,
) -> Tuple[float, float]:
    """Wilson のスコア区間による割合の信頼区間を計算する。

    Parameters
    ----------
    count : int
        成功数（分子）
    n : int
        試行数（分母）
    confidence : float
        信頼係数（既定 0.95）

    Returns
    -------
    (ci_lower, ci_upper) : Tuple[float, float]
    """
    if n <= 0:
        return (0.0, 0.0)

    count = max(0, min(int(count), int(n)))
    n = int(n)

    # 信頼係数に応じた z 値
    if abs(confidence - 0.95) < 1e-4:
        z = Z_95
    else:
        # 近似または scipy がない場合の標準正規分布分位点
        from math import erf
        # 簡易近似（0.90, 0.95, 0.99 に対応）
        if abs(confidence - 0.90) < 1e-4:
            z = 1.6448536269514722
        elif abs(confidence - 0.99) < 1e-4:
            z = 2.5758293035489004
        else:
            z = Z_95

    p = count / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denominator
    margin = (z / denominator) * np.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * n * n)))

    lower = max(0.0, float(center - margin))
    upper = min(1.0, float(center + margin))
    return (lower, upper)


def bootstrap_ci(
    data: Sequence[float] | np.ndarray,
    stat_func: Callable[[np.ndarray], float] = np.mean,
    n_resamples: int = 1000,
    confidence: float = 0.95,
    random_state: int = 42,
) -> Tuple[float, float]:
    """1次元配列に対するノンパラメトリックブートストラップ信頼区間。

    Parameters
    ----------
    data : Sequence[float] | np.ndarray
        サンプルデータ
    stat_func : Callable
        統計量関数（既定 np.mean）
    n_resamples : int
        リサンプリング回数（既定 1,000）
    confidence : float
        信頼係数（既定 0.95）
    random_state : int
        乱数シード（既定 42）

    Returns
    -------
    (ci_lower, ci_upper) : Tuple[float, float]
    """
    arr = np.asarray(data, dtype=float)
    arr = arr[~np.isnan(arr)]
    n = len(arr)

    if n == 0:
        return (float("nan"), float("nan"))
    if n == 1 or np.all(arr == arr[0]):
        val = float(arr[0])
        return (val, val)

    rng = np.random.default_rng(random_state)
    indices = rng.integers(0, n, size=(n_resamples, n))
    resamples = arr[indices]

    # stat_func が axis を受け取るか試行
    try:
        sample_stats = stat_func(resamples, axis=1)  # type: ignore
    except TypeError:
        sample_stats = np.array([stat_func(resamples[i]) for i in range(n_resamples)])

    alpha = (1.0 - confidence) / 2.0
    lower = float(np.percentile(sample_stats, 100.0 * alpha))
    upper = float(np.percentile(sample_stats, 100.0 * (1.0 - alpha)))
    return (lower, upper)


def bootstrap_lift_ci(
    low_negs: int,
    low_total: int,
    all_negs: int,
    all_total: int,
    n_resamples: int = 1000,
    confidence: float = 0.95,
    random_state: int = 42,
) -> Tuple[float, float]:
    """低評価グループ（★1〜2）と全体グループにおける否定言及 Lift のブートストラップ信頼区間。

    Lift = P(neg | low) / P(neg | all)
         = (low_negs / low_total) / (all_negs / all_total)
    """
    if low_total <= 0 or all_total <= 0 or all_negs <= 0:
        return (float("nan"), float("nan"))

    rng = np.random.default_rng(random_state)

    # 0/1 配列を生成
    low_arr = np.zeros(low_total, dtype=float)
    low_arr[:low_negs] = 1.0

    all_arr = np.zeros(all_total, dtype=float)
    all_arr[:all_negs] = 1.0

    low_idx = rng.integers(0, low_total, size=(n_resamples, low_total))
    all_idx = rng.integers(0, all_total, size=(n_resamples, all_total))

    p_low_boot = low_arr[low_idx].mean(axis=1)
    p_all_boot = all_arr[all_idx].mean(axis=1)

    # 0 除算を防ぐ
    valid = p_all_boot > 0
    if not np.any(valid):
        return (float("nan"), float("nan"))

    lift_boot = np.where(valid, p_low_boot / np.where(valid, p_all_boot, 1.0), np.nan)
    lift_boot = lift_boot[~np.isnan(lift_boot)]

    if len(lift_boot) == 0:
        return (float("nan"), float("nan"))

    alpha = (1.0 - confidence) / 2.0
    lower = float(np.percentile(lift_boot, 100.0 * alpha))
    upper = float(np.percentile(lift_boot, 100.0 * (1.0 - alpha)))
    return (lower, upper)


def shrinkage_estimation(
    df: pd.DataFrame,
    count_col: str,
    n_col: str,
    prior_weight: float | None = None,
) -> pd.Series:
    """店舗ごとの割合（count_col / n_col）を全体平均に寄せるベータ二項分布による経験ベイズ縮小推定。

    Parameters
    ----------
    df : pd.DataFrame
        集計データフレーム
    count_col : str
        分子列名
    n_col : str
        分母列名
    prior_weight : float | None
        事前分布の重み (alpha + beta)。None の場合はモーメント法で自動推定。

    Returns
    -------
    shrunk_rates : pd.Series
        縮小推定された割合（各行に対応）
    """
    if df.empty or count_col not in df.columns or n_col not in df.columns:
        return pd.Series(dtype=float)

    counts = df[count_col].fillna(0).astype(float)
    totals = df[n_col].fillna(0).astype(float)

    total_counts = counts.sum()
    total_trials = totals.sum()

    if total_trials <= 0:
        return pd.Series(0.0, index=df.index)

    overall_rate = total_counts / total_trials

    # 事前分布パラメータ (alpha, beta) の推定
    if prior_weight is not None and prior_weight > 0:
        m = prior_weight
    else:
        # モーメント法による間接推定
        valid = totals >= 5
        if valid.sum() >= 3:
            rates = counts[valid] / totals[valid]
            sample_var = float(rates.var())
            mean_n = float(totals[valid].mean())
            sampling_var = (overall_rate * (1.0 - overall_rate)) / mean_n if mean_n > 0 else 0.0
            tau2 = max(0.0, sample_var - sampling_var)

            if tau2 > 1e-6 and overall_rate * (1.0 - overall_rate) > tau2:
                m = (overall_rate * (1.0 - overall_rate) / tau2) - 1.0
                m = float(np.clip(m, 2.0, 100.0))
            else:
                m = 10.0
        else:
            m = 10.0

    alpha = overall_rate * m
    beta = (1.0 - overall_rate) * m

    shrunk = (counts + alpha) / (totals + alpha + beta)
    return pd.Series(shrunk, index=df.index, name=f"{count_col}_shrunk")

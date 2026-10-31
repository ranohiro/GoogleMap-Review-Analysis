"""指標計算モジュール (metrics.py)

各画面およびCLIで共通して使用する分析指標を計算する。
- 観点集計 (aspect_summary): 言及率、平均感情、ネット感情、否定率、信頼区間
- 低評価ドライバー (low_rating_drivers): ★1〜2での否定言及 Lift と信頼区間
- 具体的な対象の集計 (top_subtopics): 観点ごとの頻出 subtopic
- 星評価サマリー (rating_summary): 平均星・星分布・本文あり率
- オーナー返信指標 (owner_reply_metrics): 返信率・低評価返信率・返信日数
- 月次推移 (monthly_trend): 推定日時の除外と月別指標
- 前後比較 (before_after_comparison): 指定日を挟んだ施策効果比較
- 店舗比較マトリクス (store_comparison_matrix): 店舗×観点の比較と縮小推定
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple
import numpy as np
import pandas as pd

from src.analysis.stats import (
    MIN_N,
    bootstrap_ci,
    bootstrap_lift_ci,
    is_reference_sample,
    shrinkage_estimation,
    wilson_score_interval,
)
from src.pipeline.paths import ASPECTS


def aspect_summary(
    df: pd.DataFrame,
    by: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """観点ごとの言及数・言及率・平均感情・ネット感情・否定率と信頼区間を計算する。

    分母は「タグ付け済みで本文がある口コミ (llm_tagged & has_text)」。

    Parameters
    ----------
    df : pd.DataFrame
        口コミデータ
    by : Optional[Sequence[str]]
        グループ化キー（例: ["store_key"]）

    Returns
    -------
    pd.DataFrame
        各観点（および by 指定時は各グループ×観点）の集計結果
    """
    if df.empty:
        return pd.DataFrame()

    # 分母の抽出: llm_tagged & has_text
    is_tagged = df.get("llm_tagged", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    has_text = df.get("has_text", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    valid_df = df[is_tagged & has_text]

    def _calc_aspects_for_group(sub_df: pd.DataFrame, grp_keys: Dict[str, str]) -> List[Dict]:
        n = len(sub_df)
        is_ref = is_reference_sample(n)
        rows = []

        for aspect_key, aspect_label in ASPECTS.items():
            mentioned_col = f"{aspect_key}_mentioned"
            sent_col = f"{aspect_key}_sent"
            pos_col = f"{aspect_key}_pos"
            neg_col = f"{aspect_key}_neg"

            if mentioned_col not in sub_df.columns:
                rows.append({
                    **grp_keys,
                    "aspect": aspect_key,
                    "aspect_label": aspect_label,
                    "n": n,
                    "mention_count": 0,
                    "mention_rate": 0.0,
                    "mention_rate_ci_lower": 0.0,
                    "mention_rate_ci_upper": 0.0,
                    "avg_sentiment": np.nan,
                    "avg_sentiment_ci_lower": np.nan,
                    "avg_sentiment_ci_upper": np.nan,
                    "pos_count": 0,
                    "neg_count": 0,
                    "net_sentiment": np.nan,
                    "neg_rate": 0.0,
                    "neg_rate_ci_lower": 0.0,
                    "neg_rate_ci_upper": 0.0,
                    "is_reference": is_ref,
                })
                continue

            mentioned_mask = sub_df[mentioned_col].fillna(False).astype(bool)
            mention_count = int(mentioned_mask.sum())
            mention_rate = mention_count / n if n > 0 else 0.0
            m_ci_low, m_ci_upp = wilson_score_interval(mention_count, n)

            # 感情 (-2〜+2)
            if mention_count > 0 and sent_col in sub_df.columns:
                sents = sub_df.loc[mentioned_mask, sent_col].dropna().astype(float).values
                if len(sents) > 0:
                    avg_sent = float(np.mean(sents))
                    s_ci_low, s_ci_upp = bootstrap_ci(sents, stat_func=np.mean)
                else:
                    avg_sent, s_ci_low, s_ci_upp = np.nan, np.nan, np.nan
            else:
                avg_sent, s_ci_low, s_ci_upp = np.nan, np.nan, np.nan

            # 肯定・否定数
            pos_count = int(sub_df.loc[mentioned_mask, pos_col].fillna(0).sum()) if pos_col in sub_df.columns else 0
            neg_count = int(sub_df.loc[mentioned_mask, neg_col].fillna(0).sum()) if neg_col in sub_df.columns else 0

            net_sentiment = (pos_count - neg_count) / mention_count if mention_count > 0 else np.nan

            # 否定率（分母 n に対する割合）
            neg_rate = neg_count / n if n > 0 else 0.0
            n_ci_low, n_ci_upp = wilson_score_interval(neg_count, n)

            rows.append({
                **grp_keys,
                "aspect": aspect_key,
                "aspect_label": aspect_label,
                "n": n,
                "mention_count": mention_count,
                "mention_rate": round(mention_rate, 4),
                "mention_rate_ci_lower": round(m_ci_low, 4),
                "mention_rate_ci_upper": round(m_ci_upp, 4),
                "avg_sentiment": round(avg_sent, 3) if not np.isnan(avg_sent) else np.nan,
                "avg_sentiment_ci_lower": round(s_ci_low, 3) if not np.isnan(s_ci_low) else np.nan,
                "avg_sentiment_ci_upper": round(s_ci_upp, 3) if not np.isnan(s_ci_upp) else np.nan,
                "pos_count": pos_count,
                "neg_count": neg_count,
                "net_sentiment": round(net_sentiment, 3) if not np.isnan(net_sentiment) else np.nan,
                "neg_rate": round(neg_rate, 4),
                "neg_rate_ci_lower": round(n_ci_low, 4),
                "neg_rate_ci_upper": round(n_ci_upp, 4),
                "is_reference": is_ref,
            })
        return rows

    if not by:
        results = _calc_aspects_for_group(valid_df, {})
        return pd.DataFrame(results)

    all_rows = []
    for keys, grp in valid_df.groupby(list(by)):
        if not isinstance(keys, tuple):
            keys = (keys,)
        grp_dict = {col: str(val) for col, val in zip(by, keys)}
        all_rows.extend(_calc_aspects_for_group(grp, grp_dict))

    return pd.DataFrame(all_rows)


def low_rating_drivers(
    df: pd.DataFrame,
    low: Tuple[int, ...] = (1, 2),
) -> pd.DataFrame:
    """★1〜2 での否定言及の件数と Lift および信頼区間を計算する。

    Lift = P(neg | ★1〜2) ÷ P(neg | 全体)
         = (low_negs / low_total) ÷ (all_negs / all_total)

    1 より大きいほど、低評価に特有の不満であることを示す。
    """
    if df.empty:
        return pd.DataFrame()

    is_tagged = df.get("llm_tagged", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    has_text = df.get("has_text", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    valid_df = df[is_tagged & has_text]

    all_total = len(valid_df)
    low_mask = valid_df["rating"].isin(low) if "rating" in valid_df.columns else pd.Series(False, index=valid_df.index)
    low_df = valid_df[low_mask]
    low_total = len(low_df)

    is_ref = is_reference_sample(low_total)

    rows = []
    for aspect_key, aspect_label in ASPECTS.items():
        neg_col = f"{aspect_key}_neg"
        if neg_col not in valid_df.columns:
            low_negs = 0
            all_negs = 0
        else:
            low_negs = int(low_df[neg_col].fillna(0).sum())
            all_negs = int(valid_df[neg_col].fillna(0).sum())

        p_low = low_negs / low_total if low_total > 0 else 0.0
        p_all = all_negs / all_total if all_total > 0 else 0.0

        if all_negs > 0 and p_all > 0 and low_total > 0:
            lift = p_low / p_all
            ci_low, ci_upp = bootstrap_lift_ci(low_negs, low_total, all_negs, all_total)
        else:
            lift = np.nan
            ci_low, ci_upp = np.nan, np.nan

        # 低評価群での否定割合の Wilson 区間
        p_low_ci_low, p_low_ci_upp = wilson_score_interval(low_negs, low_total)

        rows.append({
            "aspect": aspect_key,
            "aspect_label": aspect_label,
            "low_negs": low_negs,
            "low_total": low_total,
            "all_negs": all_negs,
            "all_total": all_total,
            "p_low": round(p_low, 4),
            "p_low_ci_lower": round(p_low_ci_low, 4),
            "p_low_ci_upper": round(p_low_ci_upp, 4),
            "p_all": round(p_all, 4),
            "lift": round(lift, 3) if not np.isnan(lift) else np.nan,
            "lift_ci_lower": round(ci_low, 3) if not np.isnan(ci_low) else np.nan,
            "lift_ci_upper": round(ci_upp, 3) if not np.isnan(ci_upp) else np.nan,
            "is_reference": is_ref,
        })

    res = pd.DataFrame(rows)
    # lift の降順で並べ替え（nan は後ろへ、同順位なら low_negs 降順）
    res = res.sort_values(by=["lift", "low_negs"], ascending=[False, False], na_position="last").reset_index(drop=True)
    return res


def top_subtopics(
    aspects_df: pd.DataFrame,
    aspect: str,
    sentiment: str = "neg",
    k: int = 10,
) -> pd.DataFrame:
    """ある観点の中で、よく言及される具体的な対象 (subtopic) を件数順に集計する。

    Parameters
    ----------
    aspects_df : pd.DataFrame
        review_aspects データフレーム
    aspect : str
        観点キー (例: "service")
    sentiment : str
        "neg" (否定 sentiment < 0), "pos" (肯定 sentiment > 0), "all" (全て)
    k : int
        上位取得件数
    """
    cols = ["subtopic", "count", "percentage", "verbatim_count", "verbatim_rate"]
    if aspects_df.empty or "aspect" not in aspects_df.columns:
        return pd.DataFrame(columns=cols)

    sub = aspects_df[aspects_df["aspect"] == aspect]
    if sentiment == "neg" and "sentiment" in sub.columns:
        sub = sub[sub["sentiment"] < 0]
    elif sentiment == "pos" and "sentiment" in sub.columns:
        sub = sub[sub["sentiment"] > 0]

    if sub.empty or "subtopic" not in sub.columns:
        return pd.DataFrame(columns=cols)

    valid_subtopics = sub[sub["subtopic"].notna() & (sub["subtopic"].str.strip() != "")]
    total_items = len(valid_subtopics)
    if total_items == 0:
        return pd.DataFrame(columns=cols)

    grouped = valid_subtopics.groupby("subtopic").agg(
        count=("review_uid", "count"),
        verbatim_count=("evidence_verbatim", lambda x: int(x.fillna(False).sum())),
    ).reset_index()

    grouped["percentage"] = (grouped["count"] / total_items).round(4)
    grouped["verbatim_rate"] = (grouped["verbatim_count"] / grouped["count"]).round(4)

    grouped = grouped.sort_values(by=["count", "verbatim_count"], ascending=[False, False]).head(k).reset_index(drop=True)
    return grouped


def rating_summary(df: pd.DataFrame) -> Dict:
    """星評価の分布・平均星・本文あり率・タグ付け率を計算する。"""
    if df.empty:
        return {
            "total_reviews": 0,
            "mean_rating": np.nan,
            "mean_rating_ci_lower": np.nan,
            "mean_rating_ci_upper": np.nan,
            "distribution": {str(i): 0 for i in range(1, 6)},
            "distribution_percent": {str(i): 0.0 for i in range(1, 6)},
            "has_text_count": 0,
            "has_text_rate": 0.0,
            "has_text_ci_lower": 0.0,
            "has_text_ci_upper": 0.0,
            "tagged_count": 0,
            "tagged_rate": 0.0,
            "is_reference": True,
        }

    total = len(df)
    ratings = df["rating"].dropna().astype(float).values
    if len(ratings) > 0:
        mean_r = float(np.mean(ratings))
        r_ci_low, r_ci_upp = bootstrap_ci(ratings, stat_func=np.mean)
    else:
        mean_r, r_ci_low, r_ci_upp = np.nan, np.nan, np.nan

    # 星分布
    dist = {str(i): 0 for i in range(1, 6)}
    dist_pct = {str(i): 0.0 for i in range(1, 6)}
    if "rating" in df.columns:
        counts = df["rating"].value_counts().to_dict()
        for i in range(1, 6):
            c = int(counts.get(i, counts.get(float(i), 0)))
            dist[str(i)] = c
            dist_pct[str(i)] = round(c / total, 4) if total > 0 else 0.0

    # 本文あり率
    has_text_cnt = int(df["has_text"].fillna(False).sum()) if "has_text" in df.columns else 0
    has_text_rate = has_text_cnt / total if total > 0 else 0.0
    ht_ci_low, ht_ci_upp = wilson_score_interval(has_text_cnt, total)

    # タグ付け済み数
    tagged_cnt = int(df["llm_tagged"].fillna(False).sum()) if "llm_tagged" in df.columns else 0
    tagged_rate = tagged_cnt / has_text_cnt if has_text_cnt > 0 else 0.0

    return {
        "total_reviews": total,
        "mean_rating": round(mean_r, 2) if not np.isnan(mean_r) else np.nan,
        "mean_rating_ci_lower": round(r_ci_low, 2) if not np.isnan(r_ci_low) else np.nan,
        "mean_rating_ci_upper": round(r_ci_upp, 2) if not np.isnan(r_ci_upp) else np.nan,
        "distribution": dist,
        "distribution_percent": dist_pct,
        "has_text_count": has_text_cnt,
        "has_text_rate": round(has_text_rate, 4),
        "has_text_ci_lower": round(ht_ci_low, 4),
        "has_text_ci_upper": round(ht_ci_upp, 4),
        "tagged_count": tagged_cnt,
        "tagged_rate": round(tagged_rate, 4),
        "is_reference": is_reference_sample(total),
    }


def owner_reply_metrics(df: pd.DataFrame) -> Dict:
    """オーナー返信の指標（全体返信率、★1〜2返信率、返信日数の中央値）を計算する。"""
    if df.empty or "has_owner_reply" not in df.columns:
        return {
            "total_reviews": 0,
            "reply_count": 0,
            "reply_rate": 0.0,
            "reply_rate_ci_lower": 0.0,
            "reply_rate_ci_upper": 0.0,
            "low_rating_total": 0,
            "low_rating_reply_count": 0,
            "low_rating_reply_rate": 0.0,
            "low_rating_reply_ci_lower": 0.0,
            "low_rating_reply_ci_upper": 0.0,
            "median_reply_days": None,
        }

    total = len(df)
    reply_cnt = int(df["has_owner_reply"].fillna(False).sum())
    reply_rate = reply_cnt / total if total > 0 else 0.0
    r_ci_low, r_ci_upp = wilson_score_interval(reply_cnt, total)

    # 低評価（★1〜2）での返信率
    low_df = df[df["rating"].isin([1, 2])] if "rating" in df.columns else pd.DataFrame()
    low_total = len(low_df)
    low_reply_cnt = int(low_df["has_owner_reply"].fillna(False).sum()) if low_total > 0 else 0
    low_reply_rate = low_reply_cnt / low_total if low_total > 0 else 0.0
    lr_ci_low, lr_ci_upp = wilson_score_interval(low_reply_cnt, low_total)

    # 返信までの日数の中央値
    median_days = None
    if "owner_reply_time" in df.columns and "post_time" in df.columns:
        replied = df[df["has_owner_reply"] & df["owner_reply_time"].notna() & df["post_time"].notna()]
        if not replied.empty:
            deltas = (replied["owner_reply_time"] - replied["post_time"]).dt.total_seconds() / 86400.0
            deltas = deltas[deltas >= 0]
            if len(deltas) > 0:
                median_days = round(float(deltas.median()), 1)

    return {
        "total_reviews": total,
        "reply_count": reply_cnt,
        "reply_rate": round(reply_rate, 4),
        "reply_rate_ci_lower": round(r_ci_low, 4),
        "reply_rate_ci_upper": round(r_ci_upp, 4),
        "low_rating_total": low_total,
        "low_rating_reply_count": low_reply_cnt,
        "low_rating_reply_rate": round(low_reply_rate, 4),
        "low_rating_reply_ci_lower": round(lr_ci_low, 4),
        "low_rating_reply_ci_upper": round(lr_ci_upp, 4),
        "median_reply_days": median_days,
    }


def language_distribution(df: pd.DataFrame) -> List[Dict]:
    """言語別の構成比と平均星を計算する。"""
    if df.empty or "language" not in df.columns:
        return []

    valid = df[df["language"].notna() & (df["language"] != "")]
    total = len(valid)
    if total == 0:
        return []

    res = []
    for lang, grp in valid.groupby("language"):
        cnt = len(grp)
        pct = cnt / total
        mean_r = float(grp["rating"].mean()) if "rating" in grp.columns and grp["rating"].notna().any() else np.nan
        res.append({
            "language": str(lang),
            "count": cnt,
            "percentage": round(pct, 4),
            "mean_rating": round(mean_r, 2) if not np.isnan(mean_r) else None,
        })

    res.sort(key=lambda x: x["count"], reverse=True)
    return res


def monthly_trend(
    df: pd.DataFrame,
    exclude_estimated: bool = True,
) -> Tuple[pd.DataFrame, int]:
    """月別の口コミ件数・平均星・観点別否定率を計算する。

    Parameters
    ----------
    df : pd.DataFrame
        口コミデータ
    exclude_estimated : bool
        推定日時 (time_is_estimated == True) を除外するか（設計書 §5.4: 月単位集計では除外推奨）

    Returns
    -------
    (trend_df, excluded_count) : Tuple[pd.DataFrame, int]
    """
    cols = ["year_month", "count", "avg_rating"]
    if df.empty or "post_time" not in df.columns:
        return pd.DataFrame(columns=cols), 0

    sub = df.copy()
    excluded_count = 0
    if exclude_estimated and "time_is_estimated" in sub.columns:
        est_mask = sub["time_is_estimated"].fillna(False).astype(bool)
        excluded_count = int(est_mask.sum())
        sub = sub[~est_mask]

    sub = sub[sub["post_time"].notna()]
    if sub.empty:
        return pd.DataFrame(columns=cols), excluded_count

    sub["year_month"] = sub["post_time"].dt.strftime("%Y-%m")

    # 月別基本指標
    grouped = sub.groupby("year_month")
    trend_rows = []

    for ym, grp in grouped:
        cnt = len(grp)
        avg_r = float(grp["rating"].mean()) if "rating" in grp.columns and grp["rating"].notna().any() else np.nan

        row = {
            "year_month": ym,
            "count": cnt,
            "avg_rating": round(avg_r, 2) if not np.isnan(avg_r) else None,
        }

        # 観点ごとの否定率
        tagged_grp = grp[grp.get("llm_tagged", False) & grp.get("has_text", False)]
        n_tagged = len(tagged_grp)
        for key in ASPECTS:
            neg_col = f"{key}_neg"
            if n_tagged > 0 and neg_col in tagged_grp.columns:
                negs = int(tagged_grp[neg_col].fillna(0).sum())
                row[f"{key}_neg_rate"] = round(negs / n_tagged, 4)
            else:
                row[f"{key}_neg_rate"] = None

        trend_rows.append(row)

    res_df = pd.DataFrame(trend_rows).sort_values("year_month").reset_index(drop=True)
    return res_df, excluded_count


def before_after_comparison(
    df: pd.DataFrame,
    split_date: str,
) -> Dict:
    """指定日を境にした前後期間の施策効果比較サマリーを計算する。"""
    if df.empty or "post_time" not in df.columns:
        return {"before": None, "after": None, "split_date": split_date}

    split_dt = pd.to_datetime(split_date)
    before_df = df[df["post_time"] < split_dt]
    after_df = df[df["post_time"] >= split_dt]

    return {
        "split_date": split_date,
        "before": {
            "ratings": rating_summary(before_df),
            "aspects": aspect_summary(before_df).to_dict(orient="records") if not before_df.empty else [],
        },
        "after": {
            "ratings": rating_summary(after_df),
            "aspects": aspect_summary(after_df).to_dict(orient="records") if not after_df.empty else [],
        },
    }


def store_comparison_matrix(
    df: pd.DataFrame,
    metric: str = "mention_rate",
    use_shrinkage: bool = False,
) -> pd.DataFrame:
    """店舗×観点のマトリクス表を作成する（Screen ⑤用）。

    Parameters
    ----------
    df : pd.DataFrame
        口コミデータ
    metric : str
        "mention_rate", "net_sentiment", "neg_rate", "avg_sentiment"
    use_shrinkage : bool
        True の場合、言及率・否定率に経験ベイズ縮小推定を適用する
    """
    if df.empty or "store_key" not in df.columns:
        return pd.DataFrame()

    asp_df = aspect_summary(df, by=["store_key"])
    if asp_df.empty:
        return pd.DataFrame()

    if use_shrinkage and metric in ["mention_rate", "neg_rate"]:
        # 縮小推定を観点ごとに適用
        shrunk_values = []
        for aspect_key in ASPECTS:
            sub = asp_df[asp_df["aspect"] == aspect_key].copy()
            count_col = "mention_count" if metric == "mention_rate" else "neg_count"
            sub["shrunk"] = shrinkage_estimation(sub, count_col=count_col, n_col="n")
            shrunk_values.append(sub[["store_key", "aspect", "shrunk"]])

        shrunk_df = pd.concat(shrunk_values, ignore_index=True)
        pivot = shrunk_df.pivot(index="store_key", columns="aspect", values="shrunk").round(4)
    else:
        pivot = asp_df.pivot(index="store_key", columns="aspect", values=metric)

    return pivot

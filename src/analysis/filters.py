"""フィルタリングモジュール (filters.py)

口コミデータ (reviews DataFrame) に対する各種絞り込みを行う。
- 店舗 (store_key / store_id)
- 期間 (開始日, 終了日)
- 星評価 (1〜5)
- 言語 (ja, en 等)
- 本文の有無 (has_text)
- 推定日時の除外 (exclude_estimated_time)
- キーワード検索 (review_text)
- 観点・感情 (特定の観点に言及、または肯定/否定)
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple
import pandas as pd


def apply(
    df: pd.DataFrame,
    stores: Optional[Sequence[str]] = None,
    period: Optional[Tuple[Optional[str], Optional[str]]] = None,
    ratings: Optional[Sequence[int]] = None,
    languages: Optional[Sequence[str]] = None,
    has_text: Optional[bool] = None,
    exclude_estimated_time: bool = False,
    query: Optional[str] = None,
    brand: Optional[str] = None,
    aspect: Optional[str] = None,
    sentiment_filter: Optional[str] = None,
) -> pd.DataFrame:
    """指定された条件で口コミ DataFrame を絞り込む。

    Parameters
    ----------
    df : pd.DataFrame
        対象の口コミ DataFrame
    stores : Optional[Sequence[str]]
        店舗キー (store_key) または店舗ID (store_id) のリスト
    period : Optional[Tuple[Optional[str], Optional[str]]]
        (開始日, 終了日) のタプル (YYYY-MM-DD 形式)
    ratings : Optional[Sequence[int]]
        星評価のリスト (例: [1, 2])
    languages : Optional[Sequence[str]]
        言語コードのリスト (例: ["ja", "en"])
    has_text : Optional[bool]
        本文の有無 (True: ありのみ, False: なしのみ, None: 全て)
    exclude_estimated_time : bool
        True の場合、相対表記から推定した日時 (time_is_estimated == True) を除外
    query : Optional[str]
        本文のフリーワード検索文字列
    brand : Optional[str]
        ブランド名
    aspect : Optional[str]
        観点キー (例: "taste", "service")
    sentiment_filter : Optional[str]
        "pos", "neg", "all"（観点感情での絞り込み）

    Returns
    -------
    filtered_df : pd.DataFrame
    """
    if df.empty:
        return df.copy()

    res = df.copy()

    # 1. 店舗
    if stores:
        valid_stores = [str(s) for s in stores if s]
        if valid_stores:
            key_mask = res["store_key"].isin(valid_stores) if "store_key" in res.columns else pd.Series(False, index=res.index)
            id_mask = res["store_id"].isin(valid_stores) if "store_id" in res.columns else pd.Series(False, index=res.index)
            res = res[key_mask | id_mask]

    # 2. ブランド
    if brand and "brand" in res.columns:
        res = res[res["brand"] == brand]

    # 3. 期間
    if period and "post_time" in res.columns:
        start_date, end_date = period
        if start_date:
            res = res[res["post_time"] >= pd.to_datetime(start_date)]
        if end_date:
            # 終了日の23:59:59まで含める
            res = res[res["post_time"] <= pd.to_datetime(f"{end_date} 23:59:59")]

    # 4. 星評価
    if ratings is not None and len(ratings) > 0 and "rating" in res.columns:
        valid_ratings = [int(r) for r in ratings]
        res = res[res["rating"].isin(valid_ratings)]

    # 5. 言語
    if languages is not None and len(languages) > 0 and "language" in res.columns:
        valid_langs = [str(l).lower() for l in languages]
        res = res[res["language"].str.lower().isin(valid_langs)]

    # 6. 本文の有無
    if has_text is not None and "has_text" in res.columns:
        res = res[res["has_text"] == bool(has_text)]

    # 7. 推定日時の除外
    if exclude_estimated_time and "time_is_estimated" in res.columns:
        res = res[~res["time_is_estimated"].fillna(False).astype(bool)]

    # 8. キーワード検索
    if query and "review_text" in res.columns:
        q = str(query).strip()
        if q:
            res = res[res["review_text"].fillna("").str.contains(q, case=False, regex=False)]

    # 9. 観点および感情
    if aspect:
        mentioned_col = f"{aspect}_mentioned"
        if mentioned_col in res.columns:
            res = res[res[mentioned_col].fillna(False).astype(bool)]
            if sentiment_filter == "pos":
                pos_col = f"{aspect}_pos"
                if pos_col in res.columns:
                    res = res[res[pos_col] == 1.0]
            elif sentiment_filter == "neg":
                neg_col = f"{aspect}_neg"
                if neg_col in res.columns:
                    res = res[res[neg_col] == 1.0]

    return res

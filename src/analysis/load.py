"""データ読み込み・統合モジュール (load.py)

データの唯一の入口。
- 口コミデータ (reviews_tagged.parquet または fallback: reviews.parquet) の読み込み
- 個人情報 (reviewer_name, reviewer_id, reviewer_attributes) の除外 (PII 保護)
- 店舗マスタ (stores.csv) との結合 (store_key の付与)
- 店舗一覧 (akakara_places_YYYYMMDD.csv) の読み込みとマスタ結合
- 観点詳細 (review_aspects.parquet) の読み込み
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.pipeline.paths import ASPECTS, MASTER_STORES, PROCESSED_DIR, PROMPT_VERSION

# PII（個人特定情報）列。これらは分析に不要であり絶対にメモリ上に保持・画面出力しない
PII_COLUMNS = ["reviewer_name", "reviewer_id", "reviewer_attributes"]


def get_data_dir() -> str:
    """環境変数 ANALYSIS_DATA_DIR または既定の PROCESSED_DIR を返す。"""
    return os.environ.get("ANALYSIS_DATA_DIR", PROCESSED_DIR)


def get_master_dir() -> str:
    """環境変数 ANALYSIS_MASTER_DIR または既定の data/master を返す。"""
    default_master = os.path.dirname(MASTER_STORES)
    return os.environ.get("ANALYSIS_MASTER_DIR", default_master)


def get_metadata() -> Dict[str, Optional[str]]:
    """データの更新日時と観点定義のバージョンを取得する。"""
    data_dir = get_data_dir()
    master_dir = get_master_dir()

    tagged_path = os.path.join(data_dir, "reviews_tagged.parquet")
    raw_path = os.path.join(data_dir, "reviews.parquet")
    aspects_path = os.path.join(data_dir, "review_aspects.parquet")

    def _file_mtime(path: str) -> Optional[str]:
        if os.path.exists(path):
            ts = os.path.getmtime(path)
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        return None

    return {
        "prompt_version": PROMPT_VERSION,
        "reviews_tagged_mtime": _file_mtime(tagged_path),
        "reviews_raw_mtime": _file_mtime(raw_path),
        "aspects_mtime": _file_mtime(aspects_path),
        "data_dir": data_dir,
        "master_dir": master_dir,
    }


def load_stores_master(master_dir: Optional[str] = None) -> pd.DataFrame:
    """店舗マスタ (stores.csv) を読み込む。"""
    mdir = master_dir or get_master_dir()
    stores_path = os.path.join(mdir, "stores.csv")

    cols = ["store_key", "store_id", "store_name", "brand", "genre", "area", "url", "place_id"]
    if not os.path.exists(stores_path):
        return pd.DataFrame(columns=cols)

    df = pd.read_csv(stores_path, encoding="utf-8")
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df["place_id"] = df["place_id"].fillna("").astype(str).str.strip()
    return df[cols]


def load_places_snapshots(master_dir: Optional[str] = None) -> List[Tuple[str, pd.DataFrame]]:
    """店舗一覧 (akakara_places_YYYYMMDD.csv) の全スナップショットを取得する。

    Returns
    -------
    list of (snapshot_date, DataFrame)
    """
    mdir = master_dir or get_master_dir()
    pattern = os.path.join(mdir, "akakara_places_*.csv")
    files = sorted(glob.glob(pattern))

    snapshots = []
    for f in files:
        m = re.search(r"akakara_places_(\d{8})\.csv", os.path.basename(f))
        if m:
            raw_date = m.group(1)
            snapshot_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        else:
            snapshot_date = datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d")

        try:
            df = pd.read_csv(f, encoding="utf-8-sig")
            # 列名の正規化
            df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
            if "placeId" in df.columns:
                df["placeId"] = df["placeId"].fillna("").astype(str).str.strip()
            df["rating"] = pd.to_numeric(df.get("rating"), errors="coerce")
            df["reviews_count"] = pd.to_numeric(df.get("reviews_count"), errors="coerce").fillna(0).astype(int)
            df["snapshot_date"] = snapshot_date
            snapshots.append((snapshot_date, df))
        except Exception:
            continue

    return snapshots


def load_places(master_dir: Optional[str] = None) -> pd.DataFrame:
    """最新の店舗一覧を読み込み、店舗マスタと結合した表を返す。"""
    snapshots = load_places_snapshots(master_dir)
    stores_df = load_stores_master(master_dir)

    if not snapshots:
        # 店舗一覧がない場合、店舗マスタから構成
        df = stores_df.copy()
        df["rating"] = np.nan
        df["reviews_count"] = 0
        df["prefecture"] = ""
        df["city"] = ""
        df["placeId"] = df["place_id"]
        df["snapshot_date"] = datetime.now().strftime("%Y-%m-%d")
        df["in_master"] = True
        df["has_reviews"] = False
        return df

    # 最新のスナップショット
    snapshot_date, places_df = snapshots[-1]
    places = places_df.copy()

    # マスタとの結合
    # 1. placeId == place_id
    # 2. 完全一致の store_name
    places["store_key"] = None
    places["brand"] = "赤から"
    places["genre"] = "鍋・居酒屋"
    places["in_master"] = False

    if not stores_df.empty:
        # 1. place_id による一致
        store_by_place = {
            r["place_id"]: r["store_key"]
            for _, r in stores_df.iterrows()
            if r["place_id"]
        }
        # 2. 店名による一致
        store_by_name = {
            r["store_name"]: r["store_key"]
            for _, r in stores_df.iterrows()
            if r["store_name"]
        }

        matched_keys = []
        for _, row in places.iterrows():
            pid = row.get("placeId", "")
            name = row.get("store_name", "")
            k = None
            if pid and pid in store_by_place:
                k = store_by_place[pid]
            elif name and name in store_by_name:
                k = store_by_name[name]
            matched_keys.append(k)

        places["store_key"] = matched_keys
        places["in_master"] = places["store_key"].notna()

    return places


def load_aspects(data_dir: Optional[str] = None) -> pd.DataFrame:
    """観点の詳細 (review_aspects.parquet) を読み込む。"""
    ddir = data_dir or get_data_dir()
    path = os.path.join(ddir, "review_aspects.parquet")

    cols = [
        "review_uid",
        "store_id",
        "aspect",
        "aspect_label",
        "sentiment",
        "subtopic",
        "evidence",
        "evidence_verbatim",
    ]

    if not os.path.exists(path):
        return pd.DataFrame(columns=cols)

    try:
        df = pd.read_parquet(path)
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df["sentiment"] = pd.to_numeric(df["sentiment"], errors="coerce")
        df["evidence_verbatim"] = df["evidence_verbatim"].fillna(False).astype(bool)
        return df[cols]
    except Exception:
        return pd.DataFrame(columns=cols)


def load_reviews(
    data_dir: Optional[str] = None,
    master_dir: Optional[str] = None,
) -> pd.DataFrame:
    """口コミデータを読み込み、店舗マスタと結合する。

    - reviews_tagged.parquet があればそれを読む。
    - なければ reviews.parquet を読み、観点列を空・未実行として補完する。
    - 個人特定情報 (PII) 列は除外する。
    """
    ddir = data_dir or get_data_dir()
    mdir = master_dir or get_master_dir()

    tagged_path = os.path.join(ddir, "reviews_tagged.parquet")
    raw_path = os.path.join(ddir, "reviews.parquet")

    is_tagged = os.path.exists(tagged_path)
    read_path = tagged_path if is_tagged else raw_path

    if not os.path.exists(read_path):
        # どちらも存在しない場合
        return pd.DataFrame()

    df = pd.read_parquet(read_path)

    # PII 除外
    cols_to_drop = [c for c in PII_COLUMNS if c in df.columns]
    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    # 店舗マスタの結合
    stores_df = load_stores_master(mdir)
    if not stores_df.empty:
        # 重複列の衝突を防ぐ
        master_subset = stores_df[["store_id", "store_key", "store_name", "brand", "genre", "area"]].drop_duplicates(subset=["store_id"])
        # df 側の store_name, brand, genre, area が空の場合はマスタで埋める
        df = df.merge(master_subset, on="store_id", how="left", suffixes=("", "_master"))
        if "store_key" not in df.columns or df["store_key"].isna().all():
            df["store_key"] = df.get("store_key_master")
        for col in ["store_name", "brand", "genre", "area"]:
            m_col = f"{col}_master"
            if m_col in df.columns:
                df[col] = df[col].fillna(df[m_col])
                df.drop(columns=[m_col], inplace=True)
    else:
        if "store_key" not in df.columns:
            df["store_key"] = df["store_id"]

    # store_key が欠損している場合は store_id で補完
    df["store_key"] = df["store_key"].fillna(df["store_id"])

    # タグ付け未実行の場合の補完
    if not is_tagged or "llm_tagged" not in df.columns:
        df["llm_tagged"] = False
        df["language"] = None
        df["overall_sentiment"] = np.nan
        for key in ASPECTS:
            df[f"{key}_mentioned"] = False
            df[f"{key}_sent"] = np.nan
            df[f"{key}_pos"] = np.nan
            df[f"{key}_neg"] = np.nan
    else:
        df["llm_tagged"] = df["llm_tagged"].fillna(False).astype(bool)

    # 型の統一
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["has_text"] = df["has_text"].fillna(False).astype(bool)
    df["has_owner_reply"] = df["has_owner_reply"].fillna(False).astype(bool)
    df["time_is_estimated"] = df["time_is_estimated"].fillna(False).astype(bool)

    # 日時変換
    for time_col in ["post_time", "owner_reply_time", "updated_time", "scraped_at"]:
        if time_col in df.columns:
            df[time_col] = pd.to_datetime(df[time_col], errors="coerce")

    if "post_year" not in df.columns or df["post_year"].isna().all():
        if "post_time" in df.columns:
            df["post_year"] = df["post_time"].dt.year

    return df


@dataclass
class Dataset:
    """分析に必要な全データセットを束ねるコンテナ。"""
    reviews: pd.DataFrame
    aspects: pd.DataFrame
    places: pd.DataFrame
    metadata: Dict[str, Optional[str]]


def load_all(
    data_dir: Optional[str] = None,
    master_dir: Optional[str] = None,
) -> Dataset:
    """全データを一括で読み込む。"""
    reviews = load_reviews(data_dir=data_dir, master_dir=master_dir)
    aspects = load_aspects(data_dir=data_dir)
    places = load_places(master_dir=master_dir)
    meta = get_metadata()

    # places の has_reviews フラグを更新
    if not reviews.empty and "store_key" in reviews.columns and "store_key" in places.columns:
        collected_keys = set(reviews["store_key"].dropna().unique())
        places["has_reviews"] = places["store_key"].isin(collected_keys)
    else:
        places["has_reviews"] = False

    return Dataset(reviews=reviews, aspects=aspects, places=places, metadata=meta)

"""店舗ターゲット解決モジュール (targets.py)

stores.csv から店舗情報を読み込み、Target オブジェクトのリストを生成する。
"""
from __future__ import annotations

import os
from typing import List, Optional
import pandas as pd

from src.api.base import Target
from src.pipeline.paths import MASTER_STORES


def get_targets(
    store_keys: Optional[List[str]] = None,
    master_path: str = MASTER_STORES,
) -> List[Target]:
    """stores.csv から Target のリストを取得する。

    Parameters
    ----------
    store_keys : Optional[List[str]]
        指定された店舗キーのリスト（例: ["store_2", "store_4"]）。
        None の場合は全店舗を対象とする。
    master_path : str
        店舗マスタファイルのパス
    """
    if not os.path.exists(master_path):
        raise FileNotFoundError(f"店舗マスタが見つかりません: {master_path}")

    df = pd.read_csv(master_path, dtype=str)
    if store_keys:
        missing = set(store_keys) - set(df["store_key"])
        if missing:
            raise ValueError(f"stores.csv に存在しない店舗キーです: {missing}")
        df = df[df["store_key"].isin(store_keys)]

    targets = []
    for _, r in df.iterrows():
        pid = str(r["place_id"]).strip() if pd.notna(r.get("place_id")) else ""
        targets.append(Target(
            store_key=str(r["store_key"]),
            store_name=str(r["store_name"]),
            url=str(r["url"]) if pd.notna(r.get("url")) else "",
            place_id=pid if pid and pid != "nan" else None,
        ))
    return targets


def get_target_by_key(store_key: str, master_path: str = MASTER_STORES) -> Target:
    """単一の store_key から Target を取得する。"""
    targets = get_targets(store_keys=[store_key], master_path=master_path)
    if not targets:
        raise ValueError(f"店舗が見つかりません: {store_key}")
    return targets[0]

"""生データ (raw CSV) 出力モジュール (writer.py)

設計書 plan/api_collector/02_design.md §3 のデータ契約に厳密に従い、
data/raw/reviews_{store_key}_{YYYYMMDD_HHMMSS}.csv を出力する。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd

from src.api.base import Target
from src.pipeline.paths import RAW_DIR

RAW_COLUMNS = [
    "store_name",
    "review_id",
    "reviewer_name",
    "reviewer_id",
    "is_local_guide",
    "reviewer_review_count",
    "reviewer_attributes",
    "rating",
    "review_text",
    "post_time",
    "updated_time",
    "relative_time",
    "owner_reply",
    "owner_reply_time",
    "source_url",
]


def write_raw_csv(
    rows: List[Dict[str, Any]],
    target: Target,
    scraped_at: Optional[datetime] = None,
    output_dir: str = RAW_DIR,
) -> str:
    """変換後の行リストを data/raw/ 配下に CSV として出力する。

    Parameters
    ----------
    rows : List[Dict[str, Any]]
        変換済みの口コミ行データ
    target : Target
        対象店舗情報
    scraped_at : Optional[datetime]
        取得日時。指定のない場合は現在時刻。
    output_dir : str
        出力先ディレクトリ (既定 data/raw)

    Returns
    -------
    output_path : str
        作成された CSV ファイルの絶対パス
    """
    os.makedirs(output_dir, exist_ok=True)
    dt = scraped_at or datetime.now()
    timestamp_str = dt.strftime("%Y%m%d_%H%M%S")
    filename = f"reviews_{target.store_key}_{timestamp_str}.csv"
    output_path = os.path.join(output_dir, filename)

    if not rows:
        df = pd.DataFrame(columns=RAW_COLUMNS)
    else:
        df = pd.DataFrame(rows)
        for col in RAW_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df = df[RAW_COLUMNS]

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path

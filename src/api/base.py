"""外部サービス連携の基本クラスとインターフェース (base.py)

設計書 plan/api_collector/02_design.md §5.1 に準拠。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class Target:
    """収集対象の店舗情報。stores.csv の 1 行に対応。"""
    store_key: str          # 例: "store_2"
    store_name: str         # 例: "赤から つくば研究学園店"
    url: str                # stores.csv の url（source_url にそのまま使用）
    place_id: Optional[str] = None  # stores.csv の place_id（あれば優先使用）


class ReviewProvider(Protocol):
    """外部サービスプロバイダのインターフェース。"""
    name: str
    supports_api: bool

    def load_file(self, path: str) -> List[Dict[str, Any]]:
        """ダウンロード済みファイル (JSON/CSV) からレコードリストを読み込む。"""
        ...

    def to_rows(self, records: List[Dict[str, Any]], target: Target) -> List[Dict[str, Any]]:
        """生レコードを raw CSV の共通スキーマ (02_design.md §3.2) の行に変換する。"""
        ...

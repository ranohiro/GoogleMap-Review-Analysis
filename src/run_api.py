"""外部サービス収集・取り込み CLI (src/run_api.py)

設計書 plan/api_collector/02_design.md §6.1 に準拠。
- オフライン取り込み: --from-file <path> --store <store_key>
- ベンダーデータの一括同期: --sync-vendor
"""
from __future__ import annotations

import argparse
import glob
import os
import re
from datetime import datetime
from typing import List

from src.api.base import Target
from src.api.providers import apify
from src.api.targets import get_target_by_key, get_targets
from src.api.writer import write_raw_csv
from src.pipeline import normalize
from src.pipeline.paths import DATA_DIR, RAW_DIR

VENDOR_APIFY_DIR = os.path.join(DATA_DIR, "raw_vendor", "apify")


def import_from_file(provider_name: str, file_path: str, store_key: str) -> str:
    """指定されたベンダーファイルから口コミを取り込み、data/raw/ に CSV を出力する。"""
    if provider_name != "apify":
        raise NotImplementedError(f"未対応のプロバイダです: {provider_name}")

    target = get_target_by_key(store_key)
    records = apify.load_file(file_path)

    # ファイル名からタイムスタンプを抽出（例: reviews_store_4_20261031_205245.json）
    m = re.search(r"_(\d{8}_\d{6})\.json$", os.path.basename(file_path))
    if m:
        scraped_at = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
    else:
        scraped_at = datetime.fromtimestamp(os.path.getmtime(file_path))

    rows = apify.to_rows(records, target)
    out_path = write_raw_csv(rows, target, scraped_at=scraped_at)
    print(f"[{store_key}] {target.store_name}: {len(rows)} 件を取り込みました -> {os.path.basename(out_path)}")
    return out_path


def sync_all_vendor_files() -> List[str]:
    """data/raw_vendor/apify/ 配下の全レビュー JSON ファイルを data/raw/ CSV に同期する。"""
    pattern = os.path.join(VENDOR_APIFY_DIR, "reviews_store_*.json")
    files = sorted(glob.glob(pattern))

    if not files:
        print("[!] 同期対象のファイルが data/raw_vendor/apify/ にありません。")
        return []

    # 店舗ごとに最新のファイルを採用（例: store_4 の 1 件テストファイルを除外し、全件ファイルを採用）
    store_files = {}
    for f in files:
        m = re.search(r"reviews_(store_\d+)_(\d{8}_\d{6})\.json$", os.path.basename(f))
        if m:
            s_key = m.group(1)
            ts = m.group(2)
            # アイテム数も考慮し、より多くのアイテムを持つファイル、または最新タイムスタンプを採用
            items = apify.load_file(f)
            if s_key not in store_files or len(items) > store_files[s_key]["count"]:
                store_files[s_key] = {"path": f, "ts": ts, "count": len(items)}

    created_csvs = []
    print(f"=== ベンダーデータ同期開始 ({len(store_files)} 店舗) ===")
    for s_key, info in sorted(store_files.items()):
        csv_path = import_from_file("apify", info["path"], s_key)
        created_csvs.append(csv_path)

    print("=== 全ファイルの取り込み完了 ===")
    return created_csvs


def main():
    parser = argparse.ArgumentParser(description="外部サービス収集・取り込み CLI")
    parser.add_argument("--provider", default="apify", choices=["apify", "outscraper"], help="プロバイダ名")
    parser.add_argument("--store", type=str, help="店舗キー (例: store_4)")
    parser.add_argument("--from-file", type=str, help="ダウンロード済みファイルパス")
    parser.add_argument("--sync-vendor", action="store_true", help="data/raw_vendor/ 配下の全ファイルを取り込み")
    parser.add_argument("--normalize", action="store_true", help="取り込み後に normalize を実行して parquet を更新")
    args = parser.parse_args()

    if args.sync_vendor:
        sync_all_vendor_files()
        if args.normalize:
            print("\n=== normalize パイプラインを実行中... ===")
            normalize.build()
            print("=== reviews.parquet を更新しました ===")
        return

    if args.from_file:
        if not args.store:
            raise SystemExit("--from-file には --store の指定が必要です。")
        import_from_file(args.provider, args.from_file, args.store)
        if args.normalize:
            print("\n=== normalize パイプラインを実行中... ===")
            normalize.build()
            print("=== reviews.parquet を更新しました ===")
        return

    parser.print_help()


if __name__ == "__main__":
    main()

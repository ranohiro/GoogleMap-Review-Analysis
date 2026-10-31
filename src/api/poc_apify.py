"""
Phase 1 の試験用コマンド: Apify で店舗情報・口コミを取得し、data/raw_vendor/apify/ に保存する。
本番用の CLI（src/run_api.py）ができたら役目を終える。

実行例:
    python -m src.api.poc_apify places --query 赤から --location 東京都 --max 1 --max-charge 0.05
    python -m src.api.poc_apify reviews --store store_4 --max 1 --max-charge 0.05
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

import pandas as pd

from src.api import config
from src.api.providers import apify
from src.pipeline.paths import MASTER_STORES


def _save(kind: str, label: str, run_input: dict, run: dict, items: list) -> str:
    out_dir = os.path.join(config.VENDOR_RAW_DIR, "apify")
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"{kind}_{label}_{ts}.json")
    summary = apify.run_summary(run)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"kind": kind, "input": run_input, "run": summary, "items": items}, f, ensure_ascii=False, indent=1)
    with open(config.MANIFEST_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"provider": "apify", "method": "api", "kind": kind, "label": label,
                            "input": run_input, **summary, "item_count": len(items),
                            "vendor_raw_path": os.path.relpath(path, config.VENDOR_RAW_DIR)},
                           ensure_ascii=False) + "\n")
    return path


def _run(actor: str, run_input: dict, max_charge: float) -> tuple:
    run = apify.start_run(actor, run_input, max_charge)
    print(f"実行開始: run_id={run['id']}（課金上限 ${max_charge}）")
    run = apify.wait_run(run["id"])
    items = apify.dataset_items(run["defaultDatasetId"]) if run.get("defaultDatasetId") else []
    s = apify.run_summary(run)
    print(f"状態={s['status']} 件数={len(items)} 費用=${s['usage_total_usd']} 課金イベント={s['charged_event_counts']}")
    return run, items


def cmd_places(a):
    run_input = {
        "searchStringsArray": [a.query],
        "locationQuery": a.location,
        "maxCrawledPlacesPerSearch": a.max,
        "language": "ja",
        "skipClosedPlaces": True,
        "scrapePlaceDetailPage": False,
        "scrapeContacts": False,
        "maxReviews": 0,
        "maxImages": 0,
    }
    run, items = _run(config.APIFY_PLACES_ACTOR, run_input, a.max_charge)
    path = _save("places", a.label or a.location, run_input, run, items)
    for it in items[:5]:
        print(f"  {it.get('title')} | 星 {it.get('totalScore')} | 口コミ {it.get('reviewsCount')} | {it.get('address')}")
    print(f"保存: {path}")


def cmd_reviews(a):
    stores = pd.read_csv(MASTER_STORES, dtype=str).set_index("store_key")
    if a.store not in stores.index:
        raise SystemExit(f"stores.csv に {a.store} がありません")
    row = stores.loc[a.store]
    # Place ID があればそれで指定する（検索用 URL より確実）
    target = {"placeIds": [row["place_id"]]} if isinstance(row.get("place_id"), str) and row["place_id"] \
        else {"startUrls": [{"url": row["url"]}]}
    run_input = {
        **target,
        "maxReviews": a.max,
        "reviewsSort": "newest",
        "language": "ja",
        "personalData": True,
    }
    run, items = _run(config.APIFY_REVIEWS_ACTOR, run_input, a.max_charge)
    path = _save("reviews", a.store, run_input, run, items)
    if items:
        # 個人情報は表示せず、項目名と値の型・有無だけを出す
        print("  項目:", ", ".join(f"{k}({type(v).__name__}{'' if v not in (None, '', [], {}) else ':空'})"
                                  for k, v in items[0].items()))
    print(f"保存: {path}")


def main():
    ap = argparse.ArgumentParser(description="Apify 試験取得（Phase 1）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("places", help="店舗検索")
    p.add_argument("--query", default="赤から")
    p.add_argument("--location", default="東京都")
    p.add_argument("--label", default=None)
    p.add_argument("--max", type=int, default=1)
    p.add_argument("--max-charge", type=float, required=True)
    r = sub.add_parser("reviews", help="口コミ取得")
    r.add_argument("--store", required=True)
    r.add_argument("--max", type=int, default=1)
    r.add_argument("--max-charge", type=float, required=True)
    a = ap.parse_args()
    {"places": cmd_places, "reviews": cmd_reviews}[a.cmd](a)


if __name__ == "__main__":
    main()

"""
Apify の Actor を実行して結果を取る最小クライアント（Phase 1 用）。

- 実行の開始（start_run）は自動リトライしない（二重課金の防止）
- 状態確認・結果取得は接続エラー・429・5xx のときだけリトライする
- 実行ごとに課金上限（maxTotalChargeUsd）を必ず付ける
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List

import pandas as pd
import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.api import config
from src.api.base import Target

_DONE = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.apify_token()}"}


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


@retry(retry=retry_if_exception(_retryable), wait=wait_exponential(min=2, max=30),
       stop=stop_after_attempt(5), reraise=True)
def _get(path: str, params: dict | None = None):
    r = requests.get(f"{config.APIFY_BASE_URL}{path}", headers=_headers(), params=params, timeout=90)
    r.raise_for_status()
    return r.json()


def start_run(actor: str, run_input: dict, max_charge_usd: float) -> dict:
    """Actor の実行を開始し、実行情報（id, defaultDatasetId など）を返す。リトライしない。"""
    r = requests.post(f"{config.APIFY_BASE_URL}/acts/{actor}/runs", headers=_headers(),
                      params={"maxTotalChargeUsd": max_charge_usd}, json=run_input, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Apify の実行開始に失敗しました（HTTP {r.status_code}）: {r.text[:300]}")
    return r.json()["data"]


def wait_run(run_id: str, log=print) -> dict:
    """実行が終わるまで待ち、最終的な実行情報を返す。"""
    deadline = time.time() + config.RUN_TIMEOUT_SEC
    while True:
        run = _get(f"/actor-runs/{run_id}", {"waitForFinish": 60})["data"]
        if run["status"] in _DONE:
            return run
        if time.time() > deadline:
            raise TimeoutError(f"実行 {run_id} が時間内に終わりませんでした。後で --resume で回収してください。")
        log(f"  実行中… 状態={run['status']}")
        time.sleep(config.POLL_INTERVAL_SEC)


def dataset_items(dataset_id: str) -> list:
    return _get(f"/datasets/{dataset_id}/items", {"format": "json", "clean": "true"})


def run_summary(run: dict) -> dict:
    """費用の確認に使う項目だけを抜き出す。"""
    return {
        "run_id": run.get("id"),
        "status": run.get("status"),
        "usage_total_usd": run.get("usageTotalUsd"),
        "charged_event_counts": run.get("chargedEventCounts"),
        "started_at": run.get("startedAt"),
        "finished_at": run.get("finishedAt"),
        "dataset_id": run.get("defaultDatasetId"),
    }


def load_file(path: str) -> List[Dict[str, Any]]:
    """Apify から保存した JSON ファイルを読み込み、items リストを返す。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("items", [])


def _parse_jst_datetime(val: Any) -> str:
    """UTC ISO 8601 文字列を JST の YYYY-MM-DD HH:MM:SS 文字列に変換する。"""
    if not val or not isinstance(val, str):
        return ""
    try:
        dt = pd.to_datetime(val)
        if dt.tzinfo is None:
            dt = dt.tz_localize("UTC")
        jst = dt.tz_convert("Asia/Tokyo")
        return jst.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def to_rows(records: List[Dict[str, Any]], target: Target) -> List[Dict[str, Any]]:
    """Apify の生レコードを 02_design.md §3.2 のスキーマに準拠した行辞書のリストに変換する。"""
    rows = []
    for it in records:
        rev_id = it.get("reviewId") or ""
        name = it.get("name") or ""
        reviewer_id = str(it.get("reviewerId")) if it.get("reviewerId") is not None else ""
        is_lg = bool(it.get("isLocalGuide", False))
        rev_cnt = int(it.get("reviewerNumberOfReviews")) if it.get("reviewerNumberOfReviews") is not None else ""
        rating = int(it.get("stars") or it.get("rating") or 0)
        # 本文: 必ず原文 (text) を採用。textTranslated は使わない
        text = it.get("text") or ""
        post_time = _parse_jst_datetime(it.get("publishedAtDate"))
        relative_time = it.get("publishAt") or ""
        owner_reply = it.get("responseFromOwnerText") or ""
        owner_reply_time = _parse_jst_datetime(it.get("responseFromOwnerDate"))

        rows.append({
            "store_name": target.store_name,
            "review_id": rev_id,
            "reviewer_name": name,
            "reviewer_id": reviewer_id,
            "is_local_guide": is_lg,
            "reviewer_review_count": rev_cnt,
            "reviewer_attributes": "",
            "rating": rating,
            "review_text": text,
            "post_time": post_time,
            "updated_time": "",
            "relative_time": relative_time,
            "owner_reply": owner_reply,
            "owner_reply_time": owner_reply_time,
            "source_url": target.url,
        })
    return rows

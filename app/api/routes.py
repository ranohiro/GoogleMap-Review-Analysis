"""BFF (Backend For Frontend) API エンドポイント定義 (app/api/routes.py)

画面①〜⑥に必要なデータを集約・整形して提供する。
- GET  /api/meta               メタデータ（プロンプト版、ファイル更新日時等）
- GET  /api/filters/options    絞り込み用選択肢（店舗、ブランド、言語、期間）
- POST /api/overview           ① 全店舗一覧（都道府県別集計、散布図、収集状況）
- POST /api/aspects            ② 観点マップ（言及率・平均感情・ネット感情散布図データ）
- POST /api/aspects/subtopics  ② 観点マップ詳細（頻出サブトピック集計）
- POST /api/low-rating         ③ 低評価の要因（★1〜2否定言及 Lift、信頼区間、原文根拠）
- POST /api/reviews            ④ 口コミ検索（一覧表示、観点タグ・根拠抜粋）
- POST /api/reviews/export     ④ 口コミ CSV 書き出し
- POST /api/compare            ⑤ 店舗比較（店舗×観点マトリクス、縮小推定切替、返信率）
- POST /api/trends             ⑥ 推移（月別件数・星・観点否定率、前後比較、スナップショット）
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.analysis import filters, load, metrics
from src.analysis.stats import MIN_N
from src.pipeline.paths import ASPECTS

router = APIRouter(prefix="/api")


# --- リクエストモデル ---

class FilterParams(BaseModel):
    stores: Optional[List[str]] = Field(None, description="店舗キーまたはIDのリスト")
    period_start: Optional[str] = Field(None, description="開始日 (YYYY-MM-DD)")
    period_end: Optional[str] = Field(None, description="終了日 (YYYY-MM-DD)")
    ratings: Optional[List[int]] = Field(None, description="星評価リスト (1〜5)")
    languages: Optional[List[str]] = Field(None, description="言語コード (ja, en等)")
    has_text: Optional[bool] = Field(None, description="本文ありのみ (True/False/None)")
    exclude_estimated_time: bool = Field(False, description="推定日時を除外するか")
    query: Optional[str] = Field(None, description="本文検索キーワード")
    brand: Optional[str] = Field(None, description="ブランド")


class SubtopicRequest(BaseModel):
    filters: FilterParams = Field(default_factory=FilterParams)
    aspect: str = Field(..., description="観点キー (例: taste, service)")
    sentiment: str = Field("neg", description="感情 ('neg', 'pos', 'all')")
    k: int = Field(10, description="取得件数")


class ReviewSearchRequest(BaseModel):
    filters: FilterParams = Field(default_factory=FilterParams)
    aspect: Optional[str] = Field(None, description="観点での絞り込み")
    sentiment_filter: Optional[str] = Field(None, description="観点感情 ('pos', 'neg')")
    page: int = Field(1, ge=1, description="ページ番号")
    page_size: int = Field(20, ge=1, le=100, description="1ページあたりの件数")


class CompareRequest(BaseModel):
    filters: FilterParams = Field(default_factory=FilterParams)
    metric: str = Field("mention_rate", description="指標 ('mention_rate', 'net_sentiment', 'neg_rate', 'avg_sentiment')")
    use_shrinkage: bool = Field(False, description="経験ベイズ縮小推定を適用するか")


class TrendRequest(BaseModel):
    filters: FilterParams = Field(default_factory=FilterParams)
    exclude_estimated: bool = Field(True, description="推定日時を除外するか")
    split_date: Optional[str] = Field(None, description="前後比較の分割日 (YYYY-MM-DD)")


# --- ヘルパー関数 ---

def _apply_filter_params(df: pd.DataFrame, p: FilterParams) -> pd.DataFrame:
    period = (p.period_start, p.period_end) if (p.period_start or p.period_end) else None
    return filters.apply(
        df,
        stores=p.stores,
        period=period,
        ratings=p.ratings,
        languages=p.languages,
        has_text=p.has_text,
        exclude_estimated_time=p.exclude_estimated_time,
        query=p.query,
        brand=p.brand,
    )


def _clean_nans(val: Any) -> Any:
    """JSON シリアライズ不可の NaN / inf を None に置換する。"""
    if isinstance(val, (float, np.floating)):
        if np.isnan(val) or np.isinf(val):
            return None
        return float(val)
    elif isinstance(val, (np.integer, int)):
        return int(val)
    elif isinstance(val, (pd.Timestamp, np.datetime64)):
        return str(val)
    elif isinstance(val, dict):
        return {k: _clean_nans(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_clean_nans(v) for v in val]
    return val


# --- エンドポイント ---

@router.get("/meta")
def get_meta() -> Dict[str, Any]:
    """システムのメタ情報・データ更新日時・観点一覧を取得する。"""
    meta = load.get_metadata()
    dataset = load.load_all()
    reviews = dataset.reviews

    tagged_count = int(reviews["llm_tagged"].sum()) if not reviews.empty and "llm_tagged" in reviews.columns else 0
    total_count = len(reviews)

    return {
        **meta,
        "aspects": ASPECTS,
        "total_reviews": total_count,
        "tagged_reviews": tagged_count,
        "has_tagged_data": tagged_count > 0,
        "min_n_threshold": MIN_N,
    }


@router.get("/filters/options")
def get_filter_options() -> Dict[str, Any]:
    """絞り込みUIに必要な選択肢（店舗一覧、ブランド一覧、言語一覧、期間範囲）を取得する。"""
    dataset = load.load_all()
    reviews = dataset.reviews
    places = dataset.places
    stores_master = load.load_stores_master()

    # 店舗選択肢（口コミがある店舗、およびマスタ店舗）
    stores_list = []
    if not stores_master.empty:
        review_counts = reviews["store_key"].value_counts().to_dict() if not reviews.empty and "store_key" in reviews.columns else {}
        for _, r in stores_master.iterrows():
            k = str(r["store_key"])
            stores_list.append({
                "store_key": k,
                "store_id": str(r["store_id"]),
                "store_name": str(r["store_name"]),
                "brand": str(r.get("brand", "赤から")),
                "area": str(r.get("area", "")),
                "review_count": int(review_counts.get(k, 0)),
                "has_reviews": review_counts.get(k, 0) > 0,
            })

    # ブランド
    brands = sorted([str(b) for b in reviews["brand"].dropna().unique() if b]) if not reviews.empty and "brand" in reviews.columns else ["赤から"]

    # 言語
    languages = sorted([str(l).lower() for l in reviews["language"].dropna().unique() if l]) if not reviews.empty and "language" in reviews.columns else ["ja", "en"]

    # 期間範囲
    min_date, max_date = None, None
    if not reviews.empty and "post_time" in reviews.columns:
        valid_times = reviews["post_time"].dropna()
        if not valid_times.empty:
            min_date = valid_times.min().strftime("%Y-%m-%d")
            max_date = valid_times.max().strftime("%Y-%m-%d")

    return {
        "stores": stores_list,
        "brands": brands,
        "languages": languages,
        "min_date": min_date,
        "max_date": max_date,
        "ratings": [1, 2, 3, 4, 5],
    }


@router.post("/overview")
def get_overview(params: FilterParams) -> Dict[str, Any]:
    """① 全店舗一覧 画面用データ。

    - 都道府県別の店舗数と平均星
    - 全店舗散布図データ（横: 口コミ数、縦: 星評価、収集状況フラグ）
    - マスタ外・一覧外店舗のサマリー
    """
    dataset = load.load_all()
    places = dataset.places.copy()
    reviews = dataset.reviews.copy()

    if places.empty:
        return {
            "prefectures": [],
            "scatter": [],
            "summary": {"total_stores": 0, "collected_stores": 0, "overall_avg_rating": None},
            "unmatched_stores": [],
        }

    # ブランド絞り込みがあれば適用
    if params.brand and "brand" in places.columns:
        places = places[places["brand"] == params.brand]

    # 都道府県別集計
    pref_rows = []
    if "prefecture" in places.columns:
        valid_pref = places[places["prefecture"].notna() & (places["prefecture"] != "")]
        for pref, grp in valid_pref.groupby("prefecture"):
            cnt = len(grp)
            avg_r = float(grp["rating"].mean()) if grp["rating"].notna().any() else None
            tot_reviews = int(grp["reviews_count"].sum())
            collected = int(grp["has_reviews"].sum()) if "has_reviews" in grp.columns else 0
            pref_rows.append({
                "prefecture": str(pref),
                "store_count": cnt,
                "avg_rating": round(avg_r, 2) if avg_r is not None else None,
                "total_reviews": tot_reviews,
                "collected_count": collected,
            })
        pref_rows.sort(key=lambda x: x["store_count"], reverse=True)

    # 散布図データ
    scatter_rows = []
    for _, row in places.iterrows():
        scatter_rows.append({
            "store_name": str(row.get("store_name", "")),
            "reviews_count": int(row.get("reviews_count", 0)),
            "rating": round(float(row.get("rating", 0.0)), 2) if not pd.isna(row.get("rating")) else None,
            "prefecture": str(row.get("prefecture", "")),
            "city": str(row.get("city", "")),
            "store_key": str(row.get("store_key")) if pd.notna(row.get("store_key")) else None,
            "in_master": bool(row.get("in_master", False)),
            "has_reviews": bool(row.get("has_reviews", False)),
            "place_id": str(row.get("placeId", "")),
        })

    # 一覧にない店舗（店舗マスタにあって、places に紐付かなかった店舗）
    unmatched_in_master = []
    stores_master = load.load_stores_master()
    if not stores_master.empty:
        matched_keys = set(places["store_key"].dropna().unique())
        for _, sm in stores_master.iterrows():
            k = str(sm["store_key"])
            if k not in matched_keys:
                rev_cnt = len(reviews[reviews["store_key"] == k]) if not reviews.empty and "store_key" in reviews.columns else 0
                unmatched_in_master.append({
                    "store_key": k,
                    "store_name": str(sm["store_name"]),
                    "area": str(sm.get("area", "")),
                    "review_count": rev_cnt,
                })

    tot_stores = len(places)
    collected_cnt = int(places["has_reviews"].sum()) if "has_reviews" in places.columns else 0
    overall_r = float(places["rating"].mean()) if places["rating"].notna().any() else None

    return {
        "prefectures": pref_rows,
        "scatter": scatter_rows,
        "summary": {
            "total_stores": tot_stores,
            "collected_stores": collected_cnt,
            "overall_avg_rating": round(overall_r, 2) if overall_r is not None else None,
        },
        "unmatched_stores": unmatched_in_master,
    }


@router.post("/aspects")
def get_aspects(params: FilterParams) -> Dict[str, Any]:
    """② 観点マップ 画面用データ。

    横軸: 平均感情 (-2〜+2)
    縦軸: 言及率 (0〜100%)
    点の大きさ: 言及数
    """
    dataset = load.load_all()
    filtered = _apply_filter_params(dataset.reviews, params)

    is_tagged = int(filtered["llm_tagged"].sum()) > 0 if not filtered.empty and "llm_tagged" in filtered.columns else False
    if not is_tagged:
        return {
            "aspects": [],
            "has_tagged_data": False,
            "ratings_summary": metrics.rating_summary(filtered),
        }

    asp_df = metrics.aspect_summary(filtered)
    rows = asp_df.to_dict(orient="records")

    return {
        "aspects": _clean_nans(rows),
        "has_tagged_data": True,
        "ratings_summary": _clean_nans(metrics.rating_summary(filtered)),
        "reply_metrics": _clean_nans(metrics.owner_reply_metrics(filtered)),
    }


@router.post("/aspects/subtopics")
def get_subtopics(req: SubtopicRequest) -> Dict[str, Any]:
    """② 観点マップ詳細: 指定観点の具体的対象 (subtopic) の頻出ランキング。"""
    dataset = load.load_all()
    filtered_reviews = _apply_filter_params(dataset.reviews, req.filters)

    if filtered_reviews.empty or dataset.aspects.empty:
        return {"subtopics": [], "aspect": req.aspect, "aspect_label": ASPECTS.get(req.aspect, req.aspect)}

    # 絞り込まれた口コミの UID に該当する aspects のみ抽出
    valid_uids = set(filtered_reviews["review_uid"].dropna().unique())
    aspects_sub = dataset.aspects[dataset.aspects["review_uid"].isin(valid_uids)]

    top_df = metrics.top_subtopics(aspects_sub, aspect=req.aspect, sentiment=req.sentiment, k=req.k)
    return {
        "aspect": req.aspect,
        "aspect_label": ASPECTS.get(req.aspect, req.aspect),
        "subtopics": _clean_nans(top_df.to_dict(orient="records")),
    }


@router.post("/low-rating")
def get_low_rating_drivers(params: FilterParams) -> Dict[str, Any]:
    """③ 低評価の要因 画面用データ。

    ★1〜2 での否定言及 Lift と信頼区間、および各観点の根拠の原文一覧。
    """
    dataset = load.load_all()
    filtered = _apply_filter_params(dataset.reviews, params)

    is_tagged = int(filtered["llm_tagged"].sum()) > 0 if not filtered.empty and "llm_tagged" in filtered.columns else False
    if not is_tagged:
        return {
            "drivers": [],
            "has_tagged_data": False,
            "ratings_summary": metrics.rating_summary(filtered),
        }

    drivers_df = metrics.low_rating_drivers(filtered, low=(1, 2))

    # 各観点の低評価（★1〜2）での原文根拠をサンプル抽出
    aspect_evidence: Dict[str, List[Dict[str, Any]]] = {}
    if not dataset.aspects.empty:
        low_reviews = filtered[filtered["rating"].isin([1, 2])]
        low_uids = set(low_reviews["review_uid"].dropna().unique())
        low_asp = dataset.aspects[dataset.aspects["review_uid"].isin(low_uids)]

        # 店舗情報・星・本文を紐付け
        rev_info = low_reviews.set_index("review_uid")[["store_name", "rating", "review_text", "post_time"]].to_dict(orient="index")

        for key in ASPECTS:
            sub = low_asp[(low_asp["aspect"] == key) & (low_asp["sentiment"] < 0)]
            ev_list = []
            for _, r in sub.head(15).iterrows():
                uid = r["review_uid"]
                info = rev_info.get(uid, {})
                ev_list.append({
                    "review_uid": uid,
                    "store_name": info.get("store_name", ""),
                    "rating": info.get("rating"),
                    "post_time": str(info.get("post_time", ""))[:10],
                    "evidence": r.get("evidence"),
                    "subtopic": r.get("subtopic"),
                    "evidence_verbatim": bool(r.get("evidence_verbatim", False)),
                    "review_text": info.get("review_text"),
                })
            aspect_evidence[key] = ev_list

    return {
        "drivers": _clean_nans(drivers_df.to_dict(orient="records")),
        "aspect_evidence": aspect_evidence,
        "has_tagged_data": True,
        "ratings_summary": _clean_nans(metrics.rating_summary(filtered)),
    }


@router.post("/reviews")
def search_reviews(req: ReviewSearchRequest) -> Dict[str, Any]:
    """④ 口コミ検索 画面用データ。

    観点・感情・星・キーワードによる絞り込みとページネーション、観点タグの付与。
    個人特定情報は除外。
    """
    dataset = load.load_all()
    filtered = _apply_filter_params(dataset.reviews, req.filters)

    # 観点および感情での追加絞り込み
    if req.aspect:
        filtered = filters.apply(
            filtered,
            aspect=req.aspect,
            sentiment_filter=req.sentiment_filter,
        )

    total_count = len(filtered)
    page = req.page
    page_size = req.page_size
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    # 日時降順（なければそのまま）
    if "post_time" in filtered.columns:
        filtered = filtered.sort_values(by="post_time", ascending=False, na_position="last")

    paged_df = filtered.iloc[start_idx:end_idx]

    # 口コミごとの観点タグと根拠を取得
    aspects_by_uid: Dict[str, List[Dict[str, Any]]] = {}
    if not dataset.aspects.empty and not paged_df.empty:
        paged_uids = set(paged_df["review_uid"].dropna().unique())
        sub_asp = dataset.aspects[dataset.aspects["review_uid"].isin(paged_uids)]
        for _, r in sub_asp.iterrows():
            uid = r["review_uid"]
            if uid not in aspects_by_uid:
                aspects_by_uid[uid] = []
            aspects_by_uid[uid].append({
                "aspect": r["aspect"],
                "aspect_label": r.get("aspect_label", ASPECTS.get(r["aspect"], r["aspect"])),
                "sentiment": r["sentiment"],
                "subtopic": r.get("subtopic"),
                "evidence": r.get("evidence"),
                "evidence_verbatim": bool(r.get("evidence_verbatim", False)),
            })

    results = []
    for _, row in paged_df.iterrows():
        uid = str(row["review_uid"])
        results.append({
            "review_uid": uid,
            "store_key": str(row.get("store_key", "")),
            "store_name": str(row.get("store_name", "")),
            "brand": str(row.get("brand", "")),
            "rating": int(row["rating"]) if pd.notna(row.get("rating")) else None,
            "review_text": str(row.get("review_text", "")) if pd.notna(row.get("review_text")) else "",
            "has_text": bool(row.get("has_text", False)),
            "language": str(row.get("language", "")) if pd.notna(row.get("language")) else None,
            "post_time": str(row.get("post_time", ""))[:19] if pd.notna(row.get("post_time")) else None,
            "time_is_estimated": bool(row.get("time_is_estimated", False)),
            "relative_time": str(row.get("relative_time", "")) if pd.notna(row.get("relative_time")) else None,
            "has_owner_reply": bool(row.get("has_owner_reply", False)),
            "owner_reply": str(row.get("owner_reply", "")) if pd.notna(row.get("owner_reply")) else None,
            "llm_tagged": bool(row.get("llm_tagged", False)),
            "aspects": aspects_by_uid.get(uid, []),
        })

    return {
        "total": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": int(np.ceil(total_count / page_size)) if total_count > 0 else 1,
        "reviews": results,
    }


@router.post("/reviews/export")
def export_reviews_csv(req: ReviewSearchRequest) -> Response:
    """④ 口コミ検索: 絞り込み条件に合致する口コミの CSV ダウンロード。

    PII（投稿者名等）を含まない安全な形式で出力。
    """
    dataset = load.load_all()
    filtered = _apply_filter_params(dataset.reviews, req.filters)

    if req.aspect:
        filtered = filters.apply(
            filtered,
            aspect=req.aspect,
            sentiment_filter=req.sentiment_filter,
        )

    export_cols = [
        "review_uid", "store_key", "store_name", "rating", "post_time",
        "time_is_estimated", "has_owner_reply", "language", "review_text"
    ]
    avail_cols = [c for c in export_cols if c in filtered.columns]
    out_df = filtered[avail_cols].copy()

    stream = io.StringIO()
    out_df.to_csv(stream, index=False, encoding="utf-8-sig")
    csv_bytes = stream.getvalue().encode("utf-8-sig")

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=reviews_export.csv"},
    )


@router.post("/compare")
def get_store_comparison(req: CompareRequest) -> Dict[str, Any]:
    """⑤ 店舗比較 画面用データ。

    店舗×観点のヒートマップデータ（言及率・ネット感情・否定率）と、
    ベータ二項分布による縮小推定の切り替え。
    """
    dataset = load.load_all()
    filtered = _apply_filter_params(dataset.reviews, req.filters)

    if filtered.empty or "store_key" not in filtered.columns:
        return {
            "stores": [],
            "aspects": list(ASPECTS.keys()),
            "aspect_labels": list(ASPECTS.values()),
            "matrix": [],
            "reply_rates": [],
            "is_single_store": True,
        }

    stores_in_data = sorted(filtered["store_key"].dropna().unique().tolist())
    is_single_store = len(stores_in_data) <= 1

    # 各店舗の返信率サマリー
    reply_rows = []
    for s_key in stores_in_data:
        sub = filtered[filtered["store_key"] == s_key]
        s_name = sub["store_name"].iloc[0] if "store_name" in sub.columns and not sub.empty else s_key
        rep_m = metrics.owner_reply_metrics(sub)
        r_sum = metrics.rating_summary(sub)
        reply_rows.append({
            "store_key": s_key,
            "store_name": s_name,
            "total_reviews": r_sum["total_reviews"],
            "mean_rating": r_sum["mean_rating"],
            "reply_rate": rep_m["reply_rate"],
            "reply_rate_ci_lower": rep_m["reply_rate_ci_lower"],
            "reply_rate_ci_upper": rep_m["reply_rate_ci_upper"],
            "low_reply_rate": rep_m["low_rating_reply_rate"],
            "median_reply_days": rep_m["median_reply_days"],
        })

    # 店舗×観点マトリクス
    matrix_df = metrics.store_comparison_matrix(
        filtered,
        metric=req.metric,
        use_shrinkage=req.use_shrinkage,
    )

    # 形式整形: stores x aspects 2D リスト
    aspect_keys = list(ASPECTS.keys())
    matrix_values = []
    for s_key in stores_in_data:
        row_vals = []
        for a_key in aspect_keys:
            val = matrix_df.loc[s_key, a_key] if (s_key in matrix_df.index and a_key in matrix_df.columns) else None
            row_vals.append(_clean_nans(val))
        matrix_values.append(row_vals)

    return {
        "stores": stores_in_data,
        "store_names": [filtered[filtered["store_key"] == s]["store_name"].iloc[0] if "store_name" in filtered.columns else s for s in stores_in_data],
        "aspects": aspect_keys,
        "aspect_labels": [ASPECTS[k] for k in aspect_keys],
        "matrix": matrix_values,
        "reply_rates": _clean_nans(reply_rows),
        "is_single_store": is_single_store,
        "metric": req.metric,
        "use_shrinkage": req.use_shrinkage,
    }


@router.post("/trends")
def get_trends(req: TrendRequest) -> Dict[str, Any]:
    """⑥ 推移 画面用データ。

    月別の件数・平均星・観点別否定率、指定日の前後比較、および店舗一覧スナップショットの星推移。
    """
    dataset = load.load_all()
    filtered = _apply_filter_params(dataset.reviews, req.filters)

    trend_df, excluded_count = metrics.monthly_trend(
        filtered,
        exclude_estimated=req.exclude_estimated,
    )

    # 前後比較
    before_after = None
    if req.split_date:
        before_after = metrics.before_after_comparison(filtered, split_date=req.split_date)

    # 店舗一覧のスナップショット推移（複数存在する場合）
    snapshots_history = []
    snapshots = load.load_places_snapshots()
    if len(snapshots) >= 2:
        for snap_date, p_df in snapshots:
            avg_r = float(p_df["rating"].mean()) if p_df["rating"].notna().any() else None
            tot_cnt = int(p_df["reviews_count"].sum())
            snapshots_history.append({
                "snapshot_date": snap_date,
                "avg_rating": round(avg_r, 2) if avg_r is not None else None,
                "total_reviews": tot_cnt,
                "store_count": len(p_df),
            })

    return {
        "monthly": _clean_nans(trend_df.to_dict(orient="records")),
        "excluded_estimated_count": excluded_count,
        "before_after": _clean_nans(before_after),
        "snapshots_history": snapshots_history,
        "has_multiple_snapshots": len(snapshots) >= 2,
    }

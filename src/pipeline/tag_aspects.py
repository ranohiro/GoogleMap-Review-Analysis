"""
② LLMタグ付け: 口コミ本文を観点（味・接客・提供時間・価格・雰囲気・清潔さ・その他）× 感情(-2〜+2)に分解する。

- 星の数はLLMに渡さない（ブラインド判定。星に引きずられたラベルによるリークを防ぐ）
- 結果は data/processed/llm_cache/<prompt_version>/<model>/ に1件ずつキャッシュ。再実行しても再課金されない
- 出力:
    data/processed/review_aspects.parquet  … 縦持ち（1行 = 口コミ×観点）
    data/processed/reviews_tagged.parquet  … 横持ち（1行 = 口コミ、観点ごとの mentioned / sent / pos / neg 列）

APIキー: GEMINI_API_KEY を プロジェクト直下の .env または ~/.env に設定

実行例:
    python -m src.pipeline.tag_aspects --list-models
    python -m src.pipeline.tag_aspects --limit 5        # 試運転
    python -m src.pipeline.tag_aspects                  # 全件
"""
import argparse
import hashlib
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Literal

import pandas as pd
from pydantic import BaseModel, Field

from src.pipeline.paths import ASPECTS, BASE_DIR, LLM_CACHE_DIR, LLM_MODEL, PROCESSED_DIR, PROMPT_DIR, PROMPT_VERSION

AspectKey = Literal["taste", "service", "speed", "price", "atmosphere", "cleanliness", "other"]


class AspectItem(BaseModel):
    aspect: AspectKey
    sentiment: int = Field(description="-2,-1,0,1,2 のいずれか")
    subtopic: str = Field(description="具体的な対象（短い名詞）")
    evidence: str = Field(description="根拠となる本文の抜き出し（原文のまま）")


class ReviewAnalysis(BaseModel):
    language: str = Field(description="原文の言語 ISO 639-1")
    overall_sentiment: int = Field(description="-2,-1,0,1,2 のいずれか")
    aspects: List[AspectItem]


def _load_env():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    load_dotenv(os.path.expanduser("~/.env"))


def _client():
    _load_env()
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        sys.exit("GEMINI_API_KEY が見つかりません。プロジェクト直下の .env か ~/.env に設定してください。")
    from google import genai
    return genai.Client()


def _prompt_template():
    with open(os.path.join(PROMPT_DIR, f"{PROMPT_VERSION}.md"), encoding="utf-8") as f:
        return f.read()


def _cache_path(model, uid, text):
    h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    d = os.path.join(LLM_CACHE_DIR, PROMPT_VERSION, model.replace("/", "_"))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{uid}_{h}.json")


def _clip(v):
    try:
        return max(-2, min(2, int(v)))
    except (TypeError, ValueError):
        return None


def analyze_one(client, model, template, uid, text, force=False, max_retries=5):
    path = _cache_path(model, uid, text)
    if not force and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f), True

    from google.genai import types
    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
        response_schema=ReviewAnalysis,
    )
    prompt = template.replace("{review_text}", text)
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            parsed = ReviewAnalysis.model_validate_json(resp.text)
            result = parsed.model_dump()
            result["_meta"] = {"model": model, "prompt_version": PROMPT_VERSION, "review_uid": uid,
                               "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            usage = getattr(resp, "usage_metadata", None)
            if usage is not None:
                result["_meta"]["input_tokens"] = getattr(usage, "prompt_token_count", None)
                result["_meta"]["output_tokens"] = getattr(usage, "candidates_token_count", None)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            return result, False
        except Exception as e:  # 429/5xx/JSON不正などは指数バックオフで再試行
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + random.random()
            print(f"  [retry {attempt + 1}] {uid}: {type(e).__name__}: {str(e)[:120]} … {wait:.1f}s待機")
            time.sleep(wait)


def to_tables(reviews, results):
    """LLM結果を縦持ち・横持ちのテーブルに変換する。"""
    long_rows, review_rows = [], []
    for uid, r in results.items():
        text = reviews.loc[uid, "review_text"]
        seen = set()
        for a in r.get("aspects", []):
            if a["aspect"] in seen:  # 念のため同一観点の重複は先勝ち
                continue
            seen.add(a["aspect"])
            long_rows.append({
                "review_uid": uid,
                "store_id": reviews.loc[uid, "store_id"],
                "aspect": a["aspect"],
                "aspect_label": ASPECTS[a["aspect"]],
                "sentiment": _clip(a["sentiment"]),
                "subtopic": a.get("subtopic"),
                "evidence": a.get("evidence"),
                "evidence_verbatim": bool(a.get("evidence")) and a["evidence"].strip() in text,
            })
        review_rows.append({"review_uid": uid, "language": (r.get("language") or "").lower() or None,
                            "overall_sentiment": _clip(r.get("overall_sentiment"))})

    long_df = pd.DataFrame(long_rows, columns=["review_uid", "store_id", "aspect", "aspect_label", "sentiment",
                                               "subtopic", "evidence", "evidence_verbatim"])
    meta = pd.DataFrame(review_rows, columns=["review_uid", "language", "overall_sentiment"])

    wide = reviews.reset_index().merge(meta, on="review_uid", how="left")
    wide["llm_tagged"] = wide["review_uid"].isin(results.keys())
    for key in ASPECTS:
        s = long_df[long_df["aspect"] == key].set_index("review_uid")["sentiment"]
        tagged = wide["llm_tagged"]
        wide[f"{key}_mentioned"] = wide["review_uid"].isin(s.index).where(tagged)
        wide[f"{key}_sent"] = wide["review_uid"].map(s)
        wide[f"{key}_pos"] = (wide[f"{key}_sent"] > 0).astype(float).where(tagged)
        wide[f"{key}_neg"] = (wide[f"{key}_sent"] < 0).astype(float).where(tagged)
    return long_df, wide


def main():
    ap = argparse.ArgumentParser(description="口コミの観点別感情タグ付け（Gemini）")
    ap.add_argument("--model", default=LLM_MODEL)
    ap.add_argument("--limit", type=int, help="先頭N件だけ処理（試運転用）")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--force", action="store_true", help="キャッシュを無視して再実行")
    ap.add_argument("--dry-run", action="store_true", help="API を呼ばずに1件目のプロンプトを表示")
    ap.add_argument("--list-models", action="store_true", help="利用可能なモデルを一覧表示")
    args = ap.parse_args()

    if args.list_models:
        for m in _client().models.list():
            actions = getattr(m, "supported_actions", None) or []
            if "generateContent" in actions:
                print(m.name)
        return

    reviews = pd.read_parquet(os.path.join(PROCESSED_DIR, "reviews.parquet")).set_index("review_uid")
    targets = reviews[reviews["has_text"]]
    if args.limit:
        targets = targets.head(args.limit)
    template = _prompt_template()

    if args.dry_run:
        print(template.replace("{review_text}", targets.iloc[0]["review_text"]))
        return

    client = _client()
    print(f"モデル: {args.model} / プロンプト: {PROMPT_VERSION} / 対象: {len(targets)} 件")
    results, n_cached, errors = {}, 0, []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(analyze_one, client, args.model, template, uid, row.review_text, args.force): uid
                for uid, row in targets.iterrows()}
        for i, fut in enumerate(as_completed(futs), 1):
            uid = futs[fut]
            try:
                results[uid], cached = fut.result()
                n_cached += cached
            except Exception as e:
                errors.append((uid, str(e)[:200]))
            if i % 10 == 0 or i == len(futs):
                print(f"  {i}/{len(futs)} 完了（キャッシュ {n_cached}, エラー {len(errors)}）")

    # 今回の対象外でもキャッシュ済みのものは取り込む（--limit で分割実行した場合など）
    for uid, row in reviews[reviews["has_text"]].iterrows():
        if uid not in results:
            p = _cache_path(args.model, uid, row.review_text)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    results[uid] = json.load(f)

    long_df, wide = to_tables(reviews, results)
    long_df.to_parquet(os.path.join(PROCESSED_DIR, "review_aspects.parquet"), index=False)
    long_df.to_csv(os.path.join(PROCESSED_DIR, "review_aspects.csv"), index=False, encoding="utf-8-sig")
    wide.to_parquet(os.path.join(PROCESSED_DIR, "reviews_tagged.parquet"), index=False)

    tokens_in = sum((r.get("_meta") or {}).get("input_tokens") or 0 for r in results.values())
    tokens_out = sum((r.get("_meta") or {}).get("output_tokens") or 0 for r in results.values())
    print(f"\n保存: review_aspects.parquet（{len(long_df)} 行）, reviews_tagged.parquet（{len(wide)} 行）")
    print(f"タグ付け済み: {len(results)} 件 / トークン累計 入力 {tokens_in:,} 出力 {tokens_out:,}")
    if len(long_df):
        print(f"evidence が原文に一致した割合: {long_df['evidence_verbatim'].mean():.0%}")
    for uid, msg in errors:
        print(f"  [ERROR] {uid}: {msg}")


if __name__ == "__main__":
    main()

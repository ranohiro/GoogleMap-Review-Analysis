# CLAUDE.md

Google マップの口コミを収集し、LLM で観点別（味・接客など）に分析するプロジェクト。
応答・ドキュメント・コードコメントは日本語で書く。

## 現状
- 収集（Playwright）: `src/main.py` ほか … 稼働済み
- 分析: `src/pipeline/`（正規化 → LLM タグ付け → 人手ラベルでの評価）… 稼働済み
- **進行中**: 外部サービスでの収集。無料枠で Outscraper（CSV ダウンロードのみ）と Apify（API）を比べてから採用を決める → `plan/api_collector/03_execution_plan.md` の進捗表を見て、該当フェーズだけ読む

## コマンド（Python 3.9 / `.venv`）
```bash
source .venv/bin/activate
python -m src.main [--login | --manual]           # Playwright 収集（ブラウザ操作）
python -m src.pipeline.normalize [--all-snapshots] # raw CSV → data/processed/reviews.parquet
python -m src.pipeline.tag_aspects [--limit N]     # Gemini で観点タグ付け（課金あり・キャッシュあり）
python -m src.pipeline.gold export | evaluate      # 人手ラベルの作成・評価
# 予定（Phase 2〜4 で実装）
python -m src.run_api --provider outscraper --store store_2 --from-file <csv>  # 取り込み（課金なし）
python -m src.run_api --provider apify --store store_2 --dry-run
pytest
```

## 構成（要点）
- `src/main.py, scraper.py, parser.py, config.py, logger.py` … Playwright 収集
- `src/pipeline/` … `normalize.py`, `tag_aspects.py`, `gold.py`, `paths.py`（パスと観点の定義）, `prompts/`
- `src/api/`, `src/run_api.py`, `tests/` … 外部サービス収集（これから作る。設計は `plan/api_collector/02_design.md`）
- `data/master/stores.csv` … 店舗マスタ（`store_key` = `store_N`）
- `data/annotations/gold_sample.csv` … 人手の正解ラベル（手作業の成果。消さない・上書きする前に `.bak` を残す）
- `plan/` … 計画書。目次は `plan/README.md`

## 必ず守ること
1. **既存コードを変更しない**: `src/main.py`, `src/scraper.py`, `src/parser.py`, `src/config.py`, `src/logger.py`, `src/pipeline/**`。import して使うのは可。変更が必要だと判断したら、手を止めてユーザーに確認する。
2. **課金・外部アクセスがあるコマンドは、実行前にユーザーの承認を得る**: `src.run_api`（`--dry-run` と `--from-file` は除く）、`src.pipeline.tag_aspects`、`src.main`。
3. **秘密情報**: `.env`, `~/.env`, `browser_profile/` は開かない・表示しない。キーの有無は `grep -c KEY名 .env` で確かめる。
4. **個人情報を含むデータはコミットしない**: `data/raw/`, `data/raw_vendor/`, `data/processed/`, `data/debug/`, `data/logs/`。テスト用のデータは架空の値に置き換えた最小限のものだけ。
5. raw CSV の形式（`plan/api_collector/02_design.md` §3）を変えない。
6. 予算は未定。無料枠を超える可能性がある実行は、件数と見積もりを示して必ず承認を得る。
7. Python 3.9 なので、`X | None` を使うファイルには `from __future__ import annotations` を書く。`match` 文は使わない。

## トークン節約
- **読まない**: `.venv/`, `data/raw*/`, `data/processed/`, `data/logs/`, `data/debug/`, `browser_profile/`, `plan/api_collector/00_original.md`
- **大きいファイルは部分的に読む**: `src/scraper.py`（394 行）, `src/pipeline/tag_aspects.py`（225 行）は `grep -n` で場所を探してから範囲を指定して読む
- **データは中身を全部出さない**: `head -3`、`df.shape`、`df.columns`、`df.head(3)` まで
- **計画書は該当箇所だけ**: `03_execution_plan.md` の進捗表 → 該当フェーズ → そこで指定された設計書の節
- 下の「既知の仕様」は確認済みなので、調べ直さない

## 既知の仕様（確認済み）
- `normalize` が読むのは `data/raw/` 直下の `reviews_store_N_YYYYMMDD_HHMMSS.csv` だけ（名前が違う・サブフォルダにあるファイルは黙って無視される）
- 既定では店舗ごとに最新ファイル 1 つだけを使う。`--all-snapshots` で全ファイルを統合し、`review_uid` で重複を除く
- `relative_time` 列があれば新形式と判定。新形式の属性列名は `reviewer_attributes`（旧形式は `attributes`）
- 店舗の特定: `source_url` が `stores.csv` の `url` と完全一致 → だめならファイル名の `store_N`
- `review_uid` = `review_id`（あれば）、なければ `h_` + SHA1(store_id|投稿者名|星|本文) の先頭 16 文字。現在のデータと人手ラベルは `h_` 形式
- 日時は JST の naive datetime（タイムゾーン表記なし）で統一
- LLM キャッシュ: `data/processed/llm_cache/<PROMPT_VERSION>/<model>/<review_uid>_<本文SHA1先頭8>.json`
- 観点の定義を変えたら `prompts/aspect_vN.md` と `paths.py` の `PROMPT_VERSION` を上げる
- API キー: `.env` → `~/.env` の順に読む（`GEMINI_API_KEY`、予定: `APIFY_TOKEN`、有料化したら `OUTSCRAPER_API_KEY`）
- 依存: `requests`, `python-dotenv`, `tenacity`, `pandas`, `pyarrow` は導入済み

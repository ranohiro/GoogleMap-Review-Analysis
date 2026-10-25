# Google Map Review Scraper

Googleマップの特定店舗のレビューを抽出するためのスクレイピングツールです。
Playwrightを使用し、ブラウザを自動操作して動的なスクロール読み込みに対応しています。

## ディレクトリ構成

- `data/`: スクレイピングしたデータとログが保存されます。
  - `raw/`: 抽出直後のCSVデータ
  - `processed/`: （今後の拡張用）前処理済みのデータ
  - `logs/`: 実行ログ。エラー時の調査に使用します。
- `src/`: ソースコード
  - `main.py`: 実行用メインスクリプト
  - `scraper.py`: スクレイピングのコアロジック
  - `config.py`: 対象URLや待機時間などの設定
  - `logger.py`: ログ設定

## セットアップ手順

1. 必要なPythonライブラリをインストールします。
   ```bash
   pip install -r requirements.txt
   ```
2. Playwright用のブラウザ（Chromium）をインストールします。
   ```bash
   playwright install chromium
   ```

## 使い方

1. `src/config.py` をエディタで開き、`TARGET_URLS` に対象としたいGoogleマップの店舗URLをリスト形式で追加してください。
2. 以下のコマンドでスクリプトを実行します。

```bash
python -m src.main
```

## 出力

- 実行ログはターミナルに表示されると同時に、`data/logs/` ディレクトリ内にファイルとして保存されます。途中でエラーが出た場合はログファイルを確認してください。
- 取得できたデータは `data/raw/` フォルダに、店舗ごとのCSVおよび全件統合されたCSVとして保存されます。文字化け防止のため `utf-8-sig` (BOM付きUTF-8) エンコーディングを使用しています。

## 口コミ分析パイプライン（`src/pipeline/`）

| ステップ | コマンド | 出力 |
|---|---|---|
| ① 正規化 | `python -m src.pipeline.normalize` | `data/processed/reviews.parquet` |
| ② LLMタグ付け | `python -m src.pipeline.tag_aspects` | `data/processed/review_aspects.parquet`（縦持ち）, `reviews_tagged.parquet`（横持ち） |
| 検証 | `python -m src.pipeline.gold export` → 記入 → `python -m src.pipeline.gold evaluate` | `data/annotations/` |

- 店舗の情報（ブランド・業態・地域）は `data/master/stores.csv` で管理します。新しい店舗を追加したら、ここにも1行追加してください。
- ② には Gemini API キーが必要です。プロジェクト直下の `.env` か `~/.env` に `GEMINI_API_KEY=...` を書いてください（`.env` は Git の管理対象外です）。
- 使うモデルは環境変数 `GEMINI_MODEL` で切り替えられます。利用できるモデルは `--list-models` で確認できます。
- LLM には星の数を渡していません（星に引きずられたラベルによるリークを防ぐため）。
- 観点の定義は `src/pipeline/prompts/aspect_v1.md` にあります。定義を変えたら、ファイル名と `paths.py` の `PROMPT_VERSION` を上げてください（結果のキャッシュはバージョンごとに分けて保存されます）。

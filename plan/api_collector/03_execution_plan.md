# 実行計画（v1.1）

- 設計: [02_design.md](02_design.md)／レビュー: [01_review.md](01_review.md)
- v1.1 の変更: 無料枠だけで Outscraper と Apify を比較し、予算とサービスはその結果で決める流れに変更
- 担当の凡例: **[U]** ユーザーが行う／**[C]** Claude が行う／**[C→U承認]** Claude が準備し、ユーザーの承認後に実行（外部サービスを使うもの）
- 作業が終わったら、下の進捗表とチェックボックスを更新する

## 進捗

| Phase | 内容 | 費用 | 状態 | 完了日 |
|---|---|---|---|---|
| 0 | 準備（アカウント・無料枠の確認） | なし | 未着手 | |
| 1 | 無料枠での比較 → サービス・予算の決定 | 無料枠内 | 未着手 | |
| 2 | データ契約と変換処理・ファイル取り込み（オフライン） | なし | 未着手 | |
| 3 | API クライアント（ポーリング・リトライ・回収） | なし | 未着手 | |
| 4 | CLI とコストガード | なし | 未着手 | |
| 5 | 本番移行（store_2 → 全店舗）と ID 移行 | 無料枠内の見込み | 未着手 | |
| 6 | ドキュメント整備 | なし | 未着手 | |

```mermaid
flowchart LR
    P0["Phase 0<br>準備"] --> P1["Phase 1<br>無料枠で比較"]
    P1 --> D{"サービス・予算<br>を決める"}
    D --> P2["Phase 2<br>変換・取り込み<br>（オフライン）"]
    P2 --> P3["Phase 3<br>API クライアント"]
    P3 --> P4["Phase 4<br>CLI・コストガード"]
    P4 --> P5["Phase 5<br>本番移行"]
    P5 --> P6["Phase 6<br>ドキュメント"]
    D -. "Outscraper を無料枠の CSV だけで使う場合" .-> P2b["Phase 3 を省略し<br>Phase 4 は取り込みのみ"]
    P2b --> P5
```

---

## 全フェーズ共通の完了条件

- [ ] 既存コードに差分がない: `git diff --stat -- src/main.py src/scraper.py src/parser.py src/config.py src/logger.py src/pipeline/` の出力が空
- [ ] `pytest` がすべて通る（Phase 2 以降）
- [ ] 個人情報を含むファイルがコミットされていない: `git status --short` に `data/raw`, `data/raw_vendor`, `data/processed`, `data/debug`, `data/logs` のファイルが出ない
- [ ] この文書の進捗表を更新した

---

## Phase 0: 準備

| ID | 担当 | 作業 | 成果物 |
|---|---|---|---|
| P0-1 | [U] | Outscraper の無料アカウントを作成。公式の料金ページで、無料枠の件数・リセット時期・CSV 以外の取得方法がないかを確認 | 無料枠の条件 |
| P0-2 | [U] | Apify の無料アカウントを作成。料金ページで毎月の無料クレジットと、無料プランでの制限（1 店舗あたりの件数など）を確認。API トークンを発行し、プロジェクト直下の `.env` に `APIFY_TOKEN=...` を追記 | `.env`、無料枠の条件 |
| P0-3 | [U] | Apify Store で使う Actor を選ぶ（第一候補は公式の `compass/google-maps-reviews-scraper`）。Actor ページの単価を確認 | Actor 名・単価 |
| P0-4 | [C] | `.gitignore` に `data/raw_vendor/` を追記 | `.gitignore` |
| P0-5 | [C] | `data/master/stores.csv` に空の `place_id` 列を追加し、`python -m src.pipeline.normalize` が従来どおり 159 件を出力することを確認（ローカル処理のみ） | `stores.csv` |
| P0-6 | [C] | P0-1〜P0-3 の結果を [02_design.md §1.1・§7](02_design.md#11-比較するサービスの無料枠2026-10-31-時点の公開情報phase-0-で公式ページを確認) に反映 | 設計書の更新 |

**完了条件**
- [ ] `.env` に `APIFY_TOKEN` がある（Claude は値を読まない。`grep -c APIFY_TOKEN .env` で行数だけ確認）
- [ ] 両サービスの無料枠の条件がわかっている
- [ ] `git check-ignore data/raw_vendor/x.json` が除外を示す
- [ ] `normalize` の件数が変わらない

---

## Phase 1: 無料枠での比較

目的: 同じ店舗（store_2）を両方のサービスで取り、質を比べて**サービスと予算を決める**。ここで取ったデータは Phase 2 以降の開発（課金なし）にも使う。

| ID | 担当 | 作業 | 成果物 |
|---|---|---|---|
| P1-1 | [U] | Outscraper の Web 画面で store_2 の口コミを取得し、**CSV で**ダウンロード（言語は日本語、件数は全件＝200 件程度まで）。`data/raw_vendor/outscraper/` に置く | Outscraper の CSV |
| P1-2 | [C] | `src/api/config.py`（トークン読み込み）と `src/api/providers/apify.py` の `submit()` / `wait()` の最小版を作る。結果はそのまま `data/raw_vendor/apify/` に保存 | 最小のクライアント |
| P1-3 | [C→U承認] | Apify で store_2 を取得（件数 200 まで、新しい順、日本語、課金上限の指定ができれば指定）。無料プランの制限で件数が足りなければ、その事実を記録する | Apify の JSON |
| P1-4 | [C] | 両方のデータを、下の評価表で比べて記入し、[02_design.md §4](02_design.md#4-サービス別の項目対応候補要実測) の「確定」列を更新 | 評価表・設計書の更新 |
| P1-5 | [C] | 各サービスのデータから 3〜5 件を抜き出し、投稿者名・ID・本文を架空の値に置き換えて `tests/api/fixtures/` に置く（本文なし・オーナー返信あり・星 1 と星 5 を含める） | テスト用データ |
| P1-6 | [U] | 両サービスの管理画面で、無料枠の消費量（課金が発生していないこと）を確認 | 消費量 |
| P1-7 | [U] | 評価表を見て D1（サービス）・D2（規模）・D3（予算）を決める | 決定 |

**評価表**（P1-4。比較の基準は Google マップ上の総件数と Playwright 版の 154 件）

| 評価項目 | Outscraper（CSV） | Apify（API） |
|---|---|---|
| 取得件数 / Google マップ上の総件数 | | |
| 本文の欠け・途中切れ | | |
| 本文が原文か（翻訳文が混ざらないか）・言語コードの有無 | | |
| 投稿日時の精度（日時か、「〜か月前」だけか） | | |
| オーナー返信と返信日時 | | |
| ローカルガイド・投稿者の口コミ数 | | |
| 項目別評価（料理・サービス・雰囲気など） | | |
| `review_id` の形式（両サービスで同じか） | | |
| 短縮 URL で指定できたか／Place ID が必要か | | |
| 所要時間・手作業の量 | | |
| 無料枠で続けられる規模（月あたり件数） | | |
| 有料にした場合の 1,000 件あたりの費用 | | |
| `store_1`（店名要確認）の正式な店名 | | |

**判断の目安**
- 質が同等なら、自動化できる方（API が無料枠でも使える方）を選ぶ
- 無料枠の Outscraper CSV で十分なら、Phase 3（API クライアント）を省略し、ファイル取り込みだけで運用できる
- どちらも基準（本文・星・投稿日時・`review_id` が取れ、件数が Google マップの表示と大きく違わない）を満たさなければ、SerpApi などで同じ比較を行う

---

## Phase 2: データ契約と変換処理・ファイル取り込み（オフライン・課金なし）

Phase 1 で使ったサービスの分を作ります（採用しなかったサービスの変換処理は、比較のために作ったものがあれば残してよい）。

| ID | 担当 | 作業 | 成果物 |
|---|---|---|---|
| P2-1 | [C] | `pytest.ini`（`pythonpath = .`、`testpaths = tests`）と `requirements-dev.txt`（`pytest`）を作り、`.venv` に pytest を入れる | テスト環境 |
| P2-2 | [C] | `src/api/base.py`（`Target`, `ReviewProvider`） | |
| P2-3 | [C] | `src/api/targets.py`（`stores.csv` → `Target`、`--store`/`--all` の解決、存在しない `store_key` はエラー） | |
| P2-4 | [C] | 各 provider の `load_file()` と `to_rows()`（§4 の確定版に従う。JST 変換、原文の採用、`parse_attributes` による補完） | |
| P2-5 | [C] | `src/api/writer.py`（§3 の列順で CSV 出力、元データ保存、実行記録の追記・更新） | |
| P2-6 | [C] | `test_mapping.py`, `test_normalize_compat.py` | テスト |

**完了条件**
- [ ] `pytest` が通る
- [ ] 結合テストで、`normalize.build()` が店舗を特定でき、`review_uid == review_id`、`time_is_estimated` がすべて False、`post_time` がテスト用データの UTC 時刻 + 9 時間になっている

---

## Phase 3: API クライアント（ポーリング・リトライ・回収）

採用したサービスを API で使う場合だけ行います（Outscraper を無料枠の CSV だけで使うなら省略）。

| ID | 担当 | 作業 |
|---|---|---|
| P3-1 | [C] | `submit()`: 自動リトライなし。実行 ID を受け取ったらすぐ実行記録に `submitted` で書く |
| P3-2 | [C] | `wait()`: `tenacity` で指数バックオフ（接続エラー・429・5xx）、全体のタイムアウト、完了したら口コミのリストを返す |
| P3-3 | [C] | `--resume` 用に、実行 ID から結果だけを取得する関数 |
| P3-4 | [C] | `test_polling.py`（HTTP 呼び出しを差し替えて確認） |

**完了条件**
- [ ] `pytest` が通る
- [ ] submit が失敗・タイムアウトしたときに再送されないことをテストで確認
- [ ] API キーがログ・例外メッセージに出ないことを確認

---

## Phase 4: CLI とコストガード

| ID | 担当 | 作業 |
|---|---|---|
| P4-1 | [C] | `src/api/cost.py`（見積もり、しきい値での確認、上限での拒否、部分取得の警告）。API を使わない場合は部分取得の警告だけ |
| P4-2 | [C] | `src/run_api.py`（[02_design.md §6.1](02_design.md#61-cli) のオプション一式、店舗ごとの成功・失敗の一覧） |
| P4-3 | [C] | `test_cost_guard.py` |
| P4-4 | [C] | Phase 1 のデータに `--from-file` を使って raw CSV を作り、一時フォルダで `normalize` を通して件数と内容を確認（課金なし） |

**完了条件**
- [ ] `--dry-run` と `--from-file` で外部サービスが呼ばれない（テストで確認）
- [ ] しきい値超えで確認が出る／対話できない環境では中止する
- [ ] `MAX_REVIEWS_PER_RUN` を超える指定は拒否する
- [ ] `--from-file` で作った CSV が `normalize` に通る

---

## Phase 5: 本番移行（store_2 → 全店舗）と ID 移行

| ID | 担当 | 作業 |
|---|---|---|
| P5-1 | [C] | `src/api/migrate_uid.py`（[02_design.md §10](02_design.md#10-既存データの移行review_uid)）と、その `--dry-run` |
| P5-2 | [C] | バックアップ: `reviews.parquet` → `reviews_before_api.parquet`、`data/raw/reviews_store_2_*.csv` → `data/raw/_archive/` |
| P5-3 | [C→U承認] | 採用したサービスで store_2 を取り込む（Phase 1 のデータが全件なら、それを `--from-file` で使い、再取得しない） |
| P5-4 | [C] | `normalize` を実行し、件数を Playwright 版（154 件）と比べる。大きく違えば原因を調べて報告 |
| P5-5 | [C] | `migrate_uid --store store_2` を実行し、対応できなかった件数を報告 |
| P5-6 | [C→U承認] | `tag_aspects` を実行（キャッシュにない件数を先に伝えて承認を得る）→ `gold evaluate` で移行前と同じ評価件数が出ることを確認 |
| P5-7 | [U]／[C→U承認] | `store_1` も同じ手順で移行し、`stores.csv` の店名を正式名に更新 |
| P5-8 | [U] | D4（Playwright 版の扱い）を確定 |

**完了条件**
- [ ] `reviews.parquet` の 2 店舗が外部サービスの取得分になり、重複がない
- [ ] `gold evaluate` の対象件数が移行前と同じ（対応不明があれば理由を記録）
- [ ] 無料枠を超えていない（超える場合は事前に承認を得ている）

---

## Phase 6: ドキュメント整備

| ID | 担当 | 作業 |
|---|---|---|
| P6-1 | [C] | `README.md` に外部サービス版の節（セットアップ・コマンド・無料枠と費用の注意）と、Playwright 版との使い分けを追記 |
| P6-2 | [C] | `CLAUDE.md` の「予定」と書いたコマンドを確定版に直し、既知の仕様を更新 |
| P6-3 | [C] | この文書の進捗表を「完了」にし、バックログを見直す |

---

## バックログ

| 項目 | 前提・注意 |
|---|---|
| 差分取得（`--since`）の定常運用 | `normalize --all-snapshots` との組み合わせ手順を決めてから（[01_review.md R3](01_review.md#r3-店舗ごとに最新ファイルだけを使うルールと件数上限差分取得がぶつかる原案-6-2-6-3)） |
| 店舗の追加 | analysis_proposal フェーズ 4（寄与度モデル）に必要な店舗数を決める。無料枠を超えるなら D3 を見直す |
| 項目別評価と LLM 観点の一致度の検証 | Phase 1 で項目別評価が取れると確認できた場合 |
| 定期実行 | 差分取得が安定してから |
| 3 社目のサービス（SerpApi など） | Phase 1 で両方とも基準を満たさない場合、または料金・仕様の変更で必要になったとき |

---

## セッションの分け方（トークン節約）

1 フェーズ 1 セッションを目安にします。新しいセッションでは、最初に `CLAUDE.md` とこの文書の該当フェーズだけを読みます。

| Phase | 最初に読むもの | 読まなくてよいもの |
|---|---|---|
| 0 | この文書の Phase 0、`.gitignore`、`data/master/stores.csv` | `src/` 全般 |
| 1 | Phase 1、[02_design.md §1.1・§4・§8](02_design.md#4-サービス別の項目対応候補要実測) | `src/scraper.py`, `src/pipeline/` |
| 2 | Phase 2、[02_design.md §3・§5](02_design.md#3-データ契約raw-csv)、`src/pipeline/normalize.py` | `src/scraper.py`（列は §3.2 に記載済み） |
| 3 | Phase 3、[02_design.md §8](02_design.md#8-信頼性)、`src/api/providers/` の該当ファイル | `src/pipeline/` |
| 4 | Phase 4、[02_design.md §6・§7](02_design.md#6-処理の流れ)、`src/api/` | `src/pipeline/` |
| 5 | Phase 5、[02_design.md §10](02_design.md#10-既存データの移行review_uid)、`src/pipeline/gold.py`、`tag_aspects.py` の 60〜110 行 | `src/scraper.py` |
| 6 | Phase 6、`README.md`、`CLAUDE.md` | `src/` 全般 |

すべてのフェーズで、原案（[00_original.md](00_original.md)）と全体レビュー（[01_review.md](01_review.md)）は読まなくて構いません。判断の理由を確かめたいときだけ該当の項目を読みます。

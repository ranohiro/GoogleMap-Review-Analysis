# plan/ 目次

| ファイル | 内容 | 状態 |
|---|---|---|
| [analysis_proposal.md](analysis_proposal.md) | 口コミ × 星評価 分析システム提案書 | フェーズ 1〜2 のコード実装済み（`src/pipeline/`）。フェーズ 3〜5 は `analysis_tool/` で具体化 |
| [analysis_tool/02_execution_plan.md](analysis_tool/02_execution_plan.md) | 口コミ分析ツール（ダッシュボード）の実行計画（進捗表あり） | 未着手 |
| [analysis_tool/01_design.md](analysis_tool/01_design.md) | 口コミ分析ツールの設計書（画面・計算の定義・未決事項） | v1.0 |
| [api_collector/03_execution_plan.md](api_collector/03_execution_plan.md) | **外部サービス収集の実行計画（進捗表あり）** ← 作業はここから | 進行中 |
| [api_collector/02_design.md](api_collector/02_design.md) | 外部サービス収集の設計書（無料枠の比較・データ契約・構成・コストガード） | v1.1 |
| [api_collector/01_review.md](api_collector/01_review.md) | 原案のレビューと改善提案（判断の理由） | 確定 |
| [api_collector/00_original.md](api_collector/00_original.md) | 原案（凍結。実装には使わない） | 凍結 |

## 運用ルール
- 実装の正は `02_design.md` と `03_execution_plan.md`。設計を変えたら `02_design.md` の版と日付を更新する
- 作業が終わったら `03_execution_plan.md` の進捗表とチェックボックスを更新する
- 新しい計画を作るときは `plan/<テーマ>/` を作り、この目次に 1 行足す

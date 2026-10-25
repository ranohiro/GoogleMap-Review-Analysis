import argparse
import os
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright
from src.logger import setup_logger
from src.config import TARGET_URLS
from src.scraper import launch_context, login_flow, scrape_google_maps_reviews


def parse_args():
    parser = argparse.ArgumentParser(description="Googleマップ クチコミ収集ツール")
    parser.add_argument("--login", action="store_true",
                        help="初回のみ: ブラウザでGoogleにログインし、ログイン状態をプロファイルに保存します")
    parser.add_argument("--manual", action="store_true",
                        help="半自動モード: スクロールは人が行い、スクリプトは通信の記録だけを行います")
    return parser.parse_args()


def main():
    args = parse_args()
    logger = setup_logger()

    with sync_playwright() as p:
        context = launch_context(p, logger)
        try:
            if args.login:
                login_flow(context, logger)
                return

            logger.info("Googleマップ レビュー収集を開始します。")

            if not TARGET_URLS or TARGET_URLS[0] == "https://www.google.com/maps/place/...":
                logger.error("config.py に対象店舗のURLが設定されていません。TARGET_URLS を更新して再実行してください。")
                return

            # 保存先ディレクトリの準備
            base_dir = os.path.dirname(os.path.dirname(__file__))
            raw_dir = os.path.join(base_dir, 'data', 'raw')
            os.makedirs(raw_dir, exist_ok=True)

            all_results = []

            for idx, url in enumerate(TARGET_URLS):
                logger.info(f"--- 店舗 {idx+1}/{len(TARGET_URLS)} の処理を開始 ---")

                # スクレイピングの実行
                df = scrape_google_maps_reviews(url, logger, context, store_index=idx + 1, manual=args.manual)

                if df.empty:
                    logger.warning(f"店舗 {idx+1} のデータは取得できませんでした。")
                    continue

                # 統合用に元URLを追記
                df['source_url'] = url

                # CSVファイルとして一時保存 (店舗ごとのバックアップ)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_filename = f"reviews_store_{idx+1}_{timestamp}.csv"
                output_path = os.path.join(raw_dir, output_filename)

                try:
                    df.to_csv(output_path, index=False, encoding='utf-8-sig')
                    logger.info(f"店舗 {idx+1} のデータを保存しました: {output_path}")
                except Exception as e:
                    logger.error(f"データのCSV保存中にエラーが発生しました: {e}")

                all_results.append(df)

            # 全店舗の結合データを保存
            if all_results:
                final_df = pd.concat(all_results, ignore_index=True)
                final_path = os.path.join(raw_dir, f"all_reviews_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
                final_df.to_csv(final_path, index=False, encoding='utf-8-sig')
                logger.info(f"すべての処理が完了しました。統合データ（{len(final_df)} 件）を保存しました: {final_path}")
            else:
                logger.info("処理が完了しましたが、有効なデータは取得できませんでした。")
        finally:
            context.close()


if __name__ == "__main__":
    main()

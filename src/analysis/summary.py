"""確認用 CLI ツール (summary.py)

コマンドラインから手軽にデータ概要・星分布・観点集計を確認できる。
使用例:
    python -m src.analysis.summary
    python -m src.analysis.summary --store store_2
    python -m src.analysis.summary --store store_2 --rating 1 2
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

import pandas as pd

from src.analysis import filters, load, metrics
from src.analysis.stats import MIN_N


def format_ci(val: float, low: float, upp: float, is_pct: bool = False) -> str:
    """値と信頼区間を文字列整形する。"""
    if pd.isna(val):
        return "-"
    if is_pct:
        v_str = f"{val * 100:.1f}%"
        if not pd.isna(low) and not pd.isna(upp):
            return f"{v_str} [{low * 100:.1f}%, {upp * 100:.1f}%]"
        return v_str
    v_str = f"{val:.2f}"
    if not pd.isna(low) and not pd.isna(upp):
        return f"{v_str} [{low:.2f}, {upp:.2f}]"
    return v_str


def run_summary(store: Optional[str] = None, ratings: Optional[list[int]] = None) -> None:
    """サマリーを出力する。"""
    dataset = load.load_all()
    reviews = dataset.reviews
    meta = dataset.metadata

    print("=" * 68)
    print(" Googleマップ 口コミ分析 サマリー")
    print("=" * 68)
    print(f"観点プロンプト版: {meta.get('prompt_version', '不明')}")
    print(f"データディレクトリ: {meta.get('data_dir')}")
    if meta.get("reviews_tagged_mtime"):
        print(f"タグ付きデータ更新日時: {meta['reviews_tagged_mtime']}")
    elif meta.get("reviews_raw_mtime"):
        print(f"正規化データ更新日時: {meta['reviews_raw_mtime']} (タグ付け未実行)")

    if reviews.empty:
        print("\n[!] 口コミデータが存在しません。")
        return

    # 絞り込み
    filtered = reviews.copy()
    if store:
        filtered = filters.apply(filtered, stores=[store])
        print(f"\n[絞り込み] 店舗: {store}")
    if ratings:
        filtered = filters.apply(filtered, ratings=ratings)
        print(f"[絞り込み] 星評価: {ratings}")

    # 基本指標
    r_sum = metrics.rating_summary(filtered)
    total = r_sum["total_reviews"]
    has_text = r_sum["has_text_count"]
    tagged = r_sum["tagged_count"]

    print("-" * 68)
    print("【1. 口コミ基本情報】")
    print(f"  総口コミ数: {total:,} 件")
    print(f"  本文あり  : {has_text:,} 件 ({format_ci(r_sum['has_text_rate'], r_sum['has_text_ci_lower'], r_sum['has_text_ci_upper'], is_pct=True)})")
    print(f"  タグ付け済: {tagged:,} 件 ({r_sum['tagged_rate'] * 100:.1f}%)")
    mean_r_str = format_ci(r_sum["mean_rating"], r_sum["mean_rating_ci_lower"], r_sum["mean_rating_ci_upper"])
    print(f"  平均星    : {mean_r_str}")

    print("\n  星分布:")
    for star in range(5, 0, -1):
        cnt = r_sum["distribution"][str(star)]
        pct = r_sum["distribution_percent"][str(star)]
        bar = "#" * int(pct * 30)
        print(f"    ★{star}: {cnt:4d} 件 ({pct * 100:5.1f}%) | {bar}")

    # オーナー返信
    reply_metrics = metrics.owner_reply_metrics(filtered)
    print("\n  オーナー返信:")
    print(f"    全体返信率: {format_ci(reply_metrics['reply_rate'], reply_metrics['reply_rate_ci_lower'], reply_metrics['reply_rate_ci_upper'], is_pct=True)} ({reply_metrics['reply_count']}/{reply_metrics['total_reviews']} 件)")
    if reply_metrics["low_rating_total"] > 0:
        print(f"    低評価(★1-2)返信率: {format_ci(reply_metrics['low_rating_reply_rate'], reply_metrics['low_rating_reply_ci_lower'], reply_metrics['low_rating_reply_ci_upper'], is_pct=True)} ({reply_metrics['low_rating_reply_count']}/{reply_metrics['low_rating_total']} 件)")
    if reply_metrics["median_reply_days"] is not None:
        print(f"    返信までの中央値: {reply_metrics['median_reply_days']} 日")

    # 観点集計
    print("-" * 68)
    print("【2. 観点別分析】")
    if tagged == 0:
        print("  ※ タグ付け未実行 (reviews_tagged.parquet がまだ作成されていません)")
        print("     画面①（全店舗一覧）や星評価の集計はそのまま利用可能です。")
    else:
        asp_df = metrics.aspect_summary(filtered)
        low_df = metrics.low_rating_drivers(filtered).set_index("aspect")

        print(f"  (分母 n = {asp_df['n'].iloc[0] if not asp_df.empty else 0} 件: 本文あり&タグ付け済み)")
        if not asp_df.empty and asp_df['n'].iloc[0] < MIN_N:
            print(f"  [注] 件数が少数のため（n < {MIN_N}）、信頼区間が広く参考値となります。")

        header = f"  {'観点':<10} | {'言及率 (95% CI)':<22} | {'平均感情':<8} | {'否定率':<8} | {'低評価 Lift':<12}"
        print(header)
        print("  " + "-" * 66)

        for _, row in asp_df.iterrows():
            asp_key = row["aspect"]
            asp_lbl = row["aspect_label"]
            m_rate = format_ci(row["mention_rate"], row["mention_rate_ci_lower"], row["mention_rate_ci_upper"], is_pct=True)
            sent_str = f"{row['avg_sentiment']:+.2f}" if not pd.isna(row["avg_sentiment"]) else "-"
            neg_rate_str = f"{row['neg_rate'] * 100:.1f}%"

            lift_val = low_df.loc[asp_key, "lift"] if asp_key in low_df.index else np.nan
            lift_str = f"{lift_val:.2f}" if not pd.isna(lift_val) else "-"

            ref_mark = "*" if row["is_reference"] else " "
            print(f"  {asp_lbl:<10} | {m_rate:<22} | {sent_str:<8} | {neg_rate_str:<8} | {lift_str:<12}{ref_mark}")

    print("=" * 68)


def main():
    parser = argparse.ArgumentParser(description="Googleマップ 口コミ分析サマリー表示 CLI")
    parser.add_argument("--store", type=str, help="店舗キー (例: store_2)")
    parser.add_argument("--rating", type=int, nargs="+", help="対象星評価 (例: 1 2)")
    args = parser.parse_args()

    run_summary(store=args.store, ratings=args.rating)


if __name__ == "__main__":
    main()

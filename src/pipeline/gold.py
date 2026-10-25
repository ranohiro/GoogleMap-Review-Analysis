"""
LLMタグ付けの精度検証用：人手の正解ラベル（gold）の作成と評価。

1) export: 本文ありの口コミから星の層別でサンプルを抽出し、記入用CSVを作る
   python -m src.pipeline.gold export --n 50
   → data/annotations/gold_sample.csv の各観点列に -2〜2 を記入（触れていなければ空欄）
     ※ 判定がLLMと同条件になるよう、星の数はCSVに含めていません

2) evaluate: 記入済みCSVとLLM結果を比較
   python -m src.pipeline.gold evaluate
   → 観点ごとの検出 Precision/Recall/F1、感情の完全一致率・±1一致率・重み付きκ
"""
import argparse
import os

import numpy as np
import pandas as pd

from src.pipeline.paths import ANNOTATION_DIR, ASPECTS, PROCESSED_DIR

GOLD_PATH = os.path.join(ANNOTATION_DIR, "gold_sample.csv")


def export(n, seed):
    reviews = pd.read_parquet(os.path.join(PROCESSED_DIR, "reviews.parquet"))
    pool = reviews[reviews["has_text"]]
    if len(pool) <= n:
        sample = pool
    else:  # 星ごとに比例配分（最低1件）
        frac = n / len(pool)
        sample = pool.groupby("rating", group_keys=False).apply(
            lambda g: g.sample(max(1, round(len(g) * frac)), random_state=seed))
    out = sample[["review_uid", "store_name", "review_text"]].sample(frac=1, random_state=seed).copy()
    for key, label in ASPECTS.items():
        out[f"{key}({label})"] = ""
    out["memo"] = ""
    os.makedirs(ANNOTATION_DIR, exist_ok=True)
    if os.path.exists(GOLD_PATH):
        raise SystemExit(f"{GOLD_PATH} は既に存在します（記入済みデータの上書き防止）。別名に退避してから再実行してください。")
    out.to_csv(GOLD_PATH, index=False, encoding="utf-8-sig")
    print(f"保存: {GOLD_PATH}（{len(out)} 件）")


def _weighted_kappa(a, b, labels=(-2, -1, 0, 1, 2)):
    """二次重み付きκ（順序尺度の一致度）。"""
    idx = {v: i for i, v in enumerate(labels)}
    k = len(labels)
    O = np.zeros((k, k))
    for x, y in zip(a, b):
        O[idx[x], idx[y]] += 1
    if O.sum() == 0:
        return np.nan
    W = np.array([[(i - j) ** 2 for j in range(k)] for i in range(k)]) / (k - 1) ** 2
    E = np.outer(O.sum(1), O.sum(0)) / O.sum()
    denom = (W * E).sum()
    return 1 - (W * O).sum() / denom if denom else np.nan


def evaluate():
    gold = pd.read_csv(GOLD_PATH, encoding="utf-8-sig")
    llm = pd.read_parquet(os.path.join(PROCESSED_DIR, "reviews_tagged.parquet")).set_index("review_uid")
    gold = gold[gold["review_uid"].isin(llm.index[llm["llm_tagged"].fillna(False)])]
    if gold.empty:
        raise SystemExit("LLMタグ付け済みの口コミと一致する gold がありません")

    rows = []
    for key, label in ASPECTS.items():
        g = pd.to_numeric(gold[f"{key}({label})"], errors="coerce")
        p = llm.loc[gold["review_uid"], f"{key}_sent"].to_numpy()
        g = g.to_numpy()
        g_m, p_m = ~np.isnan(g), ~np.isnan(p)
        tp, fp, fn = (g_m & p_m).sum(), (~g_m & p_m).sum(), (g_m & ~p_m).sum()
        prec = tp / (tp + fp) if tp + fp else np.nan
        rec = tp / (tp + fn) if tp + fn else np.nan
        f1 = 2 * prec * rec / (prec + rec) if prec and rec else np.nan
        both = g_m & p_m
        gs, ps = g[both].astype(int), p[both].astype(int)
        rows.append({
            "観点": label, "gold言及": int(g_m.sum()), "LLM言及": int(p_m.sum()),
            "Precision": prec, "Recall": rec, "F1": f1,
            "感情_完全一致": (gs == ps).mean() if len(gs) else np.nan,
            "感情_±1一致": (abs(gs - ps) <= 1).mean() if len(gs) else np.nan,
            "感情_重み付きκ": _weighted_kappa(gs, ps) if len(gs) else np.nan,
        })
    res = pd.DataFrame(rows).round(2)
    print(f"評価件数: {len(gold)}")
    print(res.to_string(index=False))
    res.to_csv(os.path.join(ANNOTATION_DIR, "gold_eval_result.csv"), index=False, encoding="utf-8-sig")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--n", type=int, default=50)
    e.add_argument("--seed", type=int, default=42)
    sub.add_parser("evaluate")
    args = ap.parse_args()
    export(args.n, args.seed) if args.cmd == "export" else evaluate()


if __name__ == "__main__":
    main()

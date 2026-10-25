"""
① 正規化: data/raw/reviews_store_*.csv を統合し、分析用の reviews.parquet を作る。

- 旧形式（reviewer_name, rating, review_text, post_time="7 年前", attributes）と
  新形式（review_id, post_time=絶対日時, relative_time, owner_reply ...）の両方に対応。
- 店舗の特定は source_url（新形式）→ ファイル名の store_N（旧形式）の順で、
  data/master/stores.csv と突き合わせる。
- 同じ店舗のファイルが複数ある場合は、最新の取得ファイルのみ採用する。

実行: python -m src.pipeline.normalize
"""
import argparse
import glob
import hashlib
import os
import re
from datetime import datetime, timedelta

import pandas as pd

from src.pipeline.paths import MASTER_STORES, PROCESSED_DIR, RAW_DIR

_FILE_RE = re.compile(r"reviews_(store_\d+)_(\d{8}_\d{6})\.csv$")
_REL_RE = re.compile(r"(\d+)\s*(年|か月|ヶ月|週間|日|時間|分)前")
_UNIT_DAYS = {"年": 365.25, "か月": 30.44, "ヶ月": 30.44, "週間": 7, "日": 1, "時間": 1 / 24, "分": 1 / 1440}


def _num(s):
    return int(s.replace(",", "")) if s else None


def parse_attributes(text):
    """'ローカルガイド · 333 件のクチコミ · 1,417 枚の写真' → (is_local_guide, review_count, photo_count)"""
    if not isinstance(text, str):
        return False, None, None
    is_lg = ("ローカルガイド" in text) or ("Local Guide" in text)
    rc = re.search(r"([\d,]+)\s*件のクチコミ", text) or re.search(r"([\d,]+)\s*reviews?", text)
    pc = re.search(r"([\d,]+)\s*枚の写真", text) or re.search(r"([\d,]+)\s*photos?", text)
    return is_lg, _num(rc.group(1)) if rc else None, _num(pc.group(1)) if pc else None


def parse_relative(text, scraped_at):
    """'最終編集: 6 年前' → (推定投稿日時, 編集済みか)。年単位は粗い推定である点に注意。"""
    if not isinstance(text, str):
        return None, False
    edited = "編集" in text
    m = _REL_RE.search(text)
    if not m:
        return None, edited
    days = int(m.group(1)) * _UNIT_DAYS[m.group(2)]
    return scraped_at - timedelta(days=days), edited


def _uid(row):
    if isinstance(row.get("review_id"), str) and row["review_id"]:
        return row["review_id"]
    key = f'{row["store_id"]}|{row.get("reviewer_name")}|{row.get("rating")}|{row.get("review_text") or ""}'
    return "h_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def load_raw_files(raw_dir):
    files = []
    for path in glob.glob(os.path.join(raw_dir, "reviews_store_*.csv")):
        m = _FILE_RE.search(os.path.basename(path))
        if m:
            files.append({"path": path, "store_key": m.group(1),
                          "scraped_at": datetime.strptime(m.group(2), "%Y%m%d_%H%M%S")})
    return pd.DataFrame(files)


def normalize_one(path, store_key, scraped_at, stores):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["source_file"] = os.path.basename(path)
    df["scraped_at"] = scraped_at

    # --- 店舗の特定: source_url 優先、無ければファイル名の store_N
    store = None
    if "source_url" in df.columns and df["source_url"].notna().any():
        hit = stores[stores["url"] == df["source_url"].dropna().iloc[0]]
        store = hit.iloc[0] if len(hit) else None
    if store is None:
        hit = stores[stores["store_key"] == store_key]
        store = hit.iloc[0] if len(hit) else None
    if store is None:
        raise ValueError(f"{path}: stores.csv に該当店舗がありません（store_key={store_key}）")
    for col in ["store_id", "store_name", "brand", "genre", "area"]:
        df[col] = store[col]

    # --- 新旧スキーマの吸収
    is_new = "relative_time" in df.columns
    if is_new:
        df["post_time"] = pd.to_datetime(df["post_time"], errors="coerce")
        df["time_is_estimated"] = df["post_time"].isna()
        rel = df["relative_time"]
        attr_col = "reviewer_attributes"
    else:
        rel = df["post_time"]
        df["post_time"] = pd.NaT
        df["time_is_estimated"] = True
        attr_col = "attributes"

    parsed = rel.apply(lambda t: parse_relative(t, scraped_at))
    df["relative_time"] = rel
    df["is_edited"] = parsed.str[1]
    est = pd.to_datetime(parsed.str[0])
    df["post_time"] = df["post_time"].fillna(est)

    attrs = df.get(attr_col, pd.Series([None] * len(df))).apply(parse_attributes)
    df["reviewer_attributes"] = df.get(attr_col)
    if "is_local_guide" not in df.columns:
        df["is_local_guide"] = attrs.str[0]
    if "reviewer_review_count" not in df.columns:
        df["reviewer_review_count"] = attrs.str[1]
    df["reviewer_photo_count"] = attrs.str[2]

    for col in ["review_id", "reviewer_id", "owner_reply", "owner_reply_time", "updated_time"]:
        if col not in df.columns:
            df[col] = None
    return df


def build(raw_dir=RAW_DIR, keep_all_snapshots=False):
    stores = pd.read_csv(MASTER_STORES, dtype=str)
    files = load_raw_files(raw_dir)
    if files.empty:
        raise SystemExit(f"{raw_dir} に reviews_store_*.csv がありません")
    if not keep_all_snapshots:
        files = files.sort_values("scraped_at").groupby("store_key").tail(1)

    df = pd.concat([normalize_one(r.path, r.store_key, r.scraped_at, stores) for r in files.itertuples()],
                   ignore_index=True)

    df["review_text"] = df["review_text"].fillna("").astype(str).str.strip()
    df["has_text"] = df["review_text"] != ""
    df["text_len"] = df["review_text"].str.len()
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["has_owner_reply"] = df["owner_reply"].fillna("").astype(str).str.strip() != ""
    df["post_year"] = df["post_time"].dt.year
    df["review_uid"] = df.apply(_uid, axis=1)

    before = len(df)
    df = df.sort_values("scraped_at").drop_duplicates("review_uid", keep="last")
    dup = before - len(df)

    cols = ["review_uid", "review_id", "store_id", "store_name", "brand", "genre", "area",
            "rating", "review_text", "has_text", "text_len",
            "reviewer_name", "reviewer_id", "is_local_guide", "reviewer_review_count", "reviewer_photo_count",
            "reviewer_attributes",
            "post_time", "time_is_estimated", "post_year", "relative_time", "is_edited", "updated_time",
            "owner_reply", "has_owner_reply", "owner_reply_time", "source_file", "scraped_at"]
    df = df[cols].reset_index(drop=True)
    for c in ["reviewer_review_count", "reviewer_photo_count", "post_year"]:
        df[c] = df[c].astype("Int64")
    for c in ["review_id", "reviewer_id", "owner_reply", "relative_time", "reviewer_name"]:
        df[c] = df[c].astype("string")
    for c in ["owner_reply_time", "updated_time"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    return df, dup


def main():
    ap = argparse.ArgumentParser(description="rawレビューCSVを統合・正規化")
    ap.add_argument("--all-snapshots", action="store_true", help="同一店舗の過去取得分も含めて統合（重複は除去）")
    args = ap.parse_args()

    df, dup = build(keep_all_snapshots=args.all_snapshots)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    out = os.path.join(PROCESSED_DIR, "reviews.parquet")
    df.to_parquet(out, index=False)
    df.to_csv(out.replace(".parquet", ".csv"), index=False, encoding="utf-8-sig")

    print(f"保存: {out}（{len(df)} 件, 重複除去 {dup} 件）")
    summary = df.groupby(["store_id", "store_name"]).agg(
        件数=("review_uid", "size"), 本文あり=("has_text", "sum"), 平均星=("rating", "mean"),
        日時推定=("time_is_estimated", "mean")).round(2)
    print(summary.to_string())


if __name__ == "__main__":
    main()

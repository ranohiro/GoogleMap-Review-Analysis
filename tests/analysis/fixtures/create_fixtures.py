"""架空のテスト用フィクスチャ生成スクリプト。

設計書 §10 に従い、実データを使わずに創作した架空のデータを生成する。
- 口コミ 25件 (2店舗分、★1〜5、本文あり/なし、推定日時/実日時、返信あり/なし、英語口コミ含む)
- 投稿者名・投稿者IDなどの架空のPII列を含め、load.py で除外されるかを検証可能にする
- 観点別タグ付きデータ (reviews_tagged.parquet, review_aspects.parquet)
- 店舗マスタ (stores.csv)
- 店舗一覧スナップショット (akakara_places_20261031.csv)
"""
from __future__ import annotations

import os
import pandas as pd
import numpy as np

ASPECTS = ["taste", "service", "speed", "price", "atmosphere", "cleanliness", "other"]

def generate_fixtures(base_dir: str) -> None:
    master_dir = os.path.join(base_dir, "master")
    processed_dir = os.path.join(base_dir, "processed")
    os.makedirs(master_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)

    # 1. 店舗マスタ stores.csv
    stores_data = [
        {"store_key": "store_1", "store_id": "mock_store_1", "store_name": "架空赤から 渋谷店", "brand": "赤から", "genre": "鍋・居酒屋", "area": "東京都渋谷区", "url": "https://maps.test/1", "place_id": "ChIJ_mock_1"},
        {"store_key": "store_2", "store_id": "mock_store_2", "store_name": "架空赤から 新宿店", "brand": "赤から", "genre": "鍋・居酒屋", "area": "東京都新宿区", "url": "https://maps.test/2", "place_id": "ChIJ_mock_2"},
        {"store_key": "store_3", "store_id": "mock_store_3", "store_name": "架空赤から 池袋店", "brand": "赤から", "genre": "鍋・居酒屋", "area": "東京都豊島区", "url": "https://maps.test/3", "place_id": ""}, # place_id空で店名一致テスト
    ]
    pd.DataFrame(stores_data).to_csv(os.path.join(master_dir, "stores.csv"), index=False, encoding="utf-8")

    # 2. 店舗一覧 akakara_places_20261031.csv
    places_data = [
        {"store_name": "架空赤から 渋谷店", "rating": 4.2, "reviews_count": 120, "prefecture": "東京都", "city": "渋谷区", "url": "https://maps.test/1", "placeId": "ChIJ_mock_1"},
        {"store_name": "架空赤から 新宿店", "rating": 3.4, "reviews_count": 80, "prefecture": "東京都", "city": "新宿区", "url": "https://maps.test/2", "placeId": "ChIJ_mock_2"},
        {"store_name": "架空赤から 池袋店", "rating": 3.8, "reviews_count": 50, "prefecture": "東京都", "city": "豊島区", "url": "https://maps.test/3", "placeId": "ChIJ_other_3"}, # 店名で一致
        {"store_name": "架空赤から 横浜西口店", "rating": 4.0, "reviews_count": 210, "prefecture": "神奈川県", "city": "横浜市", "url": "https://maps.test/4", "placeId": "ChIJ_mock_4"}, # マスタにない店舗
        {"store_name": "架空赤から 名古屋駅前店", "rating": 4.5, "reviews_count": 350, "prefecture": "愛知県", "city": "名古屋市", "url": "https://maps.test/5", "placeId": "ChIJ_mock_5"}, # マスタにない店舗
    ]
    pd.DataFrame(places_data).to_csv(os.path.join(master_dir, "akakara_places_20261031.csv"), index=False, encoding="utf-8-sig")

    # 3. 口コミデータ (25件)
    # mock_store_1: 15件, mock_store_2: 10件
    reviews_rows = []
    aspects_rows = []

    # 定義済みレビューサンプル (全創作)
    samples = [
        # store_1
        (1, "mock_store_1", 5, "赤から鍋の辛さ5番が絶品でした！店員さんも親切でした。", True, False, "2024-01-15 19:30:00", True, "2024-01-16 10:00:00", "ja", [("taste", 2, "鍋の辛さ", "絶品でした", True), ("service", 1, "接客", "親切でした", True)]),
        (2, "mock_store_1", 4, "スープの味がとても美味しくて箸が進みます。提供も早かった。", True, False, "2024-02-10 18:00:00", False, None, "ja", [("taste", 2, "スープ", "美味しくて", True), ("speed", 1, "提供時間", "早かった", True)]),
        (3, "mock_store_1", 1, "呼び出しボタンを何度押しても店員が来ず、料理も30分以上待たされた。最悪。", True, False, "2024-03-05 20:15:00", True, "2024-03-06 09:00:00", "ja", [("service", -2, "呼び出しボタン", "店員が来ず", True), ("speed", -2, "待ち時間", "30分以上待たされた", True)]),
        (4, "mock_store_1", 2, "値段の割に肉の量が少なくてがっかり。コスパが悪いです。", True, False, "2024-04-12 21:00:00", False, None, "ja", [("price", -1, "コスパ", "コスパが悪いです", True), ("taste", -1, "肉の量", "量が少なくて", True)]),
        (5, "mock_store_1", 5, "The hot pot was spicy and wonderful! Friendly staff.", True, False, "2024-05-20 19:00:00", False, None, "en", [("taste", 2, "hot pot", "spicy and wonderful", True), ("service", 2, "staff", "Friendly staff", True)]),
        (6, "mock_store_1", 3, "普通の居酒屋です。清潔感は普通でした。", True, True, "2023-06-01 12:00:00", False, None, "ja", [("cleanliness", 0, "店内", "清潔感は普通でした", True)]),
        (7, "mock_store_1", 1, "テーブルが汚れていてベタベタしていた。店員の愛想も悪い。", True, False, "2024-07-08 18:45:00", False, None, "ja", [("cleanliness", -2, "テーブル", "ベタベタしていた", True), ("service", -2, "店員の愛想", "愛想も悪い", True)]),
        (8, "mock_store_1", 4, "辛い鍋を食べたくなったらここ。締めラーメンも最高。", True, True, "2022-08-11 19:00:00", False, None, "ja", [("taste", 2, "締めラーメン", "最高", True)]),
        (9, "mock_store_1", 4, None, False, True, "2021-09-01 00:00:00", False, None, None, []), # 本文なし
        (10, "mock_store_1", 5, None, False, True, "2021-09-10 00:00:00", False, None, None, []), # 本文なし
        (11, "mock_store_1", 2, "接客態度が威圧的で気分が悪くなった。もう行きません。", True, False, "2024-09-15 20:00:00", True, "2024-09-20 14:00:00", "ja", [("service", -2, "接客態度", "威圧的で気分が悪くなった", True)]),
        (12, "mock_store_1", 5, "個室の雰囲気が落ち着いていて女子会にぴったりでした。", True, False, "2024-10-01 18:30:00", False, None, "ja", [("atmosphere", 2, "個室", "落ち着いていて", True)]),
        (13, "mock_store_1", 3, "味は普通ですが飲み放題の提供は早かったです。", True, False, "2024-10-10 21:30:00", False, None, "ja", [("taste", 0, "味", "味は普通", True), ("speed", 1, "飲み放題の提供", "早かったです", True)]),
        (14, "mock_store_1", 3, None, False, True, "2020-01-01 00:00:00", False, None, None, []), # 本文なし
        (15, "mock_store_1", 4, "せせり焼きが香ばしくて美味しいです。", True, False, "2024-10-25 19:15:00", False, None, "ja", [("taste", 1, "せせり焼き", "香ばしくて美味しい", True)]),

        # store_2
        (16, "mock_store_2", 1, "注文した鍋が40分来ない。店員に催促しても謝罪なし。", True, False, "2024-02-14 20:00:00", False, None, "ja", [("speed", -2, "提供時間", "40分来ない", True), ("service", -2, "謝罪", "謝罪なし", True)]),
        (17, "mock_store_2", 2, "エアコンの風が直撃して寒かった。鍋の味は良かったのに残念。", True, False, "2024-03-22 19:30:00", False, None, "ja", [("atmosphere", -1, "エアコン", "風が直撃して寒かった", True), ("taste", 1, "鍋の味", "味は良かった", True)]),
        (18, "mock_store_2", 5, "大満足！スープが濃厚でつくねも絶品でした。また来ます。", True, False, "2024-04-18 18:00:00", True, "2024-04-19 11:00:00", "ja", [("taste", 2, "スープ", "濃厚で", True), ("taste", 2, "つくね", "絶品でした", True)]),
        (19, "mock_store_2", 4, "Nice dining experience, friendly staff.", True, False, "2024-05-02 20:00:00", False, None, "en", [("atmosphere", 1, "experience", "Nice dining experience", True), ("service", 1, "staff", "friendly staff", True)]),
        (20, "mock_store_2", 1, "床が油で滑りそうだった。衛生管理をちゃんとしてほしい。", True, False, "2024-06-19 19:45:00", False, None, "ja", [("cleanliness", -2, "床", "滑りそうだった", True)]),
        (21, "mock_store_2", 2, "呼び出しボタンを押しても全然店員さんが来ない。", True, False, "2024-07-29 21:00:00", False, None, "ja", [("service", -2, "呼び出しボタン", "全然店員さんが来ない", True)]),
        (22, "mock_store_2", 4, "コスパ良くてボリューム満点です。", True, False, "2024-08-15 18:30:00", False, None, "ja", [("price", 1, "コスパ", "コスパ良くて", True)]),
        (23, "mock_store_2", 3, None, False, True, "2023-01-01 00:00:00", False, None, None, []), # 本文なし
        (24, "mock_store_2", 2, None, False, True, "2023-02-01 00:00:00", False, None, None, []), # 本文なし
        (25, "mock_store_2", 3, "普通の赤からです。可もなく不可もなく。", True, False, "2024-09-05 19:00:00", False, None, "ja", [("taste", 0, "赤から", "可もなく不可もなく", True)]),
    ]

    for idx, sid, rating, text, has_txt, time_est, post_t, has_reply, reply_t, lang, aspects in samples:
        uid = f"mock_uid_{idx:03d}"
        reviews_rows.append({
            "review_uid": uid,
            "review_id": f"rev_{idx:03d}",
            "store_id": sid,
            "rating": rating,
            "review_text": text if has_txt else None,
            "has_text": has_txt,
            "text_len": len(text) if text else 0,
            # 架空の PII 列 (load.py の PII 除外テスト用)
            "reviewer_name": f"FakeUser_{idx}",
            "reviewer_id": f"fake_author_{idx}",
            "reviewer_attributes": "ローカルガイド",
            "is_local_guide": (idx % 3 == 0),
            "reviewer_review_count": idx * 4,
            "post_time": pd.to_datetime(post_t),
            "time_is_estimated": time_est,
            "post_year": pd.to_datetime(post_t).year,
            "has_owner_reply": has_reply,
            "owner_reply_time": pd.to_datetime(reply_t) if reply_t else None,
            "language": lang,
            "overall_sentiment": 1 if rating >= 4 else (-1 if rating <= 2 else 0) if has_txt else None,
            "llm_tagged": has_txt,
        })

        if has_txt:
            # 観点詳細
            for asp, sent, subtop, evid, verb in aspects:
                aspects_rows.append({
                    "review_uid": uid,
                    "store_id": sid,
                    "aspect": asp,
                    "aspect_label": {"taste": "味", "service": "接客", "speed": "提供時間・待ち", "price": "価格", "atmosphere": "雰囲気", "cleanliness": "清潔さ", "other": "その他"}.get(asp, asp),
                    "sentiment": sent,
                    "subtopic": subtop,
                    "evidence": evid,
                    "evidence_verbatim": verb,
                })

    df_reviews = pd.DataFrame(reviews_rows)
    df_aspects = pd.DataFrame(aspects_rows)

    # reviews.parquet (未タグ付け相当: PII 列を含む生の正規化 parquet)
    df_reviews.to_parquet(os.path.join(processed_dir, "reviews.parquet"), index=False)
    df_reviews.to_csv(os.path.join(processed_dir, "reviews.csv"), index=False, encoding="utf-8-sig")

    # reviews_tagged.parquet (タグ付け結果を追加した横持ち)
    df_tagged = df_reviews.copy()
    for asp in ASPECTS:
        s_asp = df_aspects[df_aspects["aspect"] == asp].drop_duplicates(subset=["review_uid"]).set_index("review_uid")
        tagged = df_tagged["llm_tagged"]
        df_tagged[f"{asp}_mentioned"] = df_tagged["review_uid"].isin(s_asp.index).where(tagged, False)
        df_tagged[f"{asp}_sent"] = df_tagged["review_uid"].map(s_asp["sentiment"])
        df_tagged[f"{asp}_pos"] = (df_tagged[f"{asp}_sent"] > 0).astype(float).where(tagged, np.nan)
        df_tagged[f"{asp}_neg"] = (df_tagged[f"{asp}_sent"] < 0).astype(float).where(tagged, np.nan)

    df_tagged.to_parquet(os.path.join(processed_dir, "reviews_tagged.parquet"), index=False)
    df_aspects.to_parquet(os.path.join(processed_dir, "review_aspects.parquet"), index=False)
    df_aspects.to_csv(os.path.join(processed_dir, "review_aspects.csv"), index=False, encoding="utf-8-sig")

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
    generate_fixtures(target)
    print(f"Generated test fixtures at: {target}")

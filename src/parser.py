"""
Googleマップ内部API `listugcposts` の応答（JSON）を解析するモジュール。

応答はXSSI対策の接頭辞 `)]}'` が付いた、キー名の無い入れ子配列です。
Google側の仕様変更で位置（インデックス）がずれても壊れにくいよう、
「既知の位置で取得 → 取れなければ中身を探索して推定」の2段構えにしています。
"""
import json
import re
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

# 投稿日時（マイクロ秒単位のUNIX時間）とみなす範囲: 2005年〜2100年
_TS_MIN = 1_100_000_000 * 1_000_000
_TS_MAX = 4_100_000_000 * 1_000_000


def _g(obj, *path):
    """入れ子配列から安全に値を取り出す。途中で存在しなければ None。"""
    for key in path:
        try:
            obj = obj[key]
        except (IndexError, KeyError, TypeError):
            return None
    return obj


def _walk(obj):
    """入れ子構造のすべての葉（文字列・数値）を順に返す。"""
    if isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    else:
        yield obj


def load_rpc_json(text: str):
    """`)]}'` 接頭辞を取り除いてJSONとして読み込む。"""
    if text.startswith(")]}'"):
        text = text.split("\n", 1)[1] if "\n" in text else text[4:]
    return json.loads(text)


def _find_timestamp(obj):
    for v in _walk(obj):
        if isinstance(v, int) and not isinstance(v, bool) and _TS_MIN <= v <= _TS_MAX:
            return v
    return None


def _to_datetime(us):
    if not isinstance(us, (int, float)) or not (_TS_MIN <= us <= _TS_MAX):
        return None
    return datetime.fromtimestamp(us / 1_000_000, tz=JST).replace(tzinfo=None)


def _parse_reviewer(block):
    """レビュアー情報（名前・ID・ローカルガイド・投稿件数）を取り出す。"""
    name = _g(block, 4, 5, 0) if isinstance(_g(block, 4, 5, 0), str) else None
    blob = json.dumps(block, ensure_ascii=False)

    reviewer_id = None
    m = re.search(r"/contrib/(\d+)", blob)
    if m:
        reviewer_id = m.group(1)

    # 「ローカルガイド・クチコミ 123 件・写真 45 枚」のような属性文字列
    attr_text = None
    for v in _walk(block):
        if isinstance(v, str) and ("件" in v or "ローカルガイド" in v or "Local Guide" in v or "review" in v):
            if len(v) < 80 and not v.startswith("http"):
                attr_text = v if attr_text is None or len(v) > len(attr_text) else attr_text

    is_local_guide = bool(attr_text and ("ローカルガイド" in attr_text or "Local Guide" in attr_text))
    review_count = None
    if attr_text:
        m = re.search(r"クチコミ\s*([\d,]+)\s*件", attr_text) or re.search(r"([\d,]+)\s*件のクチコミ", attr_text) \
            or re.search(r"([\d,]+)\s*reviews?", attr_text)
        if m:
            review_count = int(m.group(1).replace(",", ""))

    if name is None:
        # 既知の位置に無い場合: URLでも属性文字列でもない短い文字列の先頭を名前とみなす
        for v in _walk(_g(block, 4)):
            if isinstance(v, str) and 0 < len(v) < 60 and not v.startswith("http") and v != attr_text:
                name = v
                break

    return name, reviewer_id, is_local_guide, review_count, attr_text


def _longest_text(obj, exclude=()):
    best = None
    for v in _walk(obj):
        if isinstance(v, str) and not v.startswith("http") and v not in exclude:
            if best is None or len(v) > len(best):
                best = v
    return best


def parse_review(entry):
    """`listugcposts` の1件分を辞書に変換する。"""
    r = _g(entry, 0)
    if not isinstance(r, list):
        return None

    review_id = _g(r, 0) if isinstance(_g(r, 0), str) else None
    meta = _g(r, 1)        # レビュアー・日時
    body = _g(r, 2)        # 評価・本文
    reply = _g(r, 3)       # オーナー返信

    name, reviewer_id, is_local_guide, review_count, attr_text = _parse_reviewer(meta)

    created_us = _g(meta, 2) if isinstance(_g(meta, 2), int) else _find_timestamp(meta)
    updated_us = _g(meta, 3) if isinstance(_g(meta, 3), int) else None
    relative_time = _g(meta, 6) if isinstance(_g(meta, 6), str) else None

    rating = _g(body, 0, 0)
    if not (isinstance(rating, int) and 1 <= rating <= 5):
        rating = None

    text = _g(body, 15, 0, 0)
    if not isinstance(text, str):
        text = _g(body, 1) if isinstance(_g(body, 1), str) else None

    owner_reply = _g(reply, 14, 0, 0)
    if not isinstance(owner_reply, str):
        owner_reply = None
    owner_reply_us = _find_timestamp(reply) if reply else None

    return {
        "review_id": review_id,
        "reviewer_name": name,
        "reviewer_id": reviewer_id,
        "is_local_guide": is_local_guide,
        "reviewer_review_count": review_count,
        "reviewer_attributes": attr_text,
        "rating": rating,
        "review_text": text,
        "post_time": _to_datetime(created_us),
        "updated_time": _to_datetime(updated_us),
        "relative_time": relative_time,
        "owner_reply": owner_reply,
        "owner_reply_time": _to_datetime(owner_reply_us),
    }


def parse_listugcposts(text: str):
    """
    応答本文を解析し、(レビュー辞書のリスト, 次ページトークン) を返す。
    次ページが無ければトークンは None。
    """
    data = load_rpc_json(text)
    next_token = _g(data, 1) if isinstance(_g(data, 1), str) and _g(data, 1) else None
    entries = _g(data, 2) or []

    reviews = []
    for entry in entries:
        try:
            rv = parse_review(entry)
        except Exception:
            rv = None
        if rv and rv.get("review_id"):
            reviews.append(rv)
    return reviews, next_token

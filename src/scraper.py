"""
Googleマップのクチコミ収集ロジック（ログイン済みプロファイル + 通信傍受方式）

方針:
  A. ログイン済みの専用Chromeプロファイルを使い「表示制限モード」を回避する
  B. 画面(DOM)ではなく、裏側の通信 `listugcposts` のJSONを傍受して解析する
  C. 次ページトークンを使って、スクロールせずに次のページを直接リクエストする
  D. 並び順を変えて複数回取得し、review_id で重複を除いて統合する
  E. (--manual) 人がスクロールし、スクリプトは通信の記録だけを行う
"""
import logging
import os
import re
import time
from datetime import datetime
from urllib.parse import quote

import pandas as pd
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from .config import (
    BASE_DIR, BROWSER_CHANNEL, DEBUG_DUMP_RAW, MAX_STALL_LOOPS, PROFILE_DIR,
    REQUEST_INTERVAL_SEC, SCROLL_PAUSE_TIME, SORT_ORDERS, TIMEOUT_MS,
)
from .parser import parse_listugcposts

RPC_KEYWORD = "listugcposts"
LIMITED_VIEW_TEXT = "表示が制限されています"

SORT_LABELS = {
    "relevant": ["関連度順", "関連性", "Most relevant"],
    "newest": ["新しい順", "Newest"],
    "highest": ["評価の高い順", "高い順", "Highest rating"],
    "lowest": ["評価の低い順", "低い順", "Lowest rating"],
}

OUTPUT_COLUMNS = [
    "store_name", "review_id", "reviewer_name", "reviewer_id", "is_local_guide",
    "reviewer_review_count", "reviewer_attributes", "rating", "review_text",
    "post_time", "updated_time", "relative_time", "owner_reply", "owner_reply_time",
]


class LimitedViewError(Exception):
    """未ログイン等でGoogleマップが表示制限モードになっている"""


# ---------------------------------------------------------------
# ブラウザ起動・ログイン
# ---------------------------------------------------------------
def launch_context(playwright, logger: logging.Logger):
    """ログイン状態を保存する専用プロファイルでブラウザを起動する。"""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    kwargs = dict(
        user_data_dir=PROFILE_DIR,
        headless=False,  # ヘッドレスだと簡易版(Lite)になりやすいため画面を表示する
        locale="ja-JP",
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    try:
        return playwright.chromium.launch_persistent_context(channel=BROWSER_CHANNEL, **kwargs)
    except Exception as e:
        if BROWSER_CHANNEL is None:
            raise
        logger.warning(f"Chrome({BROWSER_CHANNEL})の起動に失敗したため、同梱のChromiumで再試行します: {e}")
        return playwright.chromium.launch_persistent_context(**kwargs)


def _is_logged_in(context) -> bool:
    names = {c["name"] for c in context.cookies("https://www.google.com")}
    return "SID" in names or "__Secure-1PSID" in names


def login_flow(context, logger: logging.Logger, wait_minutes: int = 10) -> bool:
    """初回のみ: ブラウザ上で手動ログインしてもらい、完了を待つ。"""
    page = context.pages[0] if context.pages else context.new_page()
    if _is_logged_in(context):
        logger.info("すでにログイン済みです。")
    else:
        page.goto("https://accounts.google.com/ServiceLogin?hl=ja&continue=https://www.google.com/maps")
        logger.info("=" * 60)
        logger.info("開いたブラウザで、分析用のGoogleアカウントにログインしてください。")
        logger.info(f"ログインが完了すると自動的に次へ進みます（最大{wait_minutes}分待機）。")
        logger.info("=" * 60)
        deadline = time.time() + wait_minutes * 60
        while time.time() < deadline and not _is_logged_in(context):
            page.wait_for_timeout(2000)
        if not _is_logged_in(context):
            logger.error("時間内にログインが確認できませんでした。もう一度 --login で実行してください。")
            return False
        logger.info("ログインを確認しました。プロファイルに保存されたため、次回からは自動でログイン状態になります。")

    page.goto("https://www.google.com/maps?hl=ja")
    page.wait_for_timeout(4000)
    if LIMITED_VIEW_TEXT in page.locator("body").inner_text():
        logger.warning("ログイン後もGoogleマップが表示制限モードのままです。アカウントの状態を確認してください。")
        return False
    logger.info("Googleマップが通常モードで表示されることを確認しました。")
    return True


# ---------------------------------------------------------------
# 通信傍受
# ---------------------------------------------------------------
class ReviewCollector:
    """listugcposts の応答を受け取り、review_id で重複を除いて蓄積する。"""

    def __init__(self, logger: logging.Logger, debug_prefix: str):
        self.logger = logger
        self.reviews = {}
        self.responses = 0
        self.last_token = "init"  # None = 最終ページに到達
        self.last_url = None
        self.debug_prefix = debug_prefix
        self.debug_dir = os.path.join(BASE_DIR, "data", "debug")
        if DEBUG_DUMP_RAW:
            os.makedirs(self.debug_dir, exist_ok=True)

    def add_body(self, url: str, body: str) -> int:
        """応答本文を解析して蓄積し、新規に増えた件数を返す。"""
        self.responses += 1
        if DEBUG_DUMP_RAW:
            path = os.path.join(self.debug_dir, f"{self.debug_prefix}_{self.responses:03d}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(url + "\n\n" + body)
        try:
            items, token = parse_listugcposts(body)
        except Exception as e:
            self.logger.warning(f"通信データの解析に失敗しました（形式変更の可能性）: {e}")
            return 0
        before = len(self.reviews)
        for rv in items:
            self.reviews.setdefault(rv["review_id"], rv)
        self.last_token = token
        self.last_url = url
        return len(self.reviews) - before

    def on_response(self, response):
        if RPC_KEYWORD not in response.url:
            return
        try:
            if response.status != 200:
                self.logger.warning(f"クチコミ通信がステータス {response.status} を返しました。")
                return
            self.add_body(response.url, response.text())
        except Exception as e:
            self.logger.debug(f"応答の読み取りに失敗: {e}")


def build_page_url(url: str, token: str):
    """傍受したURLの pb パラメータ内の『次ページトークン』を差し替えたURLを作る。"""
    tok = quote(token, safe="")
    if re.search(r"!2m2!1i\d+!2s[^!&]*", url):
        return re.sub(r"!2m2!1i(\d+)!2s[^!&]*", lambda m: f"!2m2!1i{m.group(1)}!2s{tok}", url, count=1)
    if re.search(r"!2m1!1i\d+", url):
        return re.sub(r"!2m1!1i(\d+)", lambda m: f"!2m2!1i{m.group(1)}!2s{tok}", url, count=1)
    return None


# ---------------------------------------------------------------
# 画面操作
# ---------------------------------------------------------------
def _read_total_count(page):
    """店舗の総クチコミ数を画面から推定する（取得できなければ None）。"""
    try:
        txt = page.evaluate("""() => {
            const els = [...document.querySelectorAll('[aria-label]')];
            for (const el of els) {
                const m = el.getAttribute('aria-label').match(/([\\d,]+)\\s*件のクチコミ/);
                if (m) return m[1];
            }
            return null;
        }""")
        return int(txt.replace(",", "")) if txt else None
    except Exception:
        return None


def _open_reviews_tab(page, logger) -> bool:
    tab = page.locator('[role="tab"]:has-text("クチコミ"), [role="tab"]:has-text("レビュー")').first
    if tab.count() == 0:
        logger.warning("「クチコミ」タブが見つかりませんでした。")
        return False
    tab.click(force=True)
    page.wait_for_timeout(3000)
    return True


def _select_sort(page, sort_key: str, logger) -> bool:
    """並べ替えメニューを開いて指定の並び順を選ぶ。"""
    btn = page.locator('button[aria-label*="並べ替え"], button:has-text("並べ替え"), button[aria-label*="Sort"]').first
    if btn.count() == 0:
        logger.warning("「並べ替え」ボタンが見つかりませんでした。")
        return False
    btn.click(force=True)
    page.wait_for_timeout(1200)
    for label in SORT_LABELS.get(sort_key, []):
        item = page.locator(f'[role="menuitemradio"]:has-text("{label}"), [role="menuitem"]:has-text("{label}")').first
        if item.count() > 0:
            item.click(force=True)
            return True
    page.keyboard.press("Escape")
    logger.warning(f"並び順「{sort_key}」のメニュー項目が見つかりませんでした。")
    return False


def _scroll_reviews(page) -> str:
    """クチコミ一覧のスクロール領域を探し、一番下までスクロールする。"""
    return page.evaluate("""() => {
        const item = document.querySelector('.jftiEf');
        if (!item) return 'no-item';
        let el = item.parentElement;
        while (el && !(el.scrollHeight > el.clientHeight + 10 &&
                       /auto|scroll/.test(getComputedStyle(el).overflowY))) el = el.parentElement;
        if (!el) { item.scrollIntoView(); return 'no-scroller'; }
        el.scrollTop = el.scrollHeight;
        return 'ok';
    }""")


# ---------------------------------------------------------------
# 取得方式
# ---------------------------------------------------------------
def _paginate_direct(page, collector: ReviewCollector, logger) -> bool:
    """C: 次ページトークンを使って直接リクエストする。成功したら True。"""
    pages = 0
    while collector.last_token:
        url = build_page_url(collector.last_url, collector.last_token)
        if not url:
            logger.info("URLの形式を特定できなかったため、直接取得はスキップします。")
            return False
        time.sleep(REQUEST_INTERVAL_SEC)
        prev_token = collector.last_token
        # ブラウザ内の fetch で呼ぶので、ログインCookie等はそのまま使われる。
        # 応答は on_response リスナーでも受信・蓄積される。
        status = page.evaluate(
            "async (u) => { const r = await fetch(u, {credentials: 'include'}); await r.text(); return r.status; }",
            url,
        )
        page.wait_for_timeout(300)  # リスナー側の処理待ち
        if status != 200 or collector.last_token == prev_token:
            logger.warning(f"直接取得が失敗しました（ステータス: {status}）。スクロール方式に切り替えます。")
            return False
        pages += 1
        if pages % 5 == 0:
            logger.info(f"  直接取得中... {pages}ページ / 累計 {len(collector.reviews)} 件")
    return True


def _paginate_scroll(page, collector: ReviewCollector, logger):
    """フォールバック: スクロールで読み込みを発生させ、通信を傍受する。"""
    stall = 0
    prev = len(collector.reviews)
    while collector.last_token is not None and stall < MAX_STALL_LOOPS:
        _scroll_reviews(page)
        page.wait_for_timeout(int(SCROLL_PAUSE_TIME * 1000))
        now = len(collector.reviews)
        if now == prev:
            stall += 1
            # 上に少し戻してから再度下げると読み込みが再開することがある
            page.mouse.wheel(0, -600)
            page.wait_for_timeout(500)
        else:
            stall = 0
            logger.info(f"  スクロール取得中... 累計 {now} 件")
        prev = now


def _extract_from_dom(page, logger):
    """最終手段: 通信が一切傍受できなかった場合に、画面から取れる分だけ取得する。"""
    rows = []
    items = page.locator(".jftiEf")
    for i in range(items.count()):
        it = items.nth(i)
        try:
            def txt(sel):
                loc = it.locator(sel)
                return loc.first.inner_text(timeout=1000) if loc.count() > 0 else None
            rating_label = it.locator(".kvMYJc").first.get_attribute("aria-label", timeout=1000) \
                if it.locator(".kvMYJc").count() > 0 else None
            m = re.search(r"(\d+(?:\.\d+)?)", rating_label or "")
            rows.append({
                "review_id": it.get_attribute("data-review-id") or f"dom_{i}",
                "reviewer_name": txt(".d4r55"),
                "rating": float(m.group(1)) if m else None,
                "review_text": txt(".wiI7pd"),
                "relative_time": txt(".rsqaWe"),
                "reviewer_attributes": txt(".RfnDt"),
            })
        except Exception as e:
            logger.warning(f"  -> 画面からの{i+1}件目の抽出に失敗: {e}")
    return rows


# ---------------------------------------------------------------
# メイン処理（1店舗分）
# ---------------------------------------------------------------
def scrape_google_maps_reviews(url: str, logger: logging.Logger, context,
                               store_index: int = 1, manual: bool = False) -> pd.DataFrame:
    page = context.new_page()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    collector = ReviewCollector(logger, debug_prefix=f"store{store_index}_{stamp}")
    page.on("response", collector.on_response)
    store_name = None

    try:
        logger.info(f"URLへのアクセスを開始: {url}")
        page.goto(url, timeout=TIMEOUT_MS)
        page.wait_for_timeout(5000)

        if LIMITED_VIEW_TEXT in page.locator("body").inner_text():
            raise LimitedViewError(
                "Googleマップが『表示が制限されています』モードです（未ログイン扱い）。"
                "最初に `python -m src.main --login` を実行してログインしてください。"
            )

        try:
            store_name = page.locator("h1").first.inner_text(timeout=5000).strip()
        except Exception:
            pass
        total = _read_total_count(page)
        logger.info(f"店舗名: {store_name} / 画面上の総クチコミ数: {total if total else '不明'}")

        if not _open_reviews_tab(page, logger):
            raise RuntimeError("クチコミタブを開けませんでした。")

        if manual:
            logger.info("=" * 60)
            logger.info("【半自動モード】ブラウザ上でクチコミ一覧を一番下まで手動でスクロールしてください。")
            logger.info("並び順を変えて何度スクロールしてもOKです（重複は自動で除去されます）。")
            logger.info("終わったら、このターミナルで Enter キーを押してください。")
            logger.info("=" * 60)
            input()
            logger.info(f"記録した通信: {collector.responses} 回 / 取得件数: {len(collector.reviews)} 件")
        else:
            for sort_key in SORT_ORDERS:
                logger.info(f"▶ 並び順「{sort_key}」で取得します。")
                try:
                    with page.expect_response(lambda r: RPC_KEYWORD in r.url, timeout=15000):
                        if not _select_sort(page, sort_key, logger):
                            raise RuntimeError("sort-failed")
                except (PlaywrightTimeoutError, RuntimeError):
                    if collector.last_url is None:
                        logger.info("  並び替え時の通信を捉えられなかったため、スクロールで通信を発生させます。")
                        collector.last_token = "init"
                        _paginate_scroll(page, collector, logger)
                    continue
                page.wait_for_timeout(500)

                if not _paginate_direct(page, collector, logger):
                    _paginate_scroll(page, collector, logger)

                logger.info(f"  並び順「{sort_key}」終了時点の累計: {len(collector.reviews)} 件")
                if total and len(collector.reviews) >= total:
                    logger.info("  総クチコミ数に到達したため、残りの並び順はスキップします。")
                    break

        rows = list(collector.reviews.values())
        if not rows:
            logger.warning("通信からクチコミを取得できませんでした。画面からの抽出を試みます。")
            rows = _extract_from_dom(page, logger)

        if total and rows:
            rate = len(rows) / total * 100
            logger.info(f"取得率: {len(rows)} / {total} 件 ({rate:.1f}%)")
            if rate < 95:
                logger.warning("総数より少ない状態です。`--manual` での半自動取得もお試しください。")

    except LimitedViewError as e:
        logger.error(str(e))
        rows = []
    except PlaywrightTimeoutError:
        logger.error("ページの読み込み、または要素の待機でタイムアウトしました。通信環境を確認してください。")
        rows = list(collector.reviews.values())
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        rows = list(collector.reviews.values())
    finally:
        page.close()

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df.insert(0, "store_name", store_name)
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = None
    for col in ("post_time", "updated_time", "owner_reply_time"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df = df[OUTPUT_COLUMNS].sort_values("post_time", ascending=False, na_position="last")
    logger.info(f"抽出完了件数: {len(df)} 件")
    return df.reset_index(drop=True)

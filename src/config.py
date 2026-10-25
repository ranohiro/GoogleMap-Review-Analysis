import os

# 対象店舗のGoogleマップURLまたは名前のリスト
TARGET_URLS = [
    # 複数店舗を処理する場合はここに追加します。
    # 例としてダミーのURLを入れています。実際のURLに置き換えてください。
    "https://maps.app.goo.gl/x7w1BV9Pi93DAwXw8?g_st=ic",
    "https://maps.app.goo.gl/Xw9nXrYahufaaavQ9?g_st=ic"
]

# スクレイピング時の要素待機タイムアウト設定（ミリ秒）
TIMEOUT_MS = 60000

# スクロール時の待機時間（秒）
# 通信環境やマシンスペックに合わせて調整してください
SCROLL_PAUSE_TIME = 2

# ---------------------------------------------------------------
# 以下は「ログイン済みプロファイル + 通信傍受」方式の設定
# ---------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ログイン状態（Cookie等）を保存するブラウザプロファイルの場所
# ※ 中身はGoogleアカウントの認証情報なので、Git等で共有しないでください
PROFILE_DIR = os.path.join(BASE_DIR, "browser_profile")

# 使用するブラウザ。"chrome" = インストール済みのGoogle Chrome（Googleログインがブロックされにくい）
# Chromeが無い環境では None にするとPlaywright同梱のChromiumを使います
BROWSER_CHANNEL = "chrome"

# 取得する並び順（上から順に試し、全件揃った時点で残りはスキップ）
# 指定可能: "newest"(新しい順), "relevant"(関連度順), "highest"(評価の高い順), "lowest"(評価の低い順)
SORT_ORDERS = ["newest", "lowest", "highest", "relevant"]

# 次ページを直接リクエストする際の間隔（秒）。短くしすぎるとブロックされる恐れがあります
REQUEST_INTERVAL_SEC = 1.5

# スクロール方式の時、新規データが来ないまま何回待ったら打ち切るか
MAX_STALL_LOOPS = 8

# 傍受した生の通信データ（JSON）を data/debug/ に保存するか（解析不具合の調査用）
DEBUG_DUMP_RAW = True

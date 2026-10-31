"""外部サービス収集の設定。APIキーは .env → ~/.env の順に読む（tag_aspects と同じ）。"""
import os

from dotenv import load_dotenv

from src.pipeline.paths import BASE_DIR, DATA_DIR

load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv(os.path.expanduser("~/.env"))

VENDOR_RAW_DIR = os.path.join(DATA_DIR, "raw_vendor")
MANIFEST_PATH = os.path.join(VENDOR_RAW_DIR, "manifest.jsonl")

# --- Apify
APIFY_BASE_URL = "https://api.apify.com/v2"
APIFY_PLACES_ACTOR = "compass~crawler-google-places"
APIFY_REVIEWS_ACTOR = "compass~google-maps-reviews-scraper"
POLL_INTERVAL_SEC = 5
RUN_TIMEOUT_SEC = 30 * 60


def apify_token() -> str:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN が見つかりません。プロジェクト直下の .env か ~/.env に設定してください。")
    return token

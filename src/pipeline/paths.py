"""分析パイプライン共通のパス・設定。"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
MASTER_STORES = os.path.join(DATA_DIR, "master", "stores.csv")
ANNOTATION_DIR = os.path.join(DATA_DIR, "annotations")
LLM_CACHE_DIR = os.path.join(PROCESSED_DIR, "llm_cache")
PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

# 観点タクソノミー（キー → 日本語ラベル）。変更したらプロンプトのバージョンも上げること
ASPECTS = {
    "taste": "味",
    "service": "接客",
    "speed": "提供時間・待ち",
    "price": "価格",
    "atmosphere": "雰囲気",
    "cleanliness": "清潔さ",
    "other": "その他",
}

# LLM設定。モデル名は環境変数 GEMINI_MODEL で上書き可（利用可能なモデルは --list-models で確認）
LLM_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
PROMPT_VERSION = "aspect_v1"

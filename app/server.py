"""口コミ分析ツール ローカル BFF サーバー (app/server.py)

FastAPI による BFF サーバー。
- 127.0.0.1 (localhost) でのみ待ち受け、ローカルプライバシーを確保
- REST API (/api/...) と SPA 静的アセット (/...) を配信
- python -m app.server [--port 8000] [--mock] で起動
"""
from __future__ import annotations

import argparse
import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# プロジェクト直下を sys.path に追加
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.api.routes import router as api_router

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def create_app() -> FastAPI:
    """FastAPI アプリケーションインスタンスを生成する。"""
    app = FastAPI(
        title="Googleマップ 口コミ分析ツール",
        description="BFF + SPA による Google マップ 口コミ分析ダッシュボード",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
    )

    # ローカル開発用 CORS 設定
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API ルーター登録
    app.include_router(api_router)

    # 静的ファイルの提供
    if os.path.exists(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        index_file = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"status": "ok", "message": "口コミ分析ツール BFF サーバー稼働中"}

    @app.get("/health")
    def health():
        return {"status": "healthy", "service": "review-analysis-bff"}

    return app


app = create_app()


def main():
    parser = argparse.ArgumentParser(description="口コミ分析ツール BFF ローカルサーバー起動")
    parser.add_argument("--host", default="127.0.0.1", help="待ち受けホスト (既定 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="待ち受けポート (既定 8000)")
    parser.add_argument("--reload", action="store_true", help="ホットリロードを有効化")
    parser.add_argument("--mock", action="store_true", help="架空データ (fixtures) を使用して起動")
    args = parser.parse_args()

    if args.mock:
        fixtures_dir = os.path.join(BASE_DIR, "tests", "analysis", "fixtures")
        os.environ["ANALYSIS_DATA_DIR"] = os.path.join(fixtures_dir, "processed")
        os.environ["ANALYSIS_MASTER_DIR"] = os.path.join(fixtures_dir, "master")
        print("[!] 架空データ (Mock Fixtures) モードで起動します。")

    print(f"🚀 口コミ分析ツール サーバーを起動します: http://{args.host}:{args.port}")
    print(f"   API ドキュメント: http://{args.host}:{args.port}/api/docs")
    uvicorn.run("app.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()

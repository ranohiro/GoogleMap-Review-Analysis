"""Pytest設定・フィクスチャ (conftest.py)"""
from __future__ import annotations

import os
import shutil
import sys
import pytest

# プロジェクト直下を sys.path に追加
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

@pytest.fixture
def mock_env(monkeypatch):
    """環境変数 ANALYSIS_DATA_DIR と ANALYSIS_MASTER_DIR を fixtures ディレクトリに向ける。"""
    data_dir = os.path.join(FIXTURES_DIR, "processed")
    master_dir = os.path.join(FIXTURES_DIR, "master")
    monkeypatch.setenv("ANALYSIS_DATA_DIR", data_dir)
    monkeypatch.setenv("ANALYSIS_MASTER_DIR", master_dir)
    return {"data_dir": data_dir, "master_dir": master_dir}

@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """fixtures を tmp_path にコピーし、完全に独立した環境でテストを実行する。"""
    tmp_data = tmp_path / "processed"
    tmp_master = tmp_path / "master"
    shutil.copytree(os.path.join(FIXTURES_DIR, "processed"), str(tmp_data))
    shutil.copytree(os.path.join(FIXTURES_DIR, "master"), str(tmp_master))

    monkeypatch.setenv("ANALYSIS_DATA_DIR", str(tmp_data))
    monkeypatch.setenv("ANALYSIS_MASTER_DIR", str(tmp_master))
    return {"data_dir": str(tmp_data), "master_dir": str(tmp_master)}

"""Application paths that work both from source and from a PyInstaller build."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


APP_NAME = "Te_ALD_Simulator"
DEFAULT_WORKBOOK_NAME = "XRF_Te.xlsx"


def get_resource_dir() -> Path:
    """번들에 같이 들어간 파일(template.html, sample_data 등)의 위치."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def get_app_dir() -> Path:
    """사용자별 쓰기 가능한 데이터 폴더 (엑셀·생성된 html 저장 위치)."""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home()
    target = root / APP_NAME if base else root / f".{APP_NAME}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def ensure_default_workbook() -> Path:
    """앱 데이터 폴더에 원본 엑셀이 없으면 번들에 포함된 샘플로 채워둔다."""
    target = get_app_dir() / DEFAULT_WORKBOOK_NAME
    if target.exists():
        return target
    candidates = [
        get_resource_dir() / "sample_data" / DEFAULT_WORKBOOK_NAME,
        get_resource_dir() / DEFAULT_WORKBOOK_NAME,
    ]
    for source in candidates:
        if source.exists():
            shutil.copy2(source, target)
            return target
    return target


def template_path() -> Path:
    return get_resource_dir() / "template.html"


def generated_html_path() -> Path:
    return get_app_dir() / "dashboard.html"


__all__ = [
    "APP_NAME",
    "DEFAULT_WORKBOOK_NAME",
    "ensure_default_workbook",
    "generated_html_path",
    "get_app_dir",
    "get_resource_dir",
    "template_path",
]

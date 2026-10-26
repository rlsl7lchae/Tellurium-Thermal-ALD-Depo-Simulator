"""Te ALD Simulator 데스크톱 앱 (pywebview 래퍼).

- 처음 실행: 번들된 sample_data/XRF_Te.xlsx로 대시보드 생성
- "엑셀 불러오기" 버튼: 새 엑셀을 선택하면 그 파일 기준으로 모델을 다시 계산하고
  같은 창을 새 대시보드로 새로고침
- 마지막으로 불러온 엑셀 경로는 다음 실행에도 기억함 (%LOCALAPPDATA%\\Te_ALD_Simulator)
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

import webview

from app_paths import ensure_default_workbook, generated_html_path, get_app_dir, template_path
from build_dashboard_data import build_dashboard_html

LAST_PATH_FILE = "last_workbook.json"

# 창 객체는 모듈 전역으로 둔다.
# (Api 인스턴스의 속성으로 두면 pywebview가 JS API 함수 목록을 만들 때
#  이 객체 내부까지 재귀 탐색하다가 .NET 타입 변환 오류로 죽는다.)
WINDOW = None


def _remember_workbook(path: Path) -> None:
    (get_app_dir() / LAST_PATH_FILE).write_text(
        json.dumps({"path": str(path)}, ensure_ascii=False), encoding="utf-8"
    )


def _recall_workbook():
    f = get_app_dir() / LAST_PATH_FILE
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        path = Path(data.get("path", ""))
        return path if path.exists() else None
    except Exception:
        return None


class Api:
    """JS에서 호출되는 메서드만 담는다. 여기에 다른 속성을 추가하지 말 것."""

    def open_excel(self):
        try:
            result = WINDOW.create_file_dialog(
                webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("Excel 파일 (*.xlsx)", "모든 파일 (*.*)"),
            )
        except Exception as exc:
            return {"ok": False, "error": f"파일 선택 창을 여는 중 오류: {exc}"}

        if not result:
            return {"ok": False, "error": ""}  # 사용자가 취소함 - 조용히 무시

        src = Path(result[0])
        try:
            html = build_dashboard_html(src, template_path())
        except Exception as exc:
            traceback.print_exc()
            return {"ok": False, "error": f"엑셀을 처리하는 중 오류가 발생했습니다: {exc}"}

        out = generated_html_path()
        out.write_text(html, encoding="utf-8")
        _remember_workbook(src)
        WINDOW.load_url(out.as_uri())
        return {"ok": True}


def main() -> int:
    global WINDOW

    src = _recall_workbook() or ensure_default_workbook()
    out = generated_html_path()
    try:
        html = build_dashboard_html(src, template_path())
        out.write_text(html, encoding="utf-8")
        start_url = out.as_uri()
    except Exception:
        traceback.print_exc()
        start_url = template_path().as_uri()  # 최후 수단: 빈 템플릿이라도 띄움

    WINDOW = webview.create_window(
        "Te ALD Process Simulator",
        start_url,
        width=1400,
        height=900,
        min_size=(1100, 720),
        js_api=Api(),
    )
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

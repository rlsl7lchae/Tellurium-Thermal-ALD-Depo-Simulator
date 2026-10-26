# -*- mode: python ; coding: utf-8 -*-
import os

a = Analysis(
    ["desktop_app.py"],
    pathex=[],
    binaries=[],
    datas=[("template.html", ".")] + (
        # 샘플 엑셀은 저장소에 없음(연구실 비공개). 직접 넣었을 때만 exe에 같이 묶는다.
        [("sample_data/XRF_Te.xlsx", "sample_data")] if os.path.exists("sample_data/XRF_Te.xlsx") else []
    ),
    hiddenimports=["webview.platforms.winforms", "webview.platforms.edgechromium"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Te_ALD_Simulator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="app.ico",  # 프로그램 아이콘 (바꾸려면 이 파일만 교체)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Te_ALD_Simulator",
)

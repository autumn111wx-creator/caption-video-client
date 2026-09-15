# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

webview_data = collect_data_files("webview")
webview_hidden = collect_submodules("webview")

a = Analysis(
    ["portable_app.py"],
    pathex=["."],
    binaries=[],
    datas=[("ui/index.html", "ui")] + webview_data,
    hiddenimports=webview_hidden + ["pystray._win32"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="黑底字幕视频工具",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="app.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="黑底字幕视频工具",
)

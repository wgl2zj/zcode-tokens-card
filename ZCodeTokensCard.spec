# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置:单文件、无控制台窗口、exe 自带 Z 图标。

Analysis 之后不接 COLLECT 即为 onefile 形态:binaries/datas 直接进 EXE。
构建命令(用带 PySide6 的 Python312):
  python -m PyInstaller ZCodeTokensCard.spec --noconfirm --distpath dist --workpath build
产物:dist/ZCodeTokensCard.exe(双击运行,数据来源与依赖见 docs/打包分发说明.md)
"""

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc_data"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ZCodeTokensCard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="icon.ico",
)

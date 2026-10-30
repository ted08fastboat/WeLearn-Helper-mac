# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置:WeLearn Helper.app(macOS,Universal 由构建机决定架构)。"""
from PyInstaller.utils.hooks import collect_all

VERSION = "1.0.0"
BUNDLE_ID = "com.github.welearnhelper.mac"

# tls_client 带一个 Go 编译的共享库,必须整包收进去
tls_datas, tls_binaries, tls_hidden = collect_all("tls_client")

a = Analysis(
    ["entry.py"],
    pathex=[],
    binaries=tls_binaries,
    datas=tls_datas + [("wlmac/resources", "wlmac/resources")],
    hiddenimports=tls_hidden + [
        "webview.platforms.cocoa",
        "objc",
        "Foundation",
        "AppKit",
        "Security",
        "WebKit",
        "Quartz",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "matplotlib",
              "numpy", "pandas", "pytest", "setuptools"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WeLearn Helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="build/appicon.icns",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="WeLearn Helper",
)

app = BUNDLE(
    coll,
    name="WeLearn Helper.app",
    icon="build/appicon.icns",
    bundle_identifier=BUNDLE_ID,
    info_plist={
        "CFBundleName": "WeLearn Helper",
        "CFBundleDisplayName": "WeLearn Helper",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "CFBundleGetInfoString": "WeLearn 学习助手(macOS 重写版,GPLv3)",
        "LSMinimumSystemVersion": "11.0",
        "LSApplicationCategoryType": "public.app-category.education",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
        "NSHumanReadableCopyright": "协议逆向自 YZBRH/Welearn_helper(原作者 Avenshy),GPLv3",
    },
)

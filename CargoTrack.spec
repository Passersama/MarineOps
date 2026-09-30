# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all("tzdata")
datas += tmp_ret[0]
datas += [("assets/branding/cargo-track-lockup.png", "assets/branding"), ("assets/branding/cargo-track.ico", "assets/branding")]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

datas += [("assets/branding/chevron.svg", "assets/branding"), ("assets/branding/chevron-disabled.svg", "assets/branding")]
datas += [("assets/fonts/Inter-Regular.ttf", "assets/fonts"), ("assets/fonts/Inter-SemiBold.ttf", "assets/fonts"), ("assets/fonts/Inter-OFL.txt", "assets/fonts")]
datas += [("assets/branding/chevron-dark.svg", "assets/branding"), ("assets/branding/chevron-disabled-dark.svg", "assets/branding")]
datas += [("assets/help/user-guide.html", "assets/help")]
a = Analysis(
    ["src/run_cargo_track.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="CargoTrack",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/branding/cargo-track.ico",
    version="tools/windows-version.txt",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, upx_exclude=[], name="CargoTrack")

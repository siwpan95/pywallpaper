# -*- mode: python ; coding: utf-8 -*-
# pywallpaper 安装包样板 spec（2026-08-25，2026-08-27 目录重构更新路径）
a = Analysis(
    ['G:/repos/pywallpaper/main.pyw'],
    pathex=['G:/repos/pywallpaper'],
    binaries=[],
    datas=[
        ('G:/repos/pywallpaper/recipes', 'recipes'),
        ('G:/repos/pywallpaper/effects', 'effects'),
        ('G:/repos/pywallpaper/data', 'data'),
        ('G:/repos/pywallpaper/templates', 'templates'),
        ('G:/repos/pywallpaper/assets', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pywallpaper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    contents_directory='.',
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='pywallpaper')

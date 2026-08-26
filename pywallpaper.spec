# -*- mode: python ; coding: utf-8 -*-
# pywallpaper 安装包样板 spec（2026-08-25）
a = Analysis(
    ['G:/media/pywallpaper/main.pyw'],
    pathex=['G:/media/pywallpaper'],
    binaries=[],
    datas=[
        ('G:/media/pywallpaper/recipes', 'recipes'),
        ('G:/media/pywallpaper/effects', 'effects'),
        ('G:/media/pywallpaper/data', 'data'),
        ('G:/media/pywallpaper/templates', 'templates'),
        ('G:/media/pywallpaper/assets', 'assets'),
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

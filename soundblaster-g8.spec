# -*- mode: python ; coding: utf-8 -*-
# Build with: pyinstaller soundblaster-g8.spec
# Requires compiled translations first: python tools/compile_translations.py

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('soundblaster_g8/gui/assets', 'soundblaster_g8/gui/assets'),
        ('soundblaster_g8/locale', 'soundblaster_g8/locale'),
    ],
    hiddenimports=['hid', 'hidraw'],
    hooksconfig={},
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='soundblaster-g8',
    console=False,
)

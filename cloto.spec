# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: pyinstaller cloto.spec  →  dist/Cloto(.exe)  ·  en macOS dist/Cloto.app
import sys
from PyInstaller.utils.hooks import collect_all

datas = [('cloto.html', '.'), ('icono', 'icono')]
binaries, hidden = [], []
try:                                   # pywebview (ventana nativa) si está instalado
    d, b, h = collect_all('webview'); datas += d; binaries += b; hidden += h
except Exception:
    pass

a = Analysis(['cloto.py'], datas=datas, binaries=binaries, hiddenimports=hidden, excludes=['numpy', 'PIL'])
pyz = PYZ(a.pure)

if sys.platform == 'darwin':
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Cloto', console=False, icon='icono/cloto.icns')
    coll = COLLECT(exe, a.binaries, a.datas, name='Cloto')
    app = BUNDLE(coll, name='Cloto.app', icon='icono/cloto.icns', bundle_identifier='io.cloto.app',
                 info_plist={'CFBundleName': 'Cloto', 'CFBundleShortVersionString': '1.0.0', 'NSHighResolutionCapable': True})
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='Cloto', console=False,
              icon='icono/cloto.ico' if sys.platform == 'win32' else None, upx=False)

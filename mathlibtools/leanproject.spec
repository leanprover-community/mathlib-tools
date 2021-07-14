# -*- mode: python ; coding: utf-8 -*-
"""
Originally generated with `pyinstaller`.

In future, we may want to use the approach described at
https://github.com/pyinstaller/pyinstaller/wiki/Recipe-Setuptools-Entry-Point, if we end up adding more entrypoints.
"""


block_cipher = None


a = Analysis(['leanproject.py'],
             binaries=[],
             datas=[],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='leanproject',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=True )

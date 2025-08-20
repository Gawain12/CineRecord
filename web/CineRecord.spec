# -*- mode: python ; coding: utf-8 -*-

a = Analysis(['web/app.py'],
             pathex=['.'],
             binaries=[],
             datas=[
                 ('web/templates', 'templates'),
                 ('web/static', 'static'),
                 ('config', 'config'),
                 ('data', 'data')
             ],
             hiddenimports=[],
             hookspath=[],
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=None,
             noarchive=False)
             
pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='CineRecord',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None,
          icon='web/static/icon.icns'
          )

app = BUNDLE(exe,
             name='CineRecord.app',
             icon='web/static/icon.icns',
             bundle_identifier=None)

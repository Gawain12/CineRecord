# -*- mode: python ; coding: utf-8 -*-

# This spec file is used by PyInstaller to package the Flask application.

a = Analysis(['web/app.py'],
             pathex=['.'],  # Add project root to Python path
             binaries=[],
             datas=[
                 ('web/templates', 'templates'),
                 ('web/static', 'static')
             ],
             hiddenimports=[
                 'engineio.async_drivers.gevent'  # Add any hidden imports if needed
             ],
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
          [],
          exclude_binaries=True,
          name='CineSync Hub',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,  # Set to False for a GUI application (no terminal window)
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None,
          # Add an icon for your application
          # icon='web/static/icon.ico'  # For Windows
          # icon='web/static/icon.icns' # For macOS
          )

coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='CineSyncHub')

# For macOS, create an application bundle (.app)
app = BUNDLE(coll,
             name='CineSync Hub.app',
             # icon='web/static/icon.icns',
             bundle_identifier=None)

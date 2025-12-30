# -*- mode: python ; python_format_version: 1.0 -*-

import os
import sys

block_cipher = None

# Add project root to path for imports
project_root = os.path.abspath('.')
sys.path.insert(0, project_root)

from PyInstaller.utils.hooks import collect_all

# Collect all dns modules for eventlet
datas_dns, binaries_dns, hiddenimports_dns = collect_all('dns')

added_files = [
    ('web/templates', 'web/templates'),
    ('web/static', 'web/static'),
    ('web/webview_login.py', 'web'),
    ('scrapers', 'scrapers'),
    ('config', 'config'),
] + datas_dns

a = Analysis(
    ['web/app.py'],
    pathex=[project_root],
    binaries=binaries_dns,
    datas=added_files,
    hiddenimports=[
        'eventlet.hubs.epolls',
        'eventlet.hubs.kqueue',
        'eventlet.hubs.selects',
        'engineio.async_drivers.eventlet',
        'flask_socketio',
        'webview',
        'webview.platforms.cocoa',
    ] + hiddenimports_dns,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy packages not used in production
        'scipy', 'sklearn', 'matplotlib', 'PIL', 'scrapy',
        'twisted', 'numpy.testing', 'pandas.tests',
        'pytest', 'unittest', 'doctest',
        'tkinter', 'tk', 'tcl',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CineRecord',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # Strip symbols for smaller size
    upx=True,
    console=False,  # Release mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CineRecord',
)

app = BUNDLE(
    coll,
    name='CineRecord.app',
    icon=None,
    bundle_identifier='com.cinerecord.app',
)

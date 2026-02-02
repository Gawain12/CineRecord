# -*- mode: python ; python_format_version: 1.0 -*-

import os
import sys

block_cipher = None

# Add project root to path for imports
project_root = os.path.abspath('.')
sys.path.insert(0, project_root)

from PyInstaller.utils.hooks import collect_all

# Collect all required files
# Collect all required files
added_files = [
    ('web/templates', 'web/templates'),
    ('web/static', 'web/static'),
    ('web/tasks', 'web/tasks'),
    ('adapters', 'adapters'),
]

a = Analysis(
    ['web/app.py'],
    pathex=[project_root],
    # Binaries and hiddenimports...
    binaries=[],
    datas=added_files,
    hiddenimports=[
        'flask_socketio',
        'simple_websocket',
        'engineio.async_drivers.threading',
        'webview',
        'webview.platforms.cocoa',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    excludes=[
        'eventlet', 'engineio.async_drivers.eventlet', 'dns',
        'scipy', 'sklearn', 'matplotlib', 'PIL', 'scrapy',
        'twisted', 'numpy.testing', 'pandas.tests',
        'pytest', 'unittest', 'doctest', 'pdb', 'distutils',
        'tkinter', 'tk', 'tcl', '_tkinter', 'Tkinter',
        'notebook', 'jupyter', 'IPython',
        'docutils', 'pygments', 'curses',
        'PyQt5', 'PySide2', 'PyQt6', 'PySide6', 'wx',
        'multiprocessing.test', 'lib2to3',
        'torch', 'tensorflow', 'tensorboard',
        'boto3', 'botocore',
        'pyarrow', 'numba', 'llvmlite', 'sympy', 'zmq',
        'uvloop', 'gevent',
        'psycopg2', 'psycopg2-binary', 'asyncpg', 'psycopg_binary',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Exclude heavy/unused folders
a.datas += Tree('scrapers', prefix='scrapers', excludes=['letterboxd-csv-imdb-tmdb-mapper', '__pycache__', '*.pyc'])
a.datas += Tree('config', prefix='config', excludes=['config.json', '__pycache__', '*.pyc'])

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

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
a = Analysis(
    ['web/app.py'],
    pathex=[project_root],
    # Binaries and hiddenimports...
    binaries=[],
    datas=[
        ('web/tasks', 'web/tasks'),
        ('adapters', 'adapters'),
    ],
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
        'scipy', 'sklearn', 'matplotlib', 'scrapy',
        'twisted', 'numpy.testing', 'pandas.tests',
        'pytest', 'unittest', 'doctest', 'pdb',
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

# Precisely include web assets and shared data
a.datas += Tree('web/templates', prefix='web/templates', excludes=['*.bak', '.DS_Store'])
a.datas += Tree('web/static', prefix='web/static', excludes=['*.bak', '.DS_Store', 'style.css.bak'])
a.datas += Tree('scrapers', prefix='scrapers', excludes=['letterboxd-csv-imdb-tmdb-mapper', '__pycache__', '*.pyc', '.DS_Store'])
a.datas += Tree('config', prefix='config', excludes=['config.json', '__pycache__', '*.pyc', '.DS_Store'])

# Include only essential shared data
if os.path.exists('data/db_imdb.csv'):
    a.datas += [('data/db_imdb.csv', 'data/db_imdb.csv', 'DATA')]

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

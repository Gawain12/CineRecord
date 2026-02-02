# CineRecord Windows Spec File
# Optimized for Windows build

import os
import sys
import glob

block_cipher = None

# Add project root to path
project_root = os.path.abspath('.')
sys.path.insert(0, project_root)

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

# Collect SSL modules (fix for _ssl DLL load failed error)
datas_ssl, binaries_ssl, hiddenimports_ssl = collect_all('ssl')

# Find OpenSSL DLLs from Python installation
def find_openssl_dlls():
    """Find OpenSSL DLLs in Python installation directories."""
    ssl_binaries = []
    search_roots = set()
    python_base = os.path.dirname(sys.executable)
    search_roots.add(python_base)
    search_roots.add(sys.prefix)
    search_roots.add(sys.base_prefix)
    
    # Common locations for OpenSSL DLLs on Windows
    search_dirs = []
    for root in sorted(search_roots):
        search_dirs.extend([
            root,
            os.path.join(root, 'DLLs'),
            os.path.join(root, 'lib-dynload'),
            os.path.join(root, 'Library', 'bin'),
            os.path.join(root, 'Lib', 'site-packages'),
        ])
    
    # OpenSSL DLL patterns (covers different versions)
    dll_patterns = [
        'libssl*.dll',
        'libcrypto*.dll',
        '_ssl*.pyd',
        'LIBEAY*.dll',  # Older OpenSSL
        'SSLEAY*.dll',  # Older OpenSSL
    ]
    
    seen = set()
    for search_dir in search_dirs:
        if os.path.exists(search_dir):
            for pattern in dll_patterns:
                for dll_path in glob.glob(os.path.join(search_dir, pattern)):
                    if os.path.isfile(dll_path):
                        if dll_path not in seen:
                            ssl_binaries.append((dll_path, '.'))
                            seen.add(dll_path)
                            print(f"Found SSL DLL: {dll_path}")
    
    return ssl_binaries

# Collect OpenSSL DLLs
openssl_binaries = find_openssl_dlls()

# Collect Microsoft runtime DLLs from Python installation
def find_windows_runtime_dlls():
    """Find MSVC runtime DLLs often needed on target machines."""
    runtime_binaries = []
    search_roots = set()
    python_base = os.path.dirname(sys.executable)
    search_roots.add(python_base)
    search_roots.add(sys.prefix)
    search_roots.add(sys.base_prefix)

    search_dirs = []
    for root in sorted(search_roots):
        search_dirs.extend([
            root,
            os.path.join(root, 'DLLs'),
        ])

    dll_patterns = [
        'vcruntime*.dll',
        'msvcp*.dll',
        'concrt*.dll',
        'ucrtbase*.dll',
        'api-ms-win-crt*.dll',
    ]

    seen = set()
    for search_dir in search_dirs:
        if os.path.exists(search_dir):
            for pattern in dll_patterns:
                for dll_path in glob.glob(os.path.join(search_dir, pattern)):
                    if os.path.isfile(dll_path) and dll_path not in seen:
                        runtime_binaries.append((dll_path, '.'))
                        seen.add(dll_path)
                        print(f"Found runtime DLL: {dll_path}")

    return runtime_binaries

runtime_binaries = find_windows_runtime_dlls()

# Data files to include
added_files = [
    ('web/templates', 'web/templates'),
    ('web/static', 'web/static'),
    ('web/tasks', 'web/tasks'),
    ('scrapers', 'scrapers'),
    ('adapters', 'adapters'),
    ('config', 'config'),
    ('data', 'data'),
] + datas_ssl

a = Analysis(
    ['web/app.py'],
    pathex=[project_root],
    binaries=binaries_ssl + openssl_binaries + runtime_binaries,
    datas=added_files,
    hiddenimports=[
        # SSL modules (critical for Windows)
        'ssl',
        '_ssl',
        # Flask-SocketIO threading mode dependencies
        'flask_socketio',
        'simple_websocket',
        'engineio.async_drivers.threading',
        'webview',
        'webview.platforms.winforms',  # Windows WebView backend
        'pkg_resources.py2_warn',
    ] + hiddenimports_ssl,
    hookspath=['hooks'],  # Load custom hooks (including SSL hook)
    hooksconfig={},
    runtime_hooks=['hooks/pyi_rth_ssl_path.py'],
    excludes=[
        'eventlet', 'engineio.async_drivers.eventlet',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CineRecord',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,  # Avoid stripping Windows binaries (can break SSL DLLs)
    # UPX can corrupt OpenSSL DLLs on Windows; leave it off for stability.
    upx=False,
    upx_exclude=[
        'libssl*.dll',
        'libcrypto*.dll',
        '_ssl*.pyd',
    ],
    exclude_binaries=True,  # Build one-folder for more reliable DLL loading
    runtime_tmpdir=None,
    console=True,  # Show console for debug
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='CineRecord',
)

# Hook for SSL on Windows
# Ensures OpenSSL DLLs are properly collected

import os
import sys
import glob
from PyInstaller.utils.hooks import collect_all

# Collect all SSL related files
datas, binaries, hiddenimports = collect_all('ssl')

# Add explicit imports
hiddenimports += ['ssl', '_ssl']

# Find OpenSSL DLLs in Python installation
def get_openssl_dlls():
    """Find OpenSSL DLLs from Python installation."""
    result = []
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
            os.path.join(root, 'lib-dynload'),
            os.path.join(root, 'Library', 'bin'),
        ])

    dll_patterns = ['libssl*.dll', 'libcrypto*.dll', '_ssl*.pyd']

    seen = set()
    for search_dir in search_dirs:
        if os.path.exists(search_dir):
            for pattern in dll_patterns:
                for dll_path in glob.glob(os.path.join(search_dir, pattern)):
                    if os.path.isfile(dll_path) and dll_path not in seen:
                        result.append((dll_path, '.'))
                        seen.add(dll_path)

    return result

binaries += get_openssl_dlls()

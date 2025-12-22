from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('eventlet.hubs')
hiddenimports += collect_submodules('dns')

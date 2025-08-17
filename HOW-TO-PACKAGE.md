# HOW-TO-PACKAGE.md

## 如何将 CineSync Hub 打包成桌面应用

本项目使用 `PyInstaller` 将基于 Flask 的 Web 应用打包成一个独立的、跨平台的可执行文件。用户下载后无需安装 Python 环境即可直接运行。

### 1. 准备工作

确保你已经安装了所有必要的依赖。除了 `requirements.txt` 中的库外，还需要打包工具：

```bash
pip install pyinstaller flask gunicorn
```

### 2. 打包命令

我们使用一个 `.spec` 文件来控制打包过程，这比直接在命令行操作更灵活、更可靠。

**打包命令:**

```bash
pyinstaller web/CineSync.spec
```

运行此命令后，`PyInstaller` 会在根目录创建一个 `dist` 文件夹，里面包含了最终的可执行文件（例如 `CineSync Hub.app` 或 `CineSync Hub.exe`）。

### 3. `CineSync.spec` 文件详解

这个文件是 `PyInstaller` 的配置文件，它告诉打包工具如何处理我们的项目。

```python
# -*- mode: python ; coding: utf-8 -*-

a = Analysis(['web/app.py'],
             pathex=['.'],
             binaries=[],
             datas=[
                 ('web/templates', 'templates'),
                 ('web/static', 'static')
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
          name='CineSync Hub',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=False, # 设置为 False 来创建无终端窗口的应用
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None,
          icon='web/static/icon.icns' # macOS 图标
          )

# macOS 特有的 .app 捆绑包配置
app = BUNDLE(exe,
             name='CineSync Hub.app',
             icon='web/static/icon.icns',
             bundle_identifier=None)
```

**关键配置解释:**

*   `Analysis(['web/app.py'], ...)`: 指定主入口文件是 `web/app.py`。
*   `datas=[...]`: 这是**最关键**的部分。它告诉 `PyInstaller` 将我们的 `templates` 和 `static` 文件夹复制到最终的应用包中，否则 Flask 将找不到 HTML, CSS 和 JS 文件。
*   `console=False`: 这会创建一个“窗口化”应用。在 Windows 上，这意味着运行时不会弹出黑色的命令行窗口。
*   `icon='...'`: 为应用指定一个自定义图标。
*   `BUNDLE(...)`: 这个部分用于在 macOS 上创建一个标准的 `.app` 应用程序包。

### 4. 图标准备

为了让应用看起来更专业，需要一个图标文件。

*   **macOS**: 需要一个 `.icns` 文件。
*   **Windows**: 需要一个 `.ico` 文件。

请将图标文件放置在 `web/static/` 目录下，并确保 `.spec` 文件中的路径正确。

---
现在，您只需按照第二步的命令操作，即可生成一个功能完整的本地桌面应用！

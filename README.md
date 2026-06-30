# CineRecord

CineRecord 是一个本地优先的电影记录管理与跨平台同步工具。后端使用 Rust，浏览器界面由同一个二进制直接提供，不需要 Python、Node.js 或额外数据库服务。

支持的平台：

- 豆瓣：公开主页读取；写入和部分受限数据需要 Cookie
- IMDb：Cookie 登录、评分与想看数据
- Trakt：设备 OAuth、评分与想看同步
- TMDB：API Key / Session
- Letterboxd：CSV 导入

## 快速开始

### 从源码运行

```bash
cargo run -p cinerecord-server
```

打开 [http://127.0.0.1:18000](http://127.0.0.1:18000)。

开发仓库会继续使用：

```text
config/v2/config.toml
data/v2/app.db
logs/v2/server.log
```

安装包会使用系统用户目录：

- macOS：`~/Library/Application Support/CineRecord`
- Windows：`%APPDATA%\CineRecord`
- Linux：`$XDG_DATA_HOME/cinerecord` 或 `~/.local/share/cinerecord`

可以通过 `CINERECORD_HOME` 指定其他目录。

## Docker

```bash
docker compose up -d --build
```

默认访问地址为 `http://127.0.0.1:18000`，数据保存在 `./cinerecord-data`。

## 打包

### macOS

```bash
./scripts/package_rust_macos.sh
```

输出：

- `dist-rust/CineRecord.app`
- `dist-rust/CineRecord-macOS-<arch>.dmg`
- `dist-rust/CineRecord-macOS-<arch>.zip`

### Linux

Linux 推荐直接使用 Docker。`dev`、`main` 和版本 tag 会自动发布对应的
`ghcr.io/gawain12/cinerecord` 镜像标签。

### Windows

```powershell
.\scripts\package_rust_windows.ps1
```

输出 `CineRecord-Windows-x64.exe` 和 ZIP 包。双击 EXE 会在后台启动服务并自动打开浏览器。

GitHub Actions 会在 `dev`、`main` 和版本 tag 上自动测试，并在真实 macOS ARM、
macOS Intel、Windows x64 runner 上打包和执行健康检查；Linux 使用 Docker 构建与容器健康检查。

## 环境变量

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `CINERECORD_HOME` | 系统用户目录 | 配置、数据库和日志目录 |
| `CINERECORD_HOST` | `127.0.0.1` | 监听地址 |
| `CINERECORD_PORT` | `18000` | 监听端口 |
| `CINERECORD_PORTABLE` | `false` | 使用当前目录保存数据 |
| `RUST_LOG` | `info,tower_http=info` | Rust 日志级别 |

## 同步安全

- 预览默认使用本地库快速生成。
- 真正执行同步前会刷新源平台和目标平台，再次确认差异。
- 默认只新增，不会用“未评分”覆盖目标平台已有评分。
- 执行前可以逐条选择或取消候选项。

Cookie、OAuth Token 和 API Key 只保存在本地配置目录。不要提交 `config/`、`data/`、`logs/` 或安装包用户数据目录。

## Legacy Python

仓库中暂时保留旧 Python 实现用于行为对照和少量迁移工具，但正式运行、Docker 和发布包均使用 Rust。新功能不应再依赖 Python 运行时。

## License

MIT

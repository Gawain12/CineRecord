# 🎬 CineRecord v2 (Rust Version)

CineRecord 是一个本地优先的电影记录管理、跨平台同步与想看清单工具。

CineRecord v2 是对原有 Python/Flask 版本的全栈重写。后端改用高性能的 **Rust** 实现，数据库升级为本地 **SQLite**，前端界面直接由同一个独立编译的可执行二进制提供，**不需要 Python、Node.js 运行环境，也无需额外配置复杂的外部数据库服务**。

<div align="center">
  <img src="docs/images/app_demo_dual.webp" width="800" alt="CineRecord 运行流程演示">
  <p><i>运行流程演示：账户状态与全量/定时同步任务流（双语版）</i></p>
</div>

---

## 📸 界面预览

<div align="center">
  <img src="docs/images/dashboard_cn.png" width="800" alt="仪表盘预览">
  <p><i>仪表盘：账户连接状态与各平台观影概览</i></p>

  <br>

  <img src="docs/images/library_cn.png" width="800" alt="影片库预览">
  <p><i>影片数据中心：多平台观影数据聚合、去重及筛选查询</i></p>

  <br>

  <img src="docs/images/sync_cn.png" width="800" alt="同步任务预览">
  <p><i>数据同步：可视化任务差分比对、执行和实时日志控制台</i></p>

  <br>

  <img src="docs/images/wishlist_cn.png" width="800" alt="想看清单预览">
  <p><i>想看清单：聚合各源平台想看数据，支持比对媒体服务器找出未入库影片</i></p>
</div>

---

## ✨ 核心特性

### 🌐 平台支持矩阵

| 平台 | 看过/评分抓取 | 想看列表抓取 | 同步目标支持 | 认证与交互方式 |
| :--- | :---: | :---: | :---: | :--- |
| **🎬 豆瓣** | ✅ | ✅ | ✅ | Cookie 导入 / 前端 WebView 自动登录 |
| **⭐ IMDb** | ✅ | ✅ | ✅ | Cookie 登录验证 |
| **🎯 Trakt** | ✅ | ✅ | ✅ | 官方设备 OAuth 授权 / 评分与想看同步 |
| **🎬 TMDB** | ✅ | ✅ | ✅ | API Key + 用户 Session 验证 |
| **🎨 CinePersona** | ✅ | ✅ | ✅ | API Key / 开放接口双向想看及看过同步 |
| **✉️ Letterboxd** | ✅ (导入) | ✅ (导入) | ⚠️ (导出) | 本地 diary.csv / watchlist.csv 导入导出 |
| **🎬 媒体服务器** | ✅ (查重) | — | — | Plex / Emby / Jellyfin API 集成与库内播放 |

### ⚡ 核心能力

* **🚀 极致轻量与高响应性**：打包后的二进制体积仅约 10MB，运行内存占用极低（常驻约 15MB），界面秒开。
* **📊 统一媒体库**：聚合所有平台的观影记录，根据 IMDB/TMDB ID 自动进行电影去重，并提供导演、类型、国家和时长等丰富媒体信息。
* **📅 智能想看清单 (Wishlist)**：汇聚各平台想看数据，支持按平台、未入库过滤。提供最新的 **「同步想看至 CinePersona」** 等双向想看同步机制。
* **🔍 媒体服务器查重 & 库内播放**：深度集成 Plex、Emby 和 Jellyfin 媒体库。自动比对想看清单与本地媒体库，找出未入库资源，点击文件名可直接跳转到播放客户端。
* **⚙️ 可视化任务调度**：内置定时任务调度器。支持配置每日/每周自动刷新和同步任务，配备 SSE 协议的实时日志控制台。
* **🔒 隐私与本地优先**：所有敏感数据（包括 Cookies、Tokens 和 API 密钥）全部以 AES 128 位密钥加密存储在本地。不含任何上传第三方的统计或遥测代码。

---

## 🚀 快速开始

### 从源码运行

确保您已安装 Rust 工具链（建议 Rust 1.75+）：

```bash
# 1. 克隆代码仓库
git clone https://github.com/Gawain12/CineRecord.git
cd CineRecord

# 2. 运行 Axum 后端服务
cargo run -p cinerecord-server
```

启动后在浏览器中打开：[http://127.0.0.1:18000](http://127.0.0.1:18000)。

### Docker 容器部署

如果您要在 NAS 或服务器上运行，推荐使用 Docker：

```bash
docker compose up -d --build
```
服务将在 `http://127.0.0.1:18000` 运行，持久化配置和数据库文件保存在宿主机的 `./cinerecord-data` 目录。

---

## 📦 打包发布

CineRecord 提供了全自动的平台打包脚本，可生成不依赖任何外部依赖的独立桌面运行程序。

### 🍎 macOS
运行封装脚本，将自动使用 `sips` 和 `iconutil` 生成高分辨率 `.icns` 图标，编译 Release 二进制并打包为 DMG 磁盘映射和 ZIP 文件：
```bash
./scripts/package_rust_macos.sh
```
* **输出路径**：`dist-rust/CineRecord.app` / `CineRecord-macOS-arm64.dmg`。
* 双击运行后应用会在后台常驻，并自动调用默认浏览器打开操作页面。

### 🔌 Windows
在 PowerShell 下运行以下脚本，将自动嵌入应用图标并生成独立 EXE 可执行包：
```powershell
.\scripts\package_rust_windows.ps1
```
* **输出路径**：`dist-rust/CineRecord-Windows-x64.exe` 及对应的 ZIP 发布包。

---

## ⚙️ 运行配置与环境变量

CineRecord v2 的默认配置文件、SQLite 数据库以及运行日志均保存在以下**系统标准路径**：
* **macOS**: `~/Library/Application Support/CineRecord`
* **Windows**: `%APPDATA%\CineRecord`
* **Linux**: `$XDG_DATA_HOME/cinerecord` 或 `~/.local/share/cinerecord`

您可以通过以下环境变量自定义服务行为：

| 环境变量 | 默认值 | 作用描述 |
| :--- | :--- | :--- |
| `CINERECORD_HOME` | 系统默认标准路径 | 重定向本地配置、SQLite 数据库及日志的根目录 |
| `CINERECORD_HOST` | `127.0.0.1` | 服务绑定与监听的 IP 地址 |
| `CINERECORD_PORT` | `18000` | 服务绑定的端口号 |
| `CINERECORD_PORTABLE` | `false` | 若设为 `true`，则会将数据直接存储在程序当前运行目录下，适合便携式 U 盘运行 |
| `RUST_LOG` | `info,tower_http=warn` | 控制 Rust 控制台日志输出级别 |

---

## 🛡️ 同步安全防护机制

为了防止同步覆盖和脏数据破坏您的各平台原有电影库，CineRecord 实现了多重防护：
1. **多重比对差分**：同步预览默认利用本地高速数据库完成比对，在正式写入目标平台前，会**强制静默刷新**双方最新的云端数据，确保版本完全一致。
2. **只增不改保护**：同步模式默认使用 **「仅新增」** 机制，本地未评分的记录绝对不会覆盖目标平台已有的评分。
3. **排除 TV 剧集**：由于 TMDB、Letterboxd 和 CinePersona 对电视剧（TV Shows）的兼容与同步方式存在差异，同步任务将自动过滤普通电视剧集，仅保留电影和少部分 IMDb 单季迷你剧，避免导入杂乱。
4. **精细化控制**：支持在执行同步清单前，在前端预览卡片中人工全选、取消勾选任意条目，做到百分百所见即所得。

---

## ♻️ 从 Legacy Python 迁移

CineRecord 目前在项目根目录的 `web/` 下短暂保留了原 Python 版的代码，仅用作底层抓取逻辑行为对照。

如果您以前使用过 Python 版本的 CineRecord，您不需要重新抓取所有数据：
1. 打开 CineRecord v2 页面，进入任意平台卡片。
2. 点击 **「导入 Legacy CSV」**。
3. 系统将自动寻找您以前存在 `data/` 目录下的 Python 版导出的 CSV 文件（如 `douban_*_wish.csv`、`imdb_*_ratings.csv` 等），一键清洗并迁移导入到 v2 的 SQLite 数据库中。

---

## 📜 License

[MIT License](./LICENSE)

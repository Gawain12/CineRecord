# CineRecord Hub - 项目进度表

> 最后更新: 2025-12-27

## 📊 项目概览

CineRecord Hub 是一个多平台影视数据同步工具，支持豆瓣、IMDB、Trakt、Letterboxd 之间的评分同步与备份。

---

## ✅ 已完成功能

### Phase 1: 核心重构 (100%)

| 功能 | 状态 | 说明 |
|------|------|------|
| UI 仪表盘重构 | ✅ | 现代化深色主题 + 侧边栏布局 |
| 导入/导出模块 | ✅ | 支持 Letterboxd/IMDB CSV 及自定义格式 |
| 账户管理优化 | ✅ | 4 平台卡片式管理 (豆瓣/IMDB/Letterboxd/Trakt) |
| 侧边栏简化 | ✅ | 状态概览 + 实时日志 |

### Phase 2: 平台支持 (95%)

| 平台 | 状态 | 功能说明 |
|------|------|------|
| 🎬 豆瓣 | ✅ | 自动登录(webview) / Cookie配置 / 数据获取 / 评分同步 |
| ⭐ IMDB | ✅ | 自动登录(webview) / Cookie配置 / 数据获取 / 评分同步 |
| 🎯 Trakt | ✅ | OAuth 设备授权 / 数据获取 / 双向同步 |
| 🎞️ Letterboxd | ✅ | CSV 导入/导出 / 同步到 Letterboxd 功能 |

### Phase 3: UI/UX 优化 (100%)

| 功能 | 状态 | 说明 |
|------|------|------|
| 账户卡片优化 | ✅ | 自动登录 + 配置Cookie 双按钮 |
| 设置页简化 | ✅ | 移除冗余自动登录按钮，只保留测试连接 |
| 同步预览分页 | ✅ | 每页10条，解决大数据量问题 |
| 会话持久化 | ✅ | 刷新后保留用户ID，不误导显示已连接 |
| 日志窗口优化 | ✅ | 固定高度滚动，字体增大 |

### Phase 4: 打包发布 (100%)

| 功能 | 状态 | 说明 |
|------|------|------|
| Windows EXE 构建 | ✅ | GitHub Actions 自动打包 |
| macOS APP 构建 | ✅ | 包含 DMG 完整格式 |
| 统一发布流程 | ✅ | Tag 推送自动创建 Release |

---

## 🏗️ 技术架构

### 后端 (Python + Flask)
```
web/
├── app.py              # Flask 主入口 + Socket.IO 事件处理
├── logic.py            # 同步逻辑 (评分计算、差异对比)
├── auth_helper.py      # Webview 自动登录 (macOS NSHTTPCookieStorage)
├── config_helper.py    # 配置文件读写 (JSON)
├── export_helper.py    # 数据导出 (CSV/JSON)
└── import_helper.py    # 数据导入 (Letterboxd CSV)
```

### 前端 (Vanilla JS + Socket.IO)
```
web/
├── templates/index.html   # 单页应用入口
└── static/
    ├── script.js          # 核心逻辑 (~2200行)
    └── style.css          # 深色主题样式 (~2600行)
```

### 数据爬取模块
```
scrapers/
├── douban_scraper.py      # 豆瓣数据获取
├── imdb_scraper.py        # IMDB 数据获取
├── trakt_client.py        # Trakt OAuth + API
└── sync_trakt_douban.py   # Trakt↔豆瓣同步
```

### 关键技术点

| 技术 | 用途 |
|------|------|
| Flask-SocketIO | 实时双向通信 (进度、日志、数据) |
| pywebview | macOS 原生 webview 登录窗口 |
| NSHTTPCookieStorage | 读取系统 Cookie 存储 |
| pandas | 数据处理与合并 |
| PyInstaller | 桌面应用打包 |

---

## 🚀 本地开发环境

### 环境要求
- Python 3.9+
- macOS 12+ (自动登录功能依赖 pyobjc)
- 推荐使用 conda 管理环境

### 快速启动
```bash
# 1. 克隆项目
git clone https://github.com/yourname/CineRecord.git
cd CineRecord

# 2. 创建虚拟环境 (可选)
conda create -n film python=3.9
conda activate film

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动服务
python -m web.app

# 5. 访问应用
# 浏览器自动打开 http://127.0.0.1:8000
```

### 本地打包
```bash
# macOS
./build_mac.sh

# Windows
build_windows.bat
```

---

## ⚠️ 注意事项

### Cookie 登录
- 豆瓣/IMDB Cookie 仅存储在本地 `config/config.json`
- 自动登录使用系统 webview，Cookie 写入系统存储后读取
- 若自动登录失败，可手动在设置页粘贴 Cookie

### 数据同步
- 同步前建议先"测试连接"确保账户有效
- 大数据量同步可能需要数分钟，请勿关闭页面
- 永久失败清单存储在 `config/permanent_failures.json`

### Letterboxd
- 不支持 API，仅通过 CSV 文件导入导出
- "同步到 Letterboxd"会下载 CSV 并打开导入页面

### Trakt
- 需要先在设置页配置 Client ID/Secret
- 使用设备授权流程，无需输入密码

---

## 📋 待开发功能

| 功能 | 优先级 | 状态 |
|------|--------|------|
| Android APK | 🔴 高 | 计划中 |
| TMDb 集成 | 🟡 中 | 评估中 |
| 批量标记已看 | 🟡 中 | 待开发 |
| 数据可视化报告 | 🟢 低 | 待开发 |

---

## 📈 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 2.1-dev | 2025-12-27 | 账户页UI优化, Letterboxd同步, 配置Cookie按钮 |
| 2.0-dev | 2025-12-22 | UI 重构, Trakt集成, CI/CD |
| 1.0 | - | 初始版本 |

---

## 📝 隐私设计原则

- ✅ 所有 Cookie 仅存储在用户本地
- ✅ 无服务器托管，无数据上传
- ✅ 开源代码，可审计
- ✅ 移动端采用离线 APK 分发

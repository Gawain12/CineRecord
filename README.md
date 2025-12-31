# 🎬 CineRecord Hub

<div align="center">

**您的私人电影数据管理中心**

支持豆瓣、IMDB、Trakt、Letterboxd、TMDB 多平台同步与备份

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Supported-blue.svg)](https://www.docker.com)

</div>

---

## ✨ 功能特性

### 🎬 多平台支持

| 平台 | 数据获取 | 评分同步 | 认证方式 |
|------|:--------:|:--------:|----------|
| **豆瓣** | ✅ | ✅ | Cookie / 自动登录 |
| **IMDB** | ✅ | ✅ | Cookie / 自动登录 |
| **Trakt** | ✅ | ✅ | OAuth 设备授权 |
| **Letterboxd** | ✅ | ✅ | CSV 导入导出 |
| **TMDB** | ✅ | ✅ | Session 授权 |

### 🔄 核心能力

- **统一电影库** - 合并所有平台数据，按时间排序，智能去重
- **评分归一化** - 豆瓣(5分制)和Letterboxd自动转换为10分制
- **双向同步** - 豆瓣 ↔ IMDB ↔ Trakt 评分互通
- **智能匹配** - 通过 IMDB ID / 名称+年份 自动匹配
- **数据备份** - 一键导出 CSV / JSON 格式

### 🖥️ 现代化界面

- 深色主题设计，舒适护眼
- 电影封面展示，评分徽章快速跳转
- 实时日志窗口，追踪任务状态
- 响应式布局，适配各种屏幕

---

## 🚀 快速开始

### 方式一：本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/CineRecord.git
cd CineRecord

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动应用
python web/app.py
```

浏览器将自动打开 `http://127.0.0.1:8000`

### 方式二：Docker 部署

```bash
# 使用 Docker Compose
docker-compose up -d

# 或直接使用 Docker
docker build -t cinerecord .
docker run -d -p 8000:8000 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/data:/app/data \
  --name cinerecord cinerecord
```

访问 `http://localhost:8000`

---

## 📖 使用指南

### 1. 连接账户

**豆瓣 / IMDB (自动登录)**
1. 点击 "🔑 自动登录" 按钮
2. 在弹出窗口完成登录
3. 登录成功后自动获取用户信息

**Trakt (设备授权)**
1. 点击 "🔗 连接 Trakt"
2. 复制显示的8位代码
3. 在打开的 trakt.tv/activate 页面输入代码
4. 确认授权后自动连接

**Letterboxd**
1. 在 Letterboxd 导出数据 (Settings → Data → Export Your Data)
2. 解压 ZIP 文件，找到 `diary.csv`
3. 点击 "📥 上传 diary.csv"

### 2. 浏览数据

切换到 **数据** 页面查看统一电影库：

- **共有** - 多平台共同标记的电影
- **独占** - 仅在单一平台标记的电影
- 点击平台徽章可直接跳转到对应网站

### 3. 同步评分

切换到 **同步** 页面：

1. 选择源平台和目标平台
2. 点击 "预览差异" 查看将要同步的内容
3. 确认后点击 "开始同步"

---

## 📁 项目结构

```
CineRecord/
├── web/                   # Web 应用核心
│   ├── app.py             # Flask 后端入口
│   ├── auth_helper.py     # 自动登录辅助
│   ├── webview_login.py   # WebView 登录窗口
│   ├── static/            # CSS/JS 前端资源
│   └── templates/         # HTML 模板
├── scrapers/              # 数据爬取模块
│   ├── douban_scraper.py  # 豆瓣
│   ├── imdb_scraper.py    # IMDB
│   ├── trakt_client.py    # Trakt
│   └── tmdb_client.py     # TMDB
├── utils/                 # 工具模块
│   └── merge_data.py      # 数据合并逻辑
├── config/                # 用户配置 (自动创建)
├── data/                  # 导出数据 (自动创建)
├── Dockerfile             # Docker 配置
├── docker-compose.yml     # Docker Compose 配置
└── requirements.txt       # Python 依赖
```

---

## 🛡️ 隐私与安全

| 特性 | 说明 |
|------|------|
| ✅ **本地存储** | Cookie 和配置仅保存在您的电脑 |
| ✅ **无云服务** | 数据不上传任何第三方服务器 |
| ✅ **开源透明** | 代码完全可审计 |
| ✅ **自主可控** | 您的数据，您做主 |

---

## 📋 开发计划

| 状态 | 功能 |
|:----:|------|
| ✅ | 豆瓣/IMDB/Trakt/Letterboxd/TMDB 支持 |
| ✅ | 统一电影库 & 封面展示 |
| ✅ | 评分归一化 (5分→10分) |
| ✅ | macOS / Windows 应用打包 |
| ✅ | Docker 部署支持 |
| 🚧 | 数据可视化报告 |
| 📋 | 移动端 PWA 支持 |

详细计划请参阅 [ROADMAP.md](./ROADMAP.md)

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📜 许可证

[MIT License](./LICENSE)

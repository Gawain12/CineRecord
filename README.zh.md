# CineSync: 豆瓣 & IMDb 评分同步工具

CineSync 是一款功能强大的命令行工具，旨在同步您在豆瓣和 IMDb 之间的电影评分。如果您同时在两个平台上记录评分，这个工具可以自动化地保持它们的一致性。

## 功能特性

- **双向同步**: 支持从豆瓣同步评分到 IMDb，或从 IMDb 同步到豆瓣。
- **增量更新**: 爬虫经过精心设计，只获取您最新的评分，使后续运行更快速、更高效。
- **默认安全**: `sync` 命令默认执行“空运行”（dry run），它会显示将要更新的电影，而不会实际执行任何更改。
- **直接 API 交互**: 工具通过官方平台 API 来更新评分，确保了操作的可靠性。

## 项目结构

```
.
├── main.py             # 所有操作的主命令行入口点。
├── data/               # 存储所有生成的 CSV 和认证文件。
├── scrapers/           # 包含用于获取评分的脚本。
├── utils/              # 包含用于合并和同步的辅助模块。
├── config/             # 你所有的个人配置都在这里。
└── requirements.txt    # Python 包依赖。
```

## 开始使用

### 1. 环境要求

- Python 3.10+
- Git

### 2. 安装

1.  **克隆仓库:**
    ```bash
    git clone <your-repo-url>
    cd CineSync
    ```

2.  **安装 Python 依赖:**
    ```bash
    pip install -r requirements.txt
    ```

### 3. 配置

这是最重要的一步。本工具需要您的浏览器 Cookie 来向豆瓣和 IMDb 进行身份验证。

1.  打开 `config/config.py` 文件。
2.  遵循文件中的详细说明，从您的浏览器中获取豆瓣和 IMDb 的 `Cookie` 字符串。
3.  将获取到的 Cookie 粘贴到 `DOUBAN_CONFIG` 和 `IMDB_CONFIG` 部分。
4.  确保在配置文件中正确设置了您的豆瓣和 IMDb 用户名。

## 使用方法

所有命令都通过 `main.py` 运行。

### 第一步：抓取你最新的评分

在同步之前，您需要从两个平台抓取您的评分。爬虫会将它们保存为 CSV 文件，并存放在 `data/` 目录中。

```bash
# 从豆瓣和 IMDb 抓取评分
python main.py scrape all
```

### 第二步：比较和同步你的评分

抓取评分后，您就可以使用 `compare` 和 `sync` 命令了。

**重要提示：** 平台的顺序至关重要。第一个平台始终是 **源平台**（评分的来源），第二个是 **目标平台**（评分的目的地）。

**比较（空运行）:**

此命令用于安全地预览更改。它会显示哪些电影在源平台已评分，但在目标平台未评分。此操作不会对您的数据做任何实际更改。

```bash
# 显示在豆瓣已评分但在 IMDb 缺失的电影
python main.py compare douban imdb

# 显示在 IMDb 已评分但在豆瓣缺失的电影
python main.py compare imdb douban
```

**同步（实时运行）:**

此命令会将缺失的评分添加到目标平台。您必须使用 `--live` 标志来执行更改。

```bash
# 从豆瓣同步评分到 IMDb
python main.py sync douban imdb --live

# 从 IMDb 同步评分到豆瓣
python main.py sync imdb douban --live
```

您还可以使用 `--limit` 标志来测试少量最旧电影的同步：

```bash
# 测试从豆瓣同步 2 部最旧的未同步电影到 IMDb
python main.py sync douban imdb --live --limit 2
```

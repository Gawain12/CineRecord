# CineSync: 豆瓣 & IMDb 评分同步工具

CineSync 是一个命令行工具，旨在同步您在豆瓣和 IMDb 上的电影评分。如果您同时在两个平台上记录评分，这个工具可以帮助您自动保持数据的一致性。

## 功能

- **双向同步**: 支持从豆瓣同步到 IMDb，或从 IMDb 同步到豆瓣。
- **增量更新**: 爬虫经过优化，仅获取您最新的评分，使后续运行更快速高效。
- **默认安全**: `sync` 命令默认执行“空运行”（dry run），它会显示将要更新的电影，而不会实际更改任何内容。

## 项目结构

```
.
├── main.py             # 所有操作的主 CLI 入口点
├── data/               # 存储所有生成的 CSV 文件
├── scrapers/           # 包含用于获取评分的脚本
├── utils/              # 包含用于合并和同步的辅助模块
├── config/             # 存放您的个人配置
└── requirements.txt    # Python 依赖包
```

## 开始使用

### 1. 准备工作

- Python 3.10+
- Git

### 2. 安装

1.  **克隆仓库:**
    ```bash
    git clone git@github.com:Gawain12/CineSync.git
    cd CineSync
    ```

2.  **安装 Python 依赖:**
    ```bash
    pip install -r requirements.txt
    ```

### 3. 配置

这是最重要的一步。本工具需要您的浏览器 Cookie 来向豆瓣和 IMDb 进行身份验证。

1.  打开 `config/config.py`。
2.  按照文件中的详细说明，从您的浏览器中获取豆瓣和 IMDb 的 `Cookie` 字符串。
3.  将 Cookie 粘贴到 `DOUBAN_CONFIG` 和 `IMDB_CONFIG` 部分。
4.  确保在配置文件中正确设置了您的豆瓣和 IMDb 用户名。

## 使用方法

所有命令都通过 `main.py` 运行。

### 步骤 1: 抓取您的最新评分

在同步之前，您需要从两个平台获取您的评分。爬虫会将它们保存为 CSV 文件存放在 `data/` 目录中。

```bash
# 从豆瓣和 IMDb 抓取评分
python main.py scrape all
```

### 步骤 2: 比较和同步您的评分

抓取评分后，您就可以使用 `compare` 和 `sync` 命令了。

**重要提示:** 平台的顺序很重要。第一个平台始终是 **源**（评分的来源），第二个是 **目标**（评分的目的地）。

**比较 (空运行):**

此命令用于安全地预览更改。它会显示哪些电影在源平台已评分，但在目标平台未评分。此操作不会做任何更改。

```bash
# 显示在豆瓣已评分但在 IMDb 缺失的电影
python main.py compare douban imdb

# 显示在 IMDb 已评分但在豆瓣缺失的电影
python main.py compare imdb douban
```

**同步 (实际执行):**

此命令会将缺失的评分添加到目标平台。默认情况下，它会进行空运行。要实际执行同步，请不要添加 `--dry-run` 标志。

```bash
# 将评分从豆瓣同步到 IMDb
python main.py sync douban imdb

# 将评分从 IMDb 同步到豆瓣
python main.py sync imdb douban
```

您也可以使用 `--limit` 标志来测试同步少量最旧的电影：

```bash
# 测试从豆瓣到 IMDb 同步 2 部最旧的未同步电影
python main.py sync douban imdb --limit 2
```

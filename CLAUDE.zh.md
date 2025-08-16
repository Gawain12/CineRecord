# CLAUDE.zh.md

该文件为 Claude Code (claude.ai/code) 在此代码库中工作时提供指导。

## 项目概述

这是一个基于 Python 的数据管道，用于抓取、同步和分析来自豆瓣和 IMDb 的电影数据。该项目被构建为一个命令行应用程序，具有明确的关注点分离：

-   **爬虫 (Scrapers)**：专门用于从豆瓣和 IMDb 获取数据并将其保存到 CSV 文件的脚本。
-   **协调器 (Orchestrator)**：一个主入口点 (`main.py`)，用于通过命令行参数运行整个管道。
-   **工具 (Utilities)**：用于合并和同步数据的辅助脚本。

## 命令

应用程序的主入口点是 `main.py`。

-   **安装依赖：**
    ```bash
    pip install -r requirements.txt
    ```

-   **运行爬虫：**
    -   **抓取特定平台：**
        ```bash
        python main.py scrape [douban|imdb|all]
        ```
    -   **执行完整抓取（忽略以前的数据）：**
        ```bash
        python main.py scrape [douban|all] --full-scrape
        ```

-   **同步平台之间的评分：**
    ```bash
    python main.py sync <source> <target>
    ```
    -   `<source>`：要从中复制评分的平台（`douban` 或 `imdb`）。
    -   `<target>`：要将评分复制到的平台（`douban` 或 `imdb`）。
    -   `--dry-run` 或 `-dr`：执行空运行，查看将同步哪些内容而不做任何更改。
    -   `--limit` 或 `-l`：仅同步指定数量的最早的电影。

-   **比较平台之间的评分：**
    ```bash
    python main.py compare <source> <target>
    ```
    -   `<source>`：拥有评分的平台。
    -   `<target>`：用于检查缺失评分的平台。

## 重要说明

-   脚本 `main.py` 中硬编码了 Python 可执行文件的路径：`/Users/gawaintan/miniforge3/envs/film/bin/python`。这可能需要根据您的环境进行调整。
-   豆瓣用户名是从 `config/config.py` 中检索的。
-   IMDb 用户名目前在 `main.py` 中是硬编码的。

## 项目结构

-   `main.py`: CLI 应用程序的主入口点。
-   `scrapers/`: 包含网络爬虫脚本 (`douban_scraper.py`, `imdb_scraper.py`)。
-   `utils/`: 包含用于数据处理和同步的实用程序脚本。
-   `config/`: 包含配置文件。
-   `data/`: 存储由爬虫生成的 CSV 文件。
-   `requirements.txt`: 列出项目的 Python 依赖项。

## 关键库

-   **argparse**: 用于在 `main.py` 中创建命令行界面。
-   **subprocess**: `main.py` 使用它来协调不同的管道脚本。
-   **pandas**: 用于数据操作。
-   **requests**: 用于同步 HTTP 请求。
-   **tqdm**: 用于显示进度条。

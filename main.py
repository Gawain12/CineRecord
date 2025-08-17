import argparse
import os
import subprocess
import time
from tqdm import tqdm

import random
import pandas as pd
from config.config import DOUBAN_CONFIG, IMDB_CONFIG
from utils.sync_rate import rate_on_imdb, rate_on_douban, get_douban_ck_from_cookie

# Import the refactored functions from the analysis module
from utils.merge_data import merge_movie_data


def get_user_csv_paths(user):
    """
    Constructs the paths to the user's ratings CSV files.
    In a real application, this would be handled by a more robust config system.
    """
    douban_csv = f'data/douban_{user}_ratings.csv'
    # The IMDb username is currently hardcoded, but could be a parameter.
    imdb_csv = 'data/imdb_ur79467081_ratings.csv' 
    return douban_csv, imdb_csv

def run_sync(source, target, user, movies_to_sync, dry_run=True, limit=None):
    """
    Main function to run the synchronization process.
    """
    print(f"Starting rating sync from {source} to {target} for user '{user}'.")

    if movies_to_sync.empty:
        print("Platforms are already in sync. No movies to migrate.")
        return

    print(f"Found {len(movies_to_sync)} movies to sync from {source} to {target}.")

    # 4. Process the synchronization
    if dry_run:
        print("\n--- DRY RUN ---")
        print("The following movies would be synced (showing first 5):")
        if source == 'douban':
            display_cols = ['Title', 'YourRating_douban', 'imdb_id']
        else:
            display_cols = ['Title', 'YourRating_imdb', 'douban_id']
        print(movies_to_sync[display_cols].head())
    else:
        print("\n--- Starting Synchronization ---")
        successful_syncs = 0
        unsuccessful_syncs = []
        if target == 'imdb':
            imdb_headers = {'cookie': IMDB_CONFIG.get('headers', {}).get('Cookie'), 'Content-Type': 'application/json'}
            for _, row in tqdm(movies_to_sync.iterrows(), total=len(movies_to_sync), desc="同步至IMDb"):
                imdb_id = row['imdb_id']
                rating = row['YourRating_douban'] * 2
                if pd.notna(imdb_id) and pd.notna(rating) and rating > 0:
                    movie_title = row.get('Title')
                    year_display = f"({int(row['Year'])})" if pd.notna(row['Year']) else "(年份未知)"
                    year_display = f"({int(row['Year'])})" if pd.notna(row['Year']) else "(年份未知)"
                    if rate_on_imdb(imdb_id, int(rating), imdb_headers, movie_title=movie_title):
                        tqdm.write(f"✅ 已同步: {row['Title']} {year_display} -> IMDb 评分: {int(rating)}")
                        successful_syncs += 1
                    else:
                        tqdm.write(f"❌ 失败: {row['Title']} {year_display} - API 调用失败。")
                        unsuccessful_syncs.append({
                            "title": row.get('Title'),
                            "id": row.get('douban_id', 'N/A'),
                            "url": row.get('URL_douban', '#')
                        })
                else:
                    tqdm.write(f"⚠️ 跳过: {row.get('Title', '未知标题')} - 未找到目标 IMDb 条目。")
                    unsuccessful_syncs.append({
                        "title": row.get('Title'),
                        "id": row.get('douban_id', 'N/A'),
                        "url": row.get('URL_douban', '#')
                    })
                    time.sleep(random.uniform(1, 3))
        elif target == 'douban':
            douban_cookie = DOUBAN_CONFIG.get('headers', {}).get('Cookie')
            ck_value = get_douban_ck_from_cookie(douban_cookie)
            douban_headers = {
                'Host': 'movie.douban.com',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': 'https://movie.douban.com',
                'Referer': 'https://m.douban.com/',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Cookie': douban_cookie
            }
            for _, row in tqdm(movies_to_sync.iterrows(), total=len(movies_to_sync), desc="同步至豆瓣"):
                douban_id = row['douban_id']
                rating = row['YourRating_imdb']
                if pd.notna(douban_id) and pd.notna(rating) and rating > 0:
                    douban_id_str = str(int(douban_id)) # Convert float to int, then to string
                    movie_title = row.get('Title') # Safely get title
                    year_display = f"({int(row['Year'])})" if pd.notna(row['Year']) else "(年份未知)"
                    year_display = f"({int(row['Year'])})" if pd.notna(row['Year']) else "(年份未知)"
                    if rate_on_douban(douban_id_str, int(rating), douban_headers, ck_value, movie_title=movie_title):
                        tqdm.write(f"✅ 已同步: {row['Title']} {year_display} -> 豆瓣评分: {int(rating)}")
                        successful_syncs += 1
                    else:
                        tqdm.write(f"❌ 失败: {row['Title']} {year_display} - API 调用失败。")
                        unsuccessful_syncs.append({
                            "title": row.get('Title'),
                            "id": row.get('imdb_id', 'N/A'),
                            "url": row.get('URL_imdb', '#')
                        })
                else:
                    title_display = row.get('Title', '未知标题')
                    tqdm.write(f"⚠️ 跳过: {title_display} - 未找到目标豆瓣条目。")
                    unsuccessful_syncs.append({
                        "title": title_display,
                        "id": row.get('imdb_id', 'N/A'),
                        "url": row.get('URL_imdb') or row.get('URL_douban', '#')
                    })
                    time.sleep(random.uniform(1, 3))

            
    print("\nSynchronization process complete.")

    # --- Post-sync Actions: Refresh data and merge ---
    if not dry_run and successful_syncs > 0:
        print("\n--- 同步摘要 ---")
        print(f"✅ 成功: {successful_syncs}")
        unsuccessful_count = len(unsuccessful_syncs)
        print(f"❌ 失败: {unsuccessful_count}")

        if unsuccessful_syncs:
            print("\n--- 失败详情 ---")
            for movie in unsuccessful_syncs:
                print(f"- {movie['title']} : {movie['url']}")
        
        # --- Generate Enriched Merged File ---
        print("\n--- Generating/Updating Your Personal Merged Ratings File ---")
        douban_csv, imdb_csv = get_user_csv_paths(user)
        if os.path.exists(douban_csv) and os.path.exists(imdb_csv):
            merge_movie_data(douban_csv, imdb_csv)
        else:
            print("⚠️ Warning: Could not generate merged file because one of the source CSVs is missing.")

        # Check if a limit was applied. If so, skip auto-refresh.
        limit_was_set = limit is not None
        
        if not limit_was_set and successful_syncs > 0:
            print(f"\n--- 正在从 {target.capitalize()} 刷新本地数据 ---")
            python_executable = "/Users/gawaintan/miniforge3/envs/film/bin/python"
            
            if target == 'douban':
                command = [python_executable, "scrapers/douban_scraper.py"]
                subprocess.run(command, check=True)
            elif target == 'imdb':
                command = [python_executable, "scrapers/imdb_scraper.py"]
                subprocess.run(command, check=True)
            
            print("--- 本地数据已刷新 ---")

        else:
            if limit_was_set:
                print("\n--- 检测到 --limit 测试运行。跳过自动数据刷新。 ---")
            if successful_syncs == 0:
                print("\n--- 没有新的评分被同步。跳过自动数据刷新。 ---")

        print("\n--- 正在生成/更新您的个人合并评分文件 ---")
        douban_csv, imdb_csv = get_user_csv_paths(user)
        if os.path.exists(douban_csv) and os.path.exists(imdb_csv):
            # Pass the user to the merge function so we can create a user-specific filename
            _, output_path = merge_movie_data(douban_csv, imdb_csv)
            if output_path:
                print(f"✅ 成功生成合并文件: {output_path}")
        else:
            print("⚠️ 警告: 由于一个或多个源CSV文件缺失，无法生成合并文件。")

# --- Helper function for sync and compare ---
def get_diff_movies(source, user):
    """Loads, merges, and compares data to find movies to be synced."""

    douban_csv, imdb_csv = get_user_csv_paths(user)
    
    if not os.path.exists(douban_csv) or not os.path.exists(imdb_csv):
        print("错误: 一个或两个评分CSV文件未找到。请先运行爬虫。")
        return None

    # The merge function now returns the dataframe and the output path
    merged_df, _ = merge_movie_data(douban_csv, imdb_csv)
    if merged_df is None:
        print("由于合并过程中出错，操作中止。")
        return None

    # Use pd.to_numeric to handle potential errors and NaNs safely
    merged_df['YourRating_imdb'] = pd.to_numeric(merged_df['YourRating_imdb'], errors='coerce')
    merged_df['YourRating_douban'] = pd.to_numeric(merged_df['YourRating_douban'], errors='coerce')
    
    if source == 'douban':
        # Find movies that have a Douban rating but no IMDb rating
        return merged_df[merged_df['YourRating_douban'].notna() & merged_df['YourRating_imdb'].isna()].copy()
    else:
        # Find movies that have an IMDb rating but no Douban rating
        return merged_df[merged_df['YourRating_imdb'].notna() & merged_df['YourRating_douban'].isna()].copy()

def main():
    parser = argparse.ArgumentParser(description="一个用于抓取和同步跨平台电影评分的工具。")
    
    # Use sub-parsers to create a command-based CLI (like 'git pull', 'git push')
    subparsers = parser.add_subparsers(dest='command', required=True, help="可执行的命令")
    
    # --- Scraper Command ---
    scrape_parser = subparsers.add_parser('scrape', help="运行爬虫以从平台获取评分。")
    scrape_parser.add_argument('platform', choices=['douban', 'imdb', 'all'], help="要抓取的平台。")
    scrape_parser.add_argument('--user', help="豆瓣用户名 (可选, 会覆盖 config.py 中的设置)。")
    scrape_parser.add_argument('--full-scrape', action='store_true', help="执行完整抓取，忽略以前的数据。")

    # --- Sync Command ---
    sync_parser = subparsers.add_parser('sync', help="查找源平台已评分但目标平台未评分的电影，并同步评分。")
    sync_parser.add_argument('source', choices=['douban', 'imdb'], help="您想要从哪个平台复制评分。")
    sync_parser.add_argument('target', choices=['douban', 'imdb'], help="您想要将评分复制到哪个平台。")
    sync_parser.add_argument('--user', help="豆瓣用户名 (可选, 会覆盖 config.py 中的设置)。")
    sync_parser.add_argument('-dr', '--dry-run', action='store_true', help="执行空运行，查看将同步哪些内容而不做任何更改。")
    sync_parser.add_argument('-l', '--limit', type=int, help="仅用于测试。同步指定数量的最早的电影。")

    # --- Compare Command ---
    compare_parser = subparsers.add_parser('compare', help="显示源平台已评分但目标平台缺失评分的电影列表。")
    compare_parser.add_argument('source', choices=['douban', 'imdb'], help="拥有评分的平台（例如 'douban'）。")
    compare_parser.add_argument('target', choices=['douban', 'imdb'], help="用于检查缺失评分的平台（例如 'imdb'）。")
    compare_parser.add_argument('--user', help="豆瓣用户名 (可选, 会覆盖 config.py 中的设置)。")

    args = parser.parse_args()

    # Hardcoded path to the python executable for the virtual environment.
    python_executable = "/Users/gawaintan/miniforge3/envs/film/bin/python"

    if args.command == 'scrape':
        user = args.user if args.user else DOUBAN_CONFIG.get('user')
        if not user:
            print("❌ 错误: 未在 config.py 或命令行参数中指定豆瓣用户。")
            return
        
        if args.platform in ['douban', 'all']:
            print("--- 运行豆瓣爬虫 ---")
            command = [python_executable, "scrapers/douban_scraper.py", "--user", user]
            if args.full_scrape:
                command.append("--full-scrape")
            subprocess.run(command, check=True)
        if args.platform in ['imdb', 'all']:
            print("--- 运行 IMDb 爬虫 ---")
            subprocess.run([python_executable, "scrapers/imdb_scraper.py"], check=True)

    elif args.command == 'sync':
        user = args.user if args.user else DOUBAN_CONFIG.get('user')
        if not user:
            print("❌ 错误: 未在 config.py 或命令行参数中指定豆瓣用户。")
            return
        if args.source == args.target:
            print("错误: 源平台和目标平台不能相同。")
            return
            
        movies_to_sync = get_diff_movies(args.source, user)
        if movies_to_sync is None:
            return # Error already printed in helper function
        
        # Sort by date and apply limit if provided
        # The column for sorting is now unified
        date_col = 'DateRated_douban' if args.source == 'douban' else 'DateRated_imdb'
        if date_col in movies_to_sync.columns:
            # Convert to datetime to handle potential string values, then sort
            movies_to_sync[date_col] = pd.to_datetime(movies_to_sync[date_col], errors='coerce')
            movies_to_sync.sort_values(by=date_col, ascending=True, inplace=True)
        
        if args.limit:
            movies_to_sync = movies_to_sync.head(args.limit)

        run_sync(args.source, args.target, user, movies_to_sync, dry_run=args.dry_run, limit=args.limit)

    elif args.command == 'compare':
        user = args.user if args.user else DOUBAN_CONFIG.get('user')
        if not user:
            print("❌ 错误: 未在 config.py 或命令行参数中指定豆瓣用户。")
            return
            
        if args.source == args.target:
            print("错误: 源平台和目标平台不能相同。")
            return

        movies_to_compare = get_diff_movies(args.source, user)
        if movies_to_compare is None:
            return # Error already printed

        if movies_to_compare.empty:
            print("\n✅ 平台已同步。未发现差异。")
        else:
            print(f"\n在 {args.source} 中发现 {len(movies_to_compare)} 部电影，这些电影在 {args.target} 中没有评分:")
            if args.source == 'douban':
                display_cols = ['Title', 'YourRating_douban', 'imdb_id', 'URL_douban']
            else:
                display_cols = ['Title', 'YourRating_imdb', 'douban_id', 'URL_imdb']
            print("-" * 80)
            # Ensure we only try to print columns that actually exist in the dataframe
            existing_display_cols = [col for col in display_cols if col in movies_to_compare.columns]
            print(movies_to_compare[existing_display_cols].to_string(index=False))
            print("-" * 80)


if __name__ == '__main__':
    main()

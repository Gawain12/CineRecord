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

def run_sync(source, target, user, movies_to_sync, dry_run=True):
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
            display_cols = ['Title_douban', 'YourRating_douban', 'Const']
        else:
            display_cols = ['Title_imdb', 'YourRating_imdb', 'Const']
        print(movies_to_sync[display_cols].head())
    else:
        print("\n--- Starting Synchronization ---")
        successful_syncs = 0
        unsuccessful_syncs = []
        if target == 'imdb':
            imdb_headers = {'cookie': IMDB_CONFIG.get('headers', {}).get('Cookie'), 'Content-Type': 'application/json'}
            for _, row in tqdm(movies_to_sync.iterrows(), total=len(movies_to_sync), desc="Syncing to IMDb"):
                imdb_id = row['Const']
                rating = row['YourRating_douban']
                if pd.notna(imdb_id) and pd.notna(rating):
                    movie_title = row.get('Title_douban') # Safely get title
                    if rate_on_imdb(imdb_id, int(rating), imdb_headers, movie_title=movie_title):
                        tqdm.write(f"✅ Synced: {row['Title_douban']} ({int(row['Year_douban'])}) -> IMDb Rating: {int(rating)}")
                        successful_syncs += 1
                    else:
                        tqdm.write(f"❌ Failed: {row['Title_douban']} ({int(row['Year_douban'])}) - API call unsuccessful.")
                        unsuccessful_syncs.append({
                            "title": row.get('Title_douban'),
                            "id": row.get('douban_id', 'N/A'),
                            "url": row.get('URL_douban', '#')
                        })
                else:
                    tqdm.write(f"⚠️ Skipped: {row.get('Title_douban', 'Unknown Title')} - Target IMDb entry not found.")
                    unsuccessful_syncs.append({
                        "title": row.get('Title_douban'),
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
            for _, row in tqdm(movies_to_sync.iterrows(), total=len(movies_to_sync), desc="Syncing to Douban"):
                douban_id = row['douban_id']
                rating = row['YourRating_imdb']
                if pd.notna(douban_id) and pd.notna(rating):
                    douban_id_str = str(int(douban_id)) # Convert float to int, then to string
                    movie_title = row.get('Title_imdb') # Safely get title
                    if rate_on_douban(douban_id_str, int(rating), douban_headers, ck_value, movie_title=movie_title):
                        tqdm.write(f"✅ Synced: {row['Title_imdb']} ({int(row['Year_imdb'])}) -> Douban Rating: {int(rating)}")
                        successful_syncs += 1
                    else:
                        tqdm.write(f"❌ Failed: {row['Title_imdb']} ({int(row['Year_imdb'])}) - API call unsuccessful.")
                        unsuccessful_syncs.append({
                            "title": row.get('Title_imdb'),
                            "id": row.get('Const', 'N/A'),
                            "url": row.get('URL_imdb', '#')
                        })
                else:
                    title_display = row.get('Title_imdb') or row.get('Title_douban', 'Unknown Title')
                    tqdm.write(f"⚠️ Skipped: {title_display} - Target Douban entry not found.")
                    unsuccessful_syncs.append({
                        "title": title_display,
                        "id": row.get('Const', 'N/A'),
                        "url": row.get('URL_imdb') or row.get('URL_douban', '#')
                    })
                    time.sleep(random.uniform(1, 3))

            
    print("\nSynchronization process complete.")

    if not dry_run:
        print("\n--- Sync Summary ---")
        print(f"✅ Successful: {successful_syncs}")
        unsuccessful_count = len(unsuccessful_syncs)
        print(f"❌ Unsuccessful: {unsuccessful_count}")

        if unsuccessful_syncs:
            print("\n--- Details for Unsuccessful Syncs ---")
            for movie in unsuccessful_syncs:
                print(f"- {movie['title']} : {movie['url']}")
        
        # --- Generate Enriched Merged File ---
        print("\n--- Generating/Updating Your Personal Merged Ratings File ---")
        douban_csv, imdb_csv = get_user_csv_paths(user)
        if os.path.exists(douban_csv) and os.path.exists(imdb_csv):
            merge_movie_data(douban_csv, imdb_csv)
        else:
            print("⚠️ Warning: Could not generate merged file because one of the source CSVs is missing.")

# --- Helper function for sync and compare ---
def get_diff_movies(source):
    """Loads, merges, and compares data to find movies to be synced."""
    user = DOUBAN_CONFIG.get('user')
    if not user:
        print("❌ Error: Douban user not found in config.py")
        return None

    douban_csv, imdb_csv = get_user_csv_paths(user)
    
    if not os.path.exists(douban_csv) or not os.path.exists(imdb_csv):
        print("Error: One or both rating CSV files were not found. Please run the scrapers first.")
        return None

    merged_df, _ = merge_movie_data(douban_csv, imdb_csv)
    if merged_df is None:
        print("Halting due to an error in the merge process.")
        return None

    if source == 'douban':
        return merged_df[merged_df['YourRating_imdb'].isnull()].copy()
    else:
        return merged_df[merged_df['YourRating_douban'].isnull()].copy()

def main():
    parser = argparse.ArgumentParser(description="一个用于抓取和同步跨平台电影评分的工具。")
    
    # Use sub-parsers to create a command-based CLI (like 'git pull', 'git push')
    subparsers = parser.add_subparsers(dest='command', required=True, help="可执行的命令")
    
    # --- Scraper Command ---
    scrape_parser = subparsers.add_parser('scrape', help="运行爬虫以从平台获取评分。")
    scrape_parser.add_argument('platform', choices=['douban', 'imdb', 'all'], help="要抓取的平台。")
    scrape_parser.add_argument('--full-scrape', action='store_true', help="执行完整抓取，忽略以前的数据。")

    # --- Sync Command ---
    sync_parser = subparsers.add_parser('sync', help="查找源平台已评分但目标平台未评分的电影，并同步评分。")
    sync_parser.add_argument('source', choices=['douban', 'imdb'], help="您想要从哪个平台复制评分。")
    sync_parser.add_argument('target', choices=['douban', 'imdb'], help="您想要将评分复制到哪个平台。")
    sync_parser.add_argument('-dr', '--dry-run', action='store_true', help="执行空运行，查看将同步哪些内容而不做任何更改。")
    sync_parser.add_argument('-l', '--limit', type=int, help="仅用于测试。同步指定数量的最早的电影。")

    # --- Compare Command ---
    compare_parser = subparsers.add_parser('compare', help="显示源平台已评分但目标平台缺失评分的电影列表。")
    compare_parser.add_argument('source', choices=['douban', 'imdb'], help="拥有评分的平台（例如 'douban'）。")
    compare_parser.add_argument('target', choices=['douban', 'imdb'], help="用于检查缺失评分的平台（例如 'imdb'）。")

    args = parser.parse_args()

    # Hardcoded path to the python executable for the virtual environment.
    python_executable = "/Users/gawaintan/miniforge3/envs/film/bin/python"

    if args.command == 'scrape':
        user = DOUBAN_CONFIG.get('user')
        if not user:
            print("❌ Error: Douban user not found in config.py")
            return
        if args.platform in ['douban', 'all']:
            print("--- Running Douban Scraper ---")
            command = [python_executable, "scrapers/douban_scraper.py", "--user", user]
            if args.full_scrape:
                command.append("--full-scrape")
            subprocess.run(command, check=True)
        if args.platform in ['imdb', 'all']:
            print("--- Running IMDb Scraper ---")
            subprocess.run([python_executable, "scrapers/imdb_scraper.py"], check=True)

    elif args.command == 'sync':
        if args.source == args.target:
            print("Error: Source and target platforms cannot be the same.")
            return
        movies_to_sync = get_diff_movies(args.source)
        if movies_to_sync is None:
            return # Error already printed in helper function
        
        # Sort by date and apply limit if provided
        date_col = 'DateRated_douban' if args.source == 'douban' else 'DateRated_imdb'
        if date_col in movies_to_sync.columns:
            movies_to_sync.sort_values(by=date_col, ascending=True, inplace=True)
        if args.limit:
            movies_to_sync = movies_to_sync.head(args.limit)

        run_sync(args.source, args.target, DOUBAN_CONFIG.get('user'), movies_to_sync, dry_run=args.dry_run)

    elif args.command == 'compare':
        if args.source == args.target:
            print("Error: Source and target platforms cannot be the same.")
            return

        movies_to_compare = get_diff_movies(args.source, args.target)
        if movies_to_compare is None:
            return # Error already printed

        if movies_to_compare.empty:
            print("\n✅ Platforms are already in sync. No differences found.")
        else:
            print(f"\nFound {len(movies_to_compare)} movies in {args.source} that are not in {args.target}:")
            if args.source == 'douban':
                display_cols = ['Title_douban', 'YourRating_douban', 'Const']
            else:
                display_cols = ['Title_imdb', 'YourRating_imdb', 'Const']
            print("-" * 60)
            print(movies_to_compare[display_cols].to_string(index=False))
            print("-" * 60)


if __name__ == '__main__':
    main()

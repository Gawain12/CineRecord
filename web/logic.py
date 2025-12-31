import os
import pandas as pd
import time
import random

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.merge_data import merge_movie_data
from utils.sync_rate import rate_on_imdb, rate_on_douban, get_douban_ck_from_cookie
# Import the robust data cleaner function
from scrapers.douban_scraper import clean_df_for_json


class SocketLogger:
    """A logger that emits messages over a WebSocket connection."""
    def __init__(self, socketio_instance):
        self.socketio = socketio_instance

    def log(self, message, type='info'):
        self.socketio.emit('log', {'message': message, 'type': type})
    
    def progress(self, current, total, step=""):
        self.socketio.emit('progress', {'current': current, 'total': total, 'step': step})


def get_diff_movies(douban_csv_path, imdb_csv_path, source, target, logger):
    """
    Get movies that exist in source but not in target (full sync mode).
    
    Returns:
        dict with 'syncable' (movies that can be synced) and 'unrated' (need rating for IMDb)
    """
    if not os.path.exists(douban_csv_path) or not os.path.exists(imdb_csv_path):
        logger.log("错误: 一个或两个评分CSV文件未找到。", 'error')
        return None
    
    temp_dir = os.path.join(os.path.dirname(douban_csv_path), 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    temp_output_path = os.path.join(temp_dir, 'temp_merged_for_diff.csv')
    
    merged_df, _ = merge_movie_data(douban_csv_path, imdb_csv_path, temp_output_path)
    if merged_df is None:
        logger.log("由于合并过程中出错，操作中止。", 'error')
        return None
    
    merged_df['YourRating_imdb'] = pd.to_numeric(merged_df['YourRating_imdb'], errors='coerce')
    merged_df['YourRating_douban'] = pd.to_numeric(merged_df['YourRating_douban'], errors='coerce')
    
    # Full sync: Get all movies from source not in target
    if source == 'douban':
        diff_df = merged_df[merged_df['YourRating_imdb'].isna() & merged_df['douban_id'].notna()].copy()
        rating_col = 'YourRating_douban'
    else:
        diff_df = merged_df[merged_df['YourRating_douban'].isna() & merged_df['imdb_id'].notna()].copy()
        rating_col = 'YourRating_imdb'
    
    date_col = 'DateRated_douban' if source == 'douban' else 'DateRated_imdb'
    if date_col in diff_df.columns:
        diff_df[date_col] = pd.to_datetime(diff_df[date_col], errors='coerce')
        diff_df.sort_values(by=date_col, ascending=True, inplace=True)
    
    # For IMDb target: separate rated (syncable) from unrated
    if target == 'imdb':
        syncable_df = diff_df[diff_df[rating_col].notna() & (diff_df[rating_col] > 0)].copy()
        unrated_df = diff_df[diff_df[rating_col].isna() | (diff_df[rating_col] == 0)].copy()
        return {'syncable': syncable_df, 'unrated': unrated_df}
    else:
        # For Douban/Trakt target: all movies are syncable (can mark as watched without rating)
        return {'syncable': diff_df, 'unrated': pd.DataFrame()}


def safe_df_to_records(df):
    """
    A robust, manual DataFrame to list-of-dicts converter that guarantees
    JSON-serializable output by explicitly handling special types.
    """
    records = []
    # Replace all special Pandas nulls with a standard one
    df = df.replace({pd.NaT: None, pd.NA: None, float('nan'): None})
    
    for row in df.itertuples(index=False):
        record = {}
        for col, val in zip(df.columns, row):
            # Explicitly convert any remaining problematic types
            if isinstance(val, (pd.Timestamp, pd.Timedelta)):
                record[col] = str(val)
            else:
                record[col] = val
        records.append(record)
    return records

def perform_sync_logic(douban_path, imdb_path, direction, is_dry_run, douban_cookie, imdb_cookie, socketio):
    """
    Main sync logic - Full sync mode (all watched movies + ratings).
    
    For IMDb target: separates unrated movies (cannot sync) and shows them as reminder.
    For Douban/Trakt target: syncs all (can mark as watched even without rating).
    """
    logger = SocketLogger(socketio)
    source, target = direction.split('-to-')
    
    failure_log_path = os.path.join(os.path.dirname(douban_path), 'sync_failures.csv')

    # Load existing failures
    failed_ids = set()
    if os.path.exists(failure_log_path):
        try:
            failures_df = pd.read_csv(failure_log_path)
            if 'douban_id' in failures_df.columns:
                failed_ids.update(failures_df['douban_id'].dropna().astype(str))
            if 'imdb_id' in failures_df.columns:
                failed_ids.update(failures_df['imdb_id'].dropna().astype(str))
        except pd.errors.EmptyDataError:
            pass
    
    logger.log(f"开始处理: 从 {source} 同步到 {target} (全量同步)", 'info')
    
    diff_result = get_diff_movies(douban_path, imdb_path, source, target, logger)

    if diff_result is None:
        logger.log("无法获取差异数据，操作终止。", 'error')
        return
    
    movies_to_sync = diff_result['syncable']
    unrated_movies = diff_result['unrated']
    
    # Emit unrated movies for IMDb target (as a reminder)
    if target == 'imdb' and not unrated_movies.empty:
        logger.log(f"⚠️ 发现 {len(unrated_movies)} 部待评价电影（无法同步到 IMDb）", 'info')
        socketio.emit('sync_unrated', {
            'movies': safe_df_to_records(unrated_movies),
            'count': len(unrated_movies)
        })

    # --- Permanent Fail List & Actual Sync Logic ---
    newly_failed_items = []
    
    # The logic to check against the permanent fail list should ONLY run during a real sync.
    if not is_dry_run:
        fail_list_path = os.path.join(os.path.dirname(douban_path), 'failed_sync_items.csv')
        try:
            failed_df = pd.read_csv(fail_list_path)
            date_col = f'DateRated_{source}'

            if 'Title' in failed_df.columns and date_col in failed_df.columns and date_col in movies_to_sync.columns:
                movies_to_sync[date_col] = pd.to_datetime(movies_to_sync[date_col], errors='coerce').dt.strftime('%Y-%m-%d')
                failed_df[date_col] = pd.to_datetime(failed_df[date_col], errors='coerce').dt.strftime('%Y-%m-%d')
                
                merged = pd.merge(movies_to_sync, failed_df[['Title', date_col]].dropna(), on=['Title', date_col], how='left', indicator=True)
                
                skipped_df = merged[merged['_merge'] == 'both']
                
                if not skipped_df.empty:
                    logger.log(f"🧠 已根据永久失败清单跳过 {len(skipped_df)} 个已知会失败的项目。", 'info')
                    for _, row in skipped_df.iterrows():
                        # During a real sync, skipped items are immediately marked as failed items in the UI.
                        socketio.emit('sync_item_failed', safe_df_to_records(pd.DataFrame([row]))[0])
                
                movies_to_sync = merged[merged['_merge'] == 'left_only'].drop(columns=['_merge'])
                
        except (FileNotFoundError, KeyError):
            pass # It's okay if the file doesn't exist yet.
    
    # --- Dry Run (Preview) Logic ---
    if is_dry_run:
        logger.log("--- 预览模式 ---", 'info')
        total_movies_preview = len(movies_to_sync)
        if total_movies_preview == 0:
            logger.log("✅ 平台已同步，无需操作。", 'success')
            # Still return an empty list so the frontend can clear the preview.
            return []
        else:
            logger.log(f"发现 {total_movies_preview} 部电影需要同步。", 'info')
            return safe_df_to_records(movies_to_sync)

    # --- The rest of the function is now ONLY for the actual sync ---
    
    # Filter out movies that have previously failed (legacy check, can be removed if merge logic is trusted)
    initial_count = len(movies_to_sync)
    movies_to_sync['douban_id'] = movies_to_sync['douban_id'].astype(str)
    movies_to_sync = movies_to_sync[
        ~movies_to_sync['douban_id'].isin(failed_ids) & 
        ~movies_to_sync['imdb_id'].isin(failed_ids)
    ]
    filtered_count = initial_count - len(movies_to_sync)
    if filtered_count > 0:
        logger.log(f"ℹ️ 已根据失败清单自动跳过 {filtered_count} 部电影。", 'info')

    
    successful_syncs = 0
    skipped_count = 0
    failed_count = 0
    total_movies = len(movies_to_sync)

    if total_movies == 0:
        logger.log("✅ 平台已同步，无需操作。", 'success')
    else:
        logger.log(f"发现 {total_movies} 部电影需要同步。", 'info')
        logger.progress(0, total_movies, "准备同步...")

        # --- Actual Sync API Calls ---
        if target == 'imdb':
            headers = {'cookie': imdb_cookie, 'Content-Type': 'application/json'}
            for i, (idx, row) in enumerate(movies_to_sync.iterrows()):
                imdb_id = row.get('imdb_id')
                rating_raw = row.get('YourRating_douban')
                rating = rating_raw * 2 if pd.notna(rating_raw) and rating_raw > 0 else None
                
                # Always update progress first
                logger.progress(i + 1, total_movies, f"同步至IMDb ({i+1}/{total_movies})")
                
                if pd.isna(imdb_id):
                    # No IMDB ID - skip
                    logger.log(f"⚠️ {i+1}/{total_movies}: {row.get('Title')} - 无 IMDb ID，跳过", 'info')
                    skipped_count += 1
                    continue
                
                if rating and rating > 0:
                    # Has rating - sync rating
                    if rate_on_imdb(imdb_id, int(rating), headers, movie_title=row.get('Title')):
                        logger.log(f"✅ {i+1}/{total_movies}: {row['Title']} -> IMDb 评分: {int(rating)}", 'success')
                        successful_syncs += 1
                    else:
                        logger.log(f"❌ {i+1}/{total_movies}: {row['Title']} - API 调用失败", 'error')
                        socketio.emit('sync_item_failed', safe_df_to_records(pd.DataFrame([row]))[0])
                        newly_failed_items.append(row)
                        failed_count += 1
                        failure_df = pd.DataFrame([{'douban_id': row.get('douban_id'), 'imdb_id': row.get('imdb_id'), 'Title': row.get('Title'), 'failed_at': pd.Timestamp.now()}])
                        failure_df.to_csv(failure_log_path, mode='a', header=not os.path.exists(failure_log_path), index=False)
                else:
                    # No rating - should not happen since we pre-filter, but just in case
                    logger.log(f"⚠️ {i+1}/{total_movies}: {row['Title']} - 跳过 (无评分)", 'info')
                    skipped_count += 1
                
                time.sleep(random.uniform(1, 3))

        elif target == 'douban':
            ck = get_douban_ck_from_cookie(douban_cookie)
            headers = { 'Cookie': douban_cookie, 'Content-Type': 'application/x-www-form-urlencoded' }
            for i, (idx, row) in enumerate(movies_to_sync.iterrows()):
                douban_id = row.get('douban_id')
                rating_raw = row.get('YourRating_imdb')
                rating = int(rating_raw) if pd.notna(rating_raw) and rating_raw > 0 else None
                
                # Always update progress first
                logger.progress(i + 1, total_movies, f"同步至豆瓣 ({i+1}/{total_movies})")
                
                if pd.isna(douban_id) or not str(douban_id).replace('.', '', 1).isdigit():
                    logger.log(f"⚠️ {i+1}/{total_movies}: {row.get('Title')} - 无有效豆瓣 ID，跳过", 'info')
                    skipped_count += 1
                    continue
                
                if rating and rating > 0:
                    # Has rating - sync rating
                    if rate_on_douban(str(int(douban_id)), int(rating), headers, ck, movie_title=row.get('Title')):
                        logger.log(f"✅ {i+1}/{total_movies}: {row['Title']} -> 豆瓣评分: {int(rating)}", 'success')
                        successful_syncs += 1
                    else:
                        logger.log(f"❌ {i+1}/{total_movies}: {row['Title']} - API 调用失败", 'error')
                        socketio.emit('sync_item_failed', safe_df_to_records(pd.DataFrame([row]))[0])
                        newly_failed_items.append(row)
                        failed_count += 1
                        failure_df = pd.DataFrame([{'douban_id': row.get('douban_id'), 'imdb_id': row.get('imdb_id'), 'Title': row.get('Title'), 'failed_at': pd.Timestamp.now()}])
                        failure_df.to_csv(failure_log_path, mode='a', header=not os.path.exists(failure_log_path), index=False)
                else:
                    # No rating - mark as watched only (豆瓣支持仅标记"看过"不评分)
                    # Use rating=0 to mark as watched without rating
                    if rate_on_douban(str(int(douban_id)), 0, headers, ck, movie_title=row.get('Title')):
                        logger.log(f"✅ {i+1}/{total_movies}: {row['Title']} -> 豆瓣 (仅标记看过)", 'success')
                        successful_syncs += 1
                    else:
                        logger.log(f"❌ {i+1}/{total_movies}: {row['Title']} - API 调用失败", 'error')
                        failed_count += 1
                
                time.sleep(random.uniform(1, 3))

    # --- After loop, update the permanent fail list ---
    if newly_failed_items:
        new_fails_df = pd.DataFrame(newly_failed_items)
        try:
            # Append new failures, avoiding duplicates
            existing_fails_df = pd.read_csv(fail_list_path)
            combined_fails_df = pd.concat([existing_fails_df, new_fails_df], ignore_index=True)
        except FileNotFoundError:
            combined_fails_df = new_fails_df
        
        # Define a robust unique key for each item
        unique_key = ['Title', 'DateRated_douban', 'DateRated_imdb', 'YourRating_douban', 'YourRating_imdb']
        # Keep only columns that exist in the dataframe to prevent errors
        existing_unique_key = [col for col in unique_key if col in combined_fails_df.columns]
        
        combined_fails_df.drop_duplicates(subset=existing_unique_key, keep='last', inplace=True)
        combined_fails_df.to_csv(fail_list_path, index=False, encoding='utf-8-sig')
        logger.log(f"永久失败清单已更新，新增 {len(new_fails_df)} 条记录。", 'info')

    logger.log(f"同步完成! ✅ 成功: {successful_syncs} / ⏭️ 跳过: {skipped_count} / ❌ 失败: {failed_count}", 'success')

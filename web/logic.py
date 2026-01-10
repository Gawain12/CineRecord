import os
import pandas as pd
import time
import random
import logging

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.merge_data import merge_movie_data
from utils.sync_rate import rate_on_imdb, rate_on_douban, get_douban_ck_from_cookie
# Import the robust data cleaner function
from scrapers.douban_scraper import clean_df_for_json
from web.data_utils import safe_df_to_records

# Get Python logger for debug messages
py_logger = logging.getLogger(__name__)


class SocketLogger:
    """A logger that emits messages over a WebSocket connection."""
    def __init__(self, socketio_instance, task_context=None):
        self.socketio = socketio_instance
        self.task_context = task_context  # Optional: {'task_name': '...', 'source': '...', 'target': '...'}

    def log(self, message, type='info'):
        # Emit to sidebar log
        if self.socketio:
            self.socketio.emit('log', {'message': message, 'type': type})
        # Also emit to task log panel and persist if in task context
        if self.task_context:
            task_name = self.task_context.get('task_name', 'Sync')
            source = self.task_context.get('source', '')
            target = self.task_context.get('target', '')
            
            if self.socketio:
                self.socketio.emit('scheduled_task_log', {
                    'type': type,
                    'task_name': task_name,
                    'source': source,
                    'target': target,
                    'message': message
                })
            
            # Persist to file
            try:
                from web.task_logs import add_task_log
                add_task_log(task_name, message, type, source, target)
            except Exception:
                pass
    
    def progress(self, current, total, step=""):
        if self.socketio:
            self.socketio.emit('progress', {'current': current, 'total': total, 'step': step})
        # Also emit progress to task log panel
        if self.task_context and step:
            task_name = self.task_context.get('task_name', 'Sync')
            msg = f"⏳ {step} ({current}/{total})"
            if self.socketio:
                self.socketio.emit('scheduled_task_log', {
                    'type': 'progress',
                    'task_name': task_name,
                    'message': msg
                })
            # Persist progress to file (less frequently - only key steps)
            if current == total or current == 1:
                try:
                    from web.task_logs import add_task_log
                    add_task_log(task_name, msg, 'progress', self.task_context.get('source', ''), self.task_context.get('target', ''))
                except Exception:
                    pass



from adapters.registry import AdapterRegistry
# ... existing imports ...
from datetime import datetime
from web.sync_cache import get_cache

def normalize_date(date_str):
    """
    Normalize date string to YYYY-MM-DD
    Handles:
    - YYYY-MM-DD (ISO)
    - M/D/YY (Douban short)
    - YYYY-M-D (Douban)
    Returns "0000-00-00" for empty/invalid dates to ensure they sort before all valid dates.
    """
    if not date_str:
        return "0000-00-00"
    
    date_str = str(date_str).strip()
    
    # Handle pandas NaN converted to string
    if date_str.lower() in ['nan', 'nat', 'none', '']:
        return "0000-00-00"
    
    # Already YYYY-MM-DD?
    if len(date_str) == 10 and date_str[4] == '-' and date_str[7] == '-':
        return date_str
        
    try:
        # Try M/D/YY (e.g. 9/9/21)
        if '/' in date_str:
            parts = date_str.split('/')
            if len(parts) == 3:
                m, d, y = map(int, parts)
                # Handle 2-digit year
                if y < 100: y = y + 2000 # Assume 21st century
                return f"{y:04d}-{m:02d}-{d:02d}"
                
        # Try parsing via datetime (fallback)
        for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%m/%d/%y'):
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except:
                pass
                
        # Return minimum date if all parsing fails
        return "0000-00-00"
    except:
        return "0000-00-00"

def normalize_movie(row, platform):
    """
    Normalize a movie record from any platform into a standard format.
    Returns:
        {
            'title': str,
            'year': str,
            'rating': float (0-10 scale),
            'ids': {'imdb': 'tt...', 'douban': '123...', ...},
            'raw': dict (original row)
        }
    """
    ids = {}
    title = str(row.get('Title', 'Unknown'))
    year = str(row.get('Year', ''))
    
    # ID Normalization
    if platform == 'douban':
        if row.get('douban_id'): ids['douban'] = str(row.get('douban_id'))
        if row.get('Const'): ids['imdb'] = str(row.get('Const'))
    elif platform == 'imdb':
        if row.get('Const'): ids['imdb'] = str(row.get('Const'))
        if row.get('imdb_id'): ids['imdb'] = str(row.get('imdb_id'))
        if row.get('IMDb ID'): ids['imdb'] = str(row.get('IMDb ID'))
    elif platform == 'trakt':
        # Trakt export often has spaces in keys 'Trakt ID', 'IMDb ID' etc
        if row.get('Trakt ID'): ids['trakt'] = str(row.get('Trakt ID'))
        if row.get('trakt_id'): ids['trakt'] = str(row.get('trakt_id'))
        if row.get('IMDb ID'): ids['imdb'] = str(row.get('IMDb ID'))
        if row.get('imdb_id'): ids['imdb'] = str(row.get('imdb_id'))
        if row.get('TMDB ID'): ids['tmdb'] = str(row.get('TMDB ID'))
        if row.get('tmdb_id'): ids['tmdb'] = str(row.get('tmdb_id'))
        if row.get('ids', {}).get('trakt'): ids['trakt'] = str(row.get('ids', {}).get('trakt'))
        if row.get('ids', {}).get('imdb'): ids['imdb'] = str(row.get('ids', {}).get('imdb'))
    elif platform == 'tmdb':
        if row.get('tmdb_id'): ids['tmdb'] = str(row.get('tmdb_id'))
        if row.get('imdb_id'): ids['imdb'] = str(row.get('imdb_id'))
    elif platform == 'letterboxd':
        if row.get('Letterboxd URI'): ids['letterboxd'] = str(row.get('Letterboxd URI'))
        if row.get('imdb_id'): ids['imdb'] = str(row.get('imdb_id'))
        if row.get('tmdb_id'): ids['tmdb'] = str(row.get('tmdb_id'))

    # Rating Normalization (0-10 scale)
    # Priority: Use user's personal rating first, then platform-public rating
    rating = 0.0
    try:
        if platform == 'douban':
            # Douban 'Your Rating' is 1-5 stars, need *2 for 10-point scale
            # 'Douban Rating' is already 10-point (public score)
            user_rating = row.get('Your Rating')
            if user_rating and str(user_rating).strip() and str(user_rating).lower() not in ['nan', 'none', '0', '0.0', '']:
                rating = float(user_rating) * 2  # 1-5 stars → 2-10 points
            # Don't fallback to 'Douban Rating' - that's the movie's public score, not user's
        elif platform == 'letterboxd':
            # Letterboxd uses 0.5-5 scale
            raw = row.get('Your Rating') or row.get('Rating') or row.get('rating')
            if raw and str(raw).strip() and str(raw).lower() not in ['nan', 'none', '']:
                rating = float(raw) * 2  # 0.5-5 → 1-10
        else:
            # IMDB, Trakt, TMDB all use 1-10 scale
            raw = row.get('Your Rating') or row.get('rating') or row.get('Rating')
            if raw and str(raw).strip() and str(raw).lower() not in ['nan', 'none', '']:
                rating = float(raw)
    except (ValueError, TypeError):
        pass

    return {
        'title': title,
        'year': year,
        'rating': rating,
        'ids': ids,
        'raw': row
    }


def get_unified_diff(source, target, logger, app_data=None, options=None):
    """
    Simplified sync strategy: Take most recent N items from source, 
    check if their IDs exist in target, sync only missing ones.
    
    Options:
        - only_new: If True (default), only sync items NOT in target
        - overwrite: If True, sync ALL items (even if in target, will overwrite ratings)
    
    This avoids timestamp dependency and rating comparison complexity.
    """
    RECENT_ITEMS_LIMIT = 100  # Only check the most recent 100 items
    
    # Parse options
    only_new = options.get('only_new', True) if options else True
    overwrite = options.get('overwrite', False) if options else False
    
    if app_data is None:
        logger.log("❌ App data context missing.", 'error')
        return None
    
    source_df = app_data.get(f'{source}_df')
    target_df = app_data.get(f'{target}_df')

    if source_df is None or source_df.empty:
        logger.log(f"❌ {source} cache is empty. Please fetch data first.", 'error')
        return None
        
    movies_to_sync = []
    
    # 1. Build target ID index (all existing IDs in target)
    target_index = set()  # Set of "id_type:id_value" strings for fast lookup
    target_records = []
    
    if target_df is not None and not target_df.empty:
        target_records = target_df.to_dict('records')
        for row in target_records:
            norm_target = normalize_movie(row, target)
            for id_type, id_val in norm_target['ids'].items():
                target_index.add(f"{id_type}:{id_val}")
        
        logger.log(f"📚 目标平台已有 {len(target_records)} 条记录", 'info')
    
    # 2. Get source records and sort by date (newest first)
    source_records = source_df.to_dict('records')
    
    def get_date(r):
        return normalize_date(str(r.get('Date Rated', '')))
    
    source_records.sort(key=get_date, reverse=True)
    
    # 3. Take only the most recent N items from source
    recent_source_records = source_records[:RECENT_ITEMS_LIMIT]
    
    logger.log(f"🔍 检查最近 {len(recent_source_records)} 条源记录...", 'info')
    
    # 4. Check each recent item - behavior depends on options
    for row in recent_source_records:
        norm_source = normalize_movie(row, source)
        
        # Check if any ID from this source item exists in target
        found_in_target = False
        for id_type, id_val in norm_source['ids'].items():
            if f"{id_type}:{id_val}" in target_index:
                found_in_target = True
                break
        
        # Decide whether to sync this item
        should_sync = False
        if overwrite:
            # Overwrite mode: sync ALL items (will update ratings even if exists)
            should_sync = True
        elif only_new:
            # Only new mode: sync only if NOT in target
            should_sync = not found_in_target
        else:
            # Both off: sync all new items (default behavior)
            should_sync = not found_in_target
        
        if should_sync:
            # This item is not in target - need to sync
            # Resolve target linking ID
            target_linking_id = None
            
            if target == 'imdb':
                target_linking_id = norm_source['ids'].get('imdb')
            elif target == 'douban':
                target_linking_id = norm_source['ids'].get('douban')
            elif target == 'trakt':
                target_linking_id = norm_source['ids'].get('trakt') or norm_source['ids'].get('imdb')
            elif target == 'tmdb':
                target_linking_id = norm_source['ids'].get('tmdb') or norm_source['ids'].get('imdb')
            elif target == 'letterboxd':
                target_linking_id = norm_source['ids'].get('imdb') or norm_source['ids'].get('tmdb')
            
            # Only add if we have a valid target ID
            if target_linking_id:
                movies_to_sync.append({
                    'Title': norm_source['title'],
                    'Year': norm_source['year'],
                    'source_rating': norm_source['rating'],
                    'target_linking_id': target_linking_id,
                    'action': 'new',
                    'ids': norm_source['ids'],
                    'URL': norm_source['raw'].get('URL') or norm_source['raw'].get('Link') or norm_source['raw'].get('Subject Link')  # 涵盖常见链接字段
                })
    
    # Filter out items without target_linking_id (cannot sync these)
    movies_to_sync = [m for m in movies_to_sync if m.get('target_linking_id')]
    
    # Filter out blacklisted items (known failures)
    cache = get_cache()
    initial_count = len(movies_to_sync)
    movies_to_sync = [
        m for m in movies_to_sync 
        if not cache.is_blacklisted(source, target, m.get('target_linking_id', ''))
    ]
    filtered_count = initial_count - len(movies_to_sync)
    if filtered_count > 0:
        logger.log(f"⏩ 已跳过 {filtered_count} 部已知无法同步的电影（黑名单缓存）", 'info')
    
    logger.log(f"🔍 预览: 发现 {len(movies_to_sync)} 部可同步电影。", 'info')
    
    return movies_to_sync

def perform_sync_logic(direction, is_dry_run, socketio, app_data=None, options=None, task_context=None):
    """
    Unified Sync Logic Entrypoint
    
    Args:
        task_context: Optional dict with {'task_name', 'source', 'target'} for scheduled task logging
    """
    logger = SocketLogger(socketio, task_context=task_context)
    try:
        source, target = direction.split('-to-')
    except:
        logger.log(f"Invalid direction: {direction}", 'error')
        return
    
    logger.log(f"🚀 开始处理: {source.upper()} -> {target.upper()}", 'info')
    
    # 1. Calculate Diff
    from web.sync_cache import get_cache
    cache = get_cache()  # Initialize cache specifically for this sync session
    
    try:
        movies_to_sync = get_unified_diff(source, target, logger, app_data, options=options)
    except Exception as e:
        logger.log(f"Diff calculation failed: {str(e)}", 'error')
        return

    if not movies_to_sync:
        logger.log("✅ 没有发现需要同步的项目。", 'success')
        return

    # Sync Options
    default_rating = options.get('default_rating', 0) if options else 0

    # Pre-process for validation/preview/skip
    import math
    for item in movies_to_sync:
        # User Feedback: Only IMDb rejects unrated items. Others allow it (as watched).
        if target == 'imdb':
            r = item.get('source_rating')
            is_valid = False
            try:
                if r and float(r) > 0 and not math.isnan(float(r)):
                    is_valid = True
            except:
                pass
            
            if not is_valid:
                # Apply default rating if configured
                if default_rating > 0:
                    item['source_rating'] = default_rating
                else:
                    if is_dry_run:
                        item['Title'] = f"{item.get('Title')} ⚠️(无评分-跳过)"
                    else:
                        item['_skip_reason'] = 'unrated'
        elif target == 'tmdb':
            r = item.get('source_rating')
            is_valid = False
            try:
                if r and float(r) > 0 and not math.isnan(float(r)):
                    is_valid = True
            except:
                pass

            if not is_valid:
                # Apply default rating if configured (same as IMDb)
                if default_rating > 0:
                    item['source_rating'] = default_rating
                else:
                    if is_dry_run:
                        item['Title'] = f"{item.get('Title')} ⚠️(无评分-TMDB不支持仅标记)"
                    else:
                        item['_skip_reason'] = 'tmdb_unrated'
        else:
            # For other platforms (Trakt, Douban), missing rating is fine (mark as watched)
            pass

    if is_dry_run:
        logger.log(f"🔍 预览: 发现 {len(movies_to_sync)} 部可同步电影。", 'info')
        return movies_to_sync

    # 2. Perform Sync (Actual Write)
    logger.progress(0, len(movies_to_sync), "准备同步...")
    
    # Get adapter for target platform
    adapter = AdapterRegistry.get(target)
    if not adapter:
        logger.log(f"❌ 找不到平台适配器: {target}", 'error')
        return
        
    # Initialize adapter instance with config (cookies etc need to be accessible)
    # Construct a temporary config dict from args or app state if needed
    # For now, we assume the adapter can be instantiated with minimal config or reuses global config
    from web.config_helper import read_config
    config = read_config()
    
    # Update config with current session cookies if provided (important for Douban/IMDb)
    # The adapter might need specific keys
    if target == 'douban':
         # logic.py imports get_douban_ck_from_cookie
        from utils.sync_rate import get_douban_ck_from_cookie
        config['douban_cookie'] = config.get('douban_cookie') # Ensure it uses what's passed or stored
        config['douban_ck'] = get_douban_ck_from_cookie(config.get('douban_cookie'))
    elif target == 'imdb':
        config['imdb_cookie'] = config.get('imdb_cookie')

    # Instantiate adapter
    # Note: Adapter constructors usually take (logger, config)
    adapter_instance = adapter(logger, config)
    
    if not adapter_instance.supports_sync:
        logger.log(f"❌ 平台 {target} 不支持写入同步。", 'error')
        return

    # Collect detailed results
    sync_results = {
        'success': [],
        'failed': [],
        'skipped': []
    }
    
    successful_syncs = 0
    failed_count = 0
    skipped_count = 0 
    total = len(movies_to_sync)

    # Helper function to get platform URL
    def get_platform_url(platform, movie_id, movie_data, media_type='movie'):
        if platform == 'douban' and movie_id:
            return f"https://movie.douban.com/subject/{movie_id}/"
        elif platform == 'imdb' and movie_id:
            return f"https://www.imdb.com/title/{movie_id}/"
        elif platform == 'tmdb' and movie_id:
            path = 'tv' if media_type == 'tv' else 'movie'
            return f"https://www.themoviedb.org/{path}/{movie_id}"
        elif platform == 'trakt' and movie_id:
            # Trakt needs slug, fallback to IMDb ID
            imdb_id = movie_data.get('ids', {}).get('imdb')
            if imdb_id:
                return f"https://trakt.tv/search/imdb/{imdb_id}"
        return '#'

    for i, row in enumerate(movies_to_sync):
        logger.progress(i + 1, total, f"同步至 {target.upper()} ({i+1}/{total})")
        
        movie_title = row.get('Title', 'Unknown')
        movie_year = row.get('Year', '')
        target_id = row.get('target_linking_id')
        rating = row.get('source_rating')
        
        # Get source URL from original data
        source_url = row.get('URL', '#')
        if not source_url or source_url == '#':
            # Try to construct from IDs
            source_id = row.get('ids', {}).get(source) if 'ids' in row else None
            if source_id:
                source_url = get_platform_url(source, source_id, row)
        
        # Check explicit skip reason
        if row.get('_skip_reason') == 'unrated':
            logger.log(f"⏩ 跳过 {movie_title} (无评分)", 'info')
            sync_results['skipped'].append({
                'title': movie_title,
                'year': movie_year,
                'source_url': source_url,
                'reason': '无评分'
            })
            skipped_count += 1
            continue
        if row.get('_skip_reason') == 'tmdb_unrated':
            logger.log(f"⏩ 跳过 {movie_title} (TMDB不支持仅标记已看)", 'info')
            sync_results['skipped'].append({
                'title': movie_title,
                'year': movie_year,
                'source_url': source_url,
                'reason': 'TMDB不支持仅标记已看'
            })
            skipped_count += 1
            continue
        
        if not target_id:
             logger.log(f"⚠️ 跳过 {movie_title} (找不到目标ID)", 'info')
             sync_results['skipped'].append({
                 'title': movie_title,
                 'year': movie_year,
                 'source_url': source_url,
                 'reason': '找不到目标ID'
             })
             skipped_count += 1
             continue
              
        # Perform the sync action
        try:
            # Validate rating - skip if no valid rating
            normalized_rating = 0
            try:
                if rating and str(rating).strip() and str(rating).lower() not in ['nan', 'none', '']:
                    normalized_rating = float(rating)
                    if normalized_rating < 0 or normalized_rating > 10:
                        raise ValueError("Rating out of range")
            except (ValueError, TypeError):
                normalized_rating = 0
            
            # Skip movies without valid ratings ONLY for IMDb target
            # Other platforms (TMDB, Trakt, Douban) allow rating=0 as "watched only"
            if normalized_rating <= 0 and target == 'imdb':
                logger.log(f"⏩ 跳过 {movie_title} (IMDb不支持无评分记录)", 'info')
                sync_results['skipped'].append({
                    'title': movie_title,
                    'year': movie_year,
                    'source_url': source_url,
                    'reason': 'IMDb不支持无评分'
                })
                skipped_count += 1
                continue
            
            success = adapter_instance.sync_movie(
                item_id=target_id,
                rating=normalized_rating,
                comment=f"Synced from {source.title()}",
                tags=[f"sync:{source}"]
            )
            
            target_url = get_platform_url(target, target_id, row)
            if target == 'tmdb':
                tmdb_id = getattr(adapter_instance, 'last_synced_tmdb_id', None)
                tmdb_media = getattr(adapter_instance, 'last_synced_media_type', 'movie')
                if tmdb_id:
                    target_url = get_platform_url(target, tmdb_id, row, media_type=tmdb_media)

            if success:
                logger.log(f"✅ 同步成功: {movie_title} (评分: {rating}/10)", 'success')
                sync_results['success'].append({
                    'title': movie_title,
                    'year': movie_year,
                    'source_rating': rating,
                    'source_url': source_url,
                    'target_url': target_url,
                    'target_id': target_id
                })
                successful_syncs += 1
            else:
                 logger.log(f"❌ 同步失败: {movie_title}", 'error')
                 
                 # Add to blacklist cache
                 cache.add_failure(source, target, target_id, movie_title, "API返回失败")
                 
                 sync_results['failed'].append({
                     'title': movie_title,
                     'year': movie_year,
                     'source_url': source_url,
                     'error_msg': 'API返回失败'
                 })
                 failed_count += 1
                 
            time.sleep(random.uniform(1.0, 3.0)) # Polite delay
            
        except Exception as e:
            logger.log(f"❌ 异常 {movie_title}: {str(e)}", 'error')
            
            # Add to blacklist cache
            cache.add_failure(source, target, target_id, movie_title, str(e))
            
            sync_results['failed'].append({
                'title': movie_title,
                'year': movie_year,
                'source_url': source_url,
                'error_msg': str(e)
            })
            failed_count += 1
            
    logger.log(f"同步完成! ✅ 成功: {successful_syncs} / ⏩ 跳过: {skipped_count} / ❌ 失败: {failed_count}", 'success')
    
    # Send detailed results to frontend
    if hasattr(logger, 'socketio'):
        logger.socketio.emit('sync_results_data', {
            'results': sync_results,
            'summary': {
                'success': successful_syncs,
                'failed': failed_count,
                'skipped': skipped_count
            },
            'source': source,
            'target': target
        })



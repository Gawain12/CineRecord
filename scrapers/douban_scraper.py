import asyncio
import os
import random
import re
import time
import sys
import math
import aiohttp
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class SocketLogger:
    def __init__(self, socketio_instance, platform):
        self.socketio = socketio_instance
        self.platform = platform
    def log(self, message, type='info'):
        self.socketio.emit('log', {'message': f'[{self.platform.upper()}] {message}', 'type': type})
    def progress(self, current, total, step=""):
        self.socketio.emit('progress', {'platform': self.platform, 'current': current, 'total': total, 'step': step})

async def fetch_imdb_id_from_web(session, douban_url, retries=3):
    if not douban_url: return None
    for _ in range(retries):
        await asyncio.sleep(random.uniform(0.5, 1.5))
        try:
            async with session.get(douban_url, verify_ssl=False, timeout=30) as r:
                if r.status == 404: return None
                r.raise_for_status()
                html_content = await r.text()
                return re.search(r'IMDb:</span>\s*(tt\d+)', html_content).group(1) if re.search(r'IMDb:</span>\s*(tt\d+)', html_content) else None
        except (aiohttp.ClientError, asyncio.TimeoutError): await asyncio.sleep(3)
    return None

IMDB_CACHE_FILE = "data/db_imdb.csv"

def load_imdb_cache():
    if not os.path.exists(IMDB_CACHE_FILE): return {}
    try:
        df = pd.read_csv(IMDB_CACHE_FILE, dtype=str)
        if 'douban_id' not in df.columns and 'id' in df.columns: df.rename(columns={'id': 'douban_id'}, inplace=True)
        if df.empty or 'douban_id' not in df.columns: return {}
        df.drop_duplicates(subset=['douban_id'], keep='last', inplace=True)
        df.dropna(subset=['douban_id', 'imdb'], inplace=True)
        return pd.Series(df.imdb.values, index=df.douban_id).to_dict()
    except Exception: return {}

def clean_df_for_json(df):
    """Converts a DataFrame to a list of records, replacing NaNs with None."""
    return df.where(pd.notnull(df), None).to_dict('records')

def save_imdb_cache(imdb_cache, logger):
    if not imdb_cache: return
    logger.log(f"正在保存 {len(imdb_cache)} 条新映射到IMDb缓存...", 'info')
    df = pd.DataFrame(list(imdb_cache.items()), columns=['douban_id', 'imdb'])
    df.drop_duplicates(subset=['douban_id'], keep='last', inplace=True)
    df.to_csv(IMDB_CACHE_FILE, index=False, encoding='utf-8')

def _normalize_status(status):
    s = str(status).lower().strip() if status else ''
    if s == 'mark':
        return 'wish'
    if s in {'collect', 'watched'}:
        return 'done'
    if s == 'do':
        return 'doing'
    return s

def _api_status(status):
    s = str(status).lower().strip() if status else ''
    if s in {'wish', 'want_to_watch', 'mark'}:
        return 'mark'
    if s in {'doing', 'do'}:
        return 'doing'
    if s in {'done', 'collect', 'watched'}:
        return 'done'
    return s or 'done'

def _allowed_statuses(status):
    s = str(status).lower().strip() if status else ''
    if s in {'wish', 'want_to_watch', 'mark'}:
        return {'mark', 'wish', 'want_to_watch'}
    if s in {'done', 'collect', 'watched'}:
        return {'done', 'collect', 'watched'}
    if s in {'doing', 'do'}:
        return {'doing', 'do'}
    return {s} if s else set()

def _write_report(output_path, records, suffix, logger):
    if not records:
        return None
    base, _ = os.path.splitext(output_path)
    report_path = f"{base}_{suffix}.csv"
    try:
        df = pd.DataFrame(records)
        df.to_csv(report_path, index=False, encoding='utf-8-sig')
        logger.log(f"已输出 {suffix} 明细: {report_path}", 'warning')
        return report_path
    except Exception as e:
        logger.log(f"无法写入 {suffix} 明细: {e}", 'error')
        return None

def process_movie_data(interest, interest_status='done'):
    subject = interest.get('subject', {})
    rating = interest.get('rating', {})
    subtitle = subject.get('card_subtitle', '')
    country = parts[1].strip() if len(parts := subtitle.split('/')) > 1 else ''
    actors = ", ".join([a['name'] for a in subject.get('actors', [])[:3]])
    status = str(interest.get('status') or '').lower().strip()
    allowed_statuses = _allowed_statuses(interest_status)
    if allowed_statuses and status not in allowed_statuses:
        return None
    
    # Determine type from subject data
    # Douban API may include 'type' or 'subtype' field, or we check if it's a TV series from URL or other indicators
    subject_type = subject.get('type', '') or subject.get('subtype', '') or ''
    subject_type = str(subject_type).lower().strip()
    if 'tv' in subject_type or 'show' in subject_type or 'series' in subject_type or 'episode' in subject_type:
        media_type = 'tv'
    else:
        # Default to movie if type field is missing
        media_type = 'movie'
    
    return {'Const': None, 'Your Rating': rating.get('value', 0) if rating else 0,
            'Date Rated': interest.get('create_time', '').split(' ')[0], 'Title': subject.get('title'),
            'Directors': ", ".join([d['name'] for d in subject.get('directors', [])]), 'Actors': actors,
            'Country': country, 'Year': subject.get('year'), 'Genres': ", ".join(subject.get('genres', [])),
            'Douban Rating': subject.get('rating', {}).get('value', 0), 'Num Votes': subject.get('rating', {}).get('count', 0),
            'MyComment': interest.get('comment', ''), 'URL': subject.get('url'), 'Cover URL': subject.get('cover_url'),
            'douban_id': subject.get('id'), 'type': media_type, 'status': _normalize_status(status or interest_status)}

async def fetch_page(session, url, start, logger, size=50, status='done', retries=3):
    params = {"type": "movie", "status": status, "count": size, "start": start, "for_mobile": 1}
    for i in range(retries):
        await asyncio.sleep(random.uniform(1.0, 2.0))
        try:
            async with session.get(url, params=params, verify_ssl=False, timeout=30) as r:
                if r.status == 200:
                    return await r.json()
                else:
                    logger.log(f"请求失败 (尝试 {i+1}/{retries}): HTTP状态码 {r.status}", 'error')
                    logger.log(f"服务器响应: {await r.text()}", 'error')
        except Exception as e:
            logger.log(f"请求异常 (尝试 {i+1}/{retries}): {e}", 'error')
    return None

async def process_interest_with_imdb(session, interest, cache, interest_status='done'):
    data = process_movie_data(interest, interest_status)
    if not data:
        return None
    douban_id = data.get('douban_id')
    if douban_id in cache: data['Const'] = cache[douban_id]
    else:
        if imdb_id := await fetch_imdb_id_from_web(session, data.get('URL')):
            data['Const'] = imdb_id
            if douban_id: cache[douban_id] = imdb_id
    return data

async def scrape_douban_async(user_id, cookie, output_path, logger, interest_status='done'):
    headers = {
        'Cookie': cookie, 
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Referer': 'https://m.douban.com/'
    }
    api_url = f"https://m.douban.com/rexxar/api/v2/user/{user_id}/interests"
    interest_status = str(interest_status).lower().strip() if interest_status else 'done'
    api_status = _api_status(interest_status)
    allowed_statuses = _allowed_statuses(interest_status)
    async with aiohttp.ClientSession(headers=headers) as session:
        logger.log("验证Cookie...", 'info')
        if not await fetch_imdb_id_from_web(session, "https://m.douban.com/movie/subject/1298697/"):
            logger.log("Cookie无效或已过期。", 'error'); return None
        logger.log("Cookie验证成功。", 'success')
        
        cache = load_imdb_cache()
        logger.log(f"已加载 {len(cache)} 条IMDb缓存。", 'info')
        
        existing_records = {}
        unrated_records = set()  # 本地评分为0的记录，需要重新获取
        force_refresh = False
        
        if os.path.exists(output_path):
            try:
                df = pd.read_csv(output_path, dtype={'douban_id': str})
                if interest_status == 'wish':
                    if 'status' not in df.columns:
                        force_refresh = True
                    else:
                        status_series = df['status'].fillna('').astype(str).str.lower().str.strip()
                        allowed_set = _allowed_statuses(interest_status)
                        allowed = status_series[status_series.isin(allowed_set)]
                        non_wish = status_series[(status_series != '') & (~status_series.isin(allowed_set))]
                        if not non_wish.empty or allowed.empty:
                            force_refresh = True
                    if force_refresh:
                        logger.log("想看缓存包含非 wish 数据，将全量重建。", 'warning')
                        df = pd.DataFrame()

                # 使用 (douban_id, date) 组合作为唯一标识
                for _, row in df.iterrows():
                    movie_id = str(row['douban_id']) if pd.notna(row['douban_id']) else ''
                    date_rated = str(row['Date Rated']) if pd.notna(row['Date Rated']) else ''
                    rating = row.get('Your Rating', 0)
                    
                    if movie_id:
                        key = f"{movie_id}_{date_rated}"
                        existing_records[key] = True
                        
                        # 如果本地评分为0，标记为需要刷新
                        try:
                            if float(rating) == 0:
                                unrated_records.add(movie_id)
                        except (ValueError, TypeError):
                            pass
                
                if not force_refresh:
                    logger.log(f"发现 {len(df)} 条已有记录，其中 {len(unrated_records)} 条无评分需刷新。", 'info')
            except Exception as e:
                logger.log(f"无法读取'{output_path}': {e}，将重新创建。", 'info')
                if os.path.exists(output_path): os.remove(output_path)
                force_refresh = True

        first_page = await fetch_page(session, api_url, 0, logger, 1, api_status)
        if not first_page or 'total' not in first_page:
            logger.log("无法获取电影总数。", 'error'); return None
        
        total_movies = first_page.get('total', 0); page_size = 50
        total_pages = math.ceil(total_movies / page_size)
        logger.log(f"共发现 {total_movies} 条电影记录。", 'info')

        new_interests = []
        pages_all_existing = 0
        STOP_PAGES_THRESHOLD = 3
        refreshed_count = 0  # 刷新的无评分记录数
        skipped_status = []
        
        for page_num in range(total_pages):
            logger.progress(page_num, total_pages, f"获取列表 {page_num+1}/{total_pages}")
            page_data = await fetch_page(session, api_url, page_num * page_size, logger, page_size, api_status)
            if not page_data or not page_data.get('interests'):
                break
            
            page_new_count = 0
            for interest in page_data['interests']:
                item_status = str(interest.get('status') or '').lower().strip()
                if allowed_statuses and item_status not in allowed_statuses:
                    subject = interest.get('subject', {}) or {}
                    skipped_status.append({
                        'douban_id': subject.get('id', ''),
                        'title': subject.get('title', ''),
                        'status': item_status,
                        'date': str(interest.get('create_time', '')).split(' ')[0],
                        'url': subject.get('url', '')
                    })
                    continue
                movie_id = str(interest.get('subject', {}).get('id', ''))
                date_str = interest.get('create_time', '').split(' ')[0]
                record_key = f"{movie_id}_{date_str}"
                
                # 刷新策略：本地无评分的记录需要重新获取（捕获评分变化）
                needs_refresh = movie_id in unrated_records
                
                if needs_refresh:
                    # 本地评分为0，重新获取
                    new_interests.append(interest)
                    page_new_count += 1
                    refreshed_count += 1
                elif force_refresh or record_key not in existing_records:
                    # 真正的新记录
                    new_interests.append(interest)
                    page_new_count += 1
            
            if page_new_count > 0:
                pages_all_existing = 0
                logger.log(f"第 {page_num+1} 页: {page_new_count} 条记录", 'info')
            else:
                pages_all_existing += 1
                logger.log(f"第 {page_num+1} 页全是已有记录 (连续 {pages_all_existing} 页)", 'info')
                if pages_all_existing >= STOP_PAGES_THRESHOLD:
                    logger.log(f"连续 {pages_all_existing} 页都是已有记录，停止抓取。", 'info')
                    break
        logger.progress(total_pages, total_pages, "列表获取完成")

        if skipped_status:
            logger.log(f"跳过 {len(skipped_status)} 条非目标状态记录。", 'warning')
            _write_report(output_path, skipped_status, "skipped_status", logger)

        if not new_interests:
            logger.log("数据已是最新。", 'success')
            try:
                df = pd.read_csv(output_path)
                return clean_df_for_json(df)
            except Exception:
                return []

        logger.log(f"发现 {len(new_interests)} 条新记录，开始处理...", 'info')
        new_interests.reverse()
        tasks = []
        task_map = {}
        for interest in new_interests:
            task = asyncio.create_task(process_interest_with_imdb(session, interest, cache, interest_status))
            tasks.append(task)
            task_map[task] = interest
        new_movies = []
        failed_process = []
        for i, task in enumerate(asyncio.as_completed(tasks)):
            interest = task_map.get(task, {})
            subject = interest.get('subject', {}) or {}
            failure_recorded = False
            try:
                record = await task
            except Exception as e:
                failed_process.append({
                    'douban_id': subject.get('id', ''),
                    'title': subject.get('title', ''),
                    'status': str(interest.get('status') or '').lower().strip(),
                    'date': str(interest.get('create_time', '')).split(' ')[0],
                    'url': subject.get('url', ''),
                    'reason': str(e)
                })
                failure_recorded = True
                record = None
            if record:
                new_movies.append(record)
            elif not failure_recorded:
                failed_process.append({
                    'douban_id': subject.get('id', ''),
                    'title': subject.get('title', ''),
                    'status': str(interest.get('status') or '').lower().strip(),
                    'date': str(interest.get('create_time', '')).split(' ')[0],
                    'url': subject.get('url', ''),
                    'reason': 'empty_record'
                })
            logger.progress(i + 1, len(tasks), f"处理详情 {i+1}/{len(tasks)}")

        logger.log("保存文件中...", 'info')
        save_imdb_cache(cache, logger)
        df_new = pd.DataFrame(new_movies)
        
        df_existing = pd.DataFrame()
        if os.path.exists(output_path) and existing_records:
            df_existing = pd.read_csv(output_path, dtype=str, encoding='utf-8-sig')
        
        df_final = pd.concat([df_new, df_existing], ignore_index=True)
        cols = ['Const', 'Your Rating', 'Date Rated', 'Title', 'Directors', 'Actors', 'Country', 'Year', 'Genres', 'Douban Rating', 'Num Votes', 'MyComment', 'URL', 'Cover URL', 'douban_id', 'type', 'status']
        df_final = df_final.reindex(columns=cols)
        df_final.drop_duplicates(subset=['douban_id'], keep='first', inplace=True)
        df_final.sort_values(by='Date Rated', ascending=False, inplace=True)
        df_final.to_csv(output_path, index=False, encoding='utf-8-sig')

        if failed_process:
            logger.log(f"处理失败或为空的记录共 {len(failed_process)} 条。", 'warning')
            _write_report(output_path, failed_process, "failed_process", logger)
        
        logger.log(f"成功！新增 {len(df_new)} 条（含刷新 {refreshed_count} 条无评分记录），总计 {len(df_final)} 条。", 'success')
        return clean_df_for_json(df_final)

def run_scraper(user_id, cookie, output_path, socketio):
    logger = SocketLogger(socketio, 'douban')
    return asyncio.run(scrape_douban_async(user_id, cookie, output_path, logger))

if __name__ == '__main__':
    import config  # Trigger __init__.py to set up fallback config.config module
    from config.config import DOUBAN_CONFIG
    class CLILogger:
        def log(self, m, t='info'): print(f"[{t.upper()}] {m}")
        def progress(self, c, t, s=""): pass
    async def cli_main():
        user = DOUBAN_CONFIG.get('user_id')
        cookie = DOUBAN_CONFIG.get('headers', {}).get('Cookie')
        output = f"data/douban_{user}_ratings.csv"
        await scrape_douban_async(user, cookie, output, CLILogger())
    asyncio.run(cli_main())

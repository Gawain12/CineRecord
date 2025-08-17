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

def process_movie_data(interest):
    subject = interest.get('subject', {})
    rating = interest.get('rating', {})
    subtitle = subject.get('card_subtitle', '')
    country = parts[1].strip() if len(parts := subtitle.split('/')) > 1 else ''
    actors = ", ".join([a['name'] for a in subject.get('actors', [])[:3]])
    return {'Const': None, 'Your Rating': rating.get('value', 0) if rating else 0,
            'Date Rated': interest.get('create_time', '').split(' ')[0], 'Title': subject.get('title'),
            'Directors': ", ".join([d['name'] for d in subject.get('directors', [])]), 'Actors': actors,
            'Country': country, 'Year': subject.get('year'), 'Genres': ", ".join(subject.get('genres', [])),
            'Douban Rating': subject.get('rating', {}).get('value', 0), 'Num Votes': subject.get('rating', {}).get('count', 0),
            'MyComment': interest.get('comment', ''), 'URL': subject.get('url'), 'Cover URL': subject.get('cover_url'),
            'douban_id': subject.get('id')}

async def fetch_page(session, url, start, logger, size=50, retries=3):
    params = {"type": "movie", "status": "done", "count": size, "start": start, "for_mobile": 1}
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

async def process_interest_with_imdb(session, interest, cache):
    data = process_movie_data(interest)
    douban_id = data.get('douban_id')
    if douban_id in cache: data['Const'] = cache[douban_id]
    else:
        if imdb_id := await fetch_imdb_id_from_web(session, data.get('URL')):
            data['Const'] = imdb_id
            if douban_id: cache[douban_id] = imdb_id
    return data

async def scrape_douban_async(user_id, cookie, output_path, logger):
    headers = {
        'Cookie': cookie, 
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Referer': 'https://m.douban.com/'
    }
    api_url = f"https://m.douban.com/rexxar/api/v2/user/{user_id}/interests"
    async with aiohttp.ClientSession(headers=headers) as session:
        logger.log("验证Cookie...", 'info')
        if not await fetch_imdb_id_from_web(session, "https://m.douban.com/movie/subject/1298697/"):
            logger.log("Cookie无效或已过期。", 'error'); return None
        logger.log("Cookie验证成功。", 'success')
        
        cache = load_imdb_cache()
        logger.log(f"已加载 {len(cache)} 条IMDb缓存。", 'info')
        
        existing_ids = set()
        if os.path.exists(output_path):
            try:
                df = pd.read_csv(output_path, dtype={'douban_id': str}, usecols=['douban_id'])
                existing_ids = set(df['douban_id'].dropna())
                logger.log(f"发现 {len(existing_ids)} 条已有记录，将进行增量更新。", 'info')
            except Exception:
                logger.log(f"无法读取'{output_path}'，将重新创建。", 'info')
                if os.path.exists(output_path): os.remove(output_path)

        first_page = await fetch_page(session, api_url, 0, logger, 1)
        if not first_page or 'total' not in first_page:
            logger.log("无法获取电影总数。", 'error'); return None
        
        total_movies = first_page.get('total', 0); page_size = 50
        total_pages = math.ceil(total_movies / page_size)
        logger.log(f"共发现 {total_movies} 条电影记录。", 'info')

        new_interests = []
        for page_num in range(total_pages):
            logger.progress(page_num, total_pages, f"获取列表 {page_num+1}/{total_pages}")
            page_data = await fetch_page(session, api_url, page_num * page_size, logger, page_size)
            if not page_data or not page_data.get('interests'): break
            
            should_stop = False
            for interest in page_data['interests']:
                if interest.get('subject', {}).get('id') in existing_ids: should_stop = True; break
                new_interests.append(interest)
            if should_stop: break
        logger.progress(total_pages, total_pages, "列表获取完成")

        if not new_interests:
            logger.log("数据已是最新。", 'success')
            try:
                df = pd.read_csv(output_path)
                return clean_df_for_json(df.head())
            except Exception:
                return []

        logger.log(f"发现 {len(new_interests)} 条新记录，开始处理...", 'info')
        new_interests.reverse()
        tasks = [process_interest_with_imdb(session, i, cache) for i in new_interests]
        new_movies = []
        for i, f in enumerate(asyncio.as_completed(tasks)):
            new_movies.append(await f)
            logger.progress(i + 1, len(tasks), f"处理详情 {i+1}/{len(tasks)}")

        logger.log("保存文件中...", 'info')
        save_imdb_cache(cache, logger)
        df_new = pd.DataFrame(new_movies)
        
        df_existing = pd.DataFrame()
        if os.path.exists(output_path) and existing_ids:
            df_existing = pd.read_csv(output_path, dtype=str, encoding='utf-8-sig')
        
        df_final = pd.concat([df_new, df_existing], ignore_index=True)
        cols = ['Const', 'Your Rating', 'Date Rated', 'Title', 'Directors', 'Actors', 'Country', 'Year', 'Genres', 'Douban Rating', 'Num Votes', 'MyComment', 'URL', 'Cover URL', 'douban_id']
        df_final = df_final.reindex(columns=cols)
        df_final.drop_duplicates(subset=['douban_id'], keep='first', inplace=True)
        df_final.sort_values(by='Date Rated', ascending=False, inplace=True)
        df_final.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        logger.log(f"成功！新增 {len(df_new)} 条，总计 {len(df_final)} 条。", 'success')
        return clean_df_for_json(df_final.head())

def run_scraper(user_id, cookie, output_path, socketio):
    logger = SocketLogger(socketio, 'douban')
    return asyncio.run(scrape_douban_async(user_id, cookie, output_path, logger))

if __name__ == '__main__':
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

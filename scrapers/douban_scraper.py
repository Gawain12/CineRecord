import asyncio
import os
import random
import re
import time
import urllib.parse
import sys
import csv
from typing import Union, Dict
import math

# Add parent directory to path to allow importing 'config'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import aiohttp
import pandas as pd
from tqdm.asyncio import tqdm

# ==============================================================================
# Part 1: Web Parsing Logic
# ==============================================================================

async def fetch_imdb_id_from_web(session: aiohttp.ClientSession, douban_url: str, retries=3) -> Union[str, None]:
    if not douban_url: return None
    if "1298697" not in douban_url: print(f"  - [Web Fetch] Cache miss, fetching IMDB ID from: {douban_url}")
    for attempt in range(retries):
        await asyncio.sleep(random.uniform(0.5, 1.5))
        try:
            async with session.get(douban_url, verify_ssl=False, timeout=30) as response:
                if response.status == 404: return None
                response.raise_for_status()
                html_content = await response.text()
                imdb_match = re.search(r'IMDb:</span>\s*(tt\d+)', html_content)
                return imdb_match.group(1) if imdb_match else None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if "1298697" not in douban_url: print(f"❌ Web fetch failed (URL={douban_url}, attempt {attempt + 1}/{retries}): {e}")
            await asyncio.sleep(3)
    return None

# ==============================================================================
# Part 2: Main Scraper Application
# ==============================================================================

from config.config import DOUBAN_CONFIG

DOUBAN_USER_ID = DOUBAN_CONFIG.get('user')
DOUBAN_HEADERS = DOUBAN_CONFIG.get('headers', {})

if not DOUBAN_USER_ID or not DOUBAN_HEADERS.get('Cookie'):
    raise SystemExit("❌ Configuration Error: Please provide 'user' and 'Cookie' in `DOUBAN_CONFIG` in `config.py`.")

print("✅ 豆瓣认证信息已从 `config.py` 加载。")

LIST_API_URL = f"https://m.douban.com/rexxar/api/v2/user/{DOUBAN_USER_ID}/interests"

async def validate_cookie(session):
    print("\n🔍 正在验证豆瓣 Cookie...")
    test_douban_url = "https://m.douban.com/movie/subject/1298697/"
    validation_id = await fetch_imdb_id_from_web(session, test_douban_url)
    if validation_id:
        print(f"✅ 豆瓣 Cookie 有效 (获取到测试ID: {validation_id})。")
        return True
    else:
        print("❌ Cookie 无效或已过期。无法从测试页面获取 IMDb ID。")
        return False

IMDB_CACHE_FILE = "data/db_imdb.csv"

def load_imdb_cache():
    if not os.path.exists(IMDB_CACHE_FILE): return {}
    try:
        df = pd.read_csv(IMDB_CACHE_FILE, dtype=str)
        if 'douban_id' not in df.columns and 'id' in df.columns:
            df.rename(columns={'id': 'douban_id'}, inplace=True)
        if df.empty or 'douban_id' not in df.columns: return {}
        df.drop_duplicates(subset=['douban_id'], keep='last', inplace=True)
        df.dropna(subset=['douban_id', 'imdb'], inplace=True)
        return pd.Series(df.imdb.values, index=df.douban_id).to_dict()
    except Exception as e:
        print(f"⚠️ 缓存文件 '{IMDB_CACHE_FILE}' 已损坏。将重新开始。原因: {e}")
        return {}

def save_imdb_cache(imdb_cache: dict):
    if not imdb_cache: return
    print(f"\n✍️  正在保存 {len(imdb_cache)} 条记录到 IMDb 缓存文件...")
    df = pd.DataFrame(list(imdb_cache.items()), columns=['douban_id', 'imdb'])
    df.drop_duplicates(subset=['douban_id'], keep='last', inplace=True)
    df.to_csv(IMDB_CACHE_FILE, index=False, encoding='utf-8')

# --- MODIFICATION START: Simplified data processing function ---
def process_movie_data(interest_data):
    subject = interest_data.get('subject', {})
    my_rating = interest_data.get('rating', {})
    
    country, actors_str = '', ''

    # 1. Country from card_subtitle
    card_subtitle = subject.get('card_subtitle', '')
    if card_subtitle:
        parts = card_subtitle.split('/')
        if len(parts) > 1:
            country = parts[1].strip()

    # 2. Actors (first 3)
    actors = subject.get('actors', [])
    if actors:
        actors_str = ", ".join([a['name'] for a in actors[:3]])

    return {
        'Const': None,
        'Your Rating': my_rating.get('value', 0) if my_rating else 0,
        'Date Rated': interest_data.get('create_time', '').split(' ')[0],
        'Title': subject.get('title'),
        'Directors': ", ".join([d['name'] for d in subject.get('directors', [])]),
        'Actors': actors_str,
        'Country': country,
        'Year': subject.get('year'),
        'Genres': ", ".join(subject.get('genres', [])),
        'Douban Rating': subject.get('rating', {}).get('value', 0),
        'Num Votes': subject.get('rating', {}).get('count', 0),
        'MyComment': interest_data.get('comment', ''),
        'URL': subject.get('url'),
        'Cover URL': subject.get('cover_url'),
        'douban_id': subject.get('id')
    }
# --- MODIFICATION END ---

async def fetch_movie_list_page(session, start_index, page_size=50, retries=3):
    params = {"type": "movie", "status": "done", "count": page_size, "start": start_index, "for_mobile": 1}
    for attempt in range(retries):
        await asyncio.sleep(random.uniform(1.0, 2.0))
        try:
            async with session.get(LIST_API_URL, params=params, verify_ssl=False, timeout=30) as r:
                r.raise_for_status()
                return await r.json()
        except Exception as e:
            print(f"❌ List request failed (start={start_index}, attempt {attempt + 1}): {e}")
            if attempt + 1 == retries: return None
    return None

async def process_interest(session, interest, imdb_cache):
    processed_data = process_movie_data(interest)
    douban_id = processed_data.get('douban_id')
    if douban_id in imdb_cache:
        processed_data['Const'] = imdb_cache[douban_id]
    else:
        imdb_id = await fetch_imdb_id_from_web(session, processed_data.get('URL'))
        if imdb_id:
            processed_data['Const'] = imdb_id
            if douban_id: imdb_cache[douban_id] = imdb_id
    return processed_data

async def main():
    start_time = time.time()
    print(f"🎬 开始为用户 {DOUBAN_USER_ID} 抓取看过的电影...")
    output_filename = f"data/douban_{DOUBAN_USER_ID}_ratings.csv"
    imdb_cache = load_imdb_cache()
    print(f"✅ 已从 '{IMDB_CACHE_FILE}' 加载 {len(imdb_cache)} 条缓存记录。")

    existing_ids = set()
    if os.path.exists(output_filename):
        try:
            df_existing = pd.read_csv(output_filename, dtype={'douban_id': str}, usecols=['douban_id'])
            existing_ids = set(df_existing['douban_id'].dropna())
            print(f"✅ 已从 '{output_filename}' 加载 {len(existing_ids)} 条现有记录。将执行增量更新。")
        except Exception as e:
            print(f"⚠️ '{output_filename}' 不兼容或为空，将被重新创建。原因: {e}")
            if os.path.exists(output_filename): os.remove(output_filename)

    async with aiohttp.ClientSession(headers=DOUBAN_HEADERS) as session:
        if not await validate_cookie(session): return

        print("\n🚀 步骤 1/2: 正在获取最新的电影记录...")
        page_size = 50
        first_page = await fetch_movie_list_page(session, 0, 1)
        if not first_page or 'total' not in first_page:
            print("❌ 无法获取电影总数。请检查您的网络或 Cookie。")
            return
        total_movies = first_page.get('total', 0)
        total_pages = math.ceil(total_movies / page_size)
        print(f"✅ 共发现 {total_movies} 条电影记录，分布在 {total_pages} 页中。")

        new_interests = []
        should_stop_fetching = False
        with tqdm(total=total_pages, desc="增量获取页面", unit="页") as pbar:
            for page_num in range(total_pages):
                page_data = await fetch_movie_list_page(session, page_num * page_size, page_size)
                pbar.update(1)
                if not page_data or not page_data.get('interests'):
                    pbar.set_description("已到达末尾")
                    break
                for interest in page_data['interests']:
                    if interest.get('subject', {}).get('id') in existing_ids:
                        pbar.set_description(f"发现重复记录，已在第 {page_num + 1} 页停止")
                        should_stop_fetching = True
                        break
                    else:
                        new_interests.append(interest)
                if should_stop_fetching:
                    break
        
        if not new_interests:
            print("\n✅ 数据已是最新，无需更新。")
        else:
            new_interests.reverse() # Keep correct chronological order
            print(f"\n✅ 发现 {len(new_interests)} 条新记录。")
            print("\n🚀 步骤 2/2: 正在并发处理电影数据...")
            tasks = [process_interest(session, i, imdb_cache) for i in new_interests]
            new_movies_data = []
            for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="处理电影数据", unit="部"):
                new_movies_data.append(await f)
            
            save_imdb_cache(imdb_cache)
            df_new = pd.DataFrame(new_movies_data)
            
            df_existing_full = pd.DataFrame()
            if os.path.exists(output_filename) and existing_ids:
                df_existing_full = pd.read_csv(output_filename, dtype=str, encoding='utf-8-sig')
            
            df_final = pd.concat([df_new, df_existing_full], ignore_index=True)

            print(f"\n💾 正在保存 {len(df_final)} 条记录到 {output_filename}...")
            
            # --- MODIFICATION: Simplified final columns list ---
            final_columns = [
                'Const', 'Your Rating', 'Date Rated', 'Title', 'Directors', 'Actors', 'Country', 
                'Year', 'Genres', 'Douban Rating', 'Num Votes', 'MyComment', 
                'URL', 'Cover URL', 'douban_id'
            ]
            
            df_final = df_final.reindex(columns=final_columns)
            df_final.drop_duplicates(subset=['douban_id'], keep='first', inplace=True)
            df_final.sort_values(by='Date Rated', ascending=False, inplace=True)
            df_final.to_csv(output_filename, index=False, encoding='utf-8-sig')
            
            print(f"新增 {len(df_new)} 条新记录。")
            print(f"总记录数: {len(df_final)}。")

    print(f"\n🎉 任务完成！总耗时: {time.time() - start_time:.2f} 秒")

if __name__ == '__main__':
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 脚本被用户终止。")
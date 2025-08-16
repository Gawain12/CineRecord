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

print("✅ Douban authentication info loaded from `config.py`.")

LIST_API_URL = f"https://m.douban.com/rexxar/api/v2/user/{DOUBAN_USER_ID}/interests"

async def validate_cookie(session):
    print("\n🔍 Validating Douban Cookie...")
    test_douban_url = "https://m.douban.com/movie/subject/1298697/"
    validation_id = await fetch_imdb_id_from_web(session, test_douban_url)
    if validation_id:
        print(f"✅ Douban Cookie is valid (fetched test ID: {validation_id}).")
        return True
    else:
        print("❌ Cookie is invalid or has expired. Could not fetch IMDb ID from the test page.")
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
        print(f"⚠️ Cache file '{IMDB_CACHE_FILE}' corrupted. Starting fresh. Reason: {e}")
        return {}

def save_imdb_cache(imdb_cache: dict):
    if not imdb_cache: return
    print(f"\n✍️  Saving {len(imdb_cache)} entries to the IMDB cache file...")
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
    print(f"🎬 Starting to scrape watched movies for user {DOUBAN_USER_ID}...")
    output_filename = f"data/douban_{DOUBAN_USER_ID}_ratings.csv"
    imdb_cache = load_imdb_cache()
    print(f"✅ Loaded {len(imdb_cache)} cached records from '{IMDB_CACHE_FILE}'.")

    existing_ids = set()
    if os.path.exists(output_filename):
        try:
            df_existing = pd.read_csv(output_filename, dtype={'douban_id': str}, usecols=['douban_id'])
            existing_ids = set(df_existing['douban_id'].dropna())
            print(f"✅ Loaded {len(existing_ids)} existing records from '{output_filename}'. Will perform an incremental update.")
        except Exception as e:
            print(f"⚠️ '{output_filename}' is incompatible or empty, will be recreated. Reason: {e}")
            if os.path.exists(output_filename): os.remove(output_filename)

    async with aiohttp.ClientSession(headers=DOUBAN_HEADERS) as session:
        if not await validate_cookie(session): return

        print("\n🚀 Step 1/2: Fetching the latest movie records...")
        page_size = 50
        first_page = await fetch_movie_list_page(session, 0, 1)
        if not first_page or 'total' not in first_page:
            print("❌ Could not retrieve the total number of movies. Please check your network or Cookie.")
            return
        total_movies = first_page.get('total', 0)
        total_pages = math.ceil(total_movies / page_size)
        print(f"✅ Found a total of {total_movies} movie records, spanning {total_pages} pages.")

        new_interests = []
        should_stop_fetching = False
        with tqdm(total=total_pages, desc="Incrementally fetching pages", unit="page") as pbar:
            for page_num in range(total_pages):
                page_data = await fetch_movie_list_page(session, page_num * page_size, page_size)
                pbar.update(1)
                if not page_data or not page_data.get('interests'):
                    pbar.set_description("Reached the end")
                    break
                for interest in page_data['interests']:
                    if interest.get('subject', {}).get('id') in existing_ids:
                        pbar.set_description(f"Duplicate record found, stopping at page {page_num + 1}")
                        should_stop_fetching = True
                        break
                    else:
                        new_interests.append(interest)
                if should_stop_fetching:
                    break
        
        if not new_interests:
            print("\n✅ Data is already up-to-date. No update needed.")
        else:
            new_interests.reverse() # Keep correct chronological order
            print(f"\n✅ Found {len(new_interests)} new records.")
            print("\n🚀 Step 2/2: Concurrently processing movie data...")
            tasks = [process_interest(session, i, imdb_cache) for i in new_interests]
            new_movies_data = []
            for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Processing movie data", unit=" movie"):
                new_movies_data.append(await f)
            
            save_imdb_cache(imdb_cache)
            df_new = pd.DataFrame(new_movies_data)
            
            df_existing_full = pd.DataFrame()
            if os.path.exists(output_filename) and existing_ids:
                df_existing_full = pd.read_csv(output_filename, dtype=str, encoding='utf-8-sig')
            
            df_final = pd.concat([df_new, df_existing_full], ignore_index=True)

            print(f"\n💾 Saving {len(df_final)} records to {output_filename}...")
            
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
            
            print(f"Added {len(df_new)} new records.")
            print(f"Total records: {len(df_final)}.")

    print(f"\n🎉 Task complete! Total time: {time.time() - start_time:.2f} seconds")

if __name__ == '__main__':
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Script terminated by user.")
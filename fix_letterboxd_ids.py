
import pandas as pd
import requests
import re
import concurrent.futures
import time
from datetime import datetime
import os

# 配置
DATA_FILE = '/Users/gawaintan/workSpace/Python/CineRecord/data/letterboxd_diary.csv'
MAX_WORKERS = 5  # 开源脚本默认就是5

# 照搬开源项目的headers和逻辑
def get_imdb_id(letterboxd_uri):
    if not isinstance(letterboxd_uri, str) or not letterboxd_uri:
        return None
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    }

    try:
        # 纯粹的GET请求，让requests自动处理重定向
        resp = requests.get(letterboxd_uri, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            print(f"❌ Status {resp.status_code} for {letterboxd_uri}")
            return None

        # 1. 优先使用开源项目的正则 (匹配 maindetails)
        re_match = re.findall(r'href=".+title/(tt\d+)/maindetails"', resp.text)
        if re_match:
            return re_match[0]
            
        # 2. 备选正则 (防止页面结构微调)
        re_match_2 = re.findall(r'imdb\.com/title/(tt\d+)', resp.text)
        if re_match_2:
            return re_match_2[0]
            
        return None
        
    except Exception as e:
        print(f"❌ Error fetching {letterboxd_uri}: {e}")
        return None

def process_file():
    if not os.path.exists(DATA_FILE):
        print(f"File not found: {DATA_FILE}")
        return

    print(f"📖 Reading {DATA_FILE}...")
    df = pd.read_csv(DATA_FILE)
    
    # 确保列存在
    if 'IMDb ID' not in df.columns:
        df['IMDb ID'] = None
    
    # 找出需要处理的行
    # 这里我们只处理 URL 存在，但 IMDb ID 缺失的
    mask = df['URL'].notna() & df['IMDb ID'].isna()
    missing_indices = df[mask].index.tolist()
    
    total = len(missing_indices)
    print(f"🔍 Found {total} movies without IMDb ID.")
    
    if total == 0:
        print("🎉 No missing IDs! You are good to go.")
        return

    # 初始化TMDB Client
    try:
        from scrapers.tmdb_client import TMDBClient
        tmdb_client = TMDBClient()
        print("✅ TMDB Client initialized for fallback.")
    except Exception as e:
        print(f"⚠️ TMDB Client init failed: {e}")
        tmdb_client = None

    processed_count = 0
    success_count = 0
    
    # 直接遍历，不使用爬虫线程池
    for idx in missing_indices:
        processed_count += 1
        
        uri = df.at[idx, 'URL']
        title = df.at[idx, 'Title'] if 'Title' in df.columns else None
        year = df.at[idx, 'Year'] if 'Year' in df.columns else None
        
        imdb_id = None
        
        # 直接使用TMDB搜索
        if tmdb_client and title:
            try:
                # 1. 搜电影
                y = int(year) if pd.notna(year) else None
                results = tmdb_client.search_movie(str(title), y)
                if results:
                    # (现有电影匹配逻辑)
                    best_match = results[0]
                    if y:
                        for res in results:
                            res_date = res.get('release_date', '')
                            if res_date and str(y) in res_date:
                                best_match = res
                                break
                    tmdb_id_val = best_match['id']
                    ext_ids = tmdb_client.get_movie_external_ids(tmdb_id_val)
                    if ext_ids and ext_ids.get('imdb_id'):
                        imdb_id = ext_ids.get('imdb_id')
                        print(f"✅ [{success_count+1}/{total}] TMDB Movie Found: {title} -> {imdb_id}", flush=True)

                # 2. 如果电影没搜到，搜TV (针对 Friends, Agents of SHIELD 等)
                if not imdb_id:
                     # print(f"📺 Trying TV Search for: {title}", flush=True)
                     params = {'query': str(title)}
                     if y: params['first_air_date_year'] = y
                     tv_results = tmdb_client._get("/search/tv", params)
                     if tv_results and tv_results.get('results'):
                         best_tv = tv_results['results'][0]
                         tv_id = best_tv['id']
                         tv_ext = tmdb_client._get(f"/tv/{tv_id}/external_ids")
                         if tv_ext and tv_ext.get('imdb_id'):
                             imdb_id = tv_ext.get('imdb_id')
                             print(f"✅ [{success_count+1}/{total}] TMDB TV Found: {title} -> {imdb_id}", flush=True)

            except Exception as e_tmdb:
                print(f"❌ TMDB Search Error: {e_tmdb}", flush=True)

        if imdb_id:
            df.at[idx, 'IMDb ID'] = imdb_id
            success_count += 1
        else:
            print(f"⚠️ [{success_count}/{processed_count}] Failed to find ID for: {title}")
            
        # 每10条保存一次
        if processed_count % 10 == 0:
            df.to_csv(DATA_FILE, index=False)

    # 最终保存
    df.to_csv(DATA_FILE, index=False)
    print(f"\n🎉 Done! Total processed: {total}, Success: {success_count}")
    print(f"💾 File saved to {DATA_FILE}")

if __name__ == "__main__":
    process_file()

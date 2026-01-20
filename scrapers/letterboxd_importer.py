
import pandas as pd
import requests
from bs4 import BeautifulSoup
import concurrent.futures
import re
import os
import time
from urllib.parse import urlparse

class LetterboxdImporter:
    def __init__(self, max_workers=10):
        self.max_workers = max_workers
        self.session = requests.Session()
        # 严格复刻 JS 脚本的 Headers
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1"
        }
    
    def get_ids(self, film_url):
        if not film_url or 'boxd.it' not in film_url and 'letterboxd.com' not in film_url:
            return {}, None

        try:
            # 自动处理重定向 (requests 默认支持)
            resp = self.session.get(film_url, headers=self.headers, timeout=10)
            if resp.status_code != 200:
                print(f"❌ Status {resp.status_code} for {film_url}")
                return {}, None
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 使用 JS 脚本同款强大的 CSS Selector (比正则稳)
            tmdb_link = soup.select_one('.micro-button[data-track-action="TMDB"]')
            imdb_link = soup.select_one('.micro-button[data-track-action="IMDb"]')
            
            ids = {}
            
            if tmdb_link and tmdb_link.has_attr('href'):
                href = tmdb_link['href']
                match = re.search(r'/(movie|tv)/(\d+)/', href)
                if match:
                    ids['TmdbIdType'] = match.group(1) # movie or tv
                    ids['TmdbId'] = match.group(2)

            if imdb_link and imdb_link.has_attr('href'):
                href = imdb_link['href']
                match = re.search(r'/title/(tt\d+)/?', href)
                if match:
                    ids['ImdbId'] = match.group(1)
            
            return ids, None # Success
            
        except Exception as e:
            return {}, str(e)

    def process_csv(self, file_path, save_path=None):
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return
            
        print(f"🚀 Integrated Python Scraper: Processing {file_path} with {self.max_workers} threads...")
        df = pd.read_csv(file_path)
        
        # 兼容 Title/Name 列名
        cols = df.columns
        url_col = 'URL' if 'URL' in cols else ('Letterboxd URI' if 'Letterboxd URI' in cols else None)
        name_col = 'Name' if 'Name' in cols else ('Title' if 'Title' in cols else None)
        
        if not url_col:
            print("No URL column found.")
            return

        # 找出需要处理的行 (IMDb ID 为空)
        if 'IMDb ID' not in df.columns:
            df['IMDb ID'] = None
            
        missing_mask = df[url_col].notna() & df['IMDb ID'].isna()
        indices = df[indices].index.tolist() if 'indices' in locals() else df[missing_mask].index.tolist()
        
        total = len(indices)
        if total == 0:
            print("All good! No missing IDs.")
            return

        print(f"Found {total} missing items.")
        
        completed = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_idx = {
                executor.submit(self.get_ids, df.at[idx, url_col]): idx 
                for idx in indices
            }
            
            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                completed += 1
                name = df.at[idx, name_col] if name_col else f"Row {idx}"
                
                try:
                    ids, error = future.result()
                    if ids:
                        if 'ImdbId' in ids:
                            df.at[idx, 'IMDb ID'] = ids['ImdbId']
                        if 'TmdbId' in ids:
                            df.at[idx, 'TMDB ID'] = ids['TmdbId']
                        # Add type based on TmdbIdType (movie or tv)
                        if 'TmdbIdType' in ids:
                            df.at[idx, 'type'] = ids['TmdbIdType']
                        else:
                            df.at[idx, 'type'] = 'movie'  # Default to movie
                        # console-like log
                        # print(f"[{completed}/{total}] {name} -> IMDb: {ids.get('ImdbId')}, TMDB: {ids.get('TmdbId')}")
                    elif error:
                        # print(f"[{completed}/{total}] ⚠️ {name} Failed: {error}")
                        pass
                except Exception as e:
                     print(f"[{completed}/{total}] ❌ Error: {e}")
                
                # 进度条效果
                if completed % 10 == 0:
                    print(f"Processing: {completed}/{total}...", end='\r')
                    
        print("\nDone!")
        if save_path:
            df.to_csv(save_path, index=False)
            print(f"Saved to {save_path}")
        else:
            df.to_csv(file_path, index=False)
            print(f"Saved to {file_path}")

# 单独运行测试
if __name__ == "__main__":
    importer = LetterboxdImporter()
    # 默认尝试 data/letterboxd_diary.csv
    # target = 'data/letterboxd_diary.csv'
    # if os.path.exists(target):
    #     importer.process_csv(target)

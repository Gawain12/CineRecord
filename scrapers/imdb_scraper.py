import requests
import csv
import time
import random
import json
import os
import re
import sys
from datetime import datetime
import pandas as pd
from tqdm import tqdm
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.config import IMDB_CONFIG, DOUBAN_CONFIG

class IMDbRatingsScraper:
    """
    Fetches IMDb user ratings incrementally and enriches them with Douban IDs.
    """
    def __init__(self):
        # Load Config
        self.user_id = IMDB_CONFIG.get('user_id')
        self.imdb_headers = IMDB_CONFIG.get('headers', {})
        self.douban_headers = DOUBAN_CONFIG.get('headers', {})

        # Set default User-Agent if not provided to avoid 403 errors
        default_user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
        if 'User-Agent' not in self.imdb_headers:
            self.imdb_headers['User-Agent'] = default_user_agent
        if 'User-Agent' not in self.douban_headers:
            self.douban_headers['User-Agent'] = default_user_agent

        if not self.user_id or not self.imdb_headers.get('Cookie') or not self.douban_headers.get('Cookie'):
            raise SystemExit("❌ Config Error: Ensure user_id and cookies are set for both IMDb and Douban.")

        print("✅ 成功加载 IMDb 和豆瓣的配置。")

        # Define base paths
        self.project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

        # Filenames and URLs
        self.output_filename = os.path.join(self.project_root, "data", f"imdb_{self.user_id}_ratings.csv")
        self.api_base_url = "https://api.graphql.imdb.com/"
        self.web_base_url = f"https://www.imdb.com/user/{self.user_id}/ratings"
        self.douban_search_url = "https://m.douban.com/rexxar/api/v2/search"

        # Session
        self.session = requests.Session()

        # Caching
        self.douban_id_cache_file = os.path.join(self.project_root, "data", "db_imdb.csv")
        self.douban_id_cache = self._load_douban_id_cache()
        self.newly_found_mappings = {}
        print(f"✅ 已从中央缓存 ('{self.douban_id_cache_file}') 加载 {len(self.douban_id_cache)} 条 IMDb-豆瓣 ID 映射。")
        print(f"ℹ️  输出的 CSV 文件将保存至: {self.output_filename}")

        # Load existing ratings for incremental check
        self.existing_imdb_ids = self._load_existing_ratings()
        print(f"✅ 在 '{self.output_filename}' 中发现 {len(self.existing_imdb_ids)} 条现有电影评分。")


    def _load_existing_ratings(self):
        if not os.path.exists(self.output_filename):
            return set()
        try:
            df = pd.read_csv(self.output_filename, usecols=['Const'], dtype={'Const': str})
            return set(df['Const'].dropna())
        except (pd.errors.ParserError, pd.errors.EmptyDataError, KeyError, FileNotFoundError):
            return set()

    def _load_douban_id_cache(self):
        if not os.path.exists(self.douban_id_cache_file):
            return {}
        try:
            df = pd.read_csv(self.douban_id_cache_file, dtype=str)
            # Standardize column name for douban id (could be 'id' or 'douban_id')
            if 'douban_id' not in df.columns and 'id' in df.columns:
                df.rename(columns={'id': 'douban_id'}, inplace=True)

            # Ensure required columns exist before proceeding
            if 'douban_id' not in df.columns or 'imdb' not in df.columns:
                print(f"⚠️ 警告: 缓存文件 '{self.douban_id_cache_file}' 缺少 'douban_id' 或 'imdb' 列。")
                return {}
            
            df.dropna(subset=['douban_id', 'imdb'], inplace=True)
            # Create a mapping from imdb_id -> douban_id for direct lookup
            return pd.Series(df.douban_id.values, index=df.imdb).to_dict()
        except (pd.errors.ParserError, pd.errors.EmptyDataError) as e:
            print(f"⚠️ 警告: 缓存文件 '{self.douban_id_cache_file}' 可能已损坏，将重新开始。原因: {e}")
            return {}

    def _save_newly_found_mappings(self):
        if not self.newly_found_mappings:
            return

        print(f"\\n✍️  正在将 {len(self.newly_found_mappings)} 条新发现的映射关系更新到中央缓存文件: {self.douban_id_cache_file}")

        # Convert the newly found mappings (imdb -> douban) to a DataFrame
        new_mappings_df = pd.DataFrame(list(self.newly_found_mappings.items()), columns=['imdb', 'douban_id'])

        # Read the existing cache file
        try:
            if os.path.exists(self.douban_id_cache_file):
                existing_df = pd.read_csv(self.douban_id_cache_file, dtype=str)
                # Standardize column names
                if 'douban_id' not in existing_df.columns and 'id' in existing_df.columns:
                    existing_df.rename(columns={'id': 'douban_id'}, inplace=True)
            else:
                existing_df = pd.DataFrame(columns=['douban_id', 'imdb'])
        except pd.errors.EmptyDataError:
            existing_df = pd.DataFrame(columns=['douban_id', 'imdb'])

        # Combine old and new mappings
        combined_df = pd.concat([existing_df, new_mappings_df], ignore_index=True)
        
        # Remove duplicates, keeping the most recent entry for any given ID
        combined_df.drop_duplicates(subset=['imdb'], keep='last', inplace=True)
        combined_df.drop_duplicates(subset=['douban_id'], keep='last', inplace=True)

        # Save the updated cache
        combined_df.to_csv(self.douban_id_cache_file, index=False, encoding='utf-8')

    def _fetch_api_page(self, cursor):
        payload = {"operationName": "userRatings", "variables": {"first": 250, "after": cursor},"extensions": {"persistedQuery": {"version": 1, "sha256Hash": "ebf2387fd2ba45d62fc54ed2ffe3940086af52e700a1b3929a099d5fce23330a"}}}
        try:
            response = self.session.post(self.api_base_url, json=payload, headers=self.imdb_headers, timeout=30)
            response.raise_for_status(); return response.json()
        except requests.RequestException as e: print(f"❌ API request failed: {e}"); return None

    def _fetch_web_page(self, page_num):
        url = f"{self.web_base_url}?sort=date_added,desc&page={page_num}"
        try:
            response = self.session.get(url, headers=self.imdb_headers, timeout=30)
            response.raise_for_status(); return response.text
        except requests.RequestException as e: print(f"❌ Web page request failed: {e}"); return None

    def _fetch_all_personal_ratings(self):
        print("\n🚀 正在从 API 获取所有个人评分...")
        personal_data_map = {}
        cursor = None
        with tqdm(desc="获取 API 页面", unit="页") as pbar:
            while True:
                api_data = self._fetch_api_page(cursor)
                if not api_data or api_data.get("errors"): break
                ratings_data = api_data.get('data', {}).get('userRatings', {})
                if not ratings_data or not ratings_data.get('edges'): break
                for edge in ratings_data['edges']:
                    node = edge.get('node', {}); imdb_id = node.get('title', {}).get('id')
                    if not imdb_id: continue
                    ur = node.get('userRating', {})
                    rating_date_raw = ur.get('date')
                    personal_data_map[imdb_id] = {
                        'my_rating': ur.get('value'),
                        'rating_date': datetime.fromisoformat(rating_date_raw.replace('Z', '+00:00')).strftime('%Y-%m-%d') if rating_date_raw else None
                    }
                page_info = ratings_data.get('pageInfo', {})
                if page_info.get('hasNextPage'):
                    cursor = page_info.get('endCursor'); pbar.update(1); pbar.set_postfix(total_ratings=len(personal_data_map))
                else: break
        print(f"✅ API 获取完成。共找到 {len(personal_data_map)} 条个人评分。")
        return personal_data_map

    def _fetch_douban_id(self, imdb_id):
        # The cache is now a direct mapping of {imdb_id: douban_id}
        if imdb_id in self.douban_id_cache:
            return self.douban_id_cache[imdb_id]

        if imdb_id in self.newly_found_mappings: 
            return self.newly_found_mappings[imdb_id]

        time.sleep(random.uniform(0.5, 2.0))
        params = {'q': imdb_id, 'type': 'movie', 'count': 1}
        try:
            response = self.session.get(self.douban_search_url, params=params, headers=self.douban_headers, timeout=20, verify=False)
            response.raise_for_status(); data = response.json()
            subjects = data.get('subjects')
            if subjects and isinstance(subjects, list) and subjects:
                douban_id = subjects[0].get('target_id')
                if douban_id:
                    print(f"  - [API] 发现新映射: IMDb {imdb_id} -> 豆瓣 {douban_id}")
                    self.newly_found_mappings[imdb_id] = douban_id
                    # Also update the main cache in memory immediately
                    self.douban_id_cache[imdb_id] = douban_id
                    return douban_id
            return None
        except requests.RequestException as e: 
            print(f"❌ Douban ID fetch for {imdb_id} failed: {e}")
            return None

    def _parse_movie_details_from_node(self, node):
        details = {}; title_info = node.get('title', {}) or {}
        details['imdb_id'] = title_info.get('id');
        if not details['imdb_id']: return None
        details['title'] = (title_info.get('titleText', {}) or {}).get('text'); details['year'] = (title_info.get('releaseYear', {}) or {}).get('year')
        details['title_type'] = (title_info.get('titleType', {}) or {}).get('text')
        release_date_obj = title_info.get('releaseDate', {}) or {}
        if all(k in release_date_obj for k in ['year', 'month', 'day']):
            try: details['release_date'] = f"{release_date_obj['year']}-{str(release_date_obj['month']).zfill(2)}-{str(release_date_obj['day']).zfill(2)}"
            except TypeError: details['release_date'] = None
        else: details['release_date'] = None
        ratings_summary = title_info.get('ratingsSummary', {}) or {}; details['imdb_rating'] = ratings_summary.get('aggregateRating'); details['imdb_votes'] = ratings_summary.get('voteCount')
        runtime = title_info.get('runtime', {}) or {}; details['runtime_minutes'] = (runtime.get('seconds', 0) or 0) // 60
        details['genres'] = ', '.join([g.get('genre', {}).get('text', '') for g in (title_info.get('titleGenres', {}) or {}).get('genres', []) or []])
        credits_list = title_info.get('principalCredits', []) or []; directors = []
        for credit_category in credits_list:
            if (credit_category.get('category', {}) or {}).get('id') == 'director':
                directors.extend([(c.get('name', {}) or {}).get('nameText', {}).get('text', '') for c in credit_category.get('credits', []) or []])
        details['director'] = ', '.join(directors)
        return details

    def scrape_all_ratings(self):
        personal_data_map = self._fetch_all_personal_ratings()
        newly_scraped_movies = []
        page_num = 1
        stop_scraping = False
        seen_on_previous_pages = set()
        print("\n🚀 正在从网页增量获取所有公开电影详情...")
        with tqdm(desc="获取网页", unit="页") as pbar:
            while not stop_scraping:
                html_content = self._fetch_web_page(page_num)
                if not html_content: break
                match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', html_content, re.DOTALL)
                if not match: break
                
                data = json.loads(match.group(1)); search_results = data['props']['pageProps']['mainColumnData']['advancedTitleSearch']
                movies_on_page = [self._parse_movie_details_from_node(edge.get('node', {})) for edge in search_results.get('edges', [])]
                movies_on_page = [m for m in movies_on_page if m]

                # --- Loop Termination Check ---
                # If all movies on this page have been seen before, it's a duplicate page.
                current_page_ids = {movie['imdb_id'] for movie in movies_on_page if movie.get('imdb_id')}
                if current_page_ids and current_page_ids.issubset(seen_on_previous_pages):
                    print(f"\n[第 {page_num} 页] 检测到重复页面。所有电影都已见过。正在停止。")
                    break
                seen_on_previous_pages.update(current_page_ids)
                # --------------------------------

                if not movies_on_page: break

                print(f"\n[第 {page_num} 页] 找到 {len(movies_on_page)} 部电影。正在处理...")
                for movie in tqdm(movies_on_page, desc=f"第 {page_num} 页", leave=False):
                    if movie['imdb_id'] in self.existing_imdb_ids:
                        print(f"\n✅ 发现已存在的电影 ({movie['imdb_id']}: {movie['title']})。正在停止增量抓取。")
                        stop_scraping = True; break
                    
                    movie['douban_id'] = self._fetch_douban_id(movie['imdb_id'])
                    if movie['imdb_id'] in personal_data_map: movie.update(personal_data_map[movie['imdb_id']])
                    newly_scraped_movies.append(movie)

                if not stop_scraping: page_num += 1; pbar.update(1); pbar.set_postfix(new_movies=len(newly_scraped_movies))

        return newly_scraped_movies

def main():
    # Unset proxy environment variables to prevent connection errors
    os.environ.pop('HTTP_PROXY', None)
    os.environ.pop('HTTPS_PROXY', None)

    start_time = time.time()
    print("="*60 + "\n" + " IMDb 增量评分抓取工具 ".center(60) + "\n" + "="*60)
    try:
        scraper = IMDbRatingsScraper()
        newly_scraped_movies = scraper.scrape_all_ratings()
        scraper._save_newly_found_mappings()

        if not newly_scraped_movies:
            print("\n✅ 未发现新电影。您的本地文件已是最新。")
            return

        print(f"\n✅ 抓取到 {len(newly_scraped_movies)} 部新电影。")
        
        export_fieldnames = ['Const', 'Your Rating', 'Date Rated', 'Title', 'URL', 'Title Type', 'IMDb Rating', 'Runtime (mins)', 'Year', 'Genres', 'Num Votes', 'Release Date', 'Directors', 'douban_id']
        export_data = []
        for movie in newly_scraped_movies:
            export_data.append({
                'Const': movie.get('imdb_id'), 'Your Rating': movie.get('my_rating'), 'Date Rated': movie.get('rating_date'),
                'Title': movie.get('title'), 'URL': f"https://www.imdb.com/title/{movie.get('imdb_id')}/",
                'Title Type': movie.get('title_type'), 'IMDb Rating': movie.get('imdb_rating'), 'Runtime (mins)': movie.get('runtime_minutes'),
                'Year': movie.get('year'), 'Genres': movie.get('genres'), 'Num Votes': movie.get('imdb_votes'),
                'Release Date': movie.get('release_date'), 'Directors': movie.get('director'),
                'douban_id': movie.get('douban_id')
            })

        df_new = pd.DataFrame(export_data)
        
        if os.path.exists(scraper.output_filename):
            print(f"📖 正在从 {scraper.output_filename} 读取现有数据以进行合并...")
            df_existing = pd.read_csv(scraper.output_filename)
            df_combined = pd.concat([df_new, df_existing], ignore_index=True)
        else:
            df_combined = df_new

        df_final = df_combined.drop_duplicates(subset=['Const'], keep='first')
        df_final.sort_values(by='Date Rated', ascending=False, inplace=True)
        df_final.to_csv(scraper.output_filename, index=False, columns=export_fieldnames, encoding='utf-8-sig')

        print(f"🎉 成功！共保存 {len(df_final)} 条记录到: {scraper.output_filename}")

    except SystemExit as e:
        print(f"\n脚本终止: {e}")
    except Exception as e:
        import traceback; print(f"\n发生意外错误: {e}"); traceback.print_exc()
    finally:
        duration = time.time() - start_time
        if duration > 1.0:
            print("\n" + "="*60 + f"\n程序在 {duration:.2f} 秒内完成。\n" + "="*60)

if __name__ == "__main__":
    main()

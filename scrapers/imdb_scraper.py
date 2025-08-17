import requests, csv, time, random, json, os, re, sys, traceback
from datetime import datetime
import pandas as pd
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.config import IMDB_CONFIG, DOUBAN_CONFIG

class SocketLogger:
    def __init__(self, socketio, platform): self.socketio, self.platform = socketio, platform
    def log(self, msg, type='info'): self.socketio.emit('log', {'message': f'[{self.platform.upper()}] {msg}', 'type': type})
    def progress(self, cur, tot, step=""): self.socketio.emit('progress', {'platform': self.platform, 'current': cur, 'total': tot, 'step': step})

class CLILogger:
    def log(self, msg, type='info'): print(f"[{type.upper()}] {msg}")
    def progress(self, cur, tot, step=""): pass

class IMDbRatingsScraper:
    def __init__(self, user_id, cookie, output_path, logger):
        self.user_id, self.output_filename, self.logger = user_id, output_path, logger
        self.imdb_headers = {'Cookie': cookie, 'User-Agent': 'Mozilla/5.0'}
        self.douban_headers = {'Cookie': DOUBAN_CONFIG.get('headers', {}).get('Cookie'), 'User-Agent': 'Mozilla/5.0'}
        self.api_url = "https://api.graphql.imdb.com/"
        self.web_url = f"https://www.imdb.com/user/{self.user_id}/ratings"
        self.douban_search_url = "https://m.douban.com/rexxar/api/v2/search"
        self.session = requests.Session()
        self.cache_file = os.path.join(os.path.dirname(output_path), "..", "data", "db_imdb.csv")
        self.cache = self._load_cache()
        self.new_mappings = {}
        self.existing_ids = self._load_existing()
        self.logger.log(f"发现 {len(self.existing_ids)} 条已有记录。", 'info')

    def _load_existing(self):
        if not os.path.exists(self.output_filename): return set()
        try: return set(pd.read_csv(self.output_filename, usecols=['Const'], dtype={'Const': str})['Const'].dropna())
        except Exception: return set()

    def _load_cache(self):
        if not os.path.exists(self.cache_file): return {}
        try:
            df = pd.read_csv(self.cache_file, dtype=str)
            if 'douban_id' not in df.columns and 'id' in df.columns: df.rename(columns={'id': 'douban_id'}, inplace=True)
            if 'douban_id' not in df.columns or 'imdb' not in df.columns: return {}
            df.dropna(subset=['douban_id', 'imdb'], inplace=True)
            return pd.Series(df.douban_id.values, index=df.imdb).to_dict()
        except Exception: return {}

    def _save_mappings(self):
        if not self.new_mappings: return
        self.logger.log(f"正在保存 {len(self.new_mappings)} 条新映射...", 'info')
        new_df = pd.DataFrame(list(self.new_mappings.items()), columns=['imdb', 'douban_id'])
        try:
            existing_df = pd.read_csv(self.cache_file, dtype=str) if os.path.exists(self.cache_file) else pd.DataFrame(columns=['douban_id', 'imdb'])
            if 'douban_id' not in existing_df.columns and 'id' in existing_df.columns: existing_df.rename(columns={'id': 'douban_id'}, inplace=True)
        except pd.errors.EmptyDataError: existing_df = pd.DataFrame(columns=['douban_id', 'imdb'])
        
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined.drop_duplicates(subset=['imdb'], keep='last', inplace=True).drop_duplicates(subset=['douban_id'], keep='last', inplace=True)
        combined.to_csv(self.cache_file, index=False, encoding='utf-8')

    def _fetch_api(self, cursor):
        payload = {"operationName":"userRatings","variables":{"first":250,"after":cursor},"extensions":{"persistedQuery":{"version":1,"sha256Hash":"ebf2387fd2ba45d62fc54ed2ffe3940086af52e700a1b3929a099d5fce23330a"}}}
        try:
            r = self.session.post(self.api_url, json=payload, headers=self.imdb_headers, timeout=30)
            r.raise_for_status(); return r.json()
        except requests.RequestException as e: self.logger.log(f"API请求失败: {e}", 'error'); return None

    def _fetch_web(self, page):
        try:
            r = self.session.get(f"{self.web_url}?sort=date_added,desc&page={page}", headers=self.imdb_headers, timeout=30)
            r.raise_for_status(); return r.text
        except requests.RequestException as e: self.logger.log(f"网页请求失败: {e}", 'error'); return None

    def _fetch_douban_id(self, imdb_id):
        if imdb_id in self.cache: return self.cache[imdb_id]
        if imdb_id in self.new_mappings: return self.new_mappings[imdb_id]
        time.sleep(random.uniform(0.5, 2.0))
        try:
            r = self.session.get(self.douban_search_url, params={'q': imdb_id, 'type': 'movie', 'count': 1}, headers=self.douban_headers, timeout=20, verify=False)
            r.raise_for_status()
            if subjects := r.json().get('subjects'):
                if douban_id := subjects[0].get('target_id'):
                    self.new_mappings[imdb_id] = douban_id; self.cache[imdb_id] = douban_id
                    return douban_id
        except requests.RequestException: pass
        return None

    def _parse_details(self, node):
        try:
            t = node.get('title', {})
            imdb_id = t.get('id')
            if not imdb_id: return None
            return {
                'imdb_id': imdb_id,
                'Title': t.get('titleText', {}).get('text'),
                'Year': t.get('releaseYear', {}).get('year'),
                'Cover URL': t.get('primaryImage', {}).get('url'),
                'URL': f"https://www.imdb.com/title/{imdb_id}/"
            }
        except (KeyError, TypeError): return None

    def scrape(self):
        self.logger.log("1/3: 从API获取个人评分...", 'info')
        ratings, cursor, count = {}, None, 0
        while True:
            self.logger.progress(count, 0, f"获取API页 {count+1}")
            data = self._fetch_api(cursor)
            if not data or not (edges := data.get('data', {}).get('userRatings', {}).get('edges')): break
            for edge in edges:
                node = edge.get('node')
                if not node: continue
                
                title_info = node.get('title', {})
                imdb_id = title_info.get('id')
                if not imdb_id: continue

                user_rating_info = node.get('userRating', {})
                rating_value = user_rating_info.get('value')
                rating_date = user_rating_info.get('date')

                if rating_value is not None and rating_date:
                    ratings[imdb_id] = {
                        'Your Rating': rating_value,
                        'Date Rated': datetime.fromisoformat(rating_date.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    }
            
            page_info = data['data']['userRatings']['pageInfo']
            if page_info.get('hasNextPage'): cursor = page_info['endCursor']; count += 1
            else: break
        self.logger.log(f"API完成, 找到 {len(ratings)} 条评分。", 'info')

        self.logger.log("2/3: 增量抓取网页详情...", 'info')
        new_movies, page = [], 1
        while True:
            self.logger.progress(page, 0, f"获取网页 {page}")
            html = self._fetch_web(page)
            if not html or not (match := re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', html, re.DOTALL)): break
            
            edges = json.loads(match.group(1))['props']['pageProps']['mainColumnData']['advancedTitleSearch']['edges']
            page_movies = [m for m in [self._parse_details(edge['node']) for edge in edges] if m]
            if not page_movies: break

            stop = False
            for movie in page_movies:
                if movie['imdb_id'] in self.existing_ids: stop = True; break
                movie.update(ratings.get(movie['imdb_id'], {}))
                new_movies.append(movie)
            if stop: break
            page += 1

        self.logger.log(f"3/3: 为 {len(new_movies)} 部新电影获取豆瓣ID...", 'info')
        total_new = len(new_movies)
        for i, movie in enumerate(new_movies):
            self.logger.progress(i + 1, total_new, f"查询豆瓣ID {i+1}/{total_new}")
            movie['douban_id'] = self._fetch_douban_id(movie['imdb_id'])

        return new_movies

def clean_df_for_json(df):
    """Converts a DataFrame to a list of records, replacing NaNs with None."""
    return df.where(pd.notnull(df), None).to_dict('records')

def run_scraper(user_id, cookie, output_path, socketio):
    logger = SocketLogger(socketio, 'imdb')
    try:
        scraper = IMDbRatingsScraper(user_id, cookie, output_path, logger)
        new_movies = scraper.scrape()
        scraper._save_mappings()
        
        if not new_movies:
            logger.log("数据已是最新。", 'success')
            try:
                df = pd.read_csv(output_path)
                return clean_df_for_json(df.head())
            except Exception:
                return []

        logger.log(f"抓取到 {len(new_movies)} 部新电影，正在保存...", 'info')
        df_new = pd.DataFrame(new_movies).rename(columns={'imdb_id': 'Const'})
        
        df_existing = pd.read_csv(scraper.output_filename) if os.path.exists(scraper.output_filename) else pd.DataFrame()
        df_final = pd.concat([df_new, df_existing], ignore_index=True).drop_duplicates(subset=['Const'], keep='first')
        df_final.sort_values(by='Date Rated', ascending=False, inplace=True)
        df_final.to_csv(scraper.output_filename, index=False, encoding='utf-8-sig')

        logger.log(f"成功！共 {len(df_final)} 条记录。", 'success')
        return clean_df_for_json(df_final.head())

    except Exception as e:
        logger.log(f"发生严重错误: {e}", 'error'); traceback.print_exc(); return None

def main():
    user, cookie = IMDB_CONFIG.get('user_id'), IMDB_CONFIG.get('headers', {}).get('Cookie')
    output = f"data/imdb_{user}_ratings.csv"
    class DummySocket:
        def emit(self, *args, **kwargs):
            pass
    run_scraper(user, cookie, output, DummySocket())

if __name__ == "__main__": main()

"""
IMDb Adapter - IMDB平台适配器
基于 scrapers/imdb_scraper.py 重构
"""

import os
import re
import json
import time
import random
import traceback
import requests
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from adapters.base import PlatformAdapter
from adapters.registry import AdapterRegistry
from adapters.utils.cache import IDMappingCache


@AdapterRegistry.register
class IMDbAdapter(PlatformAdapter):
    """
    IMDb 平台适配器
    
    认证方式: Cookie
    支持功能: 数据获取（不支持写入，IMDB无公开API）
    """
    
    platform_id = 'imdb'
    platform_name = 'IMDb'
    platform_name_en = 'IMDb'
    auth_type = 'cookie'
    supports_fetch = True
    supports_sync = True  # Enable write support via rate_on_imdb
    supports_export = True
    
    # API 配置
    API_URL = "https://api.graphql.imdb.com/"
    
    def __init__(self, logger, config: Dict[str, Any]):
        super().__init__(logger, config)
        self.cache_file = config.get('cache_file', 'data/db_imdb.csv')
        self._cache: Optional[IDMappingCache] = None
        self.session = requests.Session()
    
    @property
    def cache(self) -> IDMappingCache:
        if self._cache is None:
            self._cache = IDMappingCache(self.cache_file)
        return self._cache
    
    def get_config_keys(self) -> List[str]:
        return ['imdb_user_id', 'imdb_cookie']
    
    def test_connection(self) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """测试IMDB Cookie是否有效"""
        user_id = self.config.get('imdb_user_id')
        cookie = self.config.get('imdb_cookie')
        
        if not user_id or not cookie:
            return False, "请先配置用户ID和Cookie", None
        
        headers = {
            'Cookie': cookie,
            'User-Agent': 'Mozilla/5.0'
        }
        
        try:
            # 测试 GraphQL API
            payload = {
                "operationName": "userRatings",
                "variables": {"first": 1},
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "ebf2387fd2ba45d62fc54ed2ffe3940086af52e700a1b3929a099d5fce23330a"
                    }
                }
            }
            resp = self.session.post(self.API_URL, json=payload, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                data = resp.json()
                if 'data' in data and data['data'] is not None:
                    return True, None, {
                        'user_id': user_id,
                        'status': 'connected'
                    }
                elif 'errors' in data:
                    return False, f"API错误: {data['errors']}", None
            
            return False, f"HTTP {resp.status_code}", None
            
        except Exception as e:
            return False, f"连接失败: {str(e)}", None
    
    def fetch_data(self, output_path: str) -> Optional[List[Dict[str, Any]]]:
        """获取IMDB电影数据"""
        user_id = self.config.get('imdb_user_id')
        cookie = self.config.get('imdb_cookie')
        
        if not user_id or not cookie:
            self.logger.error("缺少用户ID或Cookie配置")
            return None
        
        try:
            scraper = IMDbScraper(
                user_id=user_id,
                cookie=cookie,
                output_path=output_path,
                logger=self.logger,
                cache=self.cache,
                douban_cookie=self.config.get('douban_cookie'),
                force_full_refresh=bool(self.config.get('force_full_refresh'))
            )
            new_movies = scraper.scrape()
            
            if not new_movies:
                self.logger.success("数据已是最新。")
                return self._load_existing_data(output_path)
            
            self.logger.info(f"抓取到 {len(new_movies)} 部新电影，正在保存...")
            
            df_new = pd.DataFrame(new_movies).rename(columns={'imdb_id': 'Const'})
            df_existing = pd.read_csv(output_path) if os.path.exists(output_path) else pd.DataFrame()
            if getattr(scraper, 'force_full_refresh', False):
                df_existing = pd.DataFrame()
            df_final = pd.concat([df_new, df_existing], ignore_index=True)
            df_final.drop_duplicates(subset=['Const'], keep='first', inplace=True)
            df_final.sort_values(by='Date Rated', ascending=False, inplace=True)
            df_final.to_csv(output_path, index=False, encoding='utf-8-sig')
            
            self.logger.success(f"成功！共 {len(df_final)} 条记录。")
            return self.clean_df_for_json(df_final)
            
        except Exception as e:
            self.logger.error(f"发生严重错误: {e}")
            traceback.print_exc()
            return None
    
    def _load_existing_data(self, output_path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(output_path):
            return []
        try:
            df = pd.read_csv(output_path)
            return self.clean_df_for_json(df)
        except:
            return []
    
    def logout(self) -> bool:
        return True

    def sync_movie(self, item_id: str, rating: float, comment: str = None, tags: List[str] = None) -> bool:
        """Rate movie on IMDb (Implementation of generic sync interface)"""
        try:
            from utils.sync_rate import rate_on_imdb
            
            if not rating:
                return True
                
            # Generic rating is 0-10 float
            import math
            if isinstance(rating, float) and math.isnan(rating):
                return True # Skip NaN ratings
                
            imdb_rating = int(round(rating))
            if imdb_rating < 1: imdb_rating = 1
            if imdb_rating > 10: imdb_rating = 10
            
            if not item_id:
                self.logger.log(f"Failed to sync: No IMDb ID found.", 'error')
                return False
                
            headers = {
                'Cookie': self.config.get('imdb_cookie'),
                'User-Agent': 'Mozilla/5.0'
            }
            
            success = rate_on_imdb(item_id, imdb_rating, headers, item_id)
            if success:
                self.logger.log(f"✅ Synced {item_id} to IMDb ({imdb_rating}/10)", 'success')
            return success
        except Exception as e:
            self.logger.log(f"Sync error for {item_id}: {e}", 'error')
            return False


class IMDbScraper:
    """IMDB 数据抓取器"""
    
    def __init__(self, user_id: str, cookie: str, output_path: str,
                 logger, cache: IDMappingCache, douban_cookie: str = None,
                 force_full_refresh: bool = False):
        self.user_id = user_id
        self.output_path = output_path
        self.logger = logger
        self.cache = cache
        self.force_full_refresh = bool(force_full_refresh)
        
        self.imdb_headers = {'Cookie': cookie, 'User-Agent': 'Mozilla/5.0'}
        self.douban_headers = {
            'Cookie': douban_cookie or '',
            'User-Agent': 'Mozilla/5.0'
        }
        
        self.api_url = "https://api.graphql.imdb.com/"
        self.web_url = f"https://www.imdb.com/user/{user_id}/ratings"
        self.douban_search_url = "https://m.douban.com/rexxar/api/v2/search"
        
        self.session = requests.Session()
        self.existing_ids = self._load_existing()
        self.new_mappings = {}
        
        if self.force_full_refresh:
            self.logger.warning("评分缓存缺少 Type 字段，已切换为全量重建以补齐类型。")
        self.logger.log(f"发现 {len(self.existing_ids)} 条已有记录。", 'info')
    
    def _load_existing(self) -> set:
        if self.force_full_refresh:
            return set()
        if not os.path.exists(self.output_path):
            return set()
        try:
            df = pd.read_csv(self.output_path, dtype={'Const': str})
            if 'Type' not in df.columns and 'type' not in df.columns and 'Title Type' not in df.columns:
                self.force_full_refresh = True
                return set()
            if 'Type' in df.columns:
                type_series = df['Type'].fillna('').astype(str).str.strip()
                if type_series.eq('').all():
                    self.force_full_refresh = True
                    return set()
            return set(df['Const'].dropna()) if 'Const' in df.columns else set()
        except:
            return set()
    
    def _fetch_api(self, cursor=None) -> Optional[Dict]:
        payload = {
            "operationName": "userRatings",
            "variables": {"first": 250, "after": cursor},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "ebf2387fd2ba45d62fc54ed2ffe3940086af52e700a1b3929a099d5fce23330a"
                }
            }
        }
        try:
            resp = self.session.post(self.api_url, json=payload, 
                                     headers=self.imdb_headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            self.logger.error(f"API请求失败: {e}")
            return None
    
    def _fetch_web(self, page: int) -> Optional[str]:
        try:
            resp = self.session.get(
                f"{self.web_url}?sort=date_added,desc&page={page}",
                headers=self.imdb_headers, timeout=30
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            self.logger.error(f"网页请求失败: {e}")
            return None
    
    def _fetch_douban_id(self, imdb_id: str) -> Optional[str]:
        # 先查缓存
        cached = self.cache.get_douban_id(imdb_id)
        if cached:
            return cached
        if imdb_id in self.new_mappings:
            return self.new_mappings[imdb_id]
        
        time.sleep(random.uniform(0.5, 2.0))
        try:
            resp = self.session.get(
                self.douban_search_url,
                params={'q': imdb_id, 'type': 'movie', 'count': 1},
                headers=self.douban_headers,
                timeout=20, verify=False
            )
            resp.raise_for_status()
            subjects = resp.json().get('subjects', [])
            if subjects:
                douban_id = subjects[0].get('target_id')
                if douban_id:
                    self.new_mappings[imdb_id] = douban_id
                    self.cache.set(douban_id, imdb_id)
                    return douban_id
        except:
            pass
        return None
    
    def _parse_details(self, node: Dict) -> Optional[Dict]:
        try:
            t = node.get('title', {})
            imdb_id = t.get('id')
            if not imdb_id:
                return None
            title_type = t.get('titleType', {}).get('text', '') or t.get('titleType', {}).get('id', '') or ''
            title_type = str(title_type).lower().strip()
            media_type = 'tv' if any(k in title_type for k in ['tv', 'series', 'episode', 'show', 'miniseries']) else 'movie'
            return {
                'imdb_id': imdb_id,
                'Title': t.get('titleText', {}).get('text'),
                'Year': t.get('releaseYear', {}).get('year'),
                'Cover URL': t.get('primaryImage', {}).get('url'),
                'URL': f"https://www.imdb.com/title/{imdb_id}/",
                'IMDb Rating': t.get('ratingsSummary', {}).get('aggregateRating', ''),
                'Num Votes': t.get('ratingsSummary', {}).get('voteCount', ''),
                'Runtime (mins)': int(t.get('runtime', {}).get('seconds', 0) / 60) if t.get('runtime', {}).get('seconds') else '',
                'Genres': ', '.join([g['genre']['text'] for g in t.get('titleGenres', {}).get('genres', []) if g.get('genre')]),
                'Directors': ', '.join([
                    c.get('name', {}).get('nameText', {}).get('text', '')
                    for group in t.get('principalCreditsV2', [])
                    if 'Director' in group.get('grouping', {}).get('text', '')
                    for c in group.get('credits', [])
                ]),
                'Type': media_type
            }
        except:
            return None
    
    def scrape(self) -> List[Dict]:
        """执行抓取"""
        # 1. 从 API 获取评分
        self.logger.log("1/3: 从API获取个人评分...", 'info')
        ratings, cursor, count = {}, None, 0
        
        while True:
            self.logger.progress(count, 0, f"获取API页 {count+1}")
            data = self._fetch_api(cursor)
            if not data:
                break
            
            data_content = data.get('data')
            if data_content is None:
                errors = data.get('errors')
                if errors:
                    self.logger.error(f"IMDb API 返回错误: {errors}")
                break
            
            user_ratings = data_content.get('userRatings', {})
            edges = user_ratings.get('edges')
            if not edges:
                break
            
            for edge in edges:
                node = edge.get('node') if edge else None
                if not node:
                    continue
                
                title_info = node.get('title', {})
                imdb_id = title_info.get('id')
                if not imdb_id:
                    continue
                
                user_rating_info = node.get('userRating', {})
                rating_value = user_rating_info.get('value')
                rating_date = user_rating_info.get('date')
                
                if rating_value is not None and rating_date:
                    ratings[imdb_id] = {
                        'Your Rating': rating_value,
                        'Date Rated': datetime.fromisoformat(
                            rating_date.replace('Z', '+00:00')
                        ).strftime('%Y-%m-%d')
                    }
            
            page_info = data['data']['userRatings']['pageInfo']
            if page_info.get('hasNextPage'):
                cursor = page_info['endCursor']
                count += 1
            else:
                break
        
        self.logger.log(f"API完成, 找到 {len(ratings)} 条评分。", 'info')
        
        # 2. 增量抓取网页详情
        self.logger.log("2/3: 增量抓取网页详情...", 'info')
        new_movies, page = [], 1
        
        while True:
            self.logger.progress(page, 0, f"获取网页 {page}")
            html = self._fetch_web(page)
            if not html:
                break
            
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
                html, re.DOTALL
            )
            if not match:
                break
            
            try:
                json_data = json.loads(match.group(1))
                edges = json_data['props']['pageProps']['mainColumnData']['advancedTitleSearch']['edges']
            except:
                break
            
            page_movies = [m for m in [self._parse_details(e['node']) for e in edges] if m]
            if not page_movies:
                break
            
            stop = False
            for movie in page_movies:
                if movie['imdb_id'] in self.existing_ids:
                    stop = True
                    break
                movie.update(ratings.get(movie['imdb_id'], {}))
                new_movies.append(movie)
            
            if stop:
                break
            page += 1
        
        # 3. 获取豆瓣ID
        self.logger.log(f"3/3: 为 {len(new_movies)} 部新电影获取豆瓣ID...", 'info')
        total_new = len(new_movies)
        for i, movie in enumerate(new_movies):
            self.logger.progress(i + 1, total_new, f"查询豆瓣ID {i+1}/{total_new}")
            movie['douban_id'] = self._fetch_douban_id(movie['imdb_id'])
        
        # 保存缓存
        self.cache.save()
        
        return new_movies


# 向后兼容：提供 run_scraper 函数
def run_scraper(user_id: str, cookie: str, output_path: str, socketio, force_full_refresh: bool = False) -> Optional[List[Dict]]:
    """
    向后兼容的入口函数
    """
    from adapters.logger import SocketLogger
    from web.config_helper import read_config
    
    config = read_config()
    logger = SocketLogger(socketio, 'imdb')
    adapter_config = {
        'imdb_user_id': user_id,
        'imdb_cookie': cookie,
        'douban_cookie': config.get('douban_cookie'),
        'cache_file': 'data/db_imdb.csv',
        'force_full_refresh': force_full_refresh
    }
    
    adapter = IMDbAdapter(logger, adapter_config)
    return adapter.fetch_data(output_path)

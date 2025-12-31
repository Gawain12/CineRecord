"""
TMDB Service - ID 映射与数据丰富服务
通过 TMDB API 实现跨平台 ID 映射

TMDB API 文档: https://developer.themoviedb.org/docs
免费注册获取 API Key: https://www.themoviedb.org/settings/api
"""

import os
import time
import requests
import logging
from typing import Optional, Dict, Any, List
from functools import lru_cache

logger = logging.getLogger(__name__)


class TMDBService:
    """
    TMDB API 服务
    
    主要功能:
    1. find_by_imdb() - 通过 IMDb ID 查找 TMDB 数据
    2. get_external_ids() - 获取电影的所有外部 ID
    3. enrich_record() - 丰富记录，补全缺失的 ID 和元数据
    
    使用示例:
        tmdb = TMDBService(api_key="your_api_key")
        result = tmdb.find_by_imdb("tt0111161")
        # {'tmdb_id': 278, 'title': 'The Shawshank Redemption', ...}
    """
    
    BASE_URL = "https://api.themoviedb.org/3"
    
    # 默认 API Key (需要用户配置自己的)
    # 此处留空，需要用户在配置中设置
    DEFAULT_API_KEY = ""
    
    def __init__(self, api_key: str = None):
        """
        初始化 TMDB 服务
        
        Args:
            api_key: TMDB API Key，如果未提供则尝试从环境变量读取
        """
        self.api_key = api_key or os.environ.get('TMDB_API_KEY') or self.DEFAULT_API_KEY
        self.session = requests.Session()
        self._rate_limit_remaining = 40
        self._rate_limit_reset = 0
    
    @property
    def is_configured(self) -> bool:
        """检查是否已配置 API Key"""
        return bool(self.api_key)
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """发送 API 请求"""
        if not self.is_configured:
            logger.warning("TMDB API Key not configured")
            return None
        
        # 简单限流
        if self._rate_limit_remaining <= 1:
            wait_time = max(0, self._rate_limit_reset - time.time())
            if wait_time > 0:
                time.sleep(wait_time)
        
        url = f"{self.BASE_URL}{endpoint}"
        default_params = {'api_key': self.api_key}
        if params:
            default_params.update(params)
        
        try:
            response = self.session.get(url, params=default_params, timeout=10)
            
            # 更新限流信息
            self._rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', 40))
            self._rate_limit_reset = int(response.headers.get('X-RateLimit-Reset', 0))
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                # 限流，等待重试
                time.sleep(2)
                return self._make_request(endpoint, params)
            else:
                logger.debug(f"TMDB API error: {response.status_code}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"TMDB request failed: {e}")
            return None
    
    def find_by_imdb(self, imdb_id: str) -> Optional[Dict[str, Any]]:
        """
        通过 IMDb ID 查找电影信息
        
        Args:
            imdb_id: IMDb ID (tt1234567 格式)
            
        Returns:
            电影信息字典，包含 tmdb_id, title, year 等
        """
        if not imdb_id or not imdb_id.startswith('tt'):
            return None
        
        data = self._make_request(f'/find/{imdb_id}', {
            'external_source': 'imdb_id'
        })
        
        if not data:
            return None
        
        # 优先返回电影结果
        movie_results = data.get('movie_results', [])
        if movie_results:
            movie = movie_results[0]
            return self._parse_movie_result(movie, imdb_id)
        
        # 其次返回剧集结果
        tv_results = data.get('tv_results', [])
        if tv_results:
            tv = tv_results[0]
            return {
                'tmdb_id': tv.get('id'),
                'title': tv.get('name'),
                'original_title': tv.get('original_name'),
                'year': self._extract_year(tv.get('first_air_date')),
                'imdb_id': imdb_id,
                'type': 'tv'
            }
        
        return None
    
    def get_external_ids(self, tmdb_id: int, media_type: str = 'movie') -> Optional[Dict[str, Any]]:
        """
        获取电影/剧集的所有外部 ID
        
        Args:
            tmdb_id: TMDB ID
            media_type: 'movie' 或 'tv'
            
        Returns:
            外部 ID 字典，包含 imdb_id, wikidata_id 等
        """
        data = self._make_request(f'/{media_type}/{tmdb_id}/external_ids')
        
        if not data:
            return None
        
        return {
            'imdb_id': data.get('imdb_id'),
            'wikidata_id': data.get('wikidata_id'),
            'facebook_id': data.get('facebook_id'),
            'instagram_id': data.get('instagram_id'),
            'twitter_id': data.get('twitter_id'),
        }
    
    def get_movie_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """
        获取电影详细信息
        
        Args:
            tmdb_id: TMDB ID
            
        Returns:
            电影详情字典
        """
        data = self._make_request(f'/movie/{tmdb_id}')
        
        if not data:
            return None
        
        return {
            'tmdb_id': data.get('id'),
            'title': data.get('title'),
            'original_title': data.get('original_title'),
            'year': self._extract_year(data.get('release_date')),
            'imdb_id': data.get('imdb_id'),
            'genres': ', '.join(g['name'] for g in data.get('genres', [])),
            'runtime': data.get('runtime'),
            'overview': data.get('overview'),
            'poster_path': data.get('poster_path'),
            'vote_average': data.get('vote_average'),
            'vote_count': data.get('vote_count'),
        }
    
    def search_movie(self, title: str, year: int = None) -> Optional[Dict[str, Any]]:
        """
        搜索电影（当没有 ID 时的 fallback）
        
        Args:
            title: 电影标题
            year: 发行年份（可选，提高准确性）
            
        Returns:
            匹配的电影信息
        """
        params = {'query': title}
        if year:
            params['year'] = year
        
        data = self._make_request('/search/movie', params)
        
        if not data or not data.get('results'):
            return None
        
        # 返回第一个结果
        movie = data['results'][0]
        return self._parse_movie_result(movie)
    
    def enrich_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        丰富记录：补全缺失的 ID 和元数据
        
        处理逻辑:
        1. 如果有 imdb_id 但无 tmdb_id，通过 find_by_imdb 查询
        2. 如果有 tmdb_id 但无 imdb_id，通过 get_external_ids 查询
        3. 如果都没有，尝试通过 title + year 搜索
        
        Args:
            record: 电影记录字典
            
        Returns:
            丰富后的记录
        """
        if not self.is_configured:
            return record
        
        result = record.copy()
        
        imdb_id = result.get('imdb_id') or result.get('Const')
        tmdb_id = result.get('tmdb_id') or result.get('TMDB ID')
        
        # Case 1: 有 IMDB，查 TMDB
        if imdb_id and not tmdb_id:
            tmdb_data = self.find_by_imdb(imdb_id)
            if tmdb_data:
                result['tmdb_id'] = tmdb_data.get('tmdb_id')
                # 补充其他缺失字段
                if not result.get('genres'):
                    result['genres'] = tmdb_data.get('genres')
                if not result.get('runtime'):
                    result['runtime'] = tmdb_data.get('runtime')
        
        # Case 2: 有 TMDB，查 IMDB
        elif tmdb_id and not imdb_id:
            ext_ids = self.get_external_ids(tmdb_id)
            if ext_ids and ext_ids.get('imdb_id'):
                result['imdb_id'] = ext_ids['imdb_id']
        
        # Case 3: 都没有，尝试搜索
        elif not imdb_id and not tmdb_id:
            title = result.get('title') or result.get('Title') or result.get('Name')
            year = result.get('year') or result.get('Year')
            if title:
                search_result = self.search_movie(title, year)
                if search_result:
                    result['tmdb_id'] = search_result.get('tmdb_id')
                    if search_result.get('imdb_id'):
                        result['imdb_id'] = search_result['imdb_id']
        
        return result
    
    def batch_enrich(self, records: List[Dict[str, Any]], 
                     progress_callback=None) -> List[Dict[str, Any]]:
        """
        批量丰富记录
        
        Args:
            records: 记录列表
            progress_callback: 进度回调函数 (current, total)
            
        Returns:
            丰富后的记录列表
        """
        total = len(records)
        results = []
        
        for i, record in enumerate(records):
            enriched = self.enrich_record(record)
            results.append(enriched)
            
            if progress_callback:
                progress_callback(i + 1, total)
            
            # 简单限流
            if i % 35 == 0 and i > 0:
                time.sleep(1)
        
        return results
    
    def _parse_movie_result(self, movie: Dict, imdb_id: str = None) -> Dict[str, Any]:
        """解析电影结果"""
        return {
            'tmdb_id': movie.get('id'),
            'title': movie.get('title'),
            'original_title': movie.get('original_title'),
            'year': self._extract_year(movie.get('release_date')),
            'imdb_id': imdb_id,
            'poster_path': movie.get('poster_path'),
            'vote_average': movie.get('vote_average'),
            'type': 'movie'
        }
    
    @staticmethod
    def _extract_year(date_str: str) -> Optional[int]:
        """从日期字符串提取年份"""
        if date_str and len(date_str) >= 4:
            try:
                return int(date_str[:4])
            except ValueError:
                pass
        return None


# 单例模式
_tmdb_instance: Optional[TMDBService] = None


def get_tmdb_service(api_key: str = None) -> TMDBService:
    """
    获取 TMDB 服务实例（单例）
    
    Args:
        api_key: API Key，仅在首次调用时生效
    """
    global _tmdb_instance
    if _tmdb_instance is None:
        _tmdb_instance = TMDBService(api_key)
    return _tmdb_instance

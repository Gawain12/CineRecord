"""
Trakt Adapter - Trakt平台适配器
基于 scrapers/trakt_client.py 重构
"""

import os
import requests
import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any, Tuple

from adapters.base import PlatformAdapter
from adapters.registry import AdapterRegistry

logger = logging.getLogger(__name__)


@AdapterRegistry.register
class TraktAdapter(PlatformAdapter):
    """
    Trakt 平台适配器
    
    认证方式: OAuth2 Device Flow
    支持功能: 数据获取、评分同步
    """
    
    platform_id = 'trakt'
    platform_name = 'Trakt'
    platform_name_en = 'Trakt'
    auth_type = 'oauth'
    supports_fetch = True
    supports_sync = True
    supports_export = True
    
    # API 配置
    BASE_URL = "https://api.trakt.tv"
    
    # 默认 API 凭证
    DEFAULT_CLIENT_ID = "b2505cf6da8f8c8678dac8ecfc43d1a780952c49a658b89a231e7dc567d28b35"
    DEFAULT_CLIENT_SECRET = "33e4fc63d53e483fe988008d1f546efb291299a9ddd079f7e2ebe52965fdf128"
    
    def __init__(self, logger_instance, config: Dict[str, Any]):
        super().__init__(logger_instance, config)
        self.client_id = (config.get('trakt_client_id') or self.DEFAULT_CLIENT_ID).strip()
        self.client_secret = (config.get('trakt_client_secret') or self.DEFAULT_CLIENT_SECRET).strip()
        self.access_token = (config.get('trakt_access_token') or '').strip()
        self.refresh_token = (config.get('trakt_refresh_token') or '').strip()
        self.token_expires = None
        
        if config.get('trakt_token_expires'):
            try:
                self.token_expires = datetime.fromisoformat(config['trakt_token_expires'])
            except:
                pass
    
    def get_config_keys(self) -> List[str]:
        return [
            'trakt_client_id', 'trakt_client_secret',
            'trakt_access_token', 'trakt_refresh_token',
            'trakt_token_expires', 'trakt_user_id',
            'trakt_display_name', 'trakt_avatar',
            'trakt_movies_rated', 'trakt_movies_watched'
        ]
    
    def _get_headers(self, auth_required: bool = True) -> Dict[str, str]:
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-version': '2',
            'trakt-api-key': self.client_id
        }
        if auth_required and self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        return headers
    
    def _make_request(self, method: str, endpoint: str, 
                      auth_required: bool = True, **kwargs) -> Optional[requests.Response]:
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers(auth_required)
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30, **kwargs)
            elif method == 'POST':
                response = requests.post(url, headers=headers, timeout=30, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            return response
        except requests.Timeout:
            self.logger.error(f"Trakt API 请求超时")
            return None
        except requests.ConnectionError:
            self.logger.error(f"Trakt API 连接错误")
            return None
        except requests.RequestException as e:
            self.logger.error(f"Trakt API 请求失败: {e}")
            return None
    
    def test_connection(self) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """测试Trakt连接"""
        if not self.access_token:
            return False, "请先授权Trakt账号", None
        
        # 检查token是否过期
        if self.is_token_expired():
            if not self.refresh_access_token():
                return False, "Token已过期且刷新失败", None
        
        response = self._make_request('GET', '/users/me?extended=full')
        
        if response and response.status_code == 200:
            profile = response.json()
            stats = self.get_user_stats('me')
            
            return True, None, {
                'user_id': profile.get('ids', {}).get('slug'),
                'username': profile.get('username'),
                'display_name': profile.get('name'),
                'avatar': profile.get('images', {}).get('avatar', {}).get('full'),
                'movies_watched': stats.get('movies', {}).get('watched') if stats else 0,
                'movies_rated': stats.get('movies', {}).get('ratings') if stats else 0,
                'profile_link': f"https://trakt.tv/users/{profile.get('ids', {}).get('slug')}"
            }
        
        return False, "无法获取用户信息", None
    
    def fetch_data(self, output_path: str) -> Optional[List[Dict[str, Any]]]:
        """获取Trakt电影数据"""
        if not self.access_token:
            self.logger.error("请先授权Trakt账号")
            return None
        
        # 刷新token
        if self.is_token_expired():
            self.logger.info("刷新访问令牌...")
            if not self.refresh_access_token():
                self.logger.error("Token刷新失败")
                return None
        
        self.logger.info("正在获取Trakt数据...")
        
        try:
            movies = self.get_all_movies_with_ratings()
            
            if movies:
                df = pd.DataFrame(movies)
                
                # 重命名列以统一格式
                column_map = {'IMDb ID': 'Const'}
                df.rename(columns=column_map, inplace=True)
                
                df.to_csv(output_path, index=False)
                
                rated_count = df['Your Rating'].notna().sum()
                self.logger.success(f"Trakt数据获取完成: {len(df)} 部电影 ({rated_count} 部已评分)")
                
                return self.clean_df_for_json(df)
            else:
                self.logger.info("未在Trakt上找到观影数据")
                return []
                
        except Exception as e:
            self.logger.error(f"Trakt数据获取失败: {e}")
            return None
    
    # ==========================================
    # OAuth2 Device Flow
    # ==========================================
    
    def start_device_auth(self) -> Optional[Dict[str, Any]]:
        """启动设备授权流程"""
        response = self._make_request(
            'POST',
            '/oauth/device/code',
            auth_required=False,
            json={'client_id': self.client_id}
        )
        
        if response and response.status_code == 200:
            data = response.json()
            return {
                'device_code': data['device_code'],
                'user_code': data['user_code'],
                'verification_url': data['verification_url'],
                'expires_in': data['expires_in'],
                'interval': data['interval']
            }
        return None
    
    def poll_device_auth(self, device_code: str) -> Dict[str, Any]:
        """轮询设备授权状态"""
        response = self._make_request(
            'POST',
            '/oauth/device/token',
            auth_required=False,
            json={
                'code': device_code,
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
        )
        
        if not response:
            return {'status': 'error', 'message': '服务器无响应'}
        
        if response.status_code == 200:
            data = response.json()
            self.access_token = data['access_token']
            self.refresh_token = data['refresh_token']
            expires_in = data['expires_in']
            self.token_expires = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            return {
                'status': 'success',
                'access_token': data['access_token'],
                'refresh_token': data['refresh_token'],
                'expires_in': expires_in,
                'token_expires': self.token_expires.isoformat()
            }
        elif response.status_code == 400:
            return {'status': 'pending'}
        elif response.status_code == 404:
            return {'status': 'expired', 'message': '授权码已过期'}
        elif response.status_code == 409:
            return {'status': 'expired', 'message': '授权码已使用'}
        elif response.status_code in [410, 418]:
            return {'status': 'denied', 'message': '用户拒绝授权'}
        elif response.status_code == 429:
            return {'status': 'slow_down'}
        else:
            return {'status': 'error', 'message': f'HTTP {response.status_code}'}
    
    def refresh_access_token(self) -> bool:
        """刷新访问令牌"""
        if not self.refresh_token:
            return False
        
        response = self._make_request(
            'POST',
            '/oauth/token',
            auth_required=False,
            json={
                'refresh_token': self.refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
                'grant_type': 'refresh_token'
            }
        )
        
        if response and response.status_code == 200:
            data = response.json()
            self.access_token = data['access_token']
            self.refresh_token = data['refresh_token']
            expires_in = data['expires_in']
            self.token_expires = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            return True
        
        return False
    
    def is_token_expired(self) -> bool:
        """检查token是否过期"""
        if not self.token_expires:
            return True
        return datetime.now(timezone.utc) >= (self.token_expires - timedelta(minutes=5))
    
    # ==========================================
    # User Data Endpoints
    # ==========================================
    
    def get_user_profile(self) -> Optional[Dict]:
        response = self._make_request('GET', '/users/me?extended=full')
        if response and response.status_code == 200:
            return response.json()
        return None
    
    def get_user_stats(self, username: str = 'me') -> Optional[Dict]:
        response = self._make_request('GET', f'/users/{username}/stats')
        if response and response.status_code == 200:
            return response.json()
        return None
    
    def get_ratings(self, username: str = 'me', page: int = 1, limit: int = 100) -> Optional[Dict]:
        response = self._make_request(
            'GET',
            f'/users/{username}/ratings/movies',
            params={'page': page, 'limit': limit, 'extended': 'full'}
        )
        
        if response and response.status_code == 200:
            return {
                'items': response.json(),
                'page': int(response.headers.get('X-Pagination-Page', 1)),
                'total_pages': int(response.headers.get('X-Pagination-Page-Count', 1)),
                'total_items': int(response.headers.get('X-Pagination-Item-Count', 0))
            }
        return None
    
    def get_watch_history(self, username: str = 'me', page: int = 1, limit: int = 100) -> Optional[Dict]:
        response = self._make_request(
            'GET',
            f'/users/{username}/history/movies',
            params={'page': page, 'limit': limit, 'extended': 'full'}
        )
        
        if response and response.status_code == 200:
            return {
                'items': response.json(),
                'page': int(response.headers.get('X-Pagination-Page', 1)),
                'total_pages': int(response.headers.get('X-Pagination-Page-Count', 1)),
                'total_items': int(response.headers.get('X-Pagination-Item-Count', 0))
            }
        return None
    
    def get_all_movies_with_ratings(self, username: str = 'me') -> List[Dict]:
        """获取所有电影并合并评分"""
        # 先获取所有评分
        ratings_data = {}
        page = 1
        while True:
            result = self.get_ratings(username, page=page, limit=100)
            if not result or not result['items']:
                break
            for item in result['items']:
                movie = item.get('movie', {})
                trakt_id = movie.get('ids', {}).get('trakt')
                if trakt_id:
                    ratings_data[trakt_id] = {
                        'rating': item.get('rating'),
                        'rated_at': item.get('rated_at', '')[:10] if item.get('rated_at') else ''
                    }
            if page >= result['total_pages']:
                break
            page += 1
        
        # 获取观看历史并合并评分
        all_movies = []
        page = 1
        seen_ids = set()
        
        while True:
            result = self.get_watch_history(username, page=page, limit=100)
            if not result or not result['items']:
                break
            
            for item in result['items']:
                movie = item.get('movie', {})
                trakt_id = movie.get('ids', {}).get('trakt')
                
                if trakt_id in seen_ids:
                    continue
                seen_ids.add(trakt_id)
                
                rating_info = ratings_data.get(trakt_id, {})
                
                all_movies.append({
                    'Title': movie.get('title'),
                    'Year': movie.get('year'),
                    'Your Rating': rating_info.get('rating'),
                    'Date Rated': rating_info.get('rated_at') or (item.get('watched_at', '')[:10] if item.get('watched_at') else ''),
                    'IMDb ID': movie.get('ids', {}).get('imdb'),
                    'Trakt ID': trakt_id,
                    'TMDB ID': movie.get('ids', {}).get('tmdb'),
                    'URL': f"https://trakt.tv/movies/{movie.get('ids', {}).get('slug', '')}",
                    'Genres': ', '.join(movie.get('genres', [])) if movie.get('genres') else '',
                    'Runtime': movie.get('runtime'),
                    'Type': 'movie'
                })
            
            if page >= result['total_pages']:
                break
            page += 1
        
        return all_movies
    
    # ==========================================
    # Sync Methods
    # ==========================================
    
    def add_to_history(self, movies: List[Dict], watched_at=None) -> Optional[Dict]:
        """添加到观看历史"""
        if not movies:
            return {'added': {'movies': 0}, 'not_found': {'movies': []}}
        
        movies_data = []
        for movie in movies:
            movie_obj = {'ids': {}}
            if movie.get('imdb_id'):
                movie_obj['ids']['imdb'] = movie['imdb_id']
            if movie.get('trakt_id'):
                movie_obj['ids']['trakt'] = movie['trakt_id']
            if watched_at:
                movie_obj['watched_at'] = watched_at.isoformat() if hasattr(watched_at, 'isoformat') else watched_at
            elif movie.get('watched_at'):
                movie_obj['watched_at'] = movie['watched_at']
            movies_data.append(movie_obj)
        
        response = self._make_request('POST', '/sync/history', json={'movies': movies_data})
        
        if response and response.status_code in [200, 201]:
            return response.json()
        return None
    
    def rate_movies(self, movies: List[Dict]) -> Optional[Dict]:
        """批量评分电影"""
        if not movies:
            return {'added': {'movies': 0}, 'not_found': {'movies': []}}
        
        movies_data = []
        for movie in movies:
            if not movie.get('rating'):
                continue
            movie_obj = {
                'ids': {},
                'rating': int(movie['rating'])
            }
            if movie.get('imdb_id'):
                movie_obj['ids']['imdb'] = movie['imdb_id']
            if movie.get('trakt_id'):
                movie_obj['ids']['trakt'] = movie['trakt_id']
            if movie.get('rated_at'):
                movie_obj['rated_at'] = movie['rated_at']
            movies_data.append(movie_obj)
        
        if not movies_data:
            return {'added': {'movies': 0}, 'not_found': {'movies': []}}
        
        response = self._make_request('POST', '/sync/ratings', json={'movies': movies_data})
        
        if response and response.status_code in [200, 201]:
            return response.json()
        return None
    
    def sync_ratings(self, movies: List[Dict[str, Any]]) -> Dict[str, Any]:
        """同步评分到Trakt"""
        results = {
            'history_added': 0,
            'ratings_added': 0,
            'not_found': []
        }
        
        # 获取现有数据
        existing = self.get_all_movies_with_ratings()
        existing_imdb_ids = {m.get('IMDb ID') for m in existing if m.get('IMDb ID')}
        
        to_add_history = []
        to_rate = []
        
        for movie in movies:
            imdb_id = movie.get('Const') or movie.get('imdb_id') or movie.get('IMDb ID')
            if not imdb_id:
                continue
            
            if imdb_id not in existing_imdb_ids:
                to_add_history.append({
                    'imdb_id': imdb_id,
                    'watched_at': movie.get('Date Rated') or datetime.now(timezone.utc).isoformat()
                })
            
            rating = movie.get('Your Rating') or movie.get('rating')
            if rating:
                to_rate.append({
                    'imdb_id': imdb_id,
                    'rating': int(rating),
                    'rated_at': movie.get('Date Rated')
                })
        
        # 批量添加历史
        if to_add_history:
            batch_size = 100
            for i in range(0, len(to_add_history), batch_size):
                batch = to_add_history[i:i+batch_size]
                result = self.add_to_history(batch)
                if result:
                    results['history_added'] += result.get('added', {}).get('movies', 0)
                    results['not_found'].extend(result.get('not_found', {}).get('movies', []))
        
        # 批量评分
        if to_rate:
            batch_size = 100
            for i in range(0, len(to_rate), batch_size):
                batch = to_rate[i:i+batch_size]
                result = self.rate_movies(batch)
                if result:
                    results['ratings_added'] += result.get('added', {}).get('movies', 0)
        
        return results
    
    def logout(self) -> bool:
        """清除Trakt凭证"""
        self.access_token = None
        self.refresh_token = None
        self.token_expires = None
        return True


# 保持向后兼容：导出 TraktClient 类
TraktClient = TraktAdapter

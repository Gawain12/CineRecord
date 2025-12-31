"""
Sync module for Trakt to Douban synchronization.
Marks movies from Trakt as watched on Douban.
"""

import requests
import re
import logging
import time
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class DoubanSyncClient:
    """Client for syncing watch status to Douban"""
    
    BASE_URL = "https://movie.douban.com"
    
    def __init__(self, cookie: str, user_id: str = None):
        self.cookie = cookie
        self.user_id = user_id
        self.headers = {
            'Cookie': cookie,
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://movie.douban.com/',
        }
    
    def _get_ck(self) -> Optional[str]:
        """Extract ck token from cookie for CSRF protection"""
        match = re.search(r'ck=([^;]+)', self.cookie)
        return match.group(1) if match else None
    
    def _get_frodo_signature(self, method: str, url: str) -> dict:
        """Generate Frodo API signature for Douban"""
        import hmac
        import hashlib
        import base64
        import urllib.parse
        
        HMAC_KEY = "bf7dddc7c9cfe6f7"
        parsed_url = urllib.parse.urlparse(url)
        path = parsed_url.path
        timestamp = str(int(time.time()))
        
        string_to_sign = f"{method.upper()}&{urllib.parse.quote(path, safe='')}&{timestamp}"
        
        hmac_sha1 = hmac.new(
            HMAC_KEY.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1
        ).digest()
        
        sig_base64 = base64.b64encode(hmac_sha1).decode('utf-8')
        return {"_sig": sig_base64, "_ts": timestamp}
    
    def search_movie_by_imdb(self, imdb_id: str) -> Optional[str]:
        """
        Search for a movie on Douban by IMDB ID using Frodo API.
        
        Returns:
            Douban movie ID if found, None otherwise
        """
        if not imdb_id:
            return None
            
        try:
            # Method 1: Use Frodo API (most reliable for IMDB ID)
            API_KEY = "0dad551ec0f84ed02907ff5c42e8ec70"
            FRODO_USER_AGENT = 'api-client/1 com.douban.frodo/7.25.0(213) Android/28 product/Pixel 3 vendor/Google model/Pixel 3 rom/android network/wifi platform/mobile nd/1'
            
            frodo_url = "https://frodo.douban.com/api/v2/search/weixin"
            sig_data = self._get_frodo_signature("GET", frodo_url)
            
            frodo_params = {
                "q": imdb_id,
                "apikey": API_KEY,
                "_sig": sig_data["_sig"],
                "_ts": sig_data["_ts"]
            }
            
            frodo_headers = {
                'Cookie': self.cookie,
                'User-Agent': FRODO_USER_AGENT,
                'Accept': 'application/json',
            }
            
            resp = requests.get(frodo_url, params=frodo_params, headers=frodo_headers, timeout=10)
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    items = data.get('items', [])
                    for item in items:
                        target = item.get('target', {})
                        target_type = item.get('target_type')
                        if target_type == 'movie':
                            douban_id = target.get('id')
                            if douban_id:
                                return str(douban_id)
                except Exception as e:
                    logger.debug(f"Frodo API parse error: {e}")
            
            # Method 2: Fallback to web search (less reliable)
            search_url = f"https://movie.douban.com/j/subject_suggest?q={imdb_id}"
            resp = requests.get(search_url, headers=self.headers, timeout=10)
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data and len(data) > 0:
                        return data[0].get('id')
                except:
                    pass
            
            # Method 3: Direct search.douban.com
            search_url = f"https://search.douban.com/movie/subject_search?search_text={imdb_id}"
            resp = requests.get(search_url, headers=self.headers, timeout=10, allow_redirects=True)
            
            if resp.status_code == 200:
                match = re.search(r'subject/(\d+)', resp.text)
                if match:
                    return match.group(1)
            
            return None
        except Exception as e:
            logger.error(f"Error searching for IMDB {imdb_id}: {e}")
            return None
    
    def mark_as_watched(self, douban_id: str, rating: int = None, comment: str = None) -> bool:
        """
        Mark a movie as watched on Douban.
        
        Args:
            douban_id: Douban movie ID
            rating: Optional rating (1-5 stars, will be converted from 1-10)
            comment: Optional short comment
            
        Returns:
            True if successful, False otherwise
        """
        try:
            ck = self._get_ck()
            if not ck:
                logger.error("Could not extract ck token from cookie")
                return False
            
            # Convert 10-point rating to 5-star (1-2=1, 3-4=2, 5-6=3, 7-8=4, 9-10=5)
            stars = None
            if rating:
                stars = min(5, max(1, (int(rating) + 1) // 2))
            
            # Build form data
            data = {
                'ck': ck,
                'interest': 'collect',  # 'collect' = watched, 'wish' = want to watch
                'foldcollect': 'U',
            }
            if stars:
                data['rating'] = stars
            if comment:
                data['comment'] = comment[:140]  # Max 140 chars
            
            url = f"{self.BASE_URL}/j/subject/{douban_id}/interest"
            
            resp = requests.post(url, data=data, headers=self.headers, timeout=10)
            
            if resp.status_code == 200:
                result = resp.json()
                if result.get('r') == 0:
                    return True
                else:
                    logger.warning(f"Douban returned error: {result}")
                    return False
            else:
                logger.error(f"HTTP {resp.status_code}: {resp.text[:200]}")
                return False
                
        except Exception as e:
            logger.error(f"Error marking {douban_id} as watched: {e}")
            return False
    
    def get_watched_movies(self) -> List[str]:
        """
        Get list of Douban IDs for movies already marked as watched.
        
        Returns:
            List of Douban movie IDs
        """
        if not self.user_id:
            return []
        
        watched_ids = []
        start = 0
        
        while True:
            url = f"{self.BASE_URL}/people/{self.user_id}/collect"
            params = {'start': start, 'sort': 'time', 'mode': 'list'}
            
            try:
                resp = requests.get(url, params=params, headers=self.headers, timeout=10)
                if resp.status_code != 200:
                    break
                
                # Extract movie IDs from page
                ids = re.findall(r'subject/(\d+)', resp.text)
                if not ids:
                    break
                
                watched_ids.extend(ids)
                
                # Check for next page
                if 'class="next"' not in resp.text:
                    break
                
                start += 15
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Error fetching watched movies: {e}")
                break
        
        return list(set(watched_ids))


def sync_trakt_to_douban(
    trakt_movies: List[Dict],
    douban_cookie: str,
    douban_user_id: str = None,
    with_ratings: bool = True,
    socketio=None
) -> Dict:
    """
    Sync movies from Trakt to Douban.
    
    Args:
        trakt_movies: List of movie records from Trakt with 'IMDb ID', 'Your Rating', etc.
        douban_cookie: Douban login cookie
        douban_user_id: Douban user ID for checking existing watched movies
        with_ratings: If True, also sync ratings (if available)
        socketio: Optional SocketIO for progress updates
        
    Returns:
        dict: Summary of sync results
    """
    client = DoubanSyncClient(douban_cookie, douban_user_id)
    
    results = {
        'synced': 0,
        'already_watched': 0,
        'not_found': 0,
        'failed': 0,
        'details': []
    }
    
    # Get already watched movies on Douban
    if socketio:
        socketio.emit('log', {'message': '📥 获取豆瓣已看列表...', 'type': 'info'})
    
    existing_watched = set()
    if douban_user_id:
        existing_watched = set(client.get_watched_movies())
    
    total = len(trakt_movies)
    
    if socketio:
        socketio.emit('log', {'message': f'📊 开始同步 {total} 部电影到豆瓣...', 'type': 'info'})
    
    for i, movie in enumerate(trakt_movies):
        imdb_id = movie.get('IMDb ID')
        title = movie.get('Title', 'Unknown')
        rating = movie.get('Your Rating') if with_ratings else None
        
        if not imdb_id:
            results['not_found'] += 1
            continue
        
        # Search for Douban ID
        douban_id = client.search_movie_by_imdb(imdb_id)
        
        if not douban_id:
            results['not_found'] += 1
            results['details'].append({'title': title, 'status': 'not_found'})
            continue
        
        # Check if already watched
        if douban_id in existing_watched:
            results['already_watched'] += 1
            continue
        
        # Mark as watched
        success = client.mark_as_watched(douban_id, rating=rating)
        
        if success:
            results['synced'] += 1
            results['details'].append({'title': title, 'status': 'synced', 'rating': rating})
        else:
            results['failed'] += 1
            results['details'].append({'title': title, 'status': 'failed'})
        
        # Rate limiting - be gentle with Douban
        time.sleep(1)
        
        # Progress update every 10 movies
        if socketio and (i + 1) % 10 == 0:
            socketio.emit('log', {
                'message': f'⏳ 同步进度: {i + 1}/{total}',
                'type': 'info'
            })
    
    if socketio:
        socketio.emit('log', {
            'message': f'✅ 同步完成: {results["synced"]} 新增, {results["already_watched"]} 已存在, {results["not_found"]} 未找到',
            'type': 'success'
        })
    
    return results

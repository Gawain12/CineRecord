"""
Letterboxd URI to Multi-Platform IDs 映射工具
用于从Letterboxd URI获取各平台ID (IMDb, TMDB, Douban, Trakt等)
"""
import requests
from bs4 import BeautifulSoup
import json
import os
import time
from typing import Optional, Dict
from urllib.parse import urlparse, urljoin


class LetterboxdIDMapper:
    """Letterboxd URI -> Multi-Platform IDs 映射器"""
    
    def __init__(self, cache_file: str = None):
        """
        初始化映射器
        
        Args:
            cache_file: 映射缓存文件路径
        """
        if cache_file is None:
            base_dir = os.path.dirname(__file__)
            # 优先使用用户可能手动维护的同目录缓存文件
            local_cache = os.path.join(base_dir, 'letterboxd_platform_mapping.json')
            data_dir = os.path.join(base_dir, '..', '..', 'data')
            default_cache = os.path.join(data_dir, 'letterboxd_platform_mapping.json')
            cache_file = local_cache if os.path.exists(local_cache) else default_cache
        
        self.cache_file = cache_file
        self.mapping = self._load_mapping()
        # 额外加载 Node 版爬虫产生的 cache 作为种子，避免重复抓取
        self._merge_external_cache()
    
    def _load_mapping(self) -> Dict[str, Dict[str, Optional[str]]]:
        """
        加载映射缓存
        
        Returns:
            Dict[letterboxd_uri, Dict[platform_id, id_value]]
            例如: {
                "https://letterboxd.com/film/inception/": {
                    "imdb_id": "tt1375666",
                    "tmdb_id": "27205",
                    "last_updated": "2026-01-04"
                }
            }
        """
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _merge_external_cache(self):
        """合并 Node 脚本生成的 cache，优先保留现有记录。"""
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            external_cache = os.path.join(
                base_dir,
                'scrapers',
                'letterboxd-csv-imdb-tmdb-mapper',
                'cache',
                'cache.json',
            )
            if os.path.exists(external_cache):
                with open(external_cache, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # cache.json 结构: key -> "type|tmdb|imdb"
                for uri, value in data.items():
                    if uri in self.mapping:
                        continue
                    parts = value.split('|')
                    if len(parts) == 3:
                        _, tmdb_id, imdb_id = parts
                        self.mapping[uri] = {
                            'tmdb_id': tmdb_id or None,
                            'imdb_id': imdb_id or None,
                            'last_updated': None,
                        }
                if data:
                    self._save_mapping()
        except Exception:
            # 静默失败，外部 cache 非关键路径
            pass

    def _save_mapping(self):
        """保存映射缓存"""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.mapping, f, indent=2, ensure_ascii=False)
    
    def get_platform_ids(self, letterboxd_uri: str) -> Dict[str, Optional[str]]:
        """
        从Letterboxd URI获取多平台IDs
        
        Args:
            letterboxd_uri: Letterboxd电影URI
            
        Returns:
            Dict包含各平台ID: {
                'imdb_id': 'tt1375666',
                'tmdb_id': '27205',
                'last_updated': '2026-01-04'
            }
        """
        if not letterboxd_uri:
            return {}

        original_uri = str(letterboxd_uri).strip()

        # 先检查原始输入是否已有缓存
        if original_uri in self.mapping:
            return self.mapping[original_uri]

        # 规范化 URI（短链/缺协议/日记链接）
        letterboxd_uri = self._normalize_uri(original_uri, resolve_shortlink=True)

        # 检查缓存（使用规范化后的键）
        if letterboxd_uri in self.mapping:
            if original_uri != letterboxd_uri:
                self.mapping[original_uri] = self.mapping[letterboxd_uri]
                self._save_mapping()
            return self.mapping[letterboxd_uri]

        # 准备User-Agent列表
        ids = {}
        # 不跨线程共享 Session，逐次创建以避免竞争
        session = requests.Session()
        
        # 使用经过验证的 "Proven Headers" (来自开源Node脚本)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1"
        }

        try:
             # print(f"[Mapper] Requesting: {letterboxd_uri}")
             response = session.get(letterboxd_uri, headers=headers, timeout=6, allow_redirects=True)
             
             if response.status_code == 200:
                 text = response.text
                 soup = BeautifulSoup(text, 'html.parser')
                 import re
                 
                 # 使用 CSS Selectors (复刻 cheerio 逻辑)
                 tmdb_link = soup.select_one('.micro-button[data-track-action="TMDB"]')
                 imdb_link = soup.select_one('.micro-button[data-track-action="IMDb"]')
                 # JSON-LD 里通常包含 sameAs -> IMDb
                 ld_json = soup.select_one('script[type="application/ld+json"]')

                 # 1. TMDB
                 if tmdb_link and tmdb_link.has_attr('href'):
                     href = tmdb_link['href']
                     match = re.search(r'/(movie|tv)/(\d+)/', href)
                     if match:
                         # ids['tmdb_type'] = match.group(1)
                         ids['tmdb_id'] = match.group(2)
                 
                 # 2. IMDb
                 if imdb_link and imdb_link.has_attr('href'):
                     href = imdb_link['href']
                     match = re.search(r'/title/(tt\d+)/?', href)
                     if match:
                         ids['imdb_id'] = match.group(1)
                 elif ld_json:
                     try:
                         data = json.loads(ld_json.text)
                         same_as = data.get('sameAs') or []
                         if isinstance(same_as, str):
                             same_as = [same_as]
                         for link in same_as:
                             match = re.search(r'/title/(tt\d+)/?', link)
                             if match:
                                 ids['imdb_id'] = match.group(1)
                                 break
                     except Exception:
                         pass

                 if ids:
                     self.update_cache(letterboxd_uri, ids)
                     return ids
             else:
                 # print(f"[Mapper] Status {response.status_code}")
                 pass
         
        except Exception as e:
            # print(f"[Mapper] Error: {e}")
            pass
        
        return ids

    def _normalize_uri(self, uri: str, resolve_shortlink: bool = True) -> str:
        """规范化 URI，处理 boxd.it 短链并补全域名。"""
        if not uri:
            return ''

        # 已有缓存时直接返回
        if uri in self.mapping:
            return uri
        uri = str(uri).strip()

        parsed = urlparse(uri)
        if not parsed.scheme:
            # 没有协议，补全 https
            uri = f"https://{uri.lstrip('/')}"
            parsed = urlparse(uri)

        # boxd.it 短链解析
        if resolve_shortlink and 'boxd.it' in parsed.netloc:
            try:
                resp = requests.head(uri, allow_redirects=True, timeout=8)
                final_url = resp.url
                if final_url and 'letterboxd.com' in final_url:
                    uri = final_url
                    parsed = urlparse(uri)
            except Exception:
                pass

        # 将用户日记链接规范化为影片页: /{user}/film/{slug}/ -> /film/{slug}/
        path = parsed.path
        parts = [p for p in path.split('/') if p]
        if len(parts) >= 3 and parts[1] == 'film':
            slug = parts[2]
            uri = urljoin(f"{parsed.scheme}://{parsed.netloc}", f"/film/{slug}/")

        return uri


    def update_cache(self, letterboxd_uri: str, ids: dict):
        """手动更新缓存 (供外部API调用使用)"""
        if not ids: return
        from datetime import datetime
        if 'last_updated' not in ids:
            ids['last_updated'] = datetime.now().strftime('%Y-%m-%d')
        self.mapping[letterboxd_uri] = ids
        self._save_mapping()
    
    def save(self):
        """显式保存缓存到磁盘。"""
        self._save_mapping()
    
    def get_imdb_id_from_uri(self, letterboxd_uri: str) -> Optional[str]:
        """
        从Letterboxd URI获取IMDb ID (向后兼容方法)
        
        Args:
            letterboxd_uri: Letterboxd电影URI
            
        Returns:
            IMDb ID (如 tt1375666) 或 None
        """
        ids = self.get_platform_ids(letterboxd_uri)
        return ids.get('imdb_id')
    
    def batch_process(self, letterboxd_uris: list, delay: float = 1.0) -> Dict[str, Dict[str, Optional[str]]]:
        """
        批量处理Letterboxd URIs
        
        Args:
            letterboxd_uris: Letterboxd URI列表
            delay: 请求间延迟(秒)
            
        Returns:
            映射字典 {letterboxd_uri: imdb_id}
        """
        results = {}
        for uri in letterboxd_uris:
            if uri and uri not in self.mapping:
                print(f"Fetching IMDb ID for {uri}...")
                imdb_id = self.get_imdb_id_from_uri(uri)
                results[uri] = imdb_id
                if delay > 0:
                    time.sleep(delay)
            else:
                results[uri] = self.mapping.get(uri)
        
        return results


# 全局映射器实例
_mapper = None


def get_mapper() -> LetterboxdIDMapper:
    """获取全局映射器实例"""
    global _mapper
    if _mapper is None:
        _mapper = LetterboxdIDMapper()
    return _mapper

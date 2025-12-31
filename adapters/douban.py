"""
Douban Adapter - 豆瓣平台适配器
基于 scrapers/douban_scraper.py 重构
"""

import asyncio
import os
import random
import re
import math
import aiohttp
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple

from adapters.base import PlatformAdapter
from adapters.registry import AdapterRegistry
from adapters.utils.cache import IDMappingCache


@AdapterRegistry.register
class DoubanAdapter(PlatformAdapter):
    """
    豆瓣平台适配器
    
    认证方式: Cookie
    支持功能: 数据获取、评分同步
    """
    
    platform_id = 'douban'
    platform_name = '豆瓣'
    platform_name_en = 'Douban'
    auth_type = 'cookie'
    supports_fetch = True
    supports_sync = True
    supports_export = True
    
    # API 配置
    API_BASE = "https://m.douban.com/rexxar/api/v2"
    HEADERS_TEMPLATE = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Referer': 'https://m.douban.com/'
    }
    
    def __init__(self, logger, config: Dict[str, Any]):
        super().__init__(logger, config)
        self.cache_file = config.get('cache_file', 'data/db_imdb.csv')
        self._cache: Optional[IDMappingCache] = None
    
    @property
    def cache(self) -> IDMappingCache:
        """延迟加载缓存"""
        if self._cache is None:
            self._cache = IDMappingCache(self.cache_file)
        return self._cache
    
    def get_config_keys(self) -> List[str]:
        return ['douban_user_id', 'douban_cookie']
    
    def test_connection(self) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """测试豆瓣Cookie是否有效"""
        user_id = self.config.get('douban_user_id')
        cookie = self.config.get('douban_cookie')
        
        if not user_id or not cookie:
            return False, "请先配置用户ID和Cookie", None
        
        # 使用同步请求测试
        import requests
        headers = {**self.HEADERS_TEMPLATE, 'Cookie': cookie}
        
        try:
            # 测试访问一个已知电影页面
            test_url = "https://m.douban.com/movie/subject/1298697/"
            resp = requests.get(test_url, headers=headers, timeout=10, verify=False)
            
            if resp.status_code == 200 and 'IMDb' in resp.text:
                return True, None, {
                    'user_id': user_id,
                    'status': 'connected'
                }
            else:
                return False, "Cookie无效或已过期", None
                
        except Exception as e:
            return False, f"连接失败: {str(e)}", None
    
    def fetch_data(self, output_path: str) -> Optional[List[Dict[str, Any]]]:
        """获取豆瓣电影数据"""
        user_id = self.config.get('douban_user_id')
        cookie = self.config.get('douban_cookie')
        
        if not user_id or not cookie:
            self.logger.error("缺少用户ID或Cookie配置")
            return None
        
        # 运行异步抓取
        return asyncio.run(self._scrape_async(user_id, cookie, output_path))
    
    async def _scrape_async(self, user_id: str, cookie: str, output_path: str) -> Optional[List[Dict[str, Any]]]:
        """异步抓取豆瓣数据"""
        headers = {**self.HEADERS_TEMPLATE, 'Cookie': cookie}
        api_url = f"{self.API_BASE}/user/{user_id}/interests"
        
        async with aiohttp.ClientSession(headers=headers) as session:
            # 验证Cookie
            self.logger.log("验证Cookie...", 'info')
            if not await self._validate_cookie(session):
                self.logger.error("Cookie无效或已过期。")
                return None
            self.logger.success("Cookie验证成功。")
            
            # 加载缓存
            self.logger.info(f"已加载 {len(self.cache)} 条IMDb缓存。")
            
            # 加载已有数据
            existing_ids = self._load_existing_ids(output_path)
            if existing_ids:
                self.logger.info(f"发现 {len(existing_ids)} 条已有记录，将进行增量更新。")
            
            # 获取总数
            first_page = await self._fetch_page(session, api_url, 0, 1)
            if not first_page or 'total' not in first_page:
                self.logger.error("无法获取电影总数。")
                return None
            
            total_movies = first_page.get('total', 0)
            page_size = 50
            total_pages = math.ceil(total_movies / page_size)
            self.logger.info(f"共发现 {total_movies} 条电影记录。")
            
            # 获取新数据
            new_interests = []
            for page_num in range(total_pages):
                self.logger.progress(page_num, total_pages, f"获取列表 {page_num+1}/{total_pages}")
                page_data = await self._fetch_page(session, api_url, page_num * page_size, page_size)
                if not page_data or not page_data.get('interests'):
                    break
                
                should_stop = False
                for interest in page_data['interests']:
                    if interest.get('subject', {}).get('id') in existing_ids:
                        should_stop = True
                        break
                    new_interests.append(interest)
                if should_stop:
                    break
            
            self.logger.progress(total_pages, total_pages, "列表获取完成")
            
            if not new_interests:
                self.logger.success("数据已是最新。")
                return self._load_existing_data(output_path)
            
            self.logger.info(f"发现 {len(new_interests)} 条新记录，开始处理...")
            new_interests.reverse()
            
            # 处理数据并获取IMDB ID
            tasks = [self._process_interest(session, i) for i in new_interests]
            new_movies = []
            for i, f in enumerate(asyncio.as_completed(tasks)):
                new_movies.append(await f)
                self.logger.progress(i + 1, len(tasks), f"处理详情 {i+1}/{len(tasks)}")
            
            # 保存
            self.logger.info("保存文件中...")
            self.cache.save()
            
            df_new = pd.DataFrame(new_movies)
            df_existing = pd.DataFrame()
            if os.path.exists(output_path) and existing_ids:
                df_existing = pd.read_csv(output_path, dtype=str, encoding='utf-8-sig')
            
            df_final = pd.concat([df_new, df_existing], ignore_index=True)
            cols = ['Const', 'Your Rating', 'Date Rated', 'Title', 'Directors', 'Actors', 
                    'Country', 'Year', 'Genres', 'Douban Rating', 'Num Votes', 'MyComment', 
                    'URL', 'Cover URL', 'douban_id']
            df_final = df_final.reindex(columns=cols)
            df_final.drop_duplicates(subset=['douban_id'], keep='first', inplace=True)
            df_final.sort_values(by='Date Rated', ascending=False, inplace=True)
            df_final.to_csv(output_path, index=False, encoding='utf-8-sig')
            
            self.logger.success(f"成功！新增 {len(df_new)} 条，总计 {len(df_final)} 条。")
            return self.clean_df_for_json(df_final)
    
    async def _validate_cookie(self, session: aiohttp.ClientSession) -> bool:
        """验证Cookie有效性"""
        try:
            async with session.get("https://m.douban.com/movie/subject/1298697/", 
                                   verify_ssl=False, timeout=30) as resp:
                if resp.status != 200:
                    return False
                text = await resp.text()
                return 'IMDb' in text
        except:
            return False
    
    async def _fetch_page(self, session: aiohttp.ClientSession, url: str, 
                         start: int, size: int = 50, retries: int = 3) -> Optional[Dict]:
        """获取分页数据"""
        params = {"type": "movie", "status": "done", "count": size, "start": start, "for_mobile": 1}
        
        for i in range(retries):
            await asyncio.sleep(random.uniform(1.0, 2.0))
            try:
                async with session.get(url, params=params, verify_ssl=False, timeout=30) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        self.logger.error(f"请求失败 (尝试 {i+1}/{retries}): HTTP状态码 {resp.status}")
            except Exception as e:
                self.logger.error(f"请求异常 (尝试 {i+1}/{retries}): {e}")
        return None
    
    async def _process_interest(self, session: aiohttp.ClientSession, interest: Dict) -> Dict:
        """处理单条记录"""
        subject = interest.get('subject', {})
        rating = interest.get('rating', {})
        subtitle = subject.get('card_subtitle', '')
        parts = subtitle.split('/')
        country = parts[1].strip() if len(parts) > 1 else ''
        actors = ", ".join([a['name'] for a in subject.get('actors', [])[:3]])
        
        data = {
            'Const': None,
            'Your Rating': rating.get('value', 0) if rating else 0,
            'Date Rated': interest.get('create_time', '').split(' ')[0],
            'Title': subject.get('title'),
            'Directors': ", ".join([d['name'] for d in subject.get('directors', [])]),
            'Actors': actors,
            'Country': country,
            'Year': subject.get('year'),
            'Genres': ", ".join(subject.get('genres', [])),
            'Douban Rating': subject.get('rating', {}).get('value', 0),
            'Num Votes': subject.get('rating', {}).get('count', 0),
            'MyComment': interest.get('comment', ''),
            'URL': subject.get('url'),
            'Cover URL': subject.get('cover_url'),
            'douban_id': subject.get('id')
        }
        
        # 获取IMDB ID
        douban_id = data.get('douban_id')
        if douban_id:
            cached_imdb = self.cache.get_imdb_id(douban_id)
            if cached_imdb:
                data['Const'] = cached_imdb
            else:
                imdb_id = await self._fetch_imdb_id(session, data.get('URL'))
                if imdb_id:
                    data['Const'] = imdb_id
                    self.cache.set(douban_id, imdb_id)
        
        return data
    
    async def _fetch_imdb_id(self, session: aiohttp.ClientSession, url: str, 
                            retries: int = 3) -> Optional[str]:
        """从豆瓣页面获取IMDB ID"""
        if not url:
            return None
        
        for _ in range(retries):
            await asyncio.sleep(random.uniform(0.5, 1.5))
            try:
                async with session.get(url, verify_ssl=False, timeout=30) as resp:
                    if resp.status == 404:
                        return None
                    resp.raise_for_status()
                    html = await resp.text()
                    match = re.search(r'IMDb:</span>\s*(tt\d+)', html)
                    return match.group(1) if match else None
            except:
                await asyncio.sleep(3)
        return None
    
    def _load_existing_ids(self, output_path: str) -> set:
        """加载已有记录的ID"""
        if not os.path.exists(output_path):
            return set()
        try:
            df = pd.read_csv(output_path, dtype={'douban_id': str}, usecols=['douban_id'])
            return set(df['douban_id'].dropna())
        except:
            return set()
    
    def _load_existing_data(self, output_path: str) -> List[Dict[str, Any]]:
        """加载已有数据"""
        if not os.path.exists(output_path):
            return []
        try:
            df = pd.read_csv(output_path)
            return self.clean_df_for_json(df)
        except:
            return []
    
    def logout(self) -> bool:
        """清除豆瓣凭证"""
        return True


# 向后兼容：提供 run_scraper 函数
def run_scraper(user_id: str, cookie: str, output_path: str, socketio) -> Optional[List[Dict]]:
    """
    向后兼容的入口函数
    
    保持与旧 scrapers/douban_scraper.py 相同的接口
    """
    from adapters.logger import SocketLogger
    
    logger = SocketLogger(socketio, 'douban')
    config = {
        'douban_user_id': user_id,
        'douban_cookie': cookie,
        'cache_file': 'data/db_imdb.csv'
    }
    
    adapter = DoubanAdapter(logger, config)
    return adapter.fetch_data(output_path)

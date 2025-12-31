"""
ID Mapping Cache
豆瓣 ID ↔ IMDB ID 双向映射缓存
"""

import os
import pandas as pd
from typing import Optional, Dict


class IDMappingCache:
    """
    电影ID映射缓存
    
    支持 豆瓣ID <-> IMDB ID 的双向查询
    数据存储在 CSV 文件中
    """
    
    def __init__(self, cache_file: str):
        """
        初始化缓存
        
        Args:
            cache_file: 缓存文件路径 (CSV)
        """
        self.cache_file = cache_file
        self._douban_to_imdb: Dict[str, str] = {}
        self._imdb_to_douban: Dict[str, str] = {}
        self._dirty = False  # 是否有未保存的更改
        self._load()
    
    def _load(self):
        """从文件加载缓存"""
        if not os.path.exists(self.cache_file):
            return
        
        try:
            df = pd.read_csv(self.cache_file, dtype=str)
            
            # 兼容旧格式：id -> douban_id
            if 'douban_id' not in df.columns and 'id' in df.columns:
                df.rename(columns={'id': 'douban_id'}, inplace=True)
            
            if 'douban_id' not in df.columns or 'imdb' not in df.columns:
                return
            
            df.dropna(subset=['douban_id', 'imdb'], inplace=True)
            df.drop_duplicates(subset=['douban_id'], keep='last', inplace=True)
            df.drop_duplicates(subset=['imdb'], keep='last', inplace=True)
            
            # 构建双向映射
            for _, row in df.iterrows():
                douban_id = str(row['douban_id'])
                imdb_id = str(row['imdb'])
                self._douban_to_imdb[douban_id] = imdb_id
                self._imdb_to_douban[imdb_id] = douban_id
                
        except Exception as e:
            print(f"Warning: Failed to load ID cache: {e}")
    
    def get_imdb_id(self, douban_id: str) -> Optional[str]:
        """通过豆瓣ID获取IMDB ID"""
        return self._douban_to_imdb.get(str(douban_id))
    
    def get_douban_id(self, imdb_id: str) -> Optional[str]:
        """通过IMDB ID获取豆瓣ID"""
        return self._imdb_to_douban.get(str(imdb_id))
    
    def set(self, douban_id: str, imdb_id: str):
        """设置映射关系"""
        douban_id = str(douban_id)
        imdb_id = str(imdb_id)
        
        self._douban_to_imdb[douban_id] = imdb_id
        self._imdb_to_douban[imdb_id] = douban_id
        self._dirty = True
    
    def has_douban_id(self, douban_id: str) -> bool:
        """检查是否有此豆瓣ID的映射"""
        return str(douban_id) in self._douban_to_imdb
    
    def has_imdb_id(self, imdb_id: str) -> bool:
        """检查是否有此IMDB ID的映射"""
        return str(imdb_id) in self._imdb_to_douban
    
    def save(self):
        """保存缓存到文件"""
        if not self._dirty:
            return
        
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            # 构建 DataFrame
            data = [
                {'douban_id': k, 'imdb': v}
                for k, v in self._douban_to_imdb.items()
            ]
            df = pd.DataFrame(data)
            df.to_csv(self.cache_file, index=False, encoding='utf-8')
            self._dirty = False
        except Exception as e:
            print(f"Warning: Failed to save ID cache: {e}")
    
    def __len__(self) -> int:
        """返回缓存的映射数量"""
        return len(self._douban_to_imdb)
    
    def __contains__(self, item: str) -> bool:
        """检查ID是否在缓存中（任一方向）"""
        return item in self._douban_to_imdb or item in self._imdb_to_douban

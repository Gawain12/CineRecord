"""
CineCSV Standard - 标准化电影记录格式
使用 IMDb ID 作为主键，兼容主流平台导出格式
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
import pandas as pd
from datetime import datetime


@dataclass
class CineRecord:
    """
    CineCSV 标准电影记录
    
    以 IMDb ID 为主键，兼容以下平台：
    - IMDb: Your Ratings export (Const 列)
    - Letterboxd: diary.csv (通过 TMDb 映射)
    - Trakt: API 输出 (IMDb ID 字段)
    - 豆瓣: 页面抓取 (IMDb 信息)
    
    字段命名规范：
    - 使用 snake_case
    - ID 字段统一格式: {platform}_id
    """
    
    # ========== 主键 ==========
    imdb_id: str  # tt1234567 格式，必填
    
    # ========== 核心字段 ==========
    title: str
    year: Optional[int] = None
    rating: Optional[float] = None  # 1-10 评分
    date_rated: Optional[str] = None  # YYYY-MM-DD
    
    # ========== 平台 ID 映射 ==========
    tmdb_id: Optional[int] = None
    douban_id: Optional[str] = None
    trakt_id: Optional[int] = None
    letterboxd_uri: Optional[str] = None  # letterboxd.com/film/xxx
    neodb_id: Optional[str] = None
    wikidata_id: Optional[str] = None  # Q12345 格式
    
    # ========== 元数据 ==========
    original_title: Optional[str] = None  # 原始标题
    directors: Optional[str] = None  # 逗号分隔
    genres: Optional[str] = None  # 逗号分隔
    runtime: Optional[int] = None  # 分钟
    cover_url: Optional[str] = None
    
    # ========== 用户数据 ==========
    comment: Optional[str] = None  # 用户短评
    watch_date: Optional[str] = None  # 观看日期 (与标记日期可能不同)
    rewatch: bool = False  # 是否重看
    tags: Optional[str] = None  # 逗号分隔标签
    
    # ========== 评分详情 ==========
    platform_rating: Optional[float] = None  # 平台均分
    vote_count: Optional[int] = None  # 评分人数
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    def to_csv_row(self) -> Dict[str, Any]:
        """转换为 CSV 行格式（排除 None 值）"""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CineRecord':
        """从字典创建，自动过滤未知字段"""
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        
        # imdb_id 是必填字段
        if 'imdb_id' not in filtered or not filtered['imdb_id']:
            raise ValueError("imdb_id is required")
        
        return cls(**filtered)
    
    @classmethod
    def from_imdb_export(cls, row: Dict[str, Any]) -> 'CineRecord':
        """从 IMDb CSV 导出行创建"""
        return cls(
            imdb_id=row.get('Const') or row.get('imdb_id'),
            title=row.get('Title') or row.get('title'),
            year=_safe_int(row.get('Year') or row.get('year')),
            rating=_safe_float(row.get('Your Rating') or row.get('rating')),
            date_rated=row.get('Date Rated') or row.get('date_rated'),
            genres=row.get('Genres') or row.get('genres'),
            directors=row.get('Directors') or row.get('directors'),
            runtime=_safe_int(row.get('Runtime (mins)') or row.get('runtime')),
        )
    
    @classmethod
    def from_letterboxd_export(cls, row: Dict[str, Any], tmdb_id: int = None) -> 'CineRecord':
        """从 Letterboxd CSV 导出行创建 (需要通过 TMDB 转换 ID)"""
        # Letterboxd 使用 TMDb ID，需要额外查询 IMDb ID
        letterboxd_rating = row.get('Rating')
        rating = _safe_float(letterboxd_rating) * 2 if letterboxd_rating else None  # 0.5-5 -> 1-10
        
        return cls(
            imdb_id='',  # 需要通过 TMDB 填充
            title=row.get('Name') or row.get('Title'),
            year=_safe_int(row.get('Year')),
            rating=rating,
            date_rated=row.get('Watched Date') or row.get('Date'),
            tmdb_id=tmdb_id,
            letterboxd_uri=row.get('Letterboxd URI'),
            rewatch=row.get('Rewatch') == 'Yes',
            tags=row.get('Tags'),
        )
    
    @classmethod
    def from_trakt_export(cls, row: Dict[str, Any]) -> 'CineRecord':
        """从 Trakt API 输出创建"""
        return cls(
            imdb_id=row.get('IMDb ID') or row.get('Const') or row.get('imdb_id'),
            title=row.get('Title') or row.get('title'),
            year=_safe_int(row.get('Year') or row.get('year')),
            rating=_safe_float(row.get('Your Rating') or row.get('rating')),
            date_rated=row.get('Date Rated') or row.get('date_rated'),
            tmdb_id=_safe_int(row.get('TMDB ID') or row.get('tmdb_id')),
            trakt_id=_safe_int(row.get('Trakt ID') or row.get('trakt_id')),
            genres=row.get('Genres') or row.get('genres'),
            runtime=_safe_int(row.get('Runtime') or row.get('runtime')),
        )
    
    @classmethod
    def from_douban_export(cls, row: Dict[str, Any]) -> 'CineRecord':
        """从豆瓣数据创建"""
        return cls(
            imdb_id=row.get('Const') or row.get('imdb_id') or '',
            title=row.get('Title') or row.get('title'),
            year=_safe_int(row.get('Year') or row.get('year')),
            rating=_safe_float(row.get('Your Rating') or row.get('rating')),
            date_rated=row.get('Date Rated') or row.get('date_rated'),
            douban_id=str(row.get('douban_id')) if row.get('douban_id') else None,
            directors=row.get('Directors') or row.get('directors'),
            genres=row.get('Genres') or row.get('genres'),
            platform_rating=_safe_float(row.get('Douban Rating')),
            vote_count=_safe_int(row.get('Num Votes')),
            cover_url=row.get('Cover URL') or row.get('cover_url'),
            comment=row.get('MyComment') or row.get('comment'),
        )


def _safe_int(value) -> Optional[int]:
    """安全转换为整数"""
    if value is None or value == '':
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _safe_float(value) -> Optional[float]:
    """安全转换为浮点数"""
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ========== CSV 列定义 ==========

# 核心列 - 导出时必须包含
CINE_CORE_COLUMNS = [
    'imdb_id', 'title', 'year', 'rating', 'date_rated'
]

# 平台 ID 列
CINE_ID_COLUMNS = [
    'imdb_id', 'tmdb_id', 'douban_id', 'trakt_id', 'letterboxd_uri', 'neodb_id'
]

# 完整列 - 包含所有元数据
CINE_FULL_COLUMNS = [
    'imdb_id', 'title', 'year', 'rating', 'date_rated',
    'tmdb_id', 'douban_id', 'trakt_id', 'letterboxd_uri',
    'original_title', 'directors', 'genres', 'runtime', 'cover_url',
    'comment', 'watch_date', 'rewatch', 'tags',
    'platform_rating', 'vote_count'
]

# IMDb 导出兼容列名映射
IMDB_COLUMN_MAP = {
    'Const': 'imdb_id',
    'Title': 'title',
    'Year': 'year',
    'Your Rating': 'rating',
    'Date Rated': 'date_rated',
    'Genres': 'genres',
    'Directors': 'directors',
    'Runtime (mins)': 'runtime',
}

# Letterboxd 导出兼容列名映射
LETTERBOXD_COLUMN_MAP = {
    'Name': 'title',
    'Year': 'year',
    'Rating': 'rating',  # 需要 *2 转换
    'Watched Date': 'date_rated',
    'Letterboxd URI': 'letterboxd_uri',
    'Rewatch': 'rewatch',
    'Tags': 'tags',
}


def normalize_dataframe(df: pd.DataFrame, source: str = 'auto') -> pd.DataFrame:
    """
    将任意来源的 DataFrame 规范化为 CineCSV 格式
    
    Args:
        df: 输入 DataFrame
        source: 数据来源 ('imdb', 'letterboxd', 'trakt', 'douban', 'auto')
    
    Returns:
        规范化后的 DataFrame
    """
    # 自动检测来源
    if source == 'auto':
        if 'Const' in df.columns:
            source = 'imdb'
        elif 'Letterboxd URI' in df.columns or 'Name' in df.columns:
            source = 'letterboxd'
        elif 'Trakt ID' in df.columns:
            source = 'trakt'
        elif 'douban_id' in df.columns:
            source = 'douban'
    
    # 应用列名映射
    if source == 'imdb':
        df = df.rename(columns=IMDB_COLUMN_MAP)
    elif source == 'letterboxd':
        df = df.rename(columns=LETTERBOXD_COLUMN_MAP)
        # 转换评分
        if 'rating' in df.columns:
            df['rating'] = df['rating'].apply(lambda x: x * 2 if pd.notna(x) else None)
    
    # 确保 imdb_id 列存在
    if 'imdb_id' not in df.columns:
        df['imdb_id'] = None
    
    return df


def export_cinecsv(records: List[CineRecord], output_path: str, 
                   columns: List[str] = None) -> None:
    """
    导出为 CineCSV 格式
    
    Args:
        records: CineRecord 列表
        output_path: 输出文件路径
        columns: 要导出的列（默认为核心列）
    """
    if columns is None:
        columns = CINE_CORE_COLUMNS
    
    data = [r.to_dict() for r in records]
    df = pd.DataFrame(data)
    
    # 只保留指定列
    existing_cols = [c for c in columns if c in df.columns]
    df = df[existing_cols]
    
    df.to_csv(output_path, index=False, encoding='utf-8-sig')

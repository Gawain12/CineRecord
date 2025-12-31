"""
Platform Adapter Base Class
定义所有平台适配器的统一接口
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
import pandas as pd


@dataclass
class MovieRecord:
    """标准化的电影记录，各平台数据转换为此格式"""
    title: str
    year: Optional[int] = None
    rating: Optional[float] = None  # 1-10 评分
    date_rated: Optional[str] = None  # YYYY-MM-DD
    
    # 各平台ID
    imdb_id: Optional[str] = None      # tt1234567
    douban_id: Optional[str] = None    # 纯数字
    trakt_id: Optional[int] = None
    tmdb_id: Optional[int] = None
    
    # 可选元数据
    url: Optional[str] = None
    cover_url: Optional[str] = None
    directors: Optional[str] = None
    genres: Optional[str] = None
    comment: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，兼容现有代码"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MovieRecord':
        """从字典创建，自动过滤未知字段"""
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


class PlatformAdapter(ABC):
    """
    平台适配器抽象基类
    
    每个平台实现此接口：
    - Douban: Cookie 认证，支持获取和同步
    - IMDb: Cookie 认证，仅获取
    - Trakt: OAuth 认证，支持获取和同步
    - Letterboxd: CSV 导入/导出，无认证
    """
    
    # 平台元数据 - 子类必须设置
    platform_id: str = ''           # 唯一标识: 'douban', 'imdb', 'trakt', 'letterboxd'
    platform_name: str = ''         # 显示名称
    platform_name_en: str = ''      # 英文名称
    auth_type: str = 'none'         # 认证类型: 'cookie', 'oauth', 'csv', 'api_key', 'none'
    
    # 功能支持
    supports_fetch: bool = True     # 是否支持获取数据
    supports_sync: bool = False     # 是否支持同步评分到平台
    supports_export: bool = True    # 是否支持导出数据
    
    def __init__(self, logger, config: Dict[str, Any]):
        """
        初始化适配器
        
        Args:
            logger: 日志记录器 (SocketLogger 或 CLILogger)
            config: 配置字典，包含认证信息等
        """
        self.logger = logger
        self.config = config
    
    # ==========================================
    # 抽象方法 - 子类必须实现
    # ==========================================
    
    @abstractmethod
    def test_connection(self) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        测试平台连接
        
        Returns:
            Tuple[success, error_message, profile_info]
            - success: 连接是否成功
            - error_message: 失败时的错误信息
            - profile_info: 成功时的用户信息字典 (user_id, username, avatar 等)
        """
        pass
    
    @abstractmethod
    def fetch_data(self, output_path: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取平台数据
        
        Args:
            output_path: CSV 输出路径
            
        Returns:
            电影记录列表（字典格式），失败返回 None
        """
        pass
    
    # ==========================================
    # 可选方法 - 子类按需覆盖
    # ==========================================
    
    def sync_ratings(self, movies: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        同步评分到平台
        
        Args:
            movies: 电影记录列表
            
        Returns:
            同步结果摘要
        """
        raise NotImplementedError(f"{self.platform_name} 不支持评分同步")
    
    def logout(self) -> bool:
        """
        登出/清除凭证
        
        Returns:
            是否成功
        """
        return True
    
    def get_config_keys(self) -> List[str]:
        """
        返回此平台需要的配置键列表
        用于清理配置时
        """
        return [
            f'{self.platform_id}_user_id',
            f'{self.platform_id}_cookie',
        ]
    
    # ==========================================
    # 工具方法
    # ==========================================
    
    def get_user_id(self) -> Optional[str]:
        """获取配置中的用户ID"""
        return self.config.get(f'{self.platform_id}_user_id')
    
    def get_cookie(self) -> Optional[str]:
        """获取配置中的Cookie"""
        return self.config.get(f'{self.platform_id}_cookie')
    
    def records_to_dataframe(self, records: List[Dict[str, Any]]) -> pd.DataFrame:
        """将记录列表转换为DataFrame"""
        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)
    
    @staticmethod
    def clean_df_for_json(df: pd.DataFrame) -> List[Dict[str, Any]]:
        """将DataFrame转换为JSON安全的记录列表"""
        if df is None or df.empty:
            return []
        return df.where(pd.notnull(df), None).to_dict('records')

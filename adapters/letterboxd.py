"""
Letterboxd Adapter - Letterboxd平台适配器
处理 CSV 导入/导出
"""

import io
import pandas as pd
from typing import Optional, List, Dict, Any, Tuple

from adapters.base import PlatformAdapter
from adapters.registry import AdapterRegistry


@AdapterRegistry.register
class LetterboxdAdapter(PlatformAdapter):
    """
    Letterboxd 平台适配器
    
    认证方式: 无 (仅 CSV 导入/导出)
    支持功能: CSV导入、CSV导出
    
    注意: Letterboxd 没有公开 API，只能通过 CSV 文件交互
    """
    
    platform_id = 'letterboxd'
    platform_name = 'Letterboxd'
    platform_name_en = 'Letterboxd'
    auth_type = 'csv'
    supports_fetch = False  # 不需要网络获取
    supports_sync = False   # 不能直接同步
    supports_export = True
    
    def test_connection(self) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Letterboxd 不需要连接测试"""
        return True, None, {'status': 'csv_only', 'message': 'Letterboxd 仅支持 CSV 导入/导出'}
    
    def fetch_data(self, output_path: str) -> Optional[List[Dict[str, Any]]]:
        """Letterboxd 不支持网络获取，请使用 import_csv"""
        raise NotImplementedError("Letterboxd 不支持直接获取数据，请使用 import_csv 方法导入 CSV 文件")
    
    def import_csv(self, csv_content: str, filename: str = 'diary.csv') -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        导入 Letterboxd CSV 文件
        
        Args:
            csv_content: CSV 文件内容
            filename: 文件名（仅用于日志）
            
        Returns:
            Tuple[DataFrame, 统计信息字典]
        """
        self.logger.info(f"正在解析 {filename}...")
        
        # 解析 CSV
        df = pd.read_csv(io.StringIO(csv_content))
        
        # Letterboxd diary.csv 列映射
        # Date, Name, Year, Letterboxd URI, Rating, Rewatch, Tags, Watched Date
        column_mapping = {
            'Name': 'Title',
            'Year': 'Year',
            'Letterboxd URI': 'URL',
            'Rating': 'Rating_letterboxd',
            'Watched Date': 'Date Rated',
            'Rewatch': 'Rewatch',
            'Tags': 'Tags',
            'Date': 'Entry Date'
        }
        
        # 重命名存在的列
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df = df.rename(columns={old_col: new_col})
        
        # 转换评分 (Letterboxd 0.5-5 → 1-10)
        if 'Rating_letterboxd' in df.columns:
            df['Your Rating'] = df['Rating_letterboxd'].apply(self._convert_rating)
        
        # 统计
        total_count = len(df)
        rated_count = df['Your Rating'].notna().sum() if 'Your Rating' in df.columns else 0
        
        stats = {
            'total_count': total_count,
            'rated_count': int(rated_count),
            'filename': filename
        }
        
        self.logger.success(f"Letterboxd 数据导入成功！共 {total_count} 部电影，{rated_count} 部已评分")
        
        return df, stats
    
    def export_csv(self, movies: List[Dict[str, Any]]) -> str:
        """
        导出为 Letterboxd 格式 CSV
        
        Letterboxd 导入格式要求:
        - Title (必需)
        - Year (推荐)
        - Rating10 (1-10评分)
        - WatchedDate (YYYY-MM-DD)
        
        Args:
            movies: 电影记录列表
            
        Returns:
            CSV 字符串
        """
        df = pd.DataFrame(movies)
        
        # 准备导出列
        export_df = pd.DataFrame()
        
        # Title
        if 'Title' in df.columns:
            export_df['Title'] = df['Title']
        
        # Year  
        if 'Year' in df.columns:
            export_df['Year'] = df['Year']
        
        # Rating (转换为 10 分制)
        if 'Your Rating' in df.columns:
            export_df['Rating10'] = df['Your Rating'].apply(
                lambda x: int(x * 2) if pd.notna(x) and x <= 5 else (int(x) if pd.notna(x) else None)
            )
        
        # Watched Date
        if 'Date Rated' in df.columns:
            export_df['WatchedDate'] = df['Date Rated']
        
        # 生成 CSV
        return export_df.to_csv(index=False)
    
    def export_for_import(self, movies: List[Dict[str, Any]]) -> Tuple[str, str]:
        """
        生成可直接导入 Letterboxd 的 CSV 文件
        
        Returns:
            Tuple[csv_content, suggested_filename]
        """
        csv_content = self.export_csv(movies)
        filename = f"cinerecord_letterboxd_import_{len(movies)}.csv"
        return csv_content, filename
    
    @staticmethod
    def _convert_rating(rating) -> Optional[int]:
        """转换 Letterboxd 评分 (0.5-5) 到 10 分制"""
        try:
            r = float(rating)
            return int(r * 2)  # 0.5-5 → 1-10
        except:
            return None
    
    @staticmethod
    def get_import_url() -> str:
        """获取 Letterboxd 导入页面 URL"""
        return "https://letterboxd.com/import/"

"""
Adapter Registry - 插件注册中心
支持动态发现和加载平台适配器
"""

from typing import Dict, List, Optional, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.base import PlatformAdapter


class AdapterRegistry:
    """
    适配器注册中心
    
    使用装饰器模式注册适配器：
    
    >>> @AdapterRegistry.register
    ... class DoubanAdapter(PlatformAdapter):
    ...     platform_id = 'douban'
    ...     ...
    
    然后通过 registry 获取和创建：
    
    >>> adapter_class = AdapterRegistry.get('douban')
    >>> adapter = AdapterRegistry.create('douban', logger, config)
    """
    
    _adapters: Dict[str, Type['PlatformAdapter']] = {}
    
    @classmethod
    def register(cls, adapter_class: Type['PlatformAdapter']) -> Type['PlatformAdapter']:
        """
        注册适配器类
        
        可用作装饰器：
        @AdapterRegistry.register
        class MyAdapter(PlatformAdapter):
            platform_id = 'my_platform'
        """
        platform_id = getattr(adapter_class, 'platform_id', None)
        if not platform_id:
            raise ValueError(f"Adapter {adapter_class.__name__} must define platform_id")
        
        cls._adapters[platform_id] = adapter_class
        return adapter_class
    
    @classmethod
    def get(cls, platform_id: str) -> Optional[Type['PlatformAdapter']]:
        """获取适配器类（不实例化）"""
        return cls._adapters.get(platform_id)
    
    @classmethod
    def list_all(cls) -> List[str]:
        """列出所有已注册的平台ID"""
        return list(cls._adapters.keys())
    
    @classmethod
    def list_adapters(cls) -> List[Dict[str, any]]:
        """列出所有适配器的元信息"""
        result = []
        for platform_id, adapter_class in cls._adapters.items():
            result.append({
                'platform_id': platform_id,
                'platform_name': getattr(adapter_class, 'platform_name', platform_id),
                'platform_name_en': getattr(adapter_class, 'platform_name_en', platform_id),
                'auth_type': getattr(adapter_class, 'auth_type', 'none'),
                'supports_fetch': getattr(adapter_class, 'supports_fetch', True),
                'supports_sync': getattr(adapter_class, 'supports_sync', False),
                'supports_export': getattr(adapter_class, 'supports_export', True),
            })
        return result
    
    @classmethod
    def create(cls, platform_id: str, logger, config: dict) -> 'PlatformAdapter':
        """
        创建适配器实例
        
        Args:
            platform_id: 平台标识
            logger: 日志记录器
            config: 配置字典
            
        Returns:
            适配器实例
            
        Raises:
            ValueError: 如果平台未注册
        """
        adapter_class = cls.get(platform_id)
        if not adapter_class:
            available = cls.list_all()
            raise ValueError(
                f"Unknown platform: '{platform_id}'. "
                f"Available platforms: {available}"
            )
        return adapter_class(logger, config)
    
    @classmethod
    def is_registered(cls, platform_id: str) -> bool:
        """检查平台是否已注册"""
        return platform_id in cls._adapters

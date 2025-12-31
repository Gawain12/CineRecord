# CineRecord Adapters - Plugin Architecture
# Import all adapters to register them with the registry

from adapters.registry import AdapterRegistry
from adapters.base import PlatformAdapter, MovieRecord
from adapters.logger import SocketLogger, CLILogger

# Auto-register all platform adapters
from adapters import douban, imdb, trakt, letterboxd

__all__ = [
    'AdapterRegistry',
    'PlatformAdapter', 
    'MovieRecord',
    'SocketLogger',
    'CLILogger',
]

"""
Sync Failure Cache - Blacklist Management
Records failed sync attempts to avoid repeated lookups of platform-exclusive content
"""

import json
import os
from datetime import datetime
from typing import Set, Dict, Any

CACHE_FILE = "data/sync_failure_cache.json"

class SyncFailureCache:
    """Manages blacklist of failed sync combinations"""
    
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = self._load_cache()
    
    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        """Load cache from file"""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_cache(self):
        """Save cache to file"""
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
    
    def _make_key(self, source: str, target: str, item_id: str) -> str:
        """Generate cache key from source-target-id combination"""
        return f"{source}|{target}|{item_id}"
    
    def is_blacklisted(self, source: str, target: str, item_id: str) -> bool:
        """Check if a combination is in the blacklist"""
        key = self._make_key(source, target, item_id)
        return key in self.cache
    
    def add_failure(self, source: str, target: str, item_id: str, title: str = "", reason: str = ""):
        """Add a failed sync record to blacklist"""
        key = self._make_key(source, target, item_id)
        self.cache[key] = {
            'source': source,
            'target': target,
            'item_id': item_id,
            'title': title,
            'reason': reason,
            'timestamp': datetime.now().isoformat(),
            'attempts': self.cache.get(key, {}).get('attempts', 0) + 1
        }
        self._save_cache()
    
    def remove(self, source: str, target: str, item_id: str):
        """Remove a specific record from blacklist"""
        key = self._make_key(source, target, item_id)
        if key in self.cache:
            del self.cache[key]
            self._save_cache()
    
    def clear_all(self):
        """Clear entire blacklist"""
        self.cache = {}
        self._save_cache()
    
    def clear_route(self, source: str, target: str):
        """Clear all records for a specific source->target route"""
        prefix = f"{source}|{target}|"
        keys_to_remove = [k for k in self.cache.keys() if k.startswith(prefix)]
        for key in keys_to_remove:
            del self.cache[key]
        self._save_cache()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        stats = {}
        for key, record in self.cache.items():
            route = f"{record['source']}->{record['target']}"
            if route not in stats:
                stats[route] = {'count': 0, 'records': []}
            stats[route]['count'] += 1
            stats[route]['records'].append({
                'title': record.get('title', 'Unknown'),
                'reason': record.get('reason', ''),
                'attempts': record.get('attempts', 1)
            })
        return stats
    
    def get_all_records(self) -> list:
        """Get all blacklist records"""
        return list(self.cache.values())

# Global instance
_cache_instance = None

def get_cache() -> SyncFailureCache:
    """Get or create global cache instance"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = SyncFailureCache()
    return _cache_instance

"""
TMDB Platform Adapter for CineRecord
Handles rating synchronization to TMDB
"""

from typing import Optional, Dict, Any, List
from adapters.base import PlatformAdapter
from adapters.registry import AdapterRegistry
from scrapers.tmdb_client import TMDBClient

@AdapterRegistry.register
class TMDBAdapter(PlatformAdapter):
    """TMDB platform adapter for rating sync"""
    
    platform_id = 'tmdb'
    platform_name = 'TMDB'
    supports_sync = True
    supports_fetch = True
    
    def __init__(self, logger, config: Dict[str, Any]):
        super().__init__(logger, config)
        self.api_key = config.get('tmdb_api_key', '')
        self.session_id = config.get('tmdb_session_id', '')
        self.client = None
        
        if self.api_key and self.session_id:
            self.client = TMDBClient(self.api_key, self.session_id)
    
    def sync_movie(self, item_id: str, rating: float, comment: str = "", tags: List[str] = None) -> bool:
        """
        Sync a movie rating to TMDB
        
        Args:
            item_id: TMDB movie ID or IMDb ID (tt format)
            rating: Rating from 0-10
            comment: Not used for TMDB
            tags: Not used for TMDB
            
        Returns:
            bool: True if successful
        """
        if not self.client:
            self.logger.log(f"TMDB client not initialized (missing API key or session)", 'error')
            return False
        
        try:
            # Check if it's an IMDb ID (starts with 'tt')
            if isinstance(item_id, str) and item_id.startswith('tt'):
                # Convert IMDb ID to TMDB ID using find API
                self.logger.log(f"Converting IMDb ID {item_id} to TMDB ID...", 'info')
                result = self.client._get(f'/find/{item_id}', {'external_source': 'imdb_id'})
                
                if result and result.get('movie_results'):
                    tmdb_id = result['movie_results'][0]['id']
                    self.logger.log(f"Found TMDB ID: {tmdb_id}", 'info')
                else:
                    self.logger.log(f"Cannot find TMDB ID for IMDb {item_id}", 'error')
                    return False
            else:
                # Already a TMDB ID
                tmdb_id = int(item_id)
            
            # TMDB uses 0.5-10 scale in 0.5 increments
            # Rating=0 means "watched without rating"
            if rating > 0:
                success = self.client.rate_movie(tmdb_id, rating)
                if success:
                    self.logger.log(f"✅ Synced to TMDB ID {tmdb_id} ({rating}/10)", 'success')
                else:
                    self.logger.log(f"Failed to rate TMDB movie {tmdb_id}", 'error')
                return success
            else:
                # For rating=0, just mark as watched (add to watchlist or favorites)
                # TMDB doesn't have a direct "watched" endpoint like Trakt
                # So we skip adding rating but log it as success
                self.logger.log(f"✅ Skipped rating for TMDB ID {tmdb_id} (watched only)", 'success')
                return True
            
        except (ValueError, TypeError) as e:
            self.logger.log(f"Invalid TMDB movie ID '{item_id}': {e}", 'error')
            return False
        except Exception as e:
            self.logger.log(f"Error rating TMDB movie {item_id}: {e}", 'error')
            return False
    
    def fetch_data(self, force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Fetch rated movies from TMDB"""
        if not self.client:
            self.logger.log("TMDB client not initialized", 'error')
            return None
        
        try:
            movies = self.client.get_all_rated_movies()
            self.logger.log(f"Fetched {len(movies) if movies else 0} rated movies from TMDB", 'success')
            return movies
        except Exception as e:
            self.logger.log(f"Error fetching TMDB data: {e}", 'error')
            return None
    
    def test_connection(self) -> bool:
        """Test TMDB API connection"""
        if not self.client:
            self.logger.log("TMDB client not initialized", 'error')
            return False
        
        try:
            result = self.client._get('/account', {'session_id': self.session_id})
            if result and 'id' in result:
                self.logger.log(f"✅ TMDB connection successful (Account ID: {result.get('id')})", 'success')
                return True
            else:
                self.logger.log("TMDB API test failed", 'error')
                return False
        except Exception as e:
            self.logger.log(f"TMDB connection test error: {e}", 'error')
            return False

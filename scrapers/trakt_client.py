"""
Trakt API Client with OAuth2 Device Flow
Handles authentication and data fetching from Trakt.tv
"""

import requests
import time
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class TraktClient:
    """Trakt API client with OAuth2 device flow authentication"""
    
    BASE_URL = "https://api.trakt.tv"
    
    def __init__(self, client_id, client_secret, access_token=None, refresh_token=None, token_expires=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expires = None
        
        if token_expires:
            if isinstance(token_expires, str):
                try:
                    self.token_expires = datetime.fromisoformat(token_expires)
                except ValueError:
                    pass
            elif isinstance(token_expires, datetime):
                self.token_expires = token_expires
    
    def _get_headers(self, auth_required=True):
        """Get headers for API requests"""
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-version': '2',
            'trakt-api-key': self.client_id
        }
        if auth_required and self.access_token:
            headers['Authorization'] = f'Bearer {self.access_token}'
        return headers
    
    def _make_request(self, method, endpoint, auth_required=True, **kwargs):
        """Make an API request with proper error handling"""
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers(auth_required)
        
        try:
            logger.debug(f"Making {method} request to {url}")
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=5, **kwargs)
            elif method == 'POST':
                response = requests.post(url, headers=headers, timeout=30, **kwargs)
            else:
                return None
            
            logger.debug(f"Response status: {response.status_code}")
            return response
        except requests.Timeout as e:
            logger.error(f"Trakt API request timed out: {e}")
            print(f"!!! TRAKT TIMEOUT: {e}")
            return None
        except requests.ConnectionError as e:
            logger.error(f"Trakt API connection error: {e}")
            print(f"!!! TRAKT CONNECTION ERROR: {e}")
            return None
        except requests.RequestException as e:
            logger.exception(f"Trakt API request failed: {e}")
            print(f"!!! TRAKT REQUEST EXCEPTION: {e}")
            return None
    
    # ==========================================
    # OAuth2 Device Flow
    # ==========================================
    
    def start_device_auth(self):
        """
        Start OAuth2 device flow authentication.
        
        Returns:
            dict: Contains device_code, user_code, verification_url, expires_in, interval
        """
        response = self._make_request(
            'POST',
            '/oauth/device/code',
            auth_required=False,
            json={'client_id': self.client_id}
        )
        
        if response and response.status_code == 200:
            data = response.json()
            return {
                'device_code': data['device_code'],
                'user_code': data['user_code'],
                'verification_url': data['verification_url'],
                'expires_in': data['expires_in'],
                'interval': data['interval']
            }
        else:
            error = response.text if response else "No response"
            logger.error(f"Failed to start device auth: {error}")
            return None
    
    def poll_device_auth(self, device_code):
        """
        Poll for device authorization completion.
        
        Args:
            device_code: The device code from start_device_auth
            
        Returns:
            dict: Contains access_token, refresh_token, expires_in on success
                  or 'pending', 'slow_down', 'expired', 'denied' status
        """
        response = self._make_request(
            'POST',
            '/oauth/device/token',
            auth_required=False,
            json={
                'code': device_code,
                'client_id': self.client_id,
                'client_secret': self.client_secret
            }
        )
        
        if not response:
            return {'status': 'error', 'message': 'No response from server'}
        
        if response.status_code == 200:
            data = response.json()
            self.access_token = data['access_token']
            self.refresh_token = data['refresh_token']
            expires_in = data['expires_in']
            self.token_expires = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            return {
                'status': 'success',
                'access_token': data['access_token'],
                'refresh_token': data['refresh_token'],
                'expires_in': expires_in,
                'token_expires': self.token_expires.isoformat()
            }
        elif response.status_code == 400:
            # Still pending authorization
            return {'status': 'pending'}
        elif response.status_code == 404:
            # Invalid device code
            return {'status': 'expired', 'message': 'Device code expired'}
        elif response.status_code == 409:
            # Already used
            return {'status': 'expired', 'message': 'Device code already used'}
        elif response.status_code == 410:
            # Denied by user
            return {'status': 'denied', 'message': 'User denied authorization'}
        elif response.status_code == 418:
            # User denied authorization
            return {'status': 'denied', 'message': 'User denied authorization'}
        elif response.status_code == 429:
            # Slow down polling
            return {'status': 'slow_down'}
        else:
            return {'status': 'error', 'message': f'HTTP {response.status_code}: {response.text}'}
    
    def refresh_access_token(self):
        """
        Refresh the access token using the refresh token.
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.refresh_token:
            return False
        
        response = self._make_request(
            'POST',
            '/oauth/token',
            auth_required=False,
            json={
                'refresh_token': self.refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
                'grant_type': 'refresh_token'
            }
        )
        
        if response and response.status_code == 200:
            data = response.json()
            self.access_token = data['access_token']
            self.refresh_token = data['refresh_token']
            expires_in = data['expires_in']
            self.token_expires = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            return True
        
        return False
    
    def is_token_expired(self):
        """Check if the current token is expired or about to expire"""
        if not self.token_expires:
            return True
        # Add 5 minute buffer
        return datetime.now(timezone.utc) >= (self.token_expires - timedelta(minutes=5))
    
    # ==========================================
    # User Data Endpoints
    # ==========================================
    
    def get_user_profile(self):
        """
        Get the authenticated user's profile.
        
        Returns:
            dict: User profile with username, ids, stats, etc.
        """
        response = self._make_request('GET', '/users/me?extended=full')
        
        if response and response.status_code == 200:
            return response.json()
        return None
    
    def get_user_stats(self, username):
        """
        Get user's statistics.
        
        Args:
            username: Trakt username or 'me'
            
        Returns:
            dict: User stats including movies watched, rated, etc.
        """
        response = self._make_request('GET', f'/users/{username}/stats')
        
        if response and response.status_code == 200:
            return response.json()
        return None
    
    def get_ratings(self, username, rating_type='movies', page=1, limit=100):
        """
        Get user's ratings.
        
        Args:
            username: Trakt username or 'me'
            rating_type: 'movies', 'shows', 'episodes', or 'all'
            page: Page number
            limit: Items per page (max 100)
            
        Returns:
            list: List of rated items with ratings
        """
        response = self._make_request(
            'GET',
            f'/users/{username}/ratings/{rating_type}',
            params={'page': page, 'limit': limit, 'extended': 'full'}
        )
        
        if response and response.status_code == 200:
            return {
                'items': response.json(),
                'page': int(response.headers.get('X-Pagination-Page', 1)),
                'total_pages': int(response.headers.get('X-Pagination-Page-Count', 1)),
                'total_items': int(response.headers.get('X-Pagination-Item-Count', 0))
            }
        return None
    
    def get_watchlist(self, username, item_type='movies', page=1, limit=100):
        """
        Get user's watchlist.
        
        Args:
            username: Trakt username or 'me'
            item_type: 'movies', 'shows', or 'all'
            page: Page number
            limit: Items per page
            
        Returns:
            list: List of watchlist items
        """
        response = self._make_request(
            'GET',
            f'/users/{username}/watchlist/{item_type}',
            params={'page': page, 'limit': limit, 'extended': 'full'}
        )
        
        if response and response.status_code == 200:
            return {
                'items': response.json(),
                'page': int(response.headers.get('X-Pagination-Page', 1)),
                'total_pages': int(response.headers.get('X-Pagination-Page-Count', 1)),
                'total_items': int(response.headers.get('X-Pagination-Item-Count', 0))
            }
        return None
    
    def get_watch_history(self, username, item_type='movies', page=1, limit=100):
        """
        Get user's watch history.
        
        Args:
            username: Trakt username or 'me'
            item_type: 'movies', 'shows', 'episodes', or 'all'
            page: Page number
            limit: Items per page
            
        Returns:
            list: List of watched items with timestamps
        """
        response = self._make_request(
            'GET',
            f'/users/{username}/history/{item_type}',
            params={'page': page, 'limit': limit, 'extended': 'full'}
        )
        
        if response and response.status_code == 200:
            return {
                'items': response.json(),
                'page': int(response.headers.get('X-Pagination-Page', 1)),
                'total_pages': int(response.headers.get('X-Pagination-Page-Count', 1)),
                'total_items': int(response.headers.get('X-Pagination-Item-Count', 0))
            }
        return None
    
    def get_all_movie_ratings(self, username='me'):
        """
        Fetch all movie ratings (handles pagination automatically).
        
        Returns:
            list: All movie ratings as standardized records
        """
        all_ratings = []
        page = 1
        
        while True:
            result = self.get_ratings(username, 'movies', page=page, limit=100)
            if not result or not result['items']:
                break
            
            for item in result['items']:
                movie = item.get('movie', {})
                all_ratings.append({
                    'Title': movie.get('title'),
                    'Year': movie.get('year'),
                    'Your Rating': item.get('rating'),
                    'Date Rated': item.get('rated_at', '')[:10] if item.get('rated_at') else '',
                    'IMDb ID': movie.get('ids', {}).get('imdb'),
                    'Trakt ID': movie.get('ids', {}).get('trakt'),
                    'TMDB ID': movie.get('ids', {}).get('tmdb'),
                    'URL': f"https://trakt.tv/movies/{movie.get('ids', {}).get('slug', '')}",
                    'Genres': ', '.join(movie.get('genres', [])) if movie.get('genres') else '',
                    'Runtime': movie.get('runtime'),
                    'Type': 'movie'
                })
            
            if page >= result['total_pages']:
                break
            page += 1
        
        return all_ratings

    def get_all_watched_movies(self, username='me'):
        """
        Fetch all watched movies from history (handles pagination automatically).
        This gets the watch history, not just rated movies.
        
        Returns:
            list: All watched movies as standardized records
        """
        all_watched = []
        page = 1
        seen_ids = set()  # Track unique movies (avoid duplicates from rewatches)
        
        while True:
            result = self.get_watch_history(username, 'movies', page=page, limit=100)
            if not result or not result['items']:
                break
            
            for item in result['items']:
                movie = item.get('movie', {})
                trakt_id = movie.get('ids', {}).get('trakt')
                
                # Skip duplicates (rewatches)
                if trakt_id in seen_ids:
                    continue
                seen_ids.add(trakt_id)
                
                all_watched.append({
                    'Title': movie.get('title'),
                    'Year': movie.get('year'),
                    'Your Rating': None,  # Watch history doesn't include rating
                    'Date Rated': item.get('watched_at', '')[:10] if item.get('watched_at') else '',
                    'IMDb ID': movie.get('ids', {}).get('imdb'),
                    'Trakt ID': trakt_id,
                    'TMDB ID': movie.get('ids', {}).get('tmdb'),
                    'URL': f"https://trakt.tv/movies/{movie.get('ids', {}).get('slug', '')}",
                    'Genres': ', '.join(movie.get('genres', [])) if movie.get('genres') else '',
                    'Runtime': movie.get('runtime'),
                    'Type': 'movie'
                })
            
            if page >= result['total_pages']:
                break
            page += 1
        
        return all_watched

    def get_all_movies_with_ratings(self, username='me'):
        """
        Fetch all watched movies and merge with ratings where available.
        This combines watch history with ratings data.
        
        Returns:
            list: All movies with ratings where available
        """
        # First get all ratings to build a lookup
        ratings_data = {}
        page = 1
        while True:
            result = self.get_ratings(username, 'movies', page=page, limit=100)
            if not result or not result['items']:
                break
            for item in result['items']:
                movie = item.get('movie', {})
                trakt_id = movie.get('ids', {}).get('trakt')
                if trakt_id:
                    ratings_data[trakt_id] = {
                        'rating': item.get('rating'),
                        'rated_at': item.get('rated_at', '')[:10] if item.get('rated_at') else ''
                    }
            if page >= result['total_pages']:
                break
            page += 1
        
        # Now get all watched movies and merge with ratings
        all_movies = []
        page = 1
        seen_ids = set()
        
        while True:
            result = self.get_watch_history(username, 'movies', page=page, limit=100)
            if not result or not result['items']:
                break
            
            for item in result['items']:
                movie = item.get('movie', {})
                trakt_id = movie.get('ids', {}).get('trakt')
                
                if trakt_id in seen_ids:
                    continue
                seen_ids.add(trakt_id)
                
                # Check if this movie has a rating
                rating_info = ratings_data.get(trakt_id, {})
                
                all_movies.append({
                    'Title': movie.get('title'),
                    'Year': movie.get('year'),
                    'Your Rating': rating_info.get('rating'),  # None if not rated
                    'Date Rated': rating_info.get('rated_at') or (item.get('watched_at', '')[:10] if item.get('watched_at') else ''),
                    'IMDb ID': movie.get('ids', {}).get('imdb'),
                    'Trakt ID': trakt_id,
                    'TMDB ID': movie.get('ids', {}).get('tmdb'),
                    'URL': f"https://trakt.tv/movies/{movie.get('ids', {}).get('slug', '')}",
                    'Genres': ', '.join(movie.get('genres', [])) if movie.get('genres') else '',
                    'Runtime': movie.get('runtime'),
                    'Type': 'movie'
                })
            
            if page >= result['total_pages']:
                break
            page += 1
        
        return all_movies

    # ==========================================
    # Sync Methods (Write Operations)
    # ==========================================
    
    def add_to_history(self, movies, watched_at=None):
        """
        Add movies to watch history.
        
        Args:
            movies: List of dicts with 'imdb_id' or 'trakt_id' or 'tmdb_id'
            watched_at: Optional datetime for when movies were watched
            
        Returns:
            dict: API response with added/not_found counts
        """
        if not movies:
            return {'added': {'movies': 0}, 'not_found': {'movies': []}}
        
        # Build the movies array for the API
        movies_data = []
        for movie in movies:
            movie_obj = {'ids': {}}
            if movie.get('imdb_id'):
                movie_obj['ids']['imdb'] = movie['imdb_id']
            if movie.get('trakt_id'):
                movie_obj['ids']['trakt'] = movie['trakt_id']
            if movie.get('tmdb_id'):
                movie_obj['ids']['tmdb'] = movie['tmdb_id']
            if watched_at:
                movie_obj['watched_at'] = watched_at.isoformat() if hasattr(watched_at, 'isoformat') else watched_at
            elif movie.get('watched_at'):
                movie_obj['watched_at'] = movie['watched_at']
            movies_data.append(movie_obj)
        
        response = self._make_request(
            'POST',
            '/sync/history',
            json={'movies': movies_data}
        )
        
        if response and response.status_code in [200, 201]:
            return response.json()
        return None
    
    def rate_movies(self, movies):
        """
        Rate multiple movies.
        
        Args:
            movies: List of dicts with 'imdb_id'/'trakt_id'/'tmdb_id' and 'rating' (1-10)
            
        Returns:
            dict: API response with added/not_found counts
        """
        if not movies:
            return {'added': {'movies': 0}, 'not_found': {'movies': []}}
        
        movies_data = []
        for movie in movies:
            if not movie.get('rating'):
                continue
            movie_obj = {
                'ids': {},
                'rating': int(movie['rating'])
            }
            if movie.get('imdb_id'):
                movie_obj['ids']['imdb'] = movie['imdb_id']
            if movie.get('trakt_id'):
                movie_obj['ids']['trakt'] = movie['trakt_id']
            if movie.get('tmdb_id'):
                movie_obj['ids']['tmdb'] = movie['tmdb_id']
            if movie.get('rated_at'):
                movie_obj['rated_at'] = movie['rated_at']
            movies_data.append(movie_obj)
        
        if not movies_data:
            return {'added': {'movies': 0}, 'not_found': {'movies': []}}
        
        response = self._make_request(
            'POST',
            '/sync/ratings',
            json={'movies': movies_data}
        )
        
        if response and response.status_code in [200, 201]:
            return response.json()
        return None
    
    def get_incremental_watched(self, since_date=None, username='me'):
        """
        Fetch watched movies since a specific date (for incremental backup).
        
        Args:
            since_date: datetime or ISO string, only fetch movies watched after this date
            username: Trakt username or 'me'
            
        Returns:
            list: Movies watched since the given date
        """
        all_watched = []
        page = 1
        seen_ids = set()
        
        # Convert to ISO format if datetime
        start_at = None
        if since_date:
            if hasattr(since_date, 'isoformat'):
                start_at = since_date.isoformat()
            else:
                start_at = since_date
        
        while True:
            params = {'page': page, 'limit': 100, 'extended': 'full'}
            if start_at:
                params['start_at'] = start_at
            
            response = self._make_request(
                'GET',
                f'/users/{username}/history/movies',
                params=params
            )
            
            if not response or response.status_code != 200:
                break
            
            items = response.json()
            if not items:
                break
            
            for item in items:
                movie = item.get('movie', {})
                trakt_id = movie.get('ids', {}).get('trakt')
                
                if trakt_id in seen_ids:
                    continue
                seen_ids.add(trakt_id)
                
                all_watched.append({
                    'Title': movie.get('title'),
                    'Year': movie.get('year'),
                    'Your Rating': None,
                    'Date Rated': item.get('watched_at', '')[:10] if item.get('watched_at') else '',
                    'IMDb ID': movie.get('ids', {}).get('imdb'),
                    'Trakt ID': trakt_id,
                    'TMDB ID': movie.get('ids', {}).get('tmdb'),
                    'URL': f"https://trakt.tv/movies/{movie.get('ids', {}).get('slug', '')}",
                    'Type': 'movie'
                })
            
            total_pages = int(response.headers.get('X-Pagination-Page-Count', 1))
            if page >= total_pages:
                break
            page += 1
        
        return all_watched
    
    def sync_from_imdb(self, imdb_movies, existing_trakt_movies=None):
        """
        Sync movies from IMDB to Trakt.
        
        Args:
            imdb_movies: List of IMDB movie records with 'Const' (IMDB ID), 'Your Rating', etc.
            existing_trakt_movies: Optional pre-fetched list of existing Trakt movies
            
        Returns:
            dict: Summary of sync results
        """
        if existing_trakt_movies is None:
            existing_trakt_movies = self.get_all_movies_with_ratings()
        
        # Build set of existing IMDB IDs in Trakt
        existing_imdb_ids = {m.get('IMDb ID') for m in existing_trakt_movies if m.get('IMDb ID')}
        
        # Find movies to sync
        to_add_history = []
        to_rate = []
        
        for movie in imdb_movies:
            imdb_id = movie.get('Const') or movie.get('IMDb ID')
            if not imdb_id:
                continue
            
            if imdb_id not in existing_imdb_ids:
                # Movie not in Trakt, add to history
                to_add_history.append({
                    'imdb_id': imdb_id,
                    'watched_at': movie.get('Date Rated') or datetime.now(timezone.utc).isoformat()
                })
            
            # Check if we need to add/update rating
            rating = movie.get('Your Rating')
            if rating:
                to_rate.append({
                    'imdb_id': imdb_id,
                    'rating': int(rating),
                    'rated_at': movie.get('Date Rated')
                })
        
        results = {
            'history_added': 0,
            'ratings_added': 0,
            'not_found': []
        }
        
        # Add to history in batches
        if to_add_history:
            batch_size = 100
            for i in range(0, len(to_add_history), batch_size):
                batch = to_add_history[i:i+batch_size]
                result = self.add_to_history(batch)
                if result:
                    results['history_added'] += result.get('added', {}).get('movies', 0)
                    results['not_found'].extend(result.get('not_found', {}).get('movies', []))
        
        # Add ratings in batches
        if to_rate:
            batch_size = 100
            for i in range(0, len(to_rate), batch_size):
                batch = to_rate[i:i+batch_size]
                result = self.rate_movies(batch)
                if result:
                    results['ratings_added'] += result.get('added', {}).get('movies', 0)
        
        return results


def run_scraper(client_id, client_secret, access_token, refresh_token, output_path, socketio=None):
    """
    Scrape Trakt ratings and save to CSV.
    
    Args:
        client_id: Trakt API client ID
        client_secret: Trakt API client secret
        access_token: OAuth access token
        refresh_token: OAuth refresh token
        output_path: Path to save the CSV
        socketio: Optional SocketIO instance for progress updates
        
    Returns:
        list: List of rating records
    """
    client = TraktClient(client_id, client_secret, access_token, refresh_token)
    
    # Refresh token if needed
    if client.is_token_expired():
        if socketio:
            socketio.emit('log', {'message': '🔄 Refreshing Trakt access token...', 'type': 'info'})
        if not client.refresh_access_token():
            if socketio:
                socketio.emit('log', {'message': '❌ Failed to refresh token', 'type': 'error'})
            return None
    
    if socketio:
        socketio.emit('log', {'message': '📥 Fetching Trakt movie ratings...', 'type': 'info'})
    
    try:
        ratings = client.get_all_movie_ratings()
        
        if ratings:
            import pandas as pd
            df = pd.DataFrame(ratings)
            df.to_csv(output_path, index=False)
            
            if socketio:
                socketio.emit('log', {'message': f'✅ Saved {len(ratings)} Trakt ratings', 'type': 'success'})
            
            return ratings
        else:
            if socketio:
                socketio.emit('log', {'message': '⚠️ No ratings found on Trakt', 'type': 'info'})
            return []
            
    except Exception as e:
        logger.exception("Trakt scraper error")
        if socketio:
            socketio.emit('log', {'message': f'❌ Error: {e}', 'type': 'error'})
        return None

"""
TMDB API Client with Session Authentication
Handles API key authentication and user session for The Movie Database
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# Default API key (user provided)
DEFAULT_TMDB_API_KEY = "8ffaf38032c0f85f4f421fb0cc1241a5"


class TMDBClient:
    """TMDB API client with session-based authentication for user actions"""
    
    BASE_URL = "https://api.themoviedb.org/3"
    AUTH_URL = "https://www.themoviedb.org/authenticate"
    
    def __init__(self, api_key: str = None, session_id: Optional[str] = None):
        self.api_key = api_key or DEFAULT_TMDB_API_KEY
        self.session_id = session_id
        self.account_id = None
        
        # Create persistent HTTP session with retry logic
        self._http_session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "DELETE", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        self._http_session.mount("https://", adapter)
        self._http_session.mount("http://", adapter)
    
    def _get_params(self, extra: dict = None) -> dict:
        """Get base params with API key"""
        params = {'api_key': self.api_key}
        if extra:
            params.update(extra)
        return params
    
    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make GET request to TMDB API with retry"""
        url = f"{self.BASE_URL}{endpoint}"
        all_params = self._get_params(params)
        
        try:
            logger.debug(f"TMDB GET: {endpoint}")
            response = self._http_session.get(url, params=all_params, timeout=45)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"TMDB API error: {e}")
            return None
    
    def _post(self, endpoint: str, data: dict = None, params: dict = None) -> Optional[dict]:
        """Make POST request to TMDB API with retry"""
        url = f"{self.BASE_URL}{endpoint}"
        all_params = self._get_params(params)
        headers = {'Content-Type': 'application/json'}
        
        try:
            logger.info(f"TMDB POST: {endpoint}")
            response = self._http_session.post(url, json=data, params=all_params, headers=headers, timeout=45)
            logger.info(f"TMDB Response status: {response.status_code}")
            if response.status_code >= 400:
                logger.error(f"TMDB API error response: {response.text}")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"TMDB API error: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response body: {e.response.text}")
            return None
    
    # ==================== Authentication ====================
    
    def create_request_token(self) -> Optional[str]:
        """Create a new request token (Step 1 of auth flow)"""
        result = self._get("/authentication/token/new")
        if result and result.get('success'):
            return result.get('request_token')
        return None
    
    def get_auth_url(self, request_token: str, redirect_url: str = None) -> str:
        """Get the URL for user to approve the token"""
        url = f"{self.AUTH_URL}/{request_token}"
        if redirect_url:
            url += f"?redirect_to={redirect_url}"
        return url
    
    def create_session(self, request_token: str) -> Optional[str]:
        """Create a session ID from approved token (Step 3 of auth flow)"""
        result = self._post("/authentication/session/new", {
            'request_token': request_token
        })
        if result and result.get('success'):
            self.session_id = result.get('session_id')
            return self.session_id
        return None
    
    def get_account_details(self) -> Optional[dict]:
        """Get authenticated user's account details"""
        if not self.session_id:
            return None
        
        result = self._get("/account", {'session_id': self.session_id})
        if result:
            self.account_id = result.get('id')
            return result
        return None
    
    def get_account_stats(self) -> Optional[dict]:
        """Get account statistics including rated movies count and watchlist count"""
        if not self.session_id:
            return None
        
        # Ensure we have account_id
        if not self.account_id:
            account = self.get_account_details()
            if not account:
                return None
        
        username = None
        account = self._get("/account", {'session_id': self.session_id})
        if account:
            username = account.get('username')
        
        # Get just first page to get total counts
        rated_result = self.get_rated_movies(page=1)
        watchlist_result = self.get_watchlist(page=1)
        
        rated_count = rated_result.get('total_results', 0) if rated_result else 0
        watchlist_count = watchlist_result.get('total_results', 0) if watchlist_result else 0
        
        return {
            'rated_count': rated_count,
            'watchlist_count': watchlist_count,
            'username': username,
            'account_id': self.account_id,
            'profile_link': f'https://www.themoviedb.org/u/{username}' if username else 'https://www.themoviedb.org/',
            'rated_link': f'https://www.themoviedb.org/u/{username}/ratings' if username else '#',
            'watchlist_link': f'https://www.themoviedb.org/u/{username}/watchlist' if username else '#'
        }
    
    def validate_api_key(self) -> bool:
        """Check if API key is valid"""
        result = self._get("/authentication")
        return result is not None and result.get('success', False)
    
    # ==================== Movie Data ====================
    
    def search_movie(self, query: str, year: int = None) -> List[dict]:
        """Search for movies by title"""
        params = {'query': query}
        if year:
            params['year'] = year
        
        result = self._get("/search/movie", params)
        if result:
            return result.get('results', [])
        return []
    
    def get_movie_details(self, movie_id: int) -> Optional[dict]:
        """Get detailed movie information"""
        return self._get(f"/movie/{movie_id}")
    
    def get_movie_external_ids(self, movie_id: int) -> Optional[dict]:
        """Get external IDs (IMDB, etc.) for a movie"""
        return self._get(f"/movie/{movie_id}/external_ids")
    
    # ==================== User Ratings ====================
    
    def get_rated_movies(self, page: int = 1) -> Optional[dict]:
        """Get movies rated by the authenticated user"""
        if not self.session_id or not self.account_id:
            account = self.get_account_details()
            if not account:
                return None
        
        return self._get(f"/account/{self.account_id}/rated/movies", {
            'session_id': self.session_id,
            'page': page,
            'sort_by': 'created_at.desc'
        })
    
    def get_all_rated_movies(self) -> List[dict]:
        """Get all rated movies (handles pagination)"""
        all_movies = []
        page = 1
        
        logger.info("Starting TMDB ratings fetch...")
        
        while True:
            logger.info(f"Fetching TMDB ratings page {page}...")
            result = self.get_rated_movies(page)
            if not result:
                logger.warning(f"Failed to fetch page {page}")
                break
            
            movies = result.get('results', [])
            if not movies:
                logger.info("No more movies found.")
                break
            
            # Debug first movie of first page to see keys
            if page == 1 and movies:
                logger.info(f"DEBUG: Sample TMDB Movie Keys: {list(movies[0].keys())}")
                logger.info(f"DEBUG: Sample TMDB Movie Data: {movies[0]}")
            
            all_movies.extend(movies)
            
            total_pages = result.get('total_pages', 1)
            logger.info(f"Page {page}/{total_pages} fetched. Total so far: {len(all_movies)}")
            
            if page >= total_pages:
                break
            
            page += 1
        
        logger.info(f"Finished fetching {len(all_movies)} TMDB ratings.")
        return all_movies
    
    def rate_movie(self, movie_id: int, rating: float) -> bool:
        """Rate a movie (rating should be 0.5-10 in 0.5 increments)"""
        if not self.session_id:
            logger.error("Session ID required for rating")
            return False
        
        # TMDB uses 0.5 to 10 scale in 0.5 increments
        rating = max(0.5, min(10.0, round(rating * 2) / 2))
        
        result = self._post(f"/movie/{movie_id}/rating", 
                           {'value': rating},
                           {'session_id': self.session_id})
        
        return result is not None and result.get('success', False)
    
    def delete_movie_rating(self, movie_id: int) -> bool:
        """Remove rating from a movie"""
        if not self.session_id:
            return False
        
        url = f"{self.BASE_URL}/movie/{movie_id}/rating"
        params = self._get_params({'session_id': self.session_id})
        
        try:
            response = requests.delete(url, params=params, timeout=30)
            return response.status_code == 200
        except:
            return False
    
    # ==================== Watchlist ====================
    
    def get_watchlist(self, page: int = 1) -> Optional[dict]:
        """Get user's movie watchlist"""
        if not self.session_id or not self.account_id:
            account = self.get_account_details()
            if not account:
                return None
        
        return self._get(f"/account/{self.account_id}/watchlist/movies", {
            'session_id': self.session_id,
            'page': page,
            'sort_by': 'created_at.desc'
        })
    
    def add_to_watchlist(self, movie_id: int, add: bool = True) -> bool:
        """Add or remove movie from watchlist"""
        if not self.session_id or not self.account_id:
            return False
        
        result = self._post(f"/account/{self.account_id}/watchlist", {
            'media_type': 'movie',
            'media_id': movie_id,
            'watchlist': add
        }, {'session_id': self.session_id})
        
        return result is not None and result.get('success', False)
    
    # ==================== ID Lookup ====================
    
    def find_by_imdb_id(self, imdb_id: str) -> Optional[dict]:
        """Find a movie by IMDB ID"""
        result = self._get(f"/find/{imdb_id}", {'external_source': 'imdb_id'})
        if result:
            movies = result.get('movie_results', [])
            if movies:
                return movies[0]
        return None
    
    # ==================== Data Export ====================
    
    def export_ratings_to_df_format(self) -> List[dict]:
        """Export all ratings in a standard DataFrame-compatible format"""
        movies = self.get_all_rated_movies()
        records = []
        
        for movie in movies:
            # Get external IDs for this movie
            ext_ids = self.get_movie_external_ids(movie['id'])
            imdb_id = ext_ids.get('imdb_id') if ext_ids else None
            
            record = {
                'tmdb_id': movie['id'],
                'imdb_id': imdb_id,
                'Title': movie.get('title', ''),
                'Year': movie.get('release_date', '')[:4] if movie.get('release_date') else '',
                'Your Rating': movie.get('rating', 0),  # User's rating
                'Date Rated': movie.get('rated_at') or movie.get('created_at', ''),  # When rated
                'Genres': ', '.join([str(g) for g in movie.get('genre_ids', [])]),
                'Overview': movie.get('overview', ''),
                'Cover URL': f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}" if movie.get('poster_path') else '',
                'URL': f"https://www.themoviedb.org/movie/{movie['id']}"
            }
            records.append(record)
        
        return records

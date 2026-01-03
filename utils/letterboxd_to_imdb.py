"""
Letterboxd to IMDb Sync Module
Syncs ratings from Letterboxd diary/ratings CSV to IMDb using GraphQL API
"""
import re
import time
import requests
from typing import Optional, Dict, List
import pandas as pd


class LetterboxdToIMDbSync:
    """Sync Letterboxd data to IMDb"""
    
    def __init__(self, imdb_cookie: str, logger=None):
        """
        Initialize sync client
        
        Args:
            imdb_cookie: IMDb cookie string for authentication
            logger: Optional logger instance with .log() method
        """
        self.imdb_cookie = imdb_cookie
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        })
        
    def log(self, message: str, level: str = 'info'):
        """Log a message if logger is available"""
        if self.logger:
            self.logger.log(message, level)
        else:
            print(f"[{level.upper()}] {message}")
    
    def get_imdb_id_from_letterboxd_uri(self, letterboxd_uri: str) -> Optional[str]:
        """
        Fetch IMDb ID from Letterboxd movie page
        
        Args:
            letterboxd_uri: Letterboxd URI like 'https://letterboxd.com/film/...'
            
        Returns:
            IMDb ID (e.g., 'tt1234567') or None if not found
        """
        if not letterboxd_uri:
            return None
            
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Accept': 'text/html',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            
            resp = requests.get(letterboxd_uri, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None
            
            # Extract IMDb ID from the page
            # Pattern: href="...title/(tt\d+)/maindetails"
            matches = re.findall(r'href=".+title/(tt\d+)/maindetails"', resp.text)
            if matches:
                return matches[0]
                
            # Alternative pattern: data-track-action="IMDb" href="https://www.imdb.com/title/(tt\d+)"
            matches = re.findall(r'imdb\.com/title/(tt\d+)', resp.text)
            if matches:
                return matches[0]
                
            return None
            
        except Exception as e:
            self.log(f"Error fetching IMDb ID from {letterboxd_uri}: {e}", 'error')
            return None
    
    def rate_on_imdb(self, imdb_id: str, rating: int) -> bool:
        """
        Rate a movie on IMDb using GraphQL API
        
        Args:
            imdb_id: IMDb ID (e.g., 'tt1234567')
            rating: Rating from 1 to 10
            
        Returns:
            True if successful, False otherwise
        """
        if not 1 <= rating <= 10:
            self.log(f"Invalid rating {rating}, must be 1-10", 'error')
            return False
            
        query = """
        mutation UpdateTitleRating($rating: Int!, $titleId: ID!) {
            rateTitle(input: {rating: $rating, titleId: $titleId}) {
                rating {
                    value
                    __typename
                }
                __typename
            }
        }
        """
        
        variables = {
            "rating": rating,
            "titleId": imdb_id
        }
        
        payload = {
            "query": query,
            "operationName": "UpdateTitleRating",
            "variables": variables
        }
        
        headers = {
            "content-type": "application/json",
            "cookie": self.imdb_cookie
        }
        
        try:
            resp = self.session.post(
                "https://api.graphql.imdb.com/",
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if resp.status_code == 429:
                self.log("IMDb rate limit exceeded, waiting...", 'warning')
                time.sleep(5)
                return False
                
            if resp.status_code != 200:
                self.log(f"Failed to rate {imdb_id}: HTTP {resp.status_code}", 'error')
                return False
                
            json_resp = resp.json()
            
            # Check for errors
            if 'errors' in json_resp and json_resp['errors']:
                error_msg = json_resp['errors'][0].get('message', 'Unknown error')
                if 'Authentication' in error_msg or 'Unauthorized' in error_msg:
                    self.log("IMDb authentication failed. Please check your cookie.", 'error')
                    return False
                self.log(f"GraphQL error: {error_msg}", 'error')
                return False
                
            return True
            
        except Exception as e:
            self.log(f"Exception rating {imdb_id}: {e}", 'error')
            return False
    
    def sync_letterboxd_csv_to_imdb(
        self, 
        letterboxd_csv_path: str,
        dry_run: bool = False,
        delay_seconds: float = 1.0
    ) -> Dict[str, int]:
        """
        Sync Letterboxd ratings CSV to IMDb
        
        Args:
            letterboxd_csv_path: Path to Letterboxd diary.csv or ratings.csv
            dry_run: If True, only show what would be synced without actually syncing
            delay_seconds: Delay between requests to avoid rate limiting
            
        Returns:
            Dictionary with sync statistics
        """
        stats = {
            'total': 0,
            'synced': 0,
            'failed': 0,
            'skipped': 0,
            'no_imdb_id': 0
        }
        
        try:
            # Read Letterboxd CSV
            df = pd.read_csv(letterboxd_csv_path)
            
            # Check for required columns
            required_cols = ['Letterboxd URI', 'Rating']
            if not all(col in df.columns for col in required_cols):
                self.log(f"CSV missing required columns: {required_cols}", 'error')
                return stats
            
            # Filter rows with ratings
            df_rated = df[df['Rating'].notna() & (df['Rating'] > 0)]
            stats['total'] = len(df_rated)
            
            self.log(f"Found {stats['total']} rated movies in Letterboxd CSV", 'info')
            
            if dry_run:
                self.log("DRY RUN - No actual syncing will occur", 'info')
            
            # Process each movie
            for idx, row in df_rated.iterrows():
                letterboxd_uri = row.get('Letterboxd URI', '')
                rating = row.get('Rating', 0)
                name = row.get('Name', 'Unknown')
                
                if not letterboxd_uri:
                    self.log(f"Skipping '{name}': No Letterboxd URI", 'warning')
                    stats['skipped'] += 1
                    continue
                
                # Letterboxd uses 0.5-5.0 scale, IMDb uses 1-10
                imdb_rating = int(float(rating) * 2)
                
                self.log(f"Processing: {name} (LB: {rating}/5, IMDb: {imdb_rating}/10)", 'info')
                
                # Get IMDb ID
                imdb_id = self.get_imdb_id_from_letterboxd_uri(letterboxd_uri)
                
                if not imdb_id:
                    self.log(f"  ⚠️  Could not find IMDb ID for '{name}'", 'warning')
                    stats['no_imdb_id'] += 1
                    continue
                
                self.log(f"  Found IMDb ID: {imdb_id}", 'info')
                
                if dry_run:
                    self.log(f"  [DRY RUN] Would rate {imdb_id} as {imdb_rating}/10", 'info')
                    stats['synced'] += 1
                else:
                    # Actually rate on IMDb
                    success = self.rate_on_imdb(imdb_id, imdb_rating)
                    
                    if success:
                        self.log(f"  ✅ Successfully rated {imdb_id}", 'success')
                        stats['synced'] += 1
                    else:
                        self.log(f"  ❌ Failed to rate {imdb_id}", 'error')
                        stats['failed'] += 1
                    
                    # Delay to avoid rate limiting
                    time.sleep(delay_seconds)
            
            # Summary
            self.log("", 'info')
            self.log("=== Sync Summary ===", 'info')
            self.log(f"Total movies: {stats['total']}", 'info')
            self.log(f"Successfully synced: {stats['synced']}", 'success')
            self.log(f"Failed: {stats['failed']}", 'error')
            self.log(f"No IMDb ID found: {stats['no_imdb_id']}", 'warning')
            self.log(f"Skipped: {stats['skipped']}", 'warning')
            
            return stats
            
        except Exception as e:
            self.log(f"Error syncing Letterboxd to IMDb: {e}", 'error')
            return stats


# CLI for testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Sync Letterboxd ratings to IMDb')
    parser.add_argument('csv_file', help='Path to Letterboxd diary.csv or ratings.csv')
    parser.add_argument('--cookie', required=True, help='IMDb cookie string')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be synced without actually syncing')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between requests in seconds')
    
    args = parser.parse_args()
    
    syncer = LetterboxdToIMDbSync(args.cookie)
    syncer.sync_letterboxd_csv_to_imdb(
        args.csv_file,
        dry_run=args.dry_run,
        delay_seconds=args.delay
    )

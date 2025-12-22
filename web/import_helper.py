"""
CineRecord Hub 2.0 - Import Helper Module
Imports movie data from various formats (Letterboxd, IMDB, etc.)
Note: Trakt JSON import is supported but hidden from UI as web export requires login.
"""

import pandas as pd
import json
import os
import re
from datetime import datetime


def detect_format(file_path):
    """
    Auto-detect the format of an imported file based on its structure.
    
    Returns:
        str: One of 'letterboxd', 'imdb', 'trakt', 'cinerecord', or 'unknown'
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.json':
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check for Trakt format
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if 'movie' in first and 'ids' in first.get('movie', {}):
                    return 'trakt'
            
            # Check for CineRecord format
            if 'movies' in data and 'exported_at' in data:
                return 'cinerecord'
                
        except:
            pass
        return 'unknown'
    
    elif ext == '.csv':
        try:
            df = pd.read_csv(file_path, nrows=5)
            columns = set(df.columns)
            
            # IMDB format has 'Const' column
            if 'Const' in columns:
                return 'imdb'
            
            # Letterboxd format has specific columns
            if 'tmdbID' in columns or ('Title' in columns and 'Rating' in columns and 'WatchedDate' in columns):
                return 'letterboxd'
            
            # CineRecord format
            if 'YourRating_douban' in columns or 'YourRating_imdb' in columns:
                return 'cinerecord'
            
        except:
            pass
        return 'unknown'
    
    return 'unknown'


def import_from_letterboxd(file_path):
    """
    Import data from Letterboxd CSV export.
    
    Letterboxd exports contain:
    - diary.csv: Date, Name, Year, Letterboxd URI, Rating, Rewatch, Tags, Watched Date
    - ratings.csv: Date, Name, Year, Letterboxd URI, Rating
    """
    df = pd.read_csv(file_path)
    
    # Normalize column names
    result_df = pd.DataFrame()
    
    # Map Letterboxd columns to standard format
    result_df['Title'] = df.get('Name', df.get('Title', ''))
    result_df['Year'] = df.get('Year', '')
    
    # Convert rating (Letterboxd uses 0.5-5, we use 1-10)
    if 'Rating' in df.columns:
        def convert_rating(r):
            try:
                rating = float(r)
                # Convert 0.5-5 to 1-10
                return int(rating * 2)
            except:
                return None
        result_df['Your Rating'] = df['Rating'].apply(convert_rating)
    
    # Date
    result_df['Date Rated'] = df.get('Watched Date', df.get('Date', ''))
    
    # Generate Letterboxd URL
    if 'Letterboxd URI' in df.columns:
        result_df['URL_letterboxd'] = df['Letterboxd URI']
    
    return result_df


def import_from_imdb(file_path):
    """
    Import data from IMDB CSV export.
    
    IMDB export contains:
    Const, Your Rating, Date Rated, Title, URL, Title Type, IMDb Rating, 
    Runtime (mins), Year, Genres, Num Votes, Release Date, Directors
    """
    df = pd.read_csv(file_path)
    
    result_df = pd.DataFrame()
    
    # Map IMDB columns
    result_df['Title'] = df.get('Title', '')
    result_df['Year'] = df.get('Year', '')
    result_df['IMDb ID'] = df.get('Const', '')
    result_df['Your Rating'] = df.get('Your Rating', '')
    result_df['Date Rated'] = df.get('Date Rated', '')
    result_df['URL_imdb'] = df.get('URL', '')
    result_df['IMDb Rating'] = df.get('IMDb Rating', '')
    result_df['Genres'] = df.get('Genres', '')
    result_df['Directors'] = df.get('Directors', '')
    
    return result_df


def import_from_trakt(file_path):
    """
    Import data from Trakt JSON export.
    
    Trakt export is a JSON array with structure:
    [
        {
            "movie": {
                "title": "...",
                "year": 2020,
                "ids": {"trakt": 123, "slug": "...", "imdb": "tt1234567", "tmdb": 456}
            },
            "rating": 8,
            "rated_at": "2020-01-01T00:00:00.000Z"
        }
    ]
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    movies = []
    for item in data:
        movie_data = item.get('movie', {})
        ids = movie_data.get('ids', {})
        
        movies.append({
            'Title': movie_data.get('title', ''),
            'Year': movie_data.get('year', ''),
            'IMDb ID': ids.get('imdb', ''),
            'TMDb ID': ids.get('tmdb', ''),
            'Trakt ID': ids.get('trakt', ''),
            'Your Rating': item.get('rating', ''),
            'Date Rated': item.get('rated_at', '').split('T')[0] if item.get('rated_at') else '',
        })
    
    return pd.DataFrame(movies)


def import_from_cinerecord(file_path):
    """
    Import data from CineRecord's own export format (JSON or CSV).
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.json':
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        movies = data.get('movies', data)  # Handle both formats
        return pd.DataFrame(movies)
    
    else:  # CSV
        return pd.read_csv(file_path)


def import_data(file_path, format_type='auto'):
    """
    Main import function that routes to appropriate format handler.
    
    Args:
        file_path: Path to the import file
        format_type: 'auto', 'letterboxd', 'imdb', 'trakt', or 'cinerecord'
        
    Returns:
        pandas DataFrame with imported data
    """
    if format_type == 'auto':
        format_type = detect_format(file_path)
    
    importers = {
        'letterboxd': import_from_letterboxd,
        'imdb': import_from_imdb,
        'trakt': import_from_trakt,
        'cinerecord': import_from_cinerecord,
    }
    
    if format_type not in importers:
        raise ValueError(f"Unknown or unsupported import format: {format_type}")
    
    df = importers[format_type](file_path)
    
    # Add import metadata
    df['_import_source'] = format_type
    df['_import_date'] = datetime.now().isoformat()
    
    return df


def merge_imported_data(existing_df, imported_df, match_by='imdb_id'):
    """
    Merge imported data with existing data, avoiding duplicates.
    
    Args:
        existing_df: Current movie catalog
        imported_df: Newly imported data
        match_by: Column to use for matching ('imdb_id', 'title_year', etc.)
        
    Returns:
        Merged DataFrame with duplicates resolved
    """
    if existing_df is None or existing_df.empty:
        return imported_df
    
    if match_by == 'imdb_id':
        # Match by IMDb ID
        existing_ids = set(existing_df.get('IMDb ID', []))
        new_movies = imported_df[~imported_df.get('IMDb ID', pd.Series()).isin(existing_ids)]
    
    elif match_by == 'title_year':
        # Match by Title + Year combination
        existing_df['_key'] = existing_df['Title'].astype(str) + '_' + existing_df['Year'].astype(str)
        imported_df['_key'] = imported_df['Title'].astype(str) + '_' + imported_df['Year'].astype(str)
        existing_keys = set(existing_df['_key'])
        new_movies = imported_df[~imported_df['_key'].isin(existing_keys)]
        # Clean up
        existing_df.drop('_key', axis=1, inplace=True)
        new_movies = new_movies.drop('_key', axis=1)
    
    else:
        # No matching, just append
        new_movies = imported_df
    
    # Combine
    merged = pd.concat([existing_df, new_movies], ignore_index=True)
    
    return merged

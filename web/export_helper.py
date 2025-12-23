"""
CineRecord Hub 2.0 - Export Helper Module
Exports movie data to various formats (Letterboxd, IMDB, JSON, etc.)
"""

import pandas as pd
import json
import os
from datetime import datetime


def export_to_letterboxd(df, output_path):
    """
    Export data to Letterboxd CSV format.
    Letterboxd expects: tmdbID, imdbID, Title, Year, Directors, WatchedDate, Rating10, WatchedDate, Rating, Review
    """
    letterboxd_df = pd.DataFrame()
    
    # Map columns
    letterboxd_df['imdbID'] = df.get('IMDb ID', df.get('imdb_id', ''))
    letterboxd_df['Title'] = df.get('Title', '')
    letterboxd_df['Year'] = df.get('Year', '')
    letterboxd_df['WatchedDate'] = df.get('Date Rated', df.get('date_rated', ''))
    
    # Convert rating (1-10 scale to 0.5-5 scale for Letterboxd)
    if 'Your Rating' in df.columns:
        letterboxd_df['Rating10'] = df['Your Rating']
    elif 'YourRating_douban' in df.columns:
        letterboxd_df['Rating10'] = df['YourRating_douban']
    elif 'YourRating_imdb' in df.columns:
        letterboxd_df['Rating10'] = df['YourRating_imdb']
    else:
        letterboxd_df['Rating10'] = ''
    
    # Letterboxd uses 0.5-5 scale, IMDB/Douban uses 1-10
    def convert_rating(r):
        try:
            rating = float(r)
            # Convert 1-10 to 0.5-5
            return rating / 2
        except:
            return ''
    
    letterboxd_df['Rating'] = letterboxd_df['Rating10'].apply(convert_rating)
    
    # Save
    letterboxd_df.to_csv(output_path, index=False)
    return output_path


def export_to_imdb(df, output_path):
    """
    Export data to IMDB-compatible CSV format.
    IMDB format: Const, Your Rating, Date Rated, Title, URL, Title Type, IMDb Rating, Runtime (mins), Year, Genres, Num Votes, Release Date, Directors
    """
    imdb_df = pd.DataFrame()
    
    # Map columns
    imdb_df['Const'] = df.get('IMDb ID', df.get('imdb_id', ''))
    imdb_df['Your Rating'] = df.get('Your Rating', df.get('YourRating_imdb', df.get('YourRating_douban', '')))
    imdb_df['Date Rated'] = df.get('Date Rated', df.get('date_rated', ''))
    imdb_df['Title'] = df.get('Title', '')
    imdb_df['URL'] = df.get('URL', df.get('URL_imdb', ''))
    imdb_df['Title Type'] = 'movie'
    imdb_df['IMDb Rating'] = df.get('IMDb Rating', df.get('imdb_rating', ''))
    imdb_df['Year'] = df.get('Year', '')
    imdb_df['Genres'] = df.get('Genres', '')
    
    # Save
    imdb_df.to_csv(output_path, index=False)
    return output_path


def export_to_json(df, output_path):
    """
    Export data to complete JSON format.
    Includes all available fields.
    """
    # Convert DataFrame to list of dicts, handling NaN values
    records = df.where(pd.notnull(df), None).to_dict(orient='records')
    
    export_data = {
        "exported_at": datetime.now().isoformat(),
        "total_count": len(records),
        "movies": records
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)
    
    return output_path


def export_to_cinerecord_csv(df, output_path):
    """
    Export data to CineRecord's standard CSV format.
    Includes all merged data fields.
    """
    # Standard columns order
    standard_columns = [
        'Title', 'Year', 'IMDb ID', 'Douban ID',
        'YourRating_douban', 'YourRating_imdb',
        'Date Rated', 'Genres', 'Directors',
        'URL_douban', 'URL_imdb', 'Cover URL'
    ]
    
    # Select available columns
    available_columns = [col for col in standard_columns if col in df.columns]
    
    # Add any extra columns not in standard list
    extra_columns = [col for col in df.columns if col not in standard_columns]
    all_columns = available_columns + extra_columns
    
    export_df = df[all_columns].copy()
    export_df.to_csv(output_path, index=False)
    return output_path


def export_to_cinepersona(df, output_path, user_stats=None):
    """
    Export data to CinePersona-compatible JSON format.
    Unified format for movie data analysis.
    
    File naming: cinepersona_export_{timestamp}.json
    """
    def safe_get(row, *keys):
        """Get first available value from multiple possible column names."""
        for key in keys:
            if key in row and pd.notna(row[key]):
                return row[key]
        return None
    
    movies = []
    for _, row in df.iterrows():
        # Determine status
        status = 'watched'
        if 'status' in row:
            status = row['status']
        elif safe_get(row, 'YourRating_douban', 'YourRating_imdb', 'Your Rating'):
            status = 'watched'
        
        # Build standardized movie object
        movie = {
            'title': safe_get(row, 'Title', 'title'),
            'title_original': safe_get(row, 'Title_original', 'original_title'),
            'year': int(safe_get(row, 'Year', 'year')) if safe_get(row, 'Year', 'year') else None,
            'ids': {
                'douban': str(safe_get(row, 'douban_id', 'Douban ID')) if safe_get(row, 'douban_id', 'Douban ID') else None,
                'imdb': safe_get(row, 'imdb_id', 'Const', 'IMDb ID'),
                'tmdb': safe_get(row, 'tmdb_id')
            },
            'status': status,
            'rating': int(safe_get(row, 'YourRating_douban', 'YourRating_imdb', 'Your Rating')) if safe_get(row, 'YourRating_douban', 'YourRating_imdb', 'Your Rating') else None,
            'rating_date': str(safe_get(row, 'DateRated_douban', 'DateRated_imdb', 'Date Rated')) if safe_get(row, 'DateRated_douban', 'DateRated_imdb', 'Date Rated') else None,
            'genres': safe_get(row, 'Genres', 'genres').split(', ') if safe_get(row, 'Genres', 'genres') else [],
            'directors': safe_get(row, 'Directors', 'directors').split(', ') if safe_get(row, 'Directors', 'directors') else [],
            'source_platform': 'douban' if safe_get(row, 'douban_id') else 'imdb'
        }
        movies.append(movie)
    
    # Calculate stats
    watched_count = len([m for m in movies if m['status'] == 'watched'])
    want_count = len([m for m in movies if m['status'] == 'want_to_watch'])
    rated_count = len([m for m in movies if m['rating'] is not None])
    
    export_data = {
        'format_version': '1.0',
        'app': 'CineRecord',
        'exported_at': datetime.now().isoformat(),
        'user_stats': user_stats or {
            'watched_count': watched_count,
            'want_to_watch_count': want_count,
            'rated_count': rated_count
        },
        'movies': movies
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)
    
    return output_path


def export_data(df, format_type, output_dir):
    """
    Main export function that routes to appropriate format handler.
    
    Args:
        df: pandas DataFrame with movie data
        format_type: one of 'letterboxd', 'imdb', 'json', 'cinerecord-csv', 'cinepersona'
        output_dir: directory to save the exported file
        
    Returns:
        Path to the exported file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    exporters = {
        'letterboxd': (export_to_letterboxd, f'letterboxd_export_{timestamp}.csv'),
        'imdb': (export_to_imdb, f'imdb_export_{timestamp}.csv'),
        'json': (export_to_json, f'cinerecord_export_{timestamp}.json'),
        'cinerecord-csv': (export_to_cinerecord_csv, f'cinerecord_export_{timestamp}.csv'),
        'cinepersona': (export_to_cinepersona, f'cinepersona_export_{timestamp}.json'),
    }
    
    if format_type not in exporters:
        raise ValueError(f"Unknown export format: {format_type}")
    
    exporter_func, filename = exporters[format_type]
    output_path = os.path.join(output_dir, filename)
    
    return exporter_func(df, output_path)

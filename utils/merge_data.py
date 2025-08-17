import pandas as pd
import numpy as np
import os

def rich_merge_movie_data(douban_csv_path, imdb_csv_path, output_path):
    """
    Loads, merges, enriches, and saves movie data from Douban and IMDb CSV files.

    Args:
        douban_csv_path (str): Path to the Douban ratings CSV file.
        imdb_csv_path (str): Path to the IMDb ratings CSV file.
        output_path (str): Path to save the final merged CSV file.
    """
    try:
        douban_df = pd.read_csv(douban_csv_path)
        imdb_df = pd.read_csv(imdb_csv_path)
        print(f"Loaded {len(douban_df)} records from Douban.")
        print(f"Loaded {len(imdb_df)} records from IMDb.")
    except FileNotFoundError as e:
        print(f"❌ Error: One of the CSV files was not found.")
        print(e)
        return

    # --- Data Cleaning and Preparation ---
    # Standardize column names for easier merging
    douban_df.rename(columns={
        'Your Rating': 'YourRating_douban',
        'Date Rated': 'DateRated_douban',
        'Douban Rating': 'PublicRating_douban',
        'Num Votes': 'Votes_douban'
    }, inplace=True)

    imdb_df.rename(columns={
        'Your Rating': 'YourRating_imdb',
        'Date Rated': 'DateRated_imdb',
        'IMDb Rating': 'PublicRating_imdb',
        'Num Votes': 'Votes_imdb',
        'Runtime (mins)': 'Runtime'
    }, inplace=True)
    
    # Ensure join key 'Const' is of the same type and handle potential read errors
    douban_df['Const'] = douban_df['Const'].astype(str)
    imdb_df['Const'] = imdb_df['Const'].astype(str)

    # --- Merging ---
    # Use an outer join to keep all records from both dataframes
    merged_df = pd.merge(douban_df, imdb_df, on='Const', how='outer', suffixes=('_douban', '_imdb'))

    # --- Data Enrichment and Field Selection ---
    final_df = pd.DataFrame()

    final_df['imdb_id'] = merged_df['Const']
    final_df['douban_id'] = merged_df['douban_id_douban'].fillna(merged_df['douban_id_imdb']).astype(str)
    
    # Smartly choose the best title
    final_df['Title'] = np.where(merged_df['Title_douban'].notna(), merged_df['Title_douban'], merged_df['Title_imdb'])
    
    final_df['Year'] = merged_df['Year_douban'].fillna(merged_df['Year_imdb']).astype('Int64')
    
    # Combine and deduplicate directors and genres
    final_df['Directors'] = merged_df['Directors_douban'].fillna(merged_df['Directors_imdb'])
    final_df['Genres'] = merged_df['Genres_douban'].fillna(merged_df['Genres_imdb'])
    
    # Take fields that only exist in one of the files
    final_df['Actors'] = merged_df.get('Actors', pd.Series(dtype='str'))
    final_df['Country'] = merged_df.get('Country', pd.Series(dtype='str'))
    final_df['Runtime'] = merged_df.get('Runtime', pd.Series(dtype='float'))

    # --- Ratings ---
    final_df['YourRating_douban'] = merged_df['YourRating_douban']
    final_df['YourRating_imdb'] = merged_df['YourRating_imdb']
    final_df['PublicRating_douban'] = merged_df['PublicRating_douban']
    final_df['Votes_douban'] = merged_df['Votes_douban']
    final_df['PublicRating_imdb'] = merged_df['PublicRating_imdb']
    final_df['Votes_imdb'] = merged_df['Votes_imdb']

    # --- First Rated Date Logic ---
    date_douban = pd.to_datetime(merged_df['DateRated_douban'], errors='coerce')
    date_imdb = pd.to_datetime(merged_df['DateRated_imdb'], errors='coerce')
    final_df['DateRated_First'] = pd.concat([date_douban, date_imdb], axis=1).min(axis=1)
    final_df['DateRated_First'] = final_df['DateRated_First'].dt.strftime('%Y-%m-%d')
    final_df['DateRated_douban'] = merged_df['DateRated_douban']
    final_df['DateRated_imdb'] = merged_df['DateRated_imdb']
    
    # --- URLs ---
    final_df['URL_douban'] = merged_df['URL_douban']
    final_df['URL_imdb'] = merged_df['URL_imdb']

    # --- Final Touches ---
    column_order = [
        'douban_id', 'imdb_id', 'Title', 'Year', 'Directors', 'Actors', 'Genres',
        'Country', 'Runtime', 'YourRating_douban', 'YourRating_imdb', 'DateRated_First', 'DateRated_douban', 'DateRated_imdb',
        'PublicRating_douban', 'Votes_douban', 'PublicRating_imdb', 'Votes_imdb',
        'URL_douban', 'URL_imdb'
    ]
    # Ensure all columns exist before ordering
    for col in column_order:
        if col not in final_df.columns:
            final_df[col] = np.nan
            
    final_df = final_df[column_order]
    
    final_df.drop_duplicates(subset=['imdb_id', 'douban_id'], inplace=True)

    # Ensure the output directory exists
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"📊 Your enriched and merged movie data has been saved to: {output_path}")

# This function is kept for compatibility with the existing main.py structure,
# but it will now call the new rich_merge_movie_data function.
def merge_movie_data(douban_csv_path, imdb_csv_path, output_path):
    """
    A wrapper function that calls the rich merging logic with a specified output path.
    This is the primary function to be used by external scripts like app.py.
    """
    rich_merge_movie_data(douban_csv_path, imdb_csv_path, output_path)
    
    # For compatibility, we return the dataframe and path.
    if os.path.exists(output_path):
        return pd.read_csv(output_path), output_path
    else:
        return None, None

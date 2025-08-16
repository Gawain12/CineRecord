import pandas as pd
import os

def merge_movie_data(douban_csv_path, imdb_csv_path, output_dir='scrapers'):
    """
    Merges movie data from Douban and IMDb CSV files into a single DataFrame.
    
    Args:
        douban_csv_path (str): Path to the Douban ratings CSV.
        imdb_csv_path (str): Path to the IMDb ratings CSV.
        output_dir (str): Directory to save the merged file.

    Returns:
        tuple: A tuple containing the merged DataFrame and the path to the saved file,
               or (None, None) if an error occurs.
    """
    if not os.path.exists(douban_csv_path):
        print(f"Error: Douban CSV file not found at {douban_csv_path}")
        return None, None
    if not os.path.exists(imdb_csv_path):
        print(f"Error: IMDb CSV file not found at {imdb_csv_path}")
        return None, None

    # Load the datasets
    douban_df = pd.read_csv(douban_csv_path)
    imdb_df = pd.read_csv(imdb_csv_path)

    print(f"Loaded {len(douban_df)} records from Douban.")
    print(f"Loaded {len(imdb_df)} records from IMDb.")

    # Standardize the merge key
    douban_df.rename(columns={'IMDB_ID': 'Const'}, inplace=True)

    # Merge the dataframes, letting pandas handle all conflicting columns with suffixes
    merged_df = pd.merge(douban_df, imdb_df, on='Const', how='outer', suffixes=('_douban', '_imdb'))
    
    # Rename the resulting suffixed columns for consistency.
    merged_df.rename(columns={
        'Your Rating_douban': 'YourRating_douban',
        'Your Rating_imdb': 'YourRating_imdb',
        'Title_douban': 'Title_douban',
        'Title_imdb': 'Title_imdb',
        'URL_douban': 'URL_douban',
        'URL_imdb': 'URL_imdb',
        'Date Rated_douban': 'DateRated_douban',
        'Date Rated_imdb': 'DateRated_imdb'
    }, inplace=True, errors='ignore')

    # Create a single, reliable 'douban_id' column from the two sources.
    merged_df['douban_id'] = merged_df['douban_id_douban'].fillna(merged_df['douban_id_imdb'])
    merged_df.drop(columns=['douban_id_douban', 'douban_id_imdb'], inplace=True, errors='ignore')

    # Save the merged data, creating a unique filename from the user's Douban ID.
    try:
        douban_user = os.path.basename(douban_csv_path).split('_')[1]
        output_filename = os.path.join(output_dir, f"merged_{douban_user}.csv")
        merged_df.to_csv(output_filename, index=False, encoding='utf-8-sig')
        
        print(f"Successfully merged data into {output_filename}")
        return merged_df, output_filename
    except IndexError:
        print("Could not determine username from douban_csv_path. Using default name.")
        output_filename = os.path.join(output_dir, "merged_output.csv")
        merged_df.to_csv(output_filename, index=False, encoding='utf-8-sig')
        return merged_df, output_filename

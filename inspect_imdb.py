
import pandas as pd

try:
    df = pd.read_csv('data/imdb_ur79467081_ratings.csv')
    print("Columns:", df.columns.tolist())
    print("\nFirst 5 rows:")
    print(df[['Title', 'Year', 'IMDb Rating', 'Your Rating']].head().to_markdown())
except Exception as e:
    print(f"Error: {e}")
    # Try alternate column names if possible or just print all columns
    if 'df' in locals():
        print("All columns:", df.columns.tolist())

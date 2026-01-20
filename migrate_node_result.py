
import pandas as pd
import os
import shutil

NODE_OUTPUT = '/Users/gawaintan/workSpace/Python/CineRecord/scrapers/letterboxd-csv-imdb-tmdb-mapper/output/watched.csv'
SYSTEM_CSV = '/Users/gawaintan/workSpace/Python/CineRecord/data/letterboxd_diary.csv'

def migrate():
    if not os.path.exists(NODE_OUTPUT):
        print(f"Node output not found at {NODE_OUTPUT}")
        return

    print("Loading Node.js script result...")
    # Node output might use strict quoting
    try:
        node_df = pd.read_csv(NODE_OUTPUT)
    except:
        print("Error reading Node output.")
        return
    
    # 映射列名
    # Node: Name, Year, URL, Rating, Watched Date, Description, TmdbIdType, TmdbId, ImdbId
    if 'ImdbId' in node_df.columns:
        node_df['IMDb ID'] = node_df['ImdbId']
    if 'TmdbId' in node_df.columns:
        node_df['TMDB ID'] = node_df['TmdbId']
        
    if os.path.exists(SYSTEM_CSV):
        system_df = pd.read_csv(SYSTEM_CSV)
        print(f"System CSV loaded. Rows: {len(system_df)}")
        
        # Merge on URL
        # 确保 URL 列名一致
        url_col_sys = 'URL' if 'URL' in system_df.columns else ('Letterboxd URI' if 'Letterboxd URI' in system_df.columns else None)
        url_col_node = 'URL' if 'URL' in node_df.columns else ('Letterboxd URI' if 'Letterboxd URI' in node_df.columns else None)
        
        if url_col_sys and url_col_node:
            # 创建 ID 映射字典
            imdb_map = dict(zip(node_df[url_col_node], node_df['IMDb ID']))
            # tmdb_map = dict(zip(node_df[url_col_node], node_df['TMDB ID']))
            
            # 更新系统 DF
            system_df['IMDb ID'] = system_df[url_col_sys].map(imdb_map).fillna(system_df['IMDb ID'])
            
            # TMDB ID is optional, but good to have
            # system_df['TMDB ID'] = system_df[url_col_sys].map(tmdb_map).fillna(system_df['TMDB ID'])
                
            system_df.to_csv(SYSTEM_CSV, index=False)
            print(f"✅ Successfully merged {len(imdb_map)} IDs into System CSV.")
        else:
            print("URL column missing, cannot merge.")
    else:
        print("System CSV not found.")

if __name__ == "__main__":
    migrate()

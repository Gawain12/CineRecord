"""
Letterboxd IMDb ID Enrichment
Fetch IMDb IDs from Letterboxd URIs and save them to local CSV
"""
import os
import re
import time
import random
import requests
import pandas as pd


def get_imdb_id_from_letterboxd_uri(letterboxd_uri):
    """
    Fetch IMDb ID from Letterboxd movie page.
    
    Args:
        letterboxd_uri: Letterboxd URI like 'https://letterboxd.com/film/...'
        
    Returns:
        IMDb ID (e.g., 'tt1234567') or None if not found
    """
    if not letterboxd_uri or pd.isna(letterboxd_uri):
        return None
        
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Accept': 'text/html',
        }
        
        resp = requests.get(letterboxd_uri, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        
        # Extract IMDb ID from page
        matches = re.findall(r'imdb\.com/title/(tt\d+)', resp.text)
        if matches:
            return matches[0]
            
        return None
        
    except Exception as e:
        return None


def enrich_letterboxd_csv_with_imdb_ids(csv_path, output_path=None, logger=None):
    """
    Enrich Letterboxd CSV by fetching and adding IMDb IDs.
    
    Args:
        csv_path: Path to Letterboxd diary.csv or ratings.csv
        output_path: Where to save enriched CSV (defaults to same as input)
        logger: Optional logger with .log() method
        
    Returns:
        Stats dict with counts
    """
    def log(msg, level='info'):
        if logger:
            logger.log(msg, level)
        else:
            print(f"[{level.upper()}] {msg}")
    
    if output_path is None:
        output_path = csv_path
    
    try:
        # Read CSV
        df = pd.read_csv(csv_path)
        
        if 'Letterboxd URI' not in df.columns:
            log("❌ CSV缺少 'Letterboxd URI' 列", 'error')
            return None
        
        # Add IMDb ID column if not exists
        if 'IMDb ID' not in df.columns:
            df['IMDb ID'] = None
        
        # Count movies needing enrichment
        needs_enrichment = df['IMDb ID'].isna() | (df['IMDb ID'] == '')
        total_to_fetch = needs_enrichment.sum()
        total_movies = len(df)
        already_has_id = total_movies - total_to_fetch
        
        log(f"📊 Letterboxd CSV: {total_movies} 部电影", 'info')
        log(f"   ✅ 已有IMDb ID: {already_has_id} 部", 'info')
        log(f"   🔍 需要获取IMDb ID: {total_to_fetch} 部", 'info')
        
        if total_to_fetch == 0:
            log("✅ 所有电影都已有IMDb ID，无需处理", 'success')
            return {
                'total': total_movies,
                'already_has_id': already_has_id,
                'fetched': 0,
                'failed': 0
            }
        
        # Fetch IMDb IDs for movies that don't have them
        fetched_count = 0
        failed_count = 0
        
        log(f"🚀 开始获取 {total_to_fetch} 部电影的IMDb ID...", 'info')
        
        if logger and hasattr(logger, 'progress'):
            logger.progress(0, total_to_fetch, "准备获取IMDb ID...")
        
        processed = 0
        for idx, row in df[needs_enrichment].iterrows():
            processed += 1
            letterboxd_uri = row['Letterboxd URI']
            name = row.get('Name', 'Unknown')
            year = row.get('Year', '')
            
            if logger and hasattr(logger, 'progress'):
                logger.progress(processed, total_to_fetch, f"获取IMDb ID ({processed}/{total_to_fetch})")
            
            # Fetch IMDb ID
            imdb_id = get_imdb_id_from_letterboxd_uri(letterboxd_uri)
            
            if imdb_id:
                df.at[idx, 'IMDb ID'] = imdb_id
                log(f"✅ {processed}/{total_to_fetch}: {name} ({year}) → {imdb_id}", 'success')
                fetched_count += 1
            else:
                log(f"⚠️ {processed}/{total_to_fetch}: {name} ({year}) - 无法获取IMDb ID", 'warning')
                failed_count += 1
            
            # Rate limiting to be nice to Letterboxd
            time.sleep(random.uniform(0.5, 1.5))
        
        # Save enriched CSV
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        log(f"💾 已保存到: {output_path}", 'info')
        log("", 'info')
        log(f"完成! ✅ 成功获取: {fetched_count} / ❌ 失败: {failed_count}", 'success')
        
        return {
            'total': total_movies,
            'already_has_id': already_has_id,
            'fetched': fetched_count,
            'failed': failed_count
        }
        
    except Exception as e:
        log(f"❌ 处理出错: {e}", 'error')
        import traceback
        traceback.print_exc()
        return None


# CLI for testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='为Letterboxd CSV添加IMDb ID')
    parser.add_argument('csv_file', help='Letterboxd diary.csv 或 ratings.csv 路径')
    parser.add_argument('-o', '--output', help='输出文件路径（默认覆盖原文件）')
    
    args = parser.parse_args()
    
    enrich_letterboxd_csv_with_imdb_ids(args.csv_file, args.output)

import requests
import pandas as pd
import json
import os
import shutil
import time
import random
import sys
import re
import argparse

# Add parent directory to path to allow importing 'config'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.config import DOUBAN_CONFIG, IMDB_CONFIG

# ==============================================================================
# SECTION 1: API Callers
# ==============================================================================

def get_douban_ck_from_cookie(cookie_string: str) -> str:
    """Safely extracts the 'ck' value from the Douban cookie."""
    match = re.search(r'ck="?([^;"]+)"?', cookie_string)
    if match:
        return match.group(1)
    print("❌ Fatal Error: Could not extract 'ck' value from Douban cookie. Script cannot continue.")
    sys.exit(1)

def rate_on_imdb(movie_const: str, rating: int, headers: dict, movie_title: str = None):
    """Rates a given movie on IMDb using the API."""
    api_url = 'https://api.graphql.imdb.com/'
    local_headers = headers.copy()
    local_headers['referer'] = f'https://www.imdb.com/title/{movie_const}/'
    
    payload = {
        "query": "mutation UpdateTitleRating($rating: Int!, $titleId: ID!) {\n  rateTitle(input: {rating: $rating, titleId: $titleId}) {\n    rating {\n      value\n    }\n  }\n}",
        "operationName": "UpdateTitleRating",
        "variables": {"rating": rating, "titleId": movie_const}
    }
    
    display_name = movie_title if movie_title else movie_const
    print(f"--> [IMDb] 准备为电影《{display_name}》评分为: {rating}")
    try:
        response = requests.post(api_url, headers=local_headers, json=payload, timeout=15)
        response.raise_for_status()
        response_data = response.json()
        if 'errors' in response_data:
            print(f"❌ [IMDb] API 评分失败 (GraphQL 错误): {response_data['errors']}")
            return False
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ [IMDb] 请求失败: {e}")
        return False

def rate_on_douban(subject_id: str, rating: int, headers: dict, ck_value: str, movie_title: str = None):
    """Rates a given movie on Douban using the API."""
    api_url = f'https://movie.douban.com/j/subject/{subject_id}/interest'
    
    # Douban's API uses a 5-star system, so we convert the 10-point rating.
    douban_rating_5_scale = round(rating / 2)
    
    payload_data = {
        'interest': 'collect', 'rating': douban_rating_5_scale, 'foldcollect': 'F',
        'tags': '', 'comment': '', 'ck': ck_value
    }
    
    display_name = movie_title if movie_title else subject_id
    print(f"--> [豆瓣] 准备为电影《{display_name}》评分为: {rating} (API发送: {douban_rating_5_scale} 星)")
    try:
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
        response = requests.post(api_url, headers=headers, data=payload_data, timeout=15, verify=False)
        response.raise_for_status()
        response_data = response.json()
        if response_data.get('r') != 0:
            print(f"   ⚠️ 警告: 服务器返回非 0 结果代码，可能表示操作未完全成功。")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ [豆瓣] 请求失败: {e}")
        return False


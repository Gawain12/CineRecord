import os
import io
import sys

# Redirection for PyInstaller windowed mode (where sys.stdout/stderr are None)
# When running with console=True, these are not None.
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

# Determine async mode
is_windows_frozen = getattr(sys, 'frozen', False) and sys.platform == 'win32'

if is_windows_frozen:
    ASYNC_MODE = 'threading'
else:
    try:
        # Only try eventlet if NOT on Windows frozen
        import eventlet
        eventlet.monkey_patch()
        ASYNC_MODE = 'eventlet'
    except (ImportError, NotImplementedError):
        ASYNC_MODE = 'threading'


# Ensure project root is in path for imports
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import logging
import json
import requests
from flask import Flask, render_template, request, jsonify, Response, redirect, session, render_template_string
from flask_socketio import SocketIO, emit
from threading import Timer
import webbrowser
import pandas as pd
import time
import re
from datetime import datetime, timezone

# --- PATH RESOLUTION (CRITICAL FOR PACKAGING) ---
if getattr(sys, 'frozen', False):
    # Running in PyInstaller bundle
    _internal_base = sys._MEIPASS
    # On Mac, sys.executable is CineRecord.app/Contents/MacOS/CineRecord
    # We want APP_ROOT to be the directory containing CineRecord.app
    if sys.platform == 'darwin':
        # Path: dist/CineRecord.app/Contents/MacOS/CineRecord
        # 3 levels up is dist/
        APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(sys.executable))))
    else:
        APP_ROOT = os.path.dirname(sys.executable)
else:
    # Development mode
    _internal_base = os.path.dirname(os.path.abspath(__file__))
    APP_ROOT = os.path.join(_internal_base, '..')

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    # In dev mode, go up one level from web/ to project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.abspath(os.path.join(project_root, relative_path))

# Setup directories in a writable location relative to the executable (not in the bundle)
DATA_DIR = os.path.join(APP_ROOT, 'data')
CONFIG_DIR = os.path.join(APP_ROOT, 'config')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

# Logger setup - write to current user directory if APP_ROOT is restricted
LOG_FILE = os.path.join(APP_ROOT, 'cinerecord.log')
_stdout_stream = sys.stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(_stdout_stream)
    ]
)
logger = logging.getLogger(__name__)

# --- FLASK APP SETUP ---
template_dir = get_resource_path('web/templates')
static_dir = get_resource_path('web/static')

logger.info(f"Initializing SocketIO with ASYNC_MODE={ASYNC_MODE}")
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(
    app,
    async_mode=ASYNC_MODE,
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=20 * 1024 * 1024
)  # Prevent reconnection during long data fetches

# Import helpers after monkey_patch
from web.config_helper import read_config, write_config
from web.logic import perform_sync_logic
from utils.merge_data import merge_movie_data
from web.auth_helper import run_login_in_thread

# Plugin Architecture - Import adapter registry
from adapters.registry import AdapterRegistry
from adapters.logger import SocketLogger
from adapters import douban, imdb, trakt, letterboxd  # Register all adapters

# Backward compatibility imports (deprecated)
from adapters.douban import run_scraper as run_douban, run_wish_scraper
from adapters.imdb import run_scraper as run_imdb
from scrapers.trakt_client import TraktClient  # Keep original for backward compat
from scrapers.tmdb_client import TMDBClient  # TMDB integration
from scrapers.sync_trakt_douban import sync_trakt_to_douban

# Scheduled Sync
from web.scheduler import get_scheduler


# Global state
CORE_COLUMNS = ['Const', 'Title', 'Your Rating', 'Date Rated', 'douban_id']
ESSENTIAL_COLUMNS = [
    'Const', 'Title', 'Your Rating', 'Date Rated', 'douban_id', 'Year', 'URL', 'Cover URL',
    'Douban Rating', 'IMDb Rating', 'Num Votes', 'Genres', 'Directors', 'Type'
]
APP_DATA = {}
APP_DATA_LOADED = False

from web.data_utils import safe_df_to_records

MEDIA_LIBRARY_CACHE_TTL = 15 * 60  # seconds

def get_server_auth_config():
    config = read_config()
    password = str(config.get('server_password', '') or '').strip()
    if not password:
        return None
    username = str(config.get('server_username') or 'cinerecord').strip() or 'cinerecord'
    return username, password

LOGIN_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>CineRecord 登录</title>
  <style>
    body { font-family: Arial, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; }
    .card { max-width:360px; margin:12vh auto; padding:24px; background:#111827; border:1px solid #1f2937; border-radius:12px; }
    h1 { font-size:18px; margin:0 0 12px; }
    label { display:block; font-size:12px; margin:10px 0 6px; color:#94a3b8; }
    input { width:100%; padding:10px 12px; border-radius:8px; border:1px solid #334155; background:#0b1220; color:#e2e8f0; }
    button { width:100%; margin-top:16px; padding:10px 12px; border:0; border-radius:8px; background:#2563eb; color:#fff; font-weight:600; cursor:pointer; }
    .error { margin-top:12px; color:#fca5a5; font-size:12px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🔒 CineRecord 登录</h1>
    <form method="post">
      <label>用户名</label>
      <input name="username" autofocus>
      <label>密码</label>
      <input type="password" name="password">
      <button type="submit">登录</button>
    </form>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
  </div>
</body>
</html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    auth_config = get_server_auth_config()
    if not auth_config:
        return redirect('/')
    error = None
    if request.method == 'POST':
        username = str(request.form.get('username') or '').strip()
        password = str(request.form.get('password') or '').strip()
        if username == auth_config[0] and password == auth_config[1]:
            session['server_auth'] = True
            return redirect('/')
        error = '用户名或密码错误'
    return render_template_string(LOGIN_TEMPLATE, error=error)

@app.route('/logout')
def logout():
    session.pop('server_auth', None)
    return redirect('/login')

@app.before_request
def enforce_login():
    auth_config = get_server_auth_config()
    if not auth_config:
        return None
    if request.path.startswith('/login') or request.path.startswith('/static/'):
        return None
    if session.get('server_auth'):
        return None
    return redirect('/login')

def normalize_imdb_id(value):
    if value is None:
        return ''
    s = str(value).strip()
    if not s:
        return ''
    s = s.lower()
    if s.startswith('tt'):
        return s
    if s.isdigit():
        return f"tt{s}"
    return s

def normalize_title(value):
    if value is None:
        return ''
    s = str(value).strip().lower()
    if not s:
        return ''
    s = re.sub(r'\s+', ' ', s)
    return s

def normalize_df_columns(df):
    if df is None or df.empty:
        return df
    rename_map = {}
    for col in df.columns:
        new_col = str(col).lstrip('\ufeff').strip()
        if new_col != col:
            rename_map[col] = new_col
    if rename_map:
        df = df.rename(columns=rename_map)
    return df

def load_douban_wish_for_user(user_id, force=False):
    user_id = str(user_id or '').strip()
    if not user_id:
        return None
    wish_path = os.path.join(DATA_DIR, f'douban_{user_id}_wish.csv')
    if not os.path.exists(wish_path):
        return None
    mtime = os.path.getmtime(wish_path)
    cached_path = APP_DATA.get('douban_wish_path')
    cached_mtime = APP_DATA.get('douban_wish_mtime')
    if not force and cached_path == wish_path and cached_mtime == mtime and APP_DATA.get('douban_wish_df') is not None:
        return APP_DATA.get('douban_wish_df')
    df_wish = pd.read_csv(wish_path)
    df_wish = normalize_df_columns(df_wish)
    df_wish = filter_wish_df(df_wish)
    df_wish = ensure_type_column(df_wish)
    APP_DATA['douban_wish_df'] = df_wish
    APP_DATA['douban_wish_path'] = wish_path
    APP_DATA['douban_wish_mtime'] = mtime
    return df_wish

def load_platform_wish_for_user(platform, user_id, force=False, assume_wish=False):
    platform = str(platform or '').strip().lower()
    user_id = str(user_id or '').strip()
    if not platform or not user_id:
        return None
    wish_path = os.path.join(DATA_DIR, f'{platform}_{user_id}_wish.csv')
    if not os.path.exists(wish_path):
        return None
    mtime = os.path.getmtime(wish_path)
    cached_path = APP_DATA.get(f'{platform}_wish_path')
    cached_mtime = APP_DATA.get(f'{platform}_wish_mtime')
    cached_df = APP_DATA.get(f'{platform}_wish_df')
    if not force and cached_path == wish_path and cached_mtime == mtime and cached_df is not None:
        return cached_df
    df_wish = pd.read_csv(wish_path)
    df_wish = normalize_df_columns(df_wish)
    if assume_wish and 'status' not in df_wish.columns:
        df_wish['status'] = 'wish'
    df_wish = filter_wish_df(df_wish)
    df_wish = ensure_type_column(df_wish)
    APP_DATA[f'{platform}_wish_df'] = df_wish
    APP_DATA[f'{platform}_wish_path'] = wish_path
    APP_DATA[f'{platform}_wish_mtime'] = mtime
    return df_wish

def load_letterboxd_watchlist(force=False):
    wish_path = os.path.join(DATA_DIR, 'letterboxd_watchlist.csv')
    if not os.path.exists(wish_path):
        return None
    mtime = os.path.getmtime(wish_path)
    cached_path = APP_DATA.get('letterboxd_wish_path')
    cached_mtime = APP_DATA.get('letterboxd_wish_mtime')
    cached_df = APP_DATA.get('letterboxd_wish_df')
    if not force and cached_path == wish_path and cached_mtime == mtime and cached_df is not None:
        return cached_df
    df_wish = pd.read_csv(wish_path)
    df_wish = normalize_df_columns(df_wish)
    if 'status' not in df_wish.columns:
        df_wish['status'] = 'wish'
    df_wish = filter_wish_df(df_wish)
    df_wish = ensure_type_column(df_wish)
    APP_DATA['letterboxd_wish_df'] = df_wish
    APP_DATA['letterboxd_wish_path'] = wish_path
    APP_DATA['letterboxd_wish_mtime'] = mtime
    return df_wish

def load_cinepersona_watchlist(force=False):
    wish_path = os.path.join(DATA_DIR, 'cinepersona_watchlist.csv')
    if not os.path.exists(wish_path):
        return None
    mtime = os.path.getmtime(wish_path)
    cached_path = APP_DATA.get('cinepersona_wish_path')
    cached_mtime = APP_DATA.get('cinepersona_wish_mtime')
    cached_df = APP_DATA.get('cinepersona_wish_df')
    if not force and cached_path == wish_path and cached_mtime == mtime and cached_df is not None:
        return cached_df
    df_wish = pd.read_csv(wish_path)
    df_wish = normalize_df_columns(df_wish)
    if 'status' not in df_wish.columns:
        df_wish['status'] = 'wish'
    df_wish = filter_wish_df(df_wish)
    df_wish = ensure_type_column(df_wish)
    APP_DATA['cinepersona_wish_df'] = df_wish
    APP_DATA['cinepersona_wish_path'] = wish_path
    APP_DATA['cinepersona_wish_mtime'] = mtime
    return df_wish

def normalize_media_base_url(url):
    if not url:
        return ''
    base = str(url).strip().rstrip('/')
    if base.endswith('/web'):
        base = base[:-4]
    return base.rstrip('/')

def build_media_item_url(base_url, item_id, server_id=None, server_type=None, plex_machine_id=None):
    if not base_url or not item_id:
        return ''
    base = normalize_media_base_url(base_url)
    if server_type == 'plex':
        machine_id = plex_machine_id or server_id
        if not machine_id:
            return ''
        return f"{base}/web/index.html#!/server/{machine_id}/details?key=/library/metadata/{item_id}"
    if server_type == 'emby':
        url = f"{base}/web/index.html#!/item?id={item_id}"
    else:
        url = f"{base}/web/index.html#!/details?id={item_id}"
    if server_id:
        url += f"&serverId={server_id}"
    return url

def get_provider_id(provider_ids, key):
    if not isinstance(provider_ids, dict):
        return ''
    for k, v in provider_ids.items():
        if str(k).lower() == str(key).lower():
            return v
    return ''

def fetch_media_server_user_id(base_url, headers):
    try:
        resp = requests.get(f"{base_url}/Users", headers=headers, timeout=15)
        resp.raise_for_status()
        users = resp.json()
        if isinstance(users, list) and users:
            return users[0].get('Id')
    except Exception:
        return None
    return None

def detect_media_server_type(base_url, api_key):
    headers = {"X-Emby-Token": api_key} if api_key else {}
    try:
        resp = requests.get(f"{base_url}/System/Info", headers=headers, timeout=10)
        if resp.status_code == 200:
            info = resp.json()
            product = str(info.get('ProductName') or '').lower()
            if 'emby' in product:
                return 'emby', info.get('Id')
            return 'jellyfin', info.get('Id')
    except Exception:
        pass
    try:
        resp = requests.get(f"{base_url}/identity", params={'X-Plex-Token': api_key}, timeout=10)
        if resp.status_code == 200:
            return 'plex', None
    except Exception:
        pass
    return 'emby', None

def fetch_media_server_items(base_url, api_key):
    headers = {"X-Emby-Token": api_key}

    def fetch_items(endpoint):
        items = []
        start_index = 0
        limit = 200
        while True:
            params = {
                "Recursive": "true",
                "IncludeItemTypes": "Movie",
                "Fields": "ProviderIds,ProductionYear,OriginalTitle,Path,MediaSources,ServerId",
                "StartIndex": start_index,
                "Limit": limit
            }
            resp = requests.get(endpoint, headers=headers, params=params, timeout=20)
            if resp.status_code >= 400:
                resp.raise_for_status()
            data = resp.json()
            batch = data.get("Items", []) or []
            if not batch:
                break
            items.extend(batch)
            total = data.get("TotalRecordCount")
            if isinstance(total, int) and len(items) >= total:
                break
            if len(batch) < limit:
                break
            start_index += len(batch)
        return items

    try:
        return fetch_items(f"{base_url}/Items")
    except requests.HTTPError as e:
        resp = e.response
        if resp is not None and resp.status_code == 400 and 'UserId' in (resp.text or ''):
            user_id = fetch_media_server_user_id(base_url, headers)
            if user_id:
                return fetch_items(f"{base_url}/Users/{user_id}/Items")
        raise

def simplify_media_items(items, base_url, server_type=None, plex_machine_id=None):
    simplified = []
    if not items:
        return simplified
    for item in items:
        provider_ids = item.get('ProviderIds', {}) or {}
        imdb_id = get_provider_id(provider_ids, 'Imdb')
        tmdb_id = get_provider_id(provider_ids, 'Tmdb')
        title = item.get('Name') or item.get('OriginalTitle') or ''
        year = item.get('ProductionYear') or ''
        item_id = item.get('Id') or ''
        server_id = item.get('ServerId') or ''
        media_path = item.get('Path') or ''
        if not media_path:
            media_sources = item.get('MediaSources') or []
            if isinstance(media_sources, list) and media_sources:
                media_path = media_sources[0].get('Path') or ''
        file_name = ''
        if media_path:
            try:
                safe_path = str(media_path).replace('\\', '/')
                file_name = os.path.basename(safe_path)
            except Exception:
                file_name = ''
        simplified.append({
            'title': title,
            'year': year,
            'imdb_id': imdb_id,
            'tmdb_id': tmdb_id,
            'item_id': item_id,
            'server_id': server_id,
            'library_url': build_media_item_url(base_url, item_id, server_id, server_type, plex_machine_id),
            'media_path': media_path,
            'file_name': file_name
        })
    return simplified

def _plex_extract_ids(video):
    imdb_id = ''
    tmdb_id = ''
    def take_imdb(val):
        nonlocal imdb_id
        if val and 'tt' in val:
            m = re.search(r'(tt\\d+)', val)
            if m:
                imdb_id = m.group(1)
    def take_tmdb(val):
        nonlocal tmdb_id
        if val:
            m = re.search(r'(\\d+)', val)
            if m:
                tmdb_id = m.group(1)
    guid_attr = video.get('guid') or ''
    if 'imdb' in guid_attr:
        take_imdb(guid_attr)
    if 'tmdb' in guid_attr:
        take_tmdb(guid_attr)
    for guid in video.findall('Guid'):
        gid = guid.get('id') or ''
        if 'imdb' in gid:
            take_imdb(gid)
        if 'tmdb' in gid:
            take_tmdb(gid)
    return imdb_id, tmdb_id

def fetch_plex_items(base_url, token):
    import xml.etree.ElementTree as ET
    params = {'X-Plex-Token': token}
    identity = requests.get(f"{base_url}/identity", params=params, timeout=10)
    identity.raise_for_status()
    machine_id = None
    try:
        machine_id = ET.fromstring(identity.text).get('machineIdentifier')
    except Exception:
        machine_id = None

    sections = requests.get(f"{base_url}/library/sections", params=params, timeout=10)
    sections.raise_for_status()
    root = ET.fromstring(sections.text)
    movie_sections = [s for s in root.findall('Directory') if s.get('type') == 'movie']
    items = []
    for section in movie_sections:
        key = section.get('key')
        if not key:
            continue
        start = 0
        size = 500
        while True:
            section_params = {
                'X-Plex-Token': token,
                'type': 1,
                'X-Plex-Container-Start': start,
                'X-Plex-Container-Size': size
            }
            resp = requests.get(f"{base_url}/library/sections/{key}/all", params=section_params, timeout=15)
            resp.raise_for_status()
            tree = ET.fromstring(resp.text)
            videos = tree.findall('Video')
            items.extend(videos)
            total = int(tree.get('totalSize') or len(videos))
            start += len(videos)
            if start >= total or not videos:
                break
    return items, machine_id

def simplify_plex_items(videos, base_url, machine_id):
    simplified = []
    if not videos:
        return simplified
    for video in videos:
        title = video.get('title') or ''
        year = video.get('year') or ''
        rating_key = video.get('ratingKey') or ''
        imdb_id, tmdb_id = _plex_extract_ids(video)
        media_path = ''
        file_name = ''
        media = video.find('Media')
        part = None
        if media is not None:
            part = media.find('Part')
        if part is not None:
            media_path = part.get('file') or ''
        if media_path:
            safe_path = str(media_path).replace('\\', '/')
            file_name = os.path.basename(safe_path)
        simplified.append({
            'title': title,
            'year': year,
            'imdb_id': imdb_id,
            'tmdb_id': tmdb_id,
            'item_id': rating_key,
            'server_id': machine_id,
            'library_url': build_media_item_url(base_url, rating_key, machine_id, 'plex', machine_id),
            'media_path': media_path,
            'file_name': file_name
        })
    return simplified

def fetch_media_server_library(config):
    base_url = normalize_media_base_url(config.get('media_server_url', ''))
    api_key = str(config.get('media_server_api_key', '') or '').strip()
    if not base_url or not api_key:
        return None, base_url

    cache = APP_DATA.get('media_server_library_cache') or {}
    cached_url = cache.get('base_url')
    fetched_at = cache.get('fetched_at') or 0
    if cached_url == base_url and cache.get('items') and (time.time() - fetched_at) < MEDIA_LIBRARY_CACHE_TTL:
        return cache.get('items'), base_url

    try:
        server_type, server_id = detect_media_server_type(base_url, api_key)
        if server_type == 'plex':
            videos, machine_id = fetch_plex_items(base_url, api_key)
            simplified = simplify_plex_items(videos, base_url, machine_id)
        else:
            items = fetch_media_server_items(base_url, api_key)
            simplified = simplify_media_items(items, base_url, server_type, server_id)
    except Exception as e:
        logger.warning(f"[Media Server] Fetch failed: {e}")
        return None, base_url

    APP_DATA['media_server_library_cache'] = {
        'base_url': base_url,
        'server_type': server_type,
        'items': simplified,
        'fetched_at': time.time()
    }
    return simplified, base_url

def normalize_cinepersona_url(url):
    if not url:
        return ''
    return str(url).strip().rstrip('/')

def extract_wishlist_imdb_id(record):
    if not isinstance(record, dict):
        return ''
    candidates = [
        record.get('Const'),
        record.get('imdb_id'),
        record.get('IMDb ID'),
        record.get('IMDB ID'),
        record.get('Imdb'),
        record.get('IMDb')
    ]
    for value in candidates:
        imdb_id = normalize_imdb_id(value)
        if imdb_id:
            return imdb_id
    return ''

def apply_media_server_matching(wishlist_records, library_items):
    if not wishlist_records:
        return wishlist_records

    if not library_items:
        for record in wishlist_records:
            record['library_matched'] = False
        return wishlist_records

    imdb_index = {}
    tmdb_index = {}
    title_year_index = {}
    for item in library_items:
        imdb_id = normalize_imdb_id(item.get('imdb_id'))
        if imdb_id and imdb_id not in imdb_index:
            imdb_index[imdb_id] = item
        tmdb_id = str(item.get('tmdb_id') or '').strip()
        if tmdb_id and tmdb_id not in tmdb_index:
            tmdb_index[tmdb_id] = item
        title = normalize_title(item.get('title'))
        year = str(item.get('year') or '').strip()
        if title and year:
            key = f"{title}|{year}"
            if key not in title_year_index:
                title_year_index[key] = item

    for record in wishlist_records:
        match = None
        imdb_id = extract_wishlist_imdb_id(record)
        if imdb_id:
            match = imdb_index.get(imdb_id)
        if not match:
            tmdb_id = str(record.get('TMDB ID') or record.get('tmdb_id') or '').strip()
            if tmdb_id:
                match = tmdb_index.get(tmdb_id)
        if not match:
            title = normalize_title(record.get('Title') or record.get('title') or record.get('Name') or '')
            year = str(record.get('Year') or record.get('year') or '').strip()
            if title and year:
                match = title_year_index.get(f"{title}|{year}")

        if match:
            record['library_matched'] = True
            record['library_item_id'] = match.get('item_id')
            record['library_title'] = match.get('title')
            record['library_year'] = match.get('year')
            record['library_url'] = match.get('library_url')
            record['library_path'] = match.get('media_path')
            record['library_file_name'] = match.get('file_name')
        else:
            record['library_matched'] = False

    return wishlist_records

def filter_wish_df(df, allowed_statuses=None):
    if df is None or df.empty:
        return df
    allowed = allowed_statuses or {'wish', 'want_to_watch', 'mark'}
    filtered = df
    if 'status' in df.columns:
        status_series = df['status'].fillna('').astype(str).str.lower().str.strip()
        filtered = df[status_series.isin(allowed)]
    else:
        # Without status, treat as invalid wishlist to avoid mixing watched items.
        return df.head(0).copy()
    if filtered is None or filtered.empty:
        return filtered
    if 'status' not in filtered.columns:
        filtered = filtered.copy()
        filtered['status'] = 'wish'
    return filtered

def normalize_type_value(value):
    if value is None:
        return ''
    s = str(value).lower().strip()
    if not s:
        return ''
    if any(k in s for k in ['tv', 'series', 'episode', 'show', 'miniseries']):
        return 'tv'
    return 'movie'

def ensure_type_column(df):
    if df is None or df.empty:
        return df
    df = df.copy()
    source_col = None
    for col in ['Type', 'type', 'Title Type', 'TmdbIdType', 'tmdb_type']:
        if col in df.columns:
            source_col = col
            break
    if source_col:
        df['Type'] = df[source_col].apply(normalize_type_value)
    else:
        df['Type'] = ''
    return df

def build_wishlist_df(config):
    frames = []
    sources = [
        ('douban', str(config.get('douban_user_id') or '').strip(), False),
        ('imdb', str(config.get('imdb_user_id') or '').strip(), True),
        ('trakt', str(config.get('trakt_user_id') or '').strip(), True),
        ('tmdb', str(config.get('tmdb_username') or config.get('tmdb_user_id') or '').strip(), True),
    ]

    for platform, user_id, assume_wish in sources:
        if not user_id:
            continue
        if platform == 'douban':
            df = load_douban_wish_for_user(user_id, force=False)
        else:
            df = load_platform_wish_for_user(platform, user_id, force=False, assume_wish=assume_wish)
        if df is None or df.empty:
            continue
        df = df.copy()
        df['source'] = platform
        frames.append(df)

    letterboxd_wish = load_letterboxd_watchlist(force=False)
    if letterboxd_wish is not None and not letterboxd_wish.empty:
        letterboxd_wish = letterboxd_wish.copy()
        letterboxd_wish['source'] = 'letterboxd'
        frames.append(letterboxd_wish)

    cinepersona_wish = load_cinepersona_watchlist(force=False)
    if cinepersona_wish is not None and not cinepersona_wish.empty:
        cinepersona_wish = cinepersona_wish.copy()
        cinepersona_wish['source'] = 'cinepersona'
        frames.append(cinepersona_wish)

    if not frames:
        return None
    return pd.concat(frames, ignore_index=True, sort=False)

def _extract_imdb_watchlist_items(data):
    records = []
    seen = set()
    list_context_keys = {
        'listItemId', 'listItem', 'listItemCreatedAt', 'listItemCreated', 'listItemRanking',
        'listItemTitle', 'listItemRank', 'listItemTime'
    }

    def normalize_title_type(value):
        if not value:
            return ''
        if isinstance(value, dict):
            value = value.get('id') or value.get('text') or ''
        return str(value)

    def add_record(title_obj, meta=None):
        imdb_id = title_obj.get('id') or title_obj.get('titleId') or title_obj.get('const')
        if not imdb_id or imdb_id in seen:
            return
        seen.add(imdb_id)
        title_text = ''
        if isinstance(title_obj.get('titleText'), dict):
            title_text = title_obj.get('titleText', {}).get('text') or ''
        if not title_text and isinstance(title_obj.get('originalTitleText'), dict):
            title_text = title_obj.get('originalTitleText', {}).get('text') or ''
        if not title_text:
            title_text = title_obj.get('title') or ''
        year = ''
        if isinstance(title_obj.get('releaseYear'), dict):
            year = title_obj.get('releaseYear', {}).get('year') or ''
        if not year:
            year = title_obj.get('year') or ''
        cover_url = ''
        if isinstance(title_obj.get('primaryImage'), dict):
            cover_url = title_obj.get('primaryImage', {}).get('url') or ''
        if not cover_url and isinstance(title_obj.get('image'), dict):
            cover_url = title_obj.get('image', {}).get('url') or ''
        title_type = normalize_title_type(title_obj.get('titleType'))
        record = {
            'Const': imdb_id,
            'Title': title_text,
            'Year': year,
            'Cover URL': cover_url,
            'URL': f"https://www.imdb.com/title/{imdb_id}/",
            'status': 'wish',
            'type': title_type
        }
        if meta and meta.get('date_added'):
            record['Date Added'] = meta.get('date_added')
        records.append(record)

    def traverse(node, meta=None, in_list=False, require_list=False):
        if isinstance(node, dict):
            current_meta = meta or {}
            date_added = None
            for key in ['listItemCreatedAt', 'createdAt', 'created', 'dateAdded', 'addedAt', 'listItemCreated']:
                if key in node:
                    date_added = node.get(key)
                    break
            if date_added:
                current_meta = dict(current_meta)
                current_meta['date_added'] = date_added

            list_context = in_list or any(k in node for k in list_context_keys)

            title_obj = None
            if 'titleText' in node and ('id' in node or 'titleId' in node or 'const' in node):
                title_obj = node
            elif isinstance(node.get('title'), dict):
                title_obj = node.get('title')

            if title_obj and (list_context or not require_list):
                add_record(title_obj, current_meta)

            for value in node.values():
                traverse(value, current_meta, list_context, require_list)
        elif isinstance(node, list):
            for item in node:
                traverse(item, meta, in_list, require_list)

    traverse(data, require_list=True)
    if not records:
        seen.clear()
        records.clear()
        traverse(data, require_list=False)
    return records

def fetch_imdb_watchlist(cookie, user_id=None, max_pages=50):
    headers = {
        'Cookie': cookie,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    session = requests.Session()
    records = []
    seen = set()

    def fetch_from_base(base_url):
        nonlocal records, seen
        for page in range(1, max_pages + 1):
            url = f"{base_url}?sort=list_order,asc&mode=detail&page={page}"
            try:
                resp = session.get(url, headers=headers, timeout=30)
            except Exception as e:
                logger.error(f"IMDb watchlist request error: {e}")
                break

            if resp.status_code != 200:
                logger.error(f"IMDb watchlist fetch failed: {resp.status_code}")
                break

            match = re.search(r'<script id=\"__NEXT_DATA__\" type=\"application/json\">(.+?)</script>', resp.text, re.DOTALL)
            if not match:
                logger.error("IMDb watchlist page missing __NEXT_DATA__")
                break

            try:
                data = json.loads(match.group(1))
            except Exception as e:
                logger.error(f"IMDb watchlist JSON parse error: {e}")
                break

            page_records = _extract_imdb_watchlist_items(data)
            if not page_records:
                break

            new_count = 0
            for record in page_records:
                imdb_id = record.get('Const')
                if imdb_id and imdb_id in seen:
                    continue
                if imdb_id:
                    seen.add(imdb_id)
                records.append(record)
                new_count += 1

            if new_count == 0:
                break

    if user_id:
        fetch_from_base(f'https://www.imdb.com/user/{user_id}/watchlist/')
    if not records:
        fetch_from_base('https://www.imdb.com/list/watchlist/')

    return records

def ensure_export_type_column(df):
    if df is None or df.empty:
        return df
    df = ensure_type_column(df)
    if 'type' in df.columns:
        df['type'] = df['type'].apply(normalize_type_value)
    else:
        df['type'] = df['Type']
    if 'Type' in df.columns:
        df.drop(columns=['Type'], inplace=True)
    return df

def needs_type_refresh(csv_path):
    if not os.path.exists(csv_path):
        return False
    try:
        df = pd.read_csv(csv_path, nrows=200)
        type_cols = ['Type', 'type', 'Title Type', 'TmdbIdType', 'tmdb_type']
        available = [c for c in type_cols if c in df.columns]
        if not available:
            return True
        col = available[0]
        series = df[col].fillna('').astype(str).str.strip()
        return series.eq('').all()
    except Exception:
        return False

def load_platform_data():
    """Load all platform CSV data into APP_DATA on server startup."""
    global APP_DATA_LOADED
    
    # Skip if we've already populated APP_DATA to avoid redundant disk IO
    if APP_DATA_LOADED and APP_DATA:
        return
    
    config = read_config()
    logger.info("[Startup] Loading platform CSV data into APP_DATA...")
    
    # Load Douban and IMDb
    for platform in ['douban', 'imdb']:
        user_id = str(config.get(f'{platform}_user_id') or '').strip()
        if user_id:
            # Load Ratings
            csv_path = os.path.join(DATA_DIR, f'{platform}_{user_id}_ratings.csv')
            if os.path.exists(csv_path):
                try:
                    df = pd.read_csv(csv_path)
                    df = normalize_df_columns(df)
                    source_cols = {'Type', 'type', 'Title Type', 'TmdbIdType', 'tmdb_type'}
                    had_type = 'Type' in df.columns
                    has_source = bool(set(df.columns) & source_cols)
                    df = ensure_type_column(df)
                    APP_DATA[f'{platform}_df'] = df
                    APP_DATA[f'{platform}_csv_path'] = csv_path
                    logger.info(f"[Startup] Loaded {platform}: {len(df)} records from {csv_path}")
                    if not had_type and has_source and len(df) > 0:
                        df.to_csv(csv_path, index=False, encoding='utf-8-sig')
                except Exception as e:
                    logger.error(f"[Startup] Error loading {platform}: {e}")
            
            # Load Wishlist (Want to Watch)
            if platform == 'douban':
                try:
                    df_wish = load_douban_wish_for_user(user_id)
                    if df_wish is not None:
                        logger.info(f"[Startup] Loaded {platform} wishlist: {len(df_wish)} records")
                except Exception as e:
                    logger.error(f"[Startup] Error loading {platform} wishlist: {e}")
    
    # Load Trakt
    trakt_user_id = config.get('trakt_user_id')
    if trakt_user_id:
        trakt_csv = os.path.join(DATA_DIR, f'trakt_{trakt_user_id}_ratings.csv')
        if not os.path.exists(trakt_csv):
            import glob
            matches = glob.glob(os.path.join(DATA_DIR, 'trakt_*_ratings.csv'))
            if matches:
                trakt_csv = matches[0]
        
        if os.path.exists(trakt_csv):
            try:
                df = pd.read_csv(trakt_csv)
                APP_DATA['trakt_df'] = df
                APP_DATA['trakt_csv_path'] = trakt_csv
                logger.info(f"[Startup] Loaded trakt: {len(df)} records from {trakt_csv}")
            except Exception as e:
                logger.error(f"[Startup] Error loading trakt: {e}")
    
    # Load Letterboxd
    letterboxd_csv = os.path.join(DATA_DIR, 'letterboxd_diary.csv')
    if not os.path.exists(letterboxd_csv):
        import glob
        matches = glob.glob(os.path.join(DATA_DIR, '*diary.csv'))
        if matches:
            letterboxd_csv = matches[0]
    
    if os.path.exists(letterboxd_csv):
        try:
            df = pd.read_csv(letterboxd_csv)
            
            # 自动获取IMDb ID (如果还没有的话)
            if 'Letterboxd URI' in df.columns and 'IMDb ID' not in df.columns:
                logger.info(f"[Startup] Letterboxd数据缺少IMDb ID，正在从URI获取...")
                from adapters.utils.letterboxd_mapper import get_mapper
                mapper = get_mapper()
                
                # 添加IMDb ID列
                def get_id(uri):
                    if pd.isna(uri) or not uri:
                        return None
                    return mapper.get_imdb_id_from_uri(str(uri))
                
                df['IMDb ID'] = df['Letterboxd URI'].apply(get_id)
                imdb_found = df['IMDb ID'].notna().sum()
                logger.info(f"[Startup] 成功获取 {imdb_found}/{len(df)} 个IMDb ID")
                
                # 保存更新后的CSV
                df.to_csv(letterboxd_csv, index=False)
                logger.info(f"[Startup] 已保存更新后的Letterboxd数据到 {letterboxd_csv}")
            
            APP_DATA['letterboxd_df'] = df
            APP_DATA['letterboxd_csv_path'] = letterboxd_csv
            logger.info(f"[Startup] Loaded letterboxd: {len(df)} records from {letterboxd_csv}")
        except Exception as e:
            logger.error(f"[Startup] Error loading letterboxd: {e}")
    
    # Load TMDB
    tmdb_user_id = config.get('tmdb_user_id')
    tmdb_csv = None
    if tmdb_user_id:
        tmdb_csv = os.path.join(DATA_DIR, f'tmdb_{tmdb_user_id}_ratings.csv')
    
    if not tmdb_csv or not os.path.exists(tmdb_csv):
        import glob
        matches = glob.glob(os.path.join(DATA_DIR, 'tmdb_*_ratings.csv'))
        if matches:
            tmdb_csv = matches[0]
    
    if tmdb_csv and os.path.exists(tmdb_csv):
        try:
            df = pd.read_csv(tmdb_csv)
            APP_DATA['tmdb_df'] = df
            APP_DATA['tmdb_csv_path'] = tmdb_csv
            logger.info(f"[Startup] Loaded tmdb: {len(df)} records from {tmdb_csv}")
        except Exception as e:
            logger.error(f"[Startup] Error loading tmdb: {e}")
    
    APP_DATA_LOADED = True
    logger.info(f"[Startup] Platform data loading complete. APP_DATA keys: {list(APP_DATA.keys())}")


@app.route('/')
def index():
    return render_template('index.html', now=time.time())

# ==========================================
# Browser Auth (OAuth-style) Routes
# ==========================================

# Store pending auth sessions
AUTH_SESSIONS = {}
AUTH_SESSION_TTL = 10 * 60

@app.route('/auth/bridge')
def auth_bridge():
    """Serve the auth bridge page for browser-based login"""
    return render_template('auth_bridge.html')

@app.route('/auth/callback', methods=['POST'])
def auth_callback():
    """Receive cookie from auth bridge page"""
    import re
    
    data = request.get_json()
    platform = data.get('platform', '')
    cookie = data.get('cookie', '')
    auth_token = data.get('token', '')
    
    if not platform or not cookie or not auth_token:
        return jsonify({'success': False, 'error': '缺少必要参数'})

    session = AUTH_SESSIONS.get(auth_token)
    if not session:
        return jsonify({'success': False, 'error': '无效或过期的token'})
    if session.get('platform') != platform:
        return jsonify({'success': False, 'error': 'token平台不匹配'})
    created_at = session.get('created', 0)
    if time.time() - created_at > AUTH_SESSION_TTL:
        AUTH_SESSIONS.pop(auth_token, None)
        return jsonify({'success': False, 'error': 'token已过期'})
    
    # Validate the cookie by making a test request
    valid = False
    user_id = None
    
    headers = {
        'Cookie': cookie,
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        if platform == 'douban':
            resp = requests.get('https://www.douban.com/mine/', 
                              headers=headers, timeout=10, allow_redirects=True)
            m = re.search(r'/people/([^/\?"]+)', resp.url)
            if m:
                user_id = m.group(1)
                valid = True
                
        elif platform == 'imdb':
            resp = requests.get('https://www.imdb.com/list/watchlist/',
                              headers=headers, timeout=10, allow_redirects=True)
            if 'signin' not in resp.url.lower() and resp.status_code != 401:
                # Try to extract user ID from page
                m = re.search(r'/user/(ur\d+)', resp.text)
                if m:
                    user_id = m.group(1)
                else:
                    user_id = 'user'  # Generic user ID
                valid = True
                
    except Exception as e:
        logger.error(f"Cookie validation error: {e}")
        return jsonify({'success': False, 'error': f'验证失败: {str(e)}'})
    
    if valid and user_id:
        # Save to config
        config = read_config()
        config[f'{platform}_cookie'] = cookie
        config[f'{platform}_user_id'] = user_id
        write_config(config)
        
        # Notify frontend via Socket.IO
        socketio.emit('browser_auth_complete', {
            'platform': platform,
            'user_id': user_id,
            'success': True
        })
        
        AUTH_SESSIONS.pop(auth_token, None)
        logger.info(f"Browser auth successful for {platform}: {user_id}")
        return jsonify({'success': True, 'user_id': user_id})
    else:
        return jsonify({'success': False, 'error': 'Cookie 无效或已过期'})

@app.route('/auth/start/<platform>')
def auth_start(platform):
    """Open auth bridge in system browser"""
    import webbrowser
    import secrets
    
    if platform not in ['douban', 'imdb']:
        return jsonify({'error': 'Invalid platform'}), 400
    
    # Generate auth token
    token = secrets.token_urlsafe(16)
    AUTH_SESSIONS[token] = {
        'platform': platform,
        'created': time.time()
    }
    
    # Build auth bridge URL
    auth_url = f"http://127.0.0.1:8000/auth/bridge?platform={platform}&token={token}&callback=http://127.0.0.1:8000"
    
    # Open in system browser
    webbrowser.open(auth_url)
    
    return jsonify({'success': True, 'message': 'Auth page opened in browser'})

# ==========================================
# Scheduled Tasks Socket.IO Events
# ==========================================

@socketio.on('get_scheduled_tasks')
def handle_get_scheduled_tasks():
    """Get all scheduled tasks"""
    try:
        scheduler = get_scheduler(socketio)
        tasks = scheduler.list_jobs()
        emit('scheduled_tasks_list', {'success': True, 'tasks': tasks})
    except Exception as e:
        logger.error(f"Failed to get scheduled tasks: {e}")
        emit('scheduled_tasks_list', {'success': False, 'error': str(e), 'tasks': []})

@socketio.on('add_scheduled_task')
def handle_add_scheduled_task(data):
    """Add a new scheduled task"""
    try:
        name = data.get('name')
        source = data.get('source')
        target = data.get('target')
        schedule = data.get('schedule')
        paused = data.get('paused', False)
        
        # Generate task ID
        import time
        task_id = f"{source}_to_{target}_{int(time.time())}"
        
        scheduler = get_scheduler(socketio)
        success = scheduler.add_sync_job(
            job_id=task_id,
            source=source,
            target=target,
            cron_expr=schedule,
            enabled=not paused,
            name=name
        )
        
        if success:
            emit('task_added', {'success': True, 'task_id': task_id})
            # Notify all clients to refresh task list
            socketio.emit('task_list_updated', {})
        else:
            emit('task_added', {'success': False, 'error': 'Failed to create task'})
            
    except Exception as e:
        logger.error(f"Failed to add scheduled task: {e}")
        emit('task_added', {'success': False, 'error': str(e)})

@socketio.on('update_scheduled_task')
def handle_update_scheduled_task(data):
    """Update an existing scheduled task"""
    try:
        task_id = data.get('task_id')
        
        scheduler = get_scheduler(socketio)
        
        # Remove old task
        scheduler.remove_job(task_id)
        
        # Add updated task with same ID
        success = scheduler.add_sync_job(
            job_id=task_id,
            source=data.get('source'),
            target=data.get('target'),
            cron_expr=data.get('schedule'),
            enabled=not data.get('paused', False),
            name=data.get('name')
        )
        
        if success:
            emit('task_updated', {'success': True, 'task_id': task_id})
            socketio.emit('task_list_updated', {})
        else:
            emit('task_updated', {'success': False, 'error': 'Failed to update task'})
            
    except Exception as e:
        logger.error(f"Failed to update scheduled task: {e}")
        emit('task_updated', {'success': False, 'error': str(e)})

@socketio.on('delete_scheduled_task')
def handle_delete_scheduled_task(data):
    """Delete a scheduled task"""
    try:
        task_id = data.get('task_id')
        
        scheduler = get_scheduler(socketio)
        success = scheduler.remove_job(task_id)
        
        if success:
            emit('task_deleted', {'success': True, 'task_id': task_id})
            socketio.emit('task_list_updated', {})
        else:
            emit('task_deleted', {'success': False, 'error': 'Task not found'})
            
    except Exception as e:
        logger.error(f"Failed to delete scheduled task: {e}")
        emit('task_deleted', {'success': False, 'error': str(e)})

@socketio.on('toggle_scheduled_task')
def handle_toggle_scheduled_task(data):
    """Toggle (pause/resume) a scheduled task"""
    try:
        task_id = data.get('task_id')
        paused = data.get('paused', False)
        
        scheduler = get_scheduler(socketio)
        
        if paused:
            success = scheduler.pause_job(task_id)
        else:
            success = scheduler.resume_job(task_id)
        
        if success:
            emit('task_status_changed', {'success': True, 'task_id': task_id, 'paused': paused})
            socketio.emit('task_list_updated', {})
        else:
            emit('task_status_changed', {'success': False, 'error': 'Failed to toggle task'})
            
    except Exception as e:
        logger.error(f"Failed to toggle scheduled task: {e}")
        emit('task_status_changed', {'success': False, 'error': str(e)})

@socketio.on('get_task_logs')
def handle_get_task_logs(data=None):
    """Get persisted task execution logs"""
    try:
        from web.task_logs import get_task_logs
        limit = data.get('limit', 50) if data else 50
        logs = get_task_logs(limit)
        emit('task_logs_loaded', {'success': True, 'logs': logs})
    except Exception as e:
        logger.error(f"Failed to get task logs: {e}")
        emit('task_logs_loaded', {'success': False, 'logs': [], 'error': str(e)})

@socketio.on('clear_task_logs')
def handle_clear_task_logs():
    """Clear all task logs"""
    try:
        from web.task_logs import clear_task_logs
        clear_task_logs()
        emit('task_logs_cleared', {'success': True})
    except Exception as e:
        logger.error(f"Failed to clear task logs: {e}")
        emit('task_logs_cleared', {'success': False, 'error': str(e)})

def _is_allowed_proxy_domain(url, allowed_domains):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if not host:
        return False
    for domain in allowed_domains:
        domain = domain.lower()
        if host == domain or host.endswith('.' + domain):
            return True
    return False

# ==========================================
# Main Entry Point
# ==========================================

@app.route('/proxy/avatar')
def proxy_avatar():
    """Proxy avatar images to bypass anti-hotlinking protection"""
    from flask import request, Response
    
    url = request.args.get('url', '')
    if not url:
        return Response('No URL provided', status=400)
    
    # Only allow proxying from known domains
    allowed_domains = ['doubanio.com', 'douban.com', 'trakt.tv', 'imdb.com', 'media-amazon.com']
    if not _is_allowed_proxy_domain(url, allowed_domains):
        return Response('Domain not allowed', status=403)
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://www.douban.com/'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            content_type = resp.headers.get('Content-Type', 'image/jpeg')
            return Response(resp.content, mimetype=content_type)
        else:
            return Response('Failed to fetch image', status=resp.status_code)
    except Exception as e:
        return Response(f'Proxy error: {e}', status=500)


@app.route('/proxy/image')
def proxy_image():
    """Proxy images to bypass anti-hotlinking protection"""
    from flask import request, Response

    url = request.args.get('url', '')
    if not url:
        return Response('No URL provided', status=400)

    allowed_domains = ['doubanio.com', 'douban.com', 'trakt.tv', 'imdb.com', 'media-amazon.com']
    if not _is_allowed_proxy_domain(url, allowed_domains):
        return Response('Domain not allowed', status=403)

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://www.douban.com/'
        }
        resp = requests.get(url, headers=headers, timeout=10)

        if resp.status_code == 200:
            content_type = resp.headers.get('Content-Type', 'image/jpeg')
            return Response(resp.content, mimetype=content_type)
        else:
            return Response('Failed to fetch image', status=resp.status_code)
    except Exception as e:
        return Response(f'Proxy error: {e}', status=500)

@app.route('/download/<platform>')
def download_data(platform):
    """Export data as downloadable file"""
    from flask import Response, request
    import io
    
    format_type = request.args.get('format', 'cinerecord-csv')
    
    # Get data from APP_DATA or load from file
    df = APP_DATA.get(f'{platform}_df')
    
    if df is None or df.empty:
        config = read_config()
        
        if platform == 'merged':
            # 🔥 使用真正的并集：从 /api/library 逻辑获取所有平台数据
            # 这会包含英文标题和所有平台的 ID
            all_movies = {}
            
            # 复用 api_get_library 中的合并逻辑
            def get_merge_key(movie):
                imdb_id = movie.get('Const') or movie.get('imdb_id') or movie.get('IMDb ID') or ''
                if imdb_id and str(imdb_id).startswith('tt'):
                    return str(imdb_id)
                title = movie.get('Title') or movie.get('Name') or ''
                year = str(movie.get('Year', ''))[:4]
                return f"{title}|{year}".lower()
            
            # 从所有平台加载数据
            for plat in ['douban', 'imdb', 'trakt', 'letterboxd', 'tmdb']:
                plat_df = APP_DATA.get(f'{plat}_df')
                if plat_df is not None and not plat_df.empty:
                    for _, row in plat_df.iterrows():
                        movie = row.to_dict()
                        key = get_merge_key(movie)
                        if key not in all_movies:
                            # 获取媒体类型：优先从 Trakt 的 'Type' 或 IMDb 的 'Title Type' 列获取
                            media_type = movie.get('Type') or movie.get('Title Type') or movie.get('type') or 'movie'
                            # 标准化为小写
                            media_type = str(media_type).lower().strip() if media_type else 'movie'
                            # 检测是否为 TV 类型 (包括 TV Series, TV Mini Series, TV Episode 等)
                            if 'tv' in media_type or 'series' in media_type or 'episode' in media_type or 'show' in media_type:
                                media_type = 'tv'
                            else:
                                media_type = 'movie'
                            
                            all_movies[key] = {
                                'imdb_id': movie.get('Const') or movie.get('imdb_id') or movie.get('IMDb ID') or '',
                                'tmdb_id': movie.get('tmdb_id') or movie.get('TMDB ID') or '',
                                'trakt_id': movie.get('trakt_id') or movie.get('Trakt ID') or '',
                                'douban_id': movie.get('douban_id') or movie.get('movie_id') or '',
                                'title': movie.get('Title') or movie.get('Name') or '',
                                'original_title': movie.get('original_title') or movie.get('Original Title') or '',
                                'year': str(movie.get('Year', ''))[:4],
                                'your_rating': movie.get('Your Rating') or movie.get('Rating') or '',
                                'date_rated': movie.get('Date Rated') or movie.get('date_rated') or movie.get('Watched Date') or '',
                                'directors': movie.get('Directors') or '',
                                'genres': movie.get('Genres') or '',
                                'type': media_type,  # 🆕 添加媒体类型字段
                                'douban_url': movie.get('douban_url') or movie.get('URL') if plat == 'douban' else '',
                                'imdb_url': movie.get('imdb_url') or movie.get('URL') if plat == 'imdb' else '',
                                'letterboxd_url': movie.get('Letterboxd URI') or movie.get('letterboxd_url') or movie.get('URL') if plat == 'letterboxd' else '',
                                'trakt_url': movie.get('trakt_url') or movie.get('URL') if plat == 'trakt' else '',
                                'tmdb_url': movie.get('tmdb_url') or movie.get('URL') if plat == 'tmdb' else '',
                                'poster_url': movie.get('Cover URL') or movie.get('poster_url') or movie.get('poster') or '',
                                'sources': [plat],
                            }
                        else:
                            # 合并：补充缺失字段
                            existing = all_movies[key]
                            if plat not in existing['sources']:
                                existing['sources'].append(plat)
                            # 补充 ID
                            if not existing['imdb_id']:
                                existing['imdb_id'] = movie.get('Const') or movie.get('imdb_id') or movie.get('IMDb ID') or ''
                            if not existing['tmdb_id']:
                                existing['tmdb_id'] = movie.get('tmdb_id') or movie.get('TMDB ID') or ''
                            # 补充英文标题
                            if not existing['original_title']:
                                existing['original_title'] = movie.get('original_title') or movie.get('Original Title') or movie.get('Title') or ''
                            # 补充 URL
                            if plat == 'letterboxd' and not existing['letterboxd_url']:
                                existing['letterboxd_url'] = movie.get('Letterboxd URI') or movie.get('letterboxd_url') or movie.get('URL') or ''
                            if plat == 'trakt' and not existing['trakt_url']:
                                existing['trakt_url'] = movie.get('trakt_url') or movie.get('URL') or ''
                            if plat == 'tmdb' and not existing['tmdb_url']:
                                existing['tmdb_url'] = movie.get('tmdb_url') or movie.get('URL') or ''
                            
                            # Merge type: prioritize TV over movie
                            new_type = movie.get('Type') or movie.get('Title Type') or movie.get('type') or ''
                            if new_type:
                                new_type = str(new_type).lower().strip()
                                if 'tv' in new_type or 'series' in new_type or 'episode' in new_type or 'show' in new_type:
                                    existing['type'] = 'tv'
                                elif not existing.get('type'):
                                    existing['type'] = 'movie'
            
            if not all_movies:
                return Response("No data available from any platform", status=404)
            
            df = pd.DataFrame(list(all_movies.values()))
            # 将 sources 列表转为字符串
            df['sources'] = df['sources'].apply(lambda x: ','.join(x) if isinstance(x, list) else x)
        else:
            # Regular platform data
            user_id = config.get(f'{platform}_user_id', '')
            csv_path = os.path.join(DATA_DIR, f'{platform}_{user_id}_ratings.csv')
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
            else:
                return Response("No data available", status=404)
    df = ensure_export_type_column(df)
    
    if format_type == 'json':
        # Full JSON export
        output = df.to_json(orient='records', force_ascii=False, indent=2)
        return Response(
            output,
            mimetype='application/json; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename={platform}_ratings.json'}
        )
    elif format_type == 'cinepersona':
        # CinePersona JSON format
        records = safe_df_to_records(df)
        import json
        output = json.dumps({'platform': platform, 'movies': records, 'total': len(records)}, 
                           ensure_ascii=False, indent=2)
        return Response(
            output,
            mimetype='application/json; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename={platform}_cinepersona.json'}
        )
    elif format_type in ['letterboxd', 'letterboxd-csv']:
        # Letterboxd CSV format - handle both format names
        try:
            # Build a minimal-yet-rich template for Letterboxd import
            # Keep Title/Year/Rating/Date plus IDs (IMDb/TMDB/Trakt) and English title for better matching
            lb_df = pd.DataFrame()
            # 获取标题 - 优先使用英文/原始标题用于 Letterboxd 匹配
            lb_df['Title'] = ''
            # 优先级: original_title > Title > Name
            if 'original_title' in df.columns:
                lb_df['Title'] = df['original_title']
            if 'Original Title' in df.columns:
                lb_df['Title'] = df['Original Title'].fillna(lb_df['Title'])
            # 如果还是空，用普通 Title
            title_col = None
            for col in ['Title', 'title', 'Name']:
                if col in df.columns:
                    title_col = col
                    break
            if title_col:
                lb_df['Title'] = lb_df['Title'].replace('', pd.NA).fillna(df[title_col])

            # Year
            year_col = 'Year' if 'Year' in df.columns else 'year' if 'year' in df.columns else None
            if year_col:
                lb_df['Year'] = pd.to_numeric(df[year_col], errors='coerce').fillna(0).astype(int)
            else:
                lb_df['Year'] = 0

            # Rating: 处理多种字段名，<=5 则转为10分制
            rating_series = None
            for col in ['your_rating', 'Your Rating', 'YourRating_douban', 'Rating']:
                if col in df.columns:
                    rating_series = df[col]
                    break
            if rating_series is not None:
                r = pd.to_numeric(rating_series, errors='coerce')
                lb_df['Rating10'] = r.apply(lambda x: x * 2 if pd.notna(x) and x <= 5 else x).fillna('')
            else:
                lb_df['Rating10'] = ''

            # Watched date normalized to YYYY-MM-DD
            date_series = None
            for col in ['Date Rated', 'Watched Date', 'DateRated_douban', 'date_rated']:
                if col in df.columns:
                    date_series = df[col]
                    break
            if date_series is not None:
                lb_df['WatchedDate'] = pd.to_datetime(date_series, errors='coerce', dayfirst=False).dt.strftime('%Y-%m-%d')
            else:
                lb_df['WatchedDate'] = ''

            # IDs for downstream matching - 使用辅助函数获取列
            def get_col(df, cols):
                for c in cols:
                    if c in df.columns:
                        return df[c]
                return ''
            lb_df['IMDB ID'] = get_col(df, ['Const', 'imdb_id', 'IMDb ID'])
            lb_df['TMDB ID'] = get_col(df, ['tmdb_id', 'TMDB ID'])
            lb_df['Trakt ID'] = get_col(df, ['trakt_id', 'Trakt ID'])
            lb_df['Letterboxd URI'] = get_col(df, ['Letterboxd URI', 'letterboxd_url', 'URL'])
            
            # Add Type column (movie or tv)
            def get_type(row):
                t = row.get('type') or row.get('Type') or row.get('Title Type') or 'movie'
                t = str(t).lower().strip() if t else 'movie'
                if 'tv' in t or 'series' in t or 'episode' in t or 'show' in t:
                    return 'tv'
                return 'movie'
            
            lb_df['Type'] = df.apply(get_type, axis=1)

            # Clean NaNs to empty string
            lb_df = lb_df.fillna('')
            
            csv_bytes = lb_df.to_csv(index=False).encode('utf-8-sig')
            return Response(
                csv_bytes,
                mimetype='text/csv',
                headers={
                    'Content-Disposition': f'attachment; filename={platform}_letterboxd.csv',
                    'Content-Type': 'text/csv; charset=utf-8-sig'
                }
            )
        except Exception as e:
            logger.error(f"Letterboxd export error: {e}")
            return Response(f"Export error: {e}", status=500)
    else:
        # Default: CineRecord CSV with UTF-8 BOM for Excel compatibility
        # Clean up ID columns to avoid floating point issues
        export_df = df.copy()
        id_columns = ['douban_id', 'imdb_id', 'Year', 'Const']
        for col in id_columns:
            if col in export_df.columns:
                # Convert to numeric then to nullable int
                export_df[col] = pd.to_numeric(export_df[col], errors='coerce')
                # For IDs, convert to string without decimals
                if col in ['douban_id', 'Year']:
                    export_df[col] = export_df[col].apply(lambda x: str(int(x)) if pd.notna(x) else '')
        
        csv_bytes = export_df.to_csv(index=False).encode('utf-8-sig')
        return Response(
            csv_bytes,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename={platform}_ratings.csv',
                'Content-Type': 'text/csv; charset=utf-8-sig'
            }
        )

@app.route('/download/wishlist')
def download_wishlist():
    """Export wishlist data as downloadable file"""
    from flask import Response, request

    format_type = request.args.get('format', 'cinerecord-csv')

    config = read_config()
    df = build_wishlist_df(config)

    if df is None or df.empty:
        return Response("No wishlist data available", status=404)

    df = filter_wish_df(df)
    export_df = ensure_export_type_column(df)
    if 'source' not in export_df.columns:
        export_df['source'] = 'douban'

    for col in ['Your Rating', 'YourRating_douban', 'YourRating_imdb', 'Douban Rating', 'IMDb Rating', 'Rating']:
        if col in export_df.columns:
            export_df.drop(columns=[col], inplace=True)

    preferred_order = [
        'Title', 'Year', 'type', 'Genres', 'Directors', 'Actors', 'Country',
        'URL', 'Cover URL', 'douban_id', 'Const', 'Date Rated', 'status', 'source'
    ]
    cols = [c for c in preferred_order if c in export_df.columns]
    remaining = [c for c in export_df.columns if c not in cols]
    export_df = export_df[cols + remaining]

    if format_type == 'json':
        output = export_df.to_json(orient='records', force_ascii=False, indent=2)
        return Response(
            output,
            mimetype='application/json; charset=utf-8',
            headers={'Content-Disposition': 'attachment; filename=wishlist.json'}
        )

    csv_bytes = export_df.to_csv(index=False).encode('utf-8-sig')
    return Response(
        csv_bytes,
        mimetype='text/csv',
        headers={
            'Content-Disposition': 'attachment; filename=wishlist.csv',
            'Content-Type': 'text/csv; charset=utf-8-sig'
        }
    )

# ==========================================
# Scheduled Sync API
# ==========================================

@app.route('/api/scheduler/jobs', methods=['GET'])
def list_scheduled_jobs():
    """Get all scheduled sync jobs"""
    from flask import jsonify
    try:
        scheduler = get_scheduler(socketio)
        jobs = scheduler.list_jobs()
        return jsonify({'success': True, 'jobs': jobs})
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scheduler/jobs', methods=['POST'])
def create_scheduled_job():
    """Create a new scheduled sync job"""
    from flask import request, jsonify
    try:
        data = request.get_json()
        job_id = data.get('job_id') or f"{data['source']}-{data['target']}-{int(time.time())}"
        source = data.get('source')
        target = data.get('target')
        cron_expr = data.get('cron')
        enabled = data.get('enabled', True)
        
        if not all([source, target, cron_expr]):
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        scheduler = get_scheduler(socketio)
        success = scheduler.add_sync_job(job_id, source, target, cron_expr, enabled)
        
        if success:
            return jsonify({'success': True, 'job_id': job_id})
        else:
            return jsonify({'success': False, 'error': 'Failed to create job'}), 500
            
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scheduler/jobs/<job_id>', methods=['DELETE'])
def delete_scheduled_job(job_id):
    """Delete a scheduled job"""
    from flask import jsonify
    try:
        scheduler = get_scheduler(socketio)
        success = scheduler.remove_job(job_id)
        return jsonify({'success': success})
    except Exception as e:
        logger.error(f"Failed to delete job: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scheduler/jobs/<job_id>/toggle', methods=['POST'])
def toggle_scheduled_job(job_id):
    """Toggle (pause/resume) a scheduled job"""
    from flask import request, jsonify
    try:
        data = request.get_json()
        action = data.get('action', 'toggle')  # 'pause' or 'resume'
        
        scheduler = get_scheduler(socketio)
        
        if action == 'pause':
            success = scheduler.pause_job(job_id)
        elif action == 'resume':
            success = scheduler.resume_job(job_id)
        else:
            # Auto-detect current state and toggle
            jobs = scheduler.list_jobs()
            current_job = next((j for j in jobs if j['id'] == job_id), None)
            if current_job and current_job.get('paused'):
                success = scheduler.resume_job(job_id)
            else:
                success = scheduler.pause_job(job_id)
        
        return jsonify({'success': success})
    except Exception as e:
        logger.error(f"Failed to toggle job: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/library')
def api_get_library():
    """REST API endpoint for unified library - bypasses socket issues"""
    from flask import request, jsonify
    import math
    
    def clean_value(val):
        """Convert NaN/None to empty string for JSON serialization"""
        if val is None:
            return ''
        if isinstance(val, float) and math.isnan(val):
            return ''
        return val
    
    def clean_id(val):
        """Clean ID fields - convert NaN/None to empty string"""
        if val is None:
            return ''
        if isinstance(val, float):
            if math.isnan(val):
                return ''
            return str(int(val))  # Convert float IDs to int string
        return str(val) if val else ''
    
    def clean_date(val):
        """Clean date fields - normalize to YYYY-MM-DD format for proper sorting"""
        if val is None:
            return ''
        if isinstance(val, float):
            if math.isnan(val):
                return ''
            return str(int(val))
        
        date_str = str(val).strip()
        if not date_str:
            return ''
        
        # Try to parse and normalize common date formats
        from datetime import datetime
        formats_to_try = [
            '%m/%d/%y',      # 12/24/25 (MM/DD/YY)
            '%m/%d/%Y',      # 12/24/2025 (MM/DD/YYYY) 
            '%Y-%m-%d',      # 2025-12-24 (ISO format)
            '%d/%m/%y',      # 24/12/25 (DD/MM/YY)
            '%d/%m/%Y',      # 24/12/2025 (DD/MM/YYYY)
            '%Y/%m/%d',      # 2025/12/24
            '%d %b %Y',      # 24 Dec 2025
            '%b %d, %Y',     # Dec 24, 2025
        ]
        
        for fmt in formats_to_try:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        return date_str
    
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    platform_filter = request.args.get('platform', 'all')
    
    # Get selected platforms from query string (comma-separated)
    # Default to all 5 platforms if not specified
    selected_platforms_str = request.args.get('platforms', 'douban,imdb,trakt,letterboxd,tmdb')
    selected_platforms = set([p.strip() for p in selected_platforms_str.split(',') if p.strip()])
    
    # 特殊情况：如果没有选择任何平台，显示所有平台的并集
    show_union = len(selected_platforms) == 0
    
    logger.info(f"[API Library] Request: filter={platform_filter}, page={page}, selected_platforms={selected_platforms}")
    
    try:
        # Ensure platform data is loaded when running under WSGI/Flask CLI
        if not APP_DATA or not any(k.endswith('_df') for k in APP_DATA.keys()):
            load_platform_data()
        
        # Collect all movies from all platforms
        all_movies = {}
        
        def get_merge_key(movie):
            # Try to find IMDb ID - check multiple variations of the column name
            imdb_id = movie.get('Const') or movie.get('imdb_id') or movie.get('IMDB ID') or movie.get('IMDb ID')
            if imdb_id and not (isinstance(imdb_id, float) and math.isnan(imdb_id)) and str(imdb_id).startswith('tt'):
                return str(imdb_id)
            
            # Fallback to Title + Year
            # Support 'Name' for Letterboxd
            title = str(movie.get('Title') or movie.get('title') or movie.get('中文名') or movie.get('Name') or '').strip()
            year = str(movie.get('Year') or movie.get('year') or movie.get('上映年份') or '')[:4]
            return f"{title}_{year}" if title else None
        
        def add_movie(movie, platform):
            key = get_merge_key(movie)
            if not key:
                if platform == 'letterboxd':
                    logger.warning(f"[Letterboxd] Skipping movie - no valid merge key. Title: {movie.get('Name')}, Year: {movie.get('Year')}, IMDb ID: {movie.get('IMDb ID')}")
                return
            
            if platform == 'letterboxd':
                logger.info(f"[Letterboxd] Adding movie: key={key}, title={movie.get('Name')}, year={movie.get('Year')}")
            
            # Extract platform-specific data
            # Handle ratings - normalize to 10-point scale
            raw_rating = movie.get('Your Rating') or movie.get('YourRating_douban') or movie.get('YourRating_imdb') or movie.get('rating') or movie.get('评分') or movie.get('Rating')
            
            # Normalize ratings: Douban/Letterboxd可能是5分制，也可能已换算到10分制
            user_rating = ''
            if raw_rating is not None:
                try:
                    rating_float = float(raw_rating)
                    # Check for NaN - NaN is not valid JSON
                    if not math.isnan(rating_float):
                        if platform in ['douban', 'letterboxd']:
                            # 如果原始分数 <=5，认为是5分制，需要乘2；>5 则视为已是10分制
                            user_rating = rating_float * 2 if rating_float <= 5 else rating_float
                        else:
                            user_rating = rating_float
                except:
                    user_rating = clean_value(raw_rating)
            else:
                user_rating = ''

            # Platform ratings (public scores)
            douban_rating_val = clean_value(movie.get('Douban Rating') or movie.get('豆瓣评分') or '')
            imdb_rating_val = clean_value(movie.get('IMDb Rating') or movie.get('IMDB Rating') or '')
            tmdb_rating_val = clean_value(movie.get('vote_average') or movie.get('tmdb_rating') or '')
            # Vote counts - both platforms use 'Num Votes'
            votes = clean_value(movie.get('Num Votes') or movie.get('评价人数') or '')
            # Assign votes based on platform
            douban_votes_val = votes if platform == 'douban' else ''
            imdb_votes_val = votes if platform == 'imdb' else ''
            
            if key not in all_movies:
                # Initialize movie entry
                title = movie.get('Title') or movie.get('title') or movie.get('中文名') or movie.get('Name') or ''
                original_title = movie.get('original_title') or movie.get('Original Title') or movie.get('原名') or ''
                year = movie.get('Year') or movie.get('year') or movie.get('上映年份') or ''
                
                # Priority: poster_url -> poster -> Cover URL -> Cover -> poster_path
                # NOTE: NaN is truthy in Python, so we must check each field individually
                poster = ''
                for poster_field in ['poster_url', 'poster', 'Cover URL', 'Cover', 'poster_path']:
                    raw_poster = movie.get(poster_field)
                    if raw_poster is not None and not (isinstance(raw_poster, float) and math.isnan(raw_poster)):
                        poster = clean_value(raw_poster)
                        if poster:
                            break
                
                date_rated = clean_date(movie.get('Date Rated') or movie.get('date_rated') or movie.get('标记日期') or movie.get('Watched Date') or '')
                imdb_id = clean_id(movie.get('Const') or movie.get('imdb_id') or movie.get('IMDB ID') or movie.get('IMDb ID'))
                douban_id = clean_id(movie.get('douban_id') or movie.get('movie_id'))
                tmdb_id = clean_id(movie.get('tmdb_id') or movie.get('TMDB ID') or movie.get('id'))
                trakt_id = clean_id(movie.get('trakt_id') or movie.get('Trakt ID'))
                
                # Parse URLs
                douban_url = clean_value(movie.get('douban_url') or movie.get('url') or '')
                if not douban_url and douban_id:
                    douban_url = f"https://movie.douban.com/subject/{douban_id}/"
                # IMDB URL - only from IMDB-specific fields or when platform is imdb
                imdb_url = clean_value(movie.get('imdb_url') or '')
                if not imdb_url and platform == 'imdb':
                    imdb_url = clean_value(movie.get('URL') or '')
                if not imdb_url and imdb_id and str(imdb_id).startswith('tt'):
                    imdb_url = f"https://www.imdb.com/title/{imdb_id}/"
                letterboxd_url = clean_value(movie.get('letterboxd_url') or movie.get('Letterboxd URI') or '')
                trakt_url = clean_value(movie.get('trakt_url') or (movie.get('URL') if platform == 'trakt' else '') or '')
                tmdb_url = ''
                if tmdb_id:
                    tmdb_url = f"https://www.themoviedb.org/movie/{tmdb_id}"

                # Extract metadata
                directors = clean_value(movie.get('Directors') or '')
                actors = clean_value(movie.get('Actors') or '')
                genres = clean_value(movie.get('Genres') or '')
                runtime = clean_value(movie.get('Runtime') or movie.get('Runtime (mins)') or '')

                # Extract type
                media_type = clean_value(movie.get('Type') or movie.get('Title Type') or movie.get('type') or 'movie')
                media_type = str(media_type).lower().strip() if media_type else 'movie'
                if 'tv' in media_type or 'series' in media_type or 'episode' in media_type or 'show' in media_type:
                    media_type = 'tv'
                else:
                    media_type = 'movie'

                all_movies[key] = {
                    'title': clean_value(title),
                    'original_title': clean_value(original_title),
                    'year': str(year)[:4] if year else '',
                    'rating': user_rating,  # User's personal rating
                    'poster_url': poster,
                    'date_rated': date_rated,
                    'imdb_id': imdb_id,
                    'douban_id': douban_id,
                    'tmdb_id': tmdb_id,
                    'trakt_id': trakt_id,
                    'douban_url': douban_url,
                    'imdb_url': imdb_url,
                    'letterboxd_url': letterboxd_url,
                    'trakt_url': trakt_url,
                    'tmdb_url': tmdb_url,
                    'sources': [platform],
                    'latest_date': date_rated,
                    'earliest_date': date_rated,  # 最早观看日期
                    'cine_id': key,  # 唯一标识符
                    # Platform-specific ratings and votes
                    'douban_rating': douban_rating_val,
                    'douban_votes': douban_votes_val,
                    'imdb_rating': imdb_rating_val,
                    'imdb_votes': imdb_votes_val,
                    'letterboxd_rating': user_rating if platform == 'letterboxd' else '',
                    'trakt_rating': user_rating if platform == 'trakt' else '',
                    'tmdb_rating': tmdb_rating_val,
                    # Metadata
                    'directors': directors,
                    'actors': actors,
                    'genres': genres,
                    'runtime': runtime,
                    'type': media_type,
                }
            else:
                # Update existing entry - track all sources
                if platform not in all_movies[key]['sources']:
                    all_movies[key]['sources'].append(platform)
                # Update dates - track both earliest and latest
                new_date = clean_date(movie.get('Date Rated') or movie.get('date_rated') or movie.get('标记日期') or movie.get('Watched Date') or movie.get('latest_date'))
                if new_date:
                    # Update latest_date if newer
                    existing_latest = str(all_movies[key].get('latest_date') or '')
                    if not existing_latest or str(new_date) > existing_latest:
                        all_movies[key]['latest_date'] = new_date
                    # Update earliest_date if older
                    existing_earliest = str(all_movies[key].get('earliest_date') or '')
                    if not existing_earliest or str(new_date) < existing_earliest:
                        all_movies[key]['earliest_date'] = new_date
                
                # Merge metadata if missing in existing entry
                directors = clean_value(movie.get('Directors') or '')
                actors = clean_value(movie.get('Actors') or '')
                genres = clean_value(movie.get('Genres') or '')
                runtime = clean_value(movie.get('Runtime') or movie.get('Runtime (mins)') or '')
                
                if directors and not all_movies[key].get('directors'):
                    all_movies[key]['directors'] = directors
                if actors and not all_movies[key].get('actors'):
                    all_movies[key]['actors'] = actors
                if genres and not all_movies[key].get('genres'):
                    all_movies[key]['genres'] = genres

                # Merge type if missing or upgrade to TV
                new_type = clean_value(movie.get('Type') or movie.get('Title Type') or movie.get('type') or '')
                if new_type:
                     new_type = str(new_type).lower().strip()
                     if 'tv' in new_type or 'series' in new_type or 'episode' in new_type or 'show' in new_type:
                         all_movies[key]['type'] = 'tv'
                     elif not all_movies[key].get('type'):
                         all_movies[key]['type'] = 'movie'
                if runtime and not all_movies[key].get('runtime'):
                    all_movies[key]['runtime'] = runtime
                
                # Extract IDs for this movie from current source
                imdb_id = clean_id(movie.get('Const') or movie.get('imdb_id') or movie.get('IMDB ID') or movie.get('IMDb ID'))
                douban_id = clean_id(movie.get('douban_id') or movie.get('movie_id'))
                tmdb_id = clean_id(movie.get('tmdb_id') or movie.get('TMDB ID') or movie.get('id'))
                trakt_id = clean_id(movie.get('trakt_id') or movie.get('Trakt ID'))
                
                # Update ratings and specific platform metadata
                # For Douban: Update all fields if coming from Douban
                if platform == 'douban':
                    if not all_movies[key].get('douban_url'):
                        all_movies[key]['douban_url'] = movie.get('douban_url') or movie.get('url') or ''
                    if douban_rating_val:
                        all_movies[key]['douban_rating'] = douban_rating_val
                    if douban_votes_val:
                        all_movies[key]['douban_votes'] = douban_votes_val
                elif platform == 'imdb':
                    if not all_movies[key].get('imdb_url'):
                        all_movies[key]['imdb_url'] = movie.get('imdb_url') or movie.get('URL') or ''
                    if imdb_rating_val:
                        all_movies[key]['imdb_rating'] = imdb_rating_val
                    if imdb_votes_val:
                        all_movies[key]['imdb_votes'] = imdb_votes_val
                elif platform == 'letterboxd':
                    if not all_movies[key].get('letterboxd_url'):
                        all_movies[key]['letterboxd_url'] = movie.get('letterboxd_url') or movie.get('Letterboxd URI') or ''
                    all_movies[key]['letterboxd_rating'] = user_rating or all_movies[key].get('letterboxd_rating', '')
                elif platform == 'trakt':
                    # Always update Trakt URL if source has one (fix for shared items)
                    new_trakt_url = movie.get('trakt_url') or movie.get('URL')
                    if new_trakt_url:
                        all_movies[key]['trakt_url'] = new_trakt_url
                    all_movies[key]['trakt_rating'] = user_rating or all_movies[key].get('trakt_rating', '')
                elif platform == 'tmdb':
                    if not all_movies[key].get('tmdb_url') and tmdb_id:
                        all_movies[key]['tmdb_url'] = f"https://www.themoviedb.org/movie/{tmdb_id}"
                    all_movies[key]['tmdb_rating'] = tmdb_rating_val or all_movies[key].get('tmdb_rating', '')
                
                # Merge poster if missing in existing
                if not all_movies[key].get('poster_url'):
                    for poster_field in ['poster_url', 'poster', 'Cover URL', 'Cover', 'poster_path']:
                        raw_poster = movie.get(poster_field)
                        if raw_poster is not None and not (isinstance(raw_poster, float) and math.isnan(raw_poster)):
                            new_poster = clean_value(raw_poster)
                            if new_poster:
                                all_movies[key]['poster_url'] = new_poster
                                break
        
        # Load data from each platform
        config = read_config()
        platforms_with_data = []
        
        # Define platform data sources
        platform_configs = {
            'douban': (config.get('douban_user_id'), lambda uid: os.path.join(DATA_DIR, f'douban_{uid}_ratings.csv')),
            'imdb': (config.get('imdb_user_id'), lambda uid: os.path.join(DATA_DIR, f'imdb_{uid}_ratings.csv')),
            'trakt': (config.get('trakt_user_id'), lambda uid: os.path.join(DATA_DIR, f'trakt_{uid}_ratings.csv')),
            'letterboxd': ('letterboxd', lambda uid: os.path.join(DATA_DIR, 'letterboxd_diary.csv')),
            'tmdb': (config.get('tmdb_user_id'), lambda uid: os.path.join(DATA_DIR, f'tmdb_{uid}_ratings.csv'))
        }
        
        import glob
        # Use APP_DATA which contains all platforms including TMDb
        for platform in platform_configs.keys():
            df = APP_DATA.get(f'{platform}_df')
            if df is not None and not df.empty:
                platforms_with_data.append(platform)
                records = df.to_dict('records')
                for movie in records:
                    add_movie(movie, platform)
        
        # Convert to list and sort by latest_date (descending - newest first)
        movies_list = list(all_movies.values())
        # 排序函数：将日期转为可比较的格式，空日期排到最后
        def sort_key(x):
            date = x.get('latest_date') or ''
            if not date:
                return '0000-00-00'  # 空日期排最后
            date_str = str(date).strip()[:10]
            # 尝试解析并统一为 YYYY-MM-DD 格式
            from datetime import datetime
            for fmt in ['%Y-%m-%d', '%m/%d/%y', '%m/%d/%Y', '%Y/%m/%d', '%d/%m/%Y']:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            # 如果无法解析，假设已是正确格式
            return date_str if len(date_str) >= 10 else '0000-00-00'
        movies_list.sort(key=sort_key, reverse=True)
        
        # Apply platform filter using selected platforms
        if show_union:
            # 特殊情况：没有勾选任何平台，显示并集
            if platform_filter == 'all':
                # 共有：显示所有电影
                pass  # movies_list已经包含所有电影
            else:
                # 平台标签：显示该平台的所有电影
                movies_list = [
                    m for m in movies_list 
                    if platform_filter in m['sources']
                ]
        else:
            # 正常情况：有勾选平台
            if platform_filter == 'all':
                # Shared: Must have ALL selected platforms (交集)
                movies_list = [
                    m for m in movies_list 
                    if selected_platforms.issubset(set(m['sources']))
                ]
            else:
                # Platform specific: Has this platform, but NOT all selected platforms
                # 即：该平台的所有 - 交集
                movies_list = [
                    m for m in movies_list 
                    if platform_filter in m['sources'] 
                    and not selected_platforms.issubset(set(m['sources']))
                ]
        
        total_count = len(movies_list)
        
        # Calculate platform counts based on selected platforms
        all_temp = list(all_movies.values())
        platform_counts = {}
        
        # Calculate intersection (shared) count first
        if show_union:
            shared_movies_count = len(all_temp)
        else:
            shared_movies = [m for m in all_temp if selected_platforms.issubset(set(m['sources']))]
            shared_movies_count = len(shared_movies)

        for platform in platform_configs.keys():
            # 获取该平台的所有电影
            platform_movies = [m for m in all_temp if platform in m['sources']]
            total_platform_count = len(platform_movies)
            
            if show_union:
                # 没选平台时，显示该平台总数
                platform_counts[platform] = total_platform_count
            else:
                # 选了平台时，显示该平台独占数 (总数 - 交集数)
                # 注意：这里我们计算的是真正会在该标签页显示的电影数量
                # 即：属于该平台 AND NOT 属于交集
                if platform in selected_platforms:
                     # 计算交集：即那些拥有所有selected_platforms的电影
                    count_in_intersection = len([
                        m for m in platform_movies 
                        if selected_platforms.issubset(set(m['sources']))
                    ])
                    platform_counts[platform] = total_platform_count - count_in_intersection
                else:
                    # 如果该平台没被勾选，它不会参与交集计算，但在标签页
                    # 按照我们的逻辑，它显示的是"属于该平台"的所有电影（还是除去交集？）
                    # 之前的逻辑是：platform_filter in m['sources'] and not selected_platforms.issubset...
                    # 所以如果selected_platforms不包含该平台，selected_platforms.issubset()对于该平台独有的电影可能是False
                    # 为了简化，我们统一显示：该平台总数 - (该平台与Selected的交集?)
                    # 不，上面的逻辑是：m['sources'] 包含当前tab平台，且 不全是 selected_platforms
                    
                    # 简单点：直接复用上面的筛选逻辑计算一遍
                    count = len([
                        m for m in platform_movies 
                        if not selected_platforms.issubset(set(m['sources']))
                    ])
                    platform_counts[platform] = count
        
        # Shared count is handled separately in response
        
        logger.info(f"[DEBUG] selected_platforms={selected_platforms}")
        
        # Shared = movies with ALL selected platforms
        if show_union:
            # 没有选择平台时，共有=所有电影
            shared_movies = all_temp
        else:
            shared_movies = [m for m in all_temp if selected_platforms.issubset(set(m['sources']))]
        logger.info(f"[DEBUG] selected_platforms={selected_platforms}")
        logger.info(f"[DEBUG] Sample sources: {[m['sources'] for m in all_temp[:5]]}")
        logger.info(f"[DEBUG] Shared count={len(shared_movies)}, Sample shared: {[m.get('title') for m in shared_movies[:3]]}")
        platform_counts['shared'] = len(shared_movies)
        
        
        # Paginate
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_movies = movies_list[start_idx:end_idx]
        
        logger.info(f"[API Library] Sending response: filter={platform_filter}, movies={len(page_movies)}, total={total_count}")
        
        return jsonify({
            'movies': page_movies,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size if total_count > 0 else 0,
            'platform_counts': platform_counts,
            'platforms_with_data': platforms_with_data,
            'filter': platform_filter
        })
        
    except Exception as e:
        logger.exception("API Library error")
        return jsonify({'error': str(e)}), 500

@socketio.on('check_session')
def handle_check_session(data):
    """Check session and validate stored credentials before showing connected state.
    
    Design principles:
    1. Validation-first: Don't show 'connected' until credentials are validated
    2. Separate data from connection state: Load cached data even if validation pending
    3. Async validation: Validate in background to avoid blocking UI
    """
    config = read_config()
    cached_data = {}
    
    # ========================================
    # Step 1: Load cached data (data != connection state)
    # ========================================
    for platform in ['douban', 'imdb']:
        user_id = config.get(f'{platform}_user_id')
        if user_id:
            csv_path = os.path.join(DATA_DIR, f'{platform}_{user_id}_ratings.csv')
            if os.path.exists(csv_path):
                try:
                    df = pd.read_csv(csv_path)
                    APP_DATA[f'{platform}_df'] = df
                    APP_DATA[f'{platform}_csv_path'] = csv_path
                    cached_data[platform] = {
                        'has_data': True,
                        'count': len(df),
                        'user_id': user_id
                    }
                    logger.debug(f"Loaded cached {platform} data: {len(df)} records")
                except Exception as e:
                    logger.error(f"Error loading cached {platform} data: {e}")
    
    
    # Load Trakt cached data
    trakt_user_id = config.get('trakt_user_id')
    if trakt_user_id:
        trakt_csv = os.path.join(DATA_DIR, f'trakt_{trakt_user_id}_ratings.csv')
        # Fallback search
        if not os.path.exists(trakt_csv):
            import glob
            matches = glob.glob(os.path.join(DATA_DIR, 'trakt_*_ratings.csv'))
            if matches:
                trakt_csv = matches[0]

        if os.path.exists(trakt_csv):
            try:
                df = pd.read_csv(trakt_csv)
                APP_DATA['trakt_df'] = df
                APP_DATA['trakt_csv_path'] = trakt_csv
                cached_data['trakt'] = {
                    'has_data': True,
                    'count': len(df),
                    'user_id': trakt_user_id
                }
                logger.debug(f"Loaded cached Trakt data: {len(df)} records")
            except Exception as e:
                logger.error(f"Error loading cached Trakt data: {e}")

    # Load Letterboxd cached data
    letterboxd_csv = os.path.join(DATA_DIR, 'letterboxd_diary.csv')
    if not os.path.exists(letterboxd_csv):
        import glob
        matches = glob.glob(os.path.join(DATA_DIR, '*diary.csv'))
        if matches:
            letterboxd_csv = matches[0]
            
    if os.path.exists(letterboxd_csv):
        try:
            df = pd.read_csv(letterboxd_csv)
            APP_DATA['letterboxd_df'] = df
            APP_DATA['letterboxd_csv_path'] = letterboxd_csv
            cached_data['letterboxd'] = {
                'has_data': True,
                'count': len(df),
                'user_id': 'letterboxd'
            }
            logger.debug(f"Loaded cached Letterboxd data: {len(df)} records")
        except Exception as e:
            logger.error(f"Error loading cached Letterboxd data: {e}")

    # Load TMDB cached data
    tmdb_user_id = config.get('tmdb_user_id')
    tmdb_csv = None
    if tmdb_user_id:
        tmdb_csv = os.path.join(DATA_DIR, f'tmdb_{tmdb_user_id}_ratings.csv')
    
    if not tmdb_csv or not os.path.exists(tmdb_csv):
        import glob
        matches = glob.glob(os.path.join(DATA_DIR, 'tmdb_*_ratings.csv'))
        if matches:
            tmdb_csv = matches[0]
            
    if tmdb_csv and os.path.exists(tmdb_csv):
        try:
            df = pd.read_csv(tmdb_csv)
            APP_DATA['tmdb_df'] = df
            APP_DATA['tmdb_csv_path'] = tmdb_csv
            cached_data['tmdb'] = {
                'has_data': True,
                'count': len(df),
                'user_id': tmdb_user_id or 'tmdb'
            }
            logger.debug(f"Loaded cached TMDB data: {len(df)} records")
        except Exception as e:
            logger.error(f"Error loading cached TMDB data: {e}")
    
    # ========================================
    # Step 2: Send initial state with pending validations
    # ========================================
    platforms_pending = {}
    
    # Cookie-based platforms (Douban/IMDB)
    for platform in ['douban', 'imdb']:
        user_id = config.get(f'{platform}_user_id')
        cookie = config.get(f'{platform}_cookie')
        if user_id and cookie:
            platforms_pending[platform] = {
                'status': 'validating',
                'user_id': user_id
            }
    
    # OAuth platforms (Trakt/TMDB)
    trakt_id = config.get('trakt_client_id')
    trakt_token = config.get('trakt_access_token')
    logger.info(f"DEBUG: Trakt Config Check - ID: {'Found' if trakt_id else 'Missing'}, Token: {'Found' if trakt_token else 'Missing'}")
    # Don't mark Trakt as validating since we disabled auto-validation
    # if trakt_id and trakt_token:
    #     platforms_pending['trakt'] = {
    #         'status': 'validating',
    #         'user_id': config.get('trakt_user_id')
    #     }
    
    tmdb_session_id = config.get('tmdb_session_id')
    tmdb_username = config.get('tmdb_username', '')
    if tmdb_session_id:
        platforms_pending['tmdb'] = {
            'status': 'validating',
            'username': tmdb_username
        }
    
    # Send initial state - frontned will show "validating" status
    emit('session_restored', {
        'platforms_pending': platforms_pending,
        'cached_data': cached_data,
        'config': config
    })
    
    # ========================================
    # Step 3: Trigger async validation for each platform
    # ========================================
    def validate_all_platforms():
        import time
        import threading
        
        # Simple lock to prevent multiple validation threads
        global VALIDATION_LOCK
        if 'VALIDATION_LOCK' not in globals():
            VALIDATION_LOCK = threading.Lock()
            
        if not VALIDATION_LOCK.acquire(blocking=False):
            return

        try:
            time.sleep(0.2)  # Small delay to let frontend render initial state
            
            
            # Validate Cookie-based platforms
            for platform in ['douban', 'imdb']:
                user_id = config.get(f'{platform}_user_id')
                cookie = config.get(f'{platform}_cookie')
                if user_id and cookie:
                    validate_cookie_platform(platform, cookie, user_id)
            
            # Validate Trakt - DISABLED: Only validate on explicit user request
            # Automatic validation causes SSL timeouts that interfere with sync preview
            # logger.info("DEBUG: Checking Trakt config in thread")
            # if config.get('trakt_access_token'):
            #     logger.info("DEBUG: Calling validate_trakt_connection from thread")
            #     validate_trakt_connection()
            
            # Validate TMDB
            if tmdb_session_id:
                validate_tmdb_connection(config)
        except Exception as e:
            logger.exception("FATAL: validate_all_platforms thread crashed")
        finally:
            VALIDATION_LOCK.release()
    
    import threading
    threading.Thread(target=validate_all_platforms, daemon=True).start()


def validate_cookie_platform(platform, cookie, user_id):
    """Validate cookie by making a test request"""
    import requests
    import re
    
    headers = {
        'Cookie': cookie,
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        if platform == 'douban':
            valid = False
            found_id = None
            
            # Method 1: If we have user_id, test mobile page (less strict anti-bot)
            if user_id:
                try:
                    # Access a public movie page with credentials to check login status
                    # Note: mobile page doesn't strictly check login for public pages, 
                    # but invalid cookie might cause issues. 
                    # Better check: mobile profile page
                    m_url = f"https://m.douban.com/people/{user_id}/"
                    m_resp = requests.get(m_url, headers=headers, timeout=10, allow_redirects=False)
                    
                    if m_resp.status_code == 200:
                        valid = True
                        found_id = user_id
                        logger.debug(f"Douban validation successful (Mobile Profile): {user_id}")
                except Exception as e:
                    logger.debug(f"Mobile validation failed: {e}")

            # Method 2: PC Mine Page (strict, often redirects to sec.douban.com)
            if not valid:
                resp = requests.get('https://www.douban.com/mine/', 
                                  headers=headers, timeout=10, allow_redirects=True)
                
                # Douban sometimes redirects through sec.douban.com with encoded URL
                from urllib.parse import unquote
                url_to_check = unquote(resp.url)
                
                # Check 1: URL match (e.g. /people/username/)
                m = re.search(r'/people/([^/\?"]+)', url_to_check)
                if m:
                    found_id = m.group(1)
                    valid = True
                    logger.debug(f"Douban validation successful (URL match): {found_id}")
                
                # Check 2: Content match (fallback for redirect/sec pages)
                elif 'accounts/logout' in resp.text:
                    m2 = re.search(r'douban\.com/people/([^/"]+)/', resp.text)
                    found_id = m2.group(1) if m2 else user_id
                    valid = True
                    logger.debug(f"Douban validation successful (Content match): {found_id}")

            if valid and found_id:
                socketio.emit('platform_validated', {
                    'platform': platform,
                    'valid': True,
                    'user_id': found_id
                })
            else:
                socketio.emit('platform_validated', {
                    'platform': platform,
                    'valid': False,
                    'error': '验证失败: 未检测到登录状态'
                })
                logger.warning(f"Douban validation failed - all methods tried")
                
        elif platform == 'imdb':
            # Test IMDB by checking if we can access user page
            resp = requests.get('https://www.imdb.com/list/watchlist/',
                              headers=headers, timeout=10, allow_redirects=True)
            if 'signin' in resp.url.lower() or resp.status_code == 401:
                socketio.emit('platform_validated', {
                    'platform': platform,
                    'valid': False,
                    'error': 'Cookie 已过期或无效'
                })
                logger.warning(f"IMDB validation failed - need login")
            else:
                socketio.emit('platform_validated', {
                    'platform': platform,
                    'valid': True,
                    'user_id': user_id
                })
                logger.debug(f"IMDB validation successful: {user_id}")
                
    except requests.RequestException as e:
        logger.error(f"{platform} validation error: {e}")
        socketio.emit('platform_validated', {
            'platform': platform,
            'valid': False,
            'error': f'网络错误: {str(e)}'
        })


def validate_trakt_connection():
    """Validate Trakt access token by making API call"""
    # logger.debug("Entered validate_trakt_connection")
    config = read_config()
    client_id = config.get('trakt_client_id', '').strip()
    client_secret = config.get('trakt_client_secret', '').strip()
    access_token = config.get('trakt_access_token', '').strip()
    refresh_token = config.get('trakt_refresh_token', '').strip()
    
    if not client_id or not access_token:
        socketio.emit('platform_validated', {
            'platform': 'trakt',
            'valid': False,
            'error': '缺少授权信息'
        })
        return
    
    global TRAKT_LAST_VALIDATED
    current_time = time.time()
    
    # Throttle validation (debounce 5 minutes unless forced?)
    # We use a global variable to track last validation timestamp
    if 'TRAKT_LAST_VALIDATED' not in globals():
        TRAKT_LAST_VALIDATED = 0
        
    if current_time - TRAKT_LAST_VALIDATED < 300: # 5 minutes
        logger.debug(f"Trakt validation skipped (throttled). Last: {TRAKT_LAST_VALIDATED}")
        return

    try:
        token_expires = config.get('trakt_token_expires')
        client = TraktClient(client_id, client_secret, access_token, refresh_token, token_expires=token_expires)
        
        # Try to refresh token if expired
        is_expired = client.is_token_expired()
        if is_expired:
            logger.info("Trakt token expired, attempting refresh...")
            if client.refresh_access_token():
                config['trakt_access_token'] = client.access_token
                config['trakt_refresh_token'] = client.refresh_token
                if client.token_expires:
                    config['trakt_token_expires'] = client.token_expires.isoformat()
                write_config(config)
                logger.info("Trakt token refreshed and saved.")
            else:
                socketio.emit('platform_validated', {
                    'platform': 'trakt',
                    'valid': False,
                    'error': 'Token 刷新失败，请重新授权'
                })
                # Do not update timestamp so we retry later? Or backoff?
                return
        
        # Get profile to verify connection
        # Only fetch profile if we haven't recently or if we just refreshed
        profile = client.get_user_profile()
        if profile:
            TRAKT_LAST_VALIDATED = current_time # Update success timestamp
            
            # Try to get stats, but don't fail if SSL error occurs
            movies_watched = 0
            movies_rated = 0
            try:
                stats = client.get_user_stats('me')
                if stats:
                    movies_watched = stats.get('movies', {}).get('watched', 0) or 0
                    movies_rated = stats.get('movies', {}).get('ratings', 0) or 0
            except Exception as e:
                logger.warning(f"Failed to fetch Trakt stats (non-critical): {e}")
            
            socketio.emit('platform_validated', {
                'platform': 'trakt',
                'valid': True,
                'profile': {
                    'user_id': profile.get('ids', {}).get('slug'),
                    'username': profile.get('username'),
                    'display_name': profile.get('name'),
                    'avatar': profile.get('images', {}).get('avatar', {}).get('full'),
                    'movies_watched': movies_watched,
                    'movies_rated': movies_rated,
                    'profile_link': f"https://trakt.tv/users/{profile.get('ids', {}).get('slug')}"
                }
            })
            logger.debug(f"Trakt validation successful: {profile.get('username')}")
        else:
            socketio.emit('platform_validated', {
                'platform': 'trakt',
                'valid': False,
                'error': '无法获取用户信息 (API Connection Failed)'
            })
            
    except Exception as e:
        logger.exception(f"Trakt validation error: {e}")
        socketio.emit('platform_validated', {
            'platform': 'trakt',
            'valid': False,
            'error': f'验证失败: {str(e)}'
        })


def validate_tmdb_connection(config):
    """Validate TMDB session by making API call"""
    from scrapers.tmdb_client import DEFAULT_TMDB_API_KEY
    
    api_key = config.get('tmdb_api_key', '') or DEFAULT_TMDB_API_KEY
    session_id = config.get('tmdb_session_id', '')
    
    if not session_id:
        socketio.emit('platform_validated', {
            'platform': 'tmdb',
            'valid': False,
            'error': '需要重新授权'
        })
        return
    
    try:
        client = TMDBClient(api_key, session_id)
        account = client.get_account_details()
        
        if account and account.get('id'):
            stats = client.get_account_stats()
            socketio.emit('platform_validated', {
                'platform': 'tmdb',
                'valid': True,
                'account': {
                    'username': account.get('username'),
                    'account_id': account.get('id'),
                    'rated_count': stats.get('rated_count', 0) if stats else 0,
                    'watchlist_count': stats.get('watchlist_count', 0) if stats else 0,
                    'profile_link': f"https://www.themoviedb.org/u/{account.get('username')}"
                }
            })
            logger.debug(f"TMDB validation successful: {account.get('username')}")
        else:
            socketio.emit('platform_validated', {
                'platform': 'tmdb',
                'valid': False,
                'error': 'Session 已过期'
            })
            
    except Exception as e:
        logger.error(f"TMDB validation error: {e}")
        socketio.emit('platform_validated', {
            'platform': 'tmdb',
            'valid': False,
            'error': f'验证失败: {str(e)}'
        })


# ==========================================
# Platform Registry Handler (Plugin System)
# ==========================================

@socketio.on('get_platforms')
def handle_get_platforms(data=None):
    """Return list of available platform adapters and their capabilities"""
    platforms = AdapterRegistry.list_adapters()
    emit('platforms_list', {'platforms': platforms})

@socketio.on('fetch_data')
def handle_fetch(data):
    platform = data.get('platform')
    config = read_config()
    # Prioritize user_id from payload (e.g. for backup) over config
    user_id = data.get('user_id') or config.get(f'{platform}_user_id')
    cookie = config.get(f'{platform}_cookie')
    
    if not (user_id and cookie):
        emit('log', {'message': f'❌ 请先在设置中填写 {platform.upper()} 用户ID和Cookie。', 'type': 'error'})
        return

    expected_path = os.path.join(DATA_DIR, f'{platform}_{user_id}_ratings.csv')
    force_full_refresh = bool(data.get('force_full') or data.get('force_full_refresh'))
    refresh_reasons = []
    if force_full_refresh:
        refresh_reasons.append('manual request')
    if platform in ['douban', 'imdb']:
        ts_key = f'{platform}_latest_record_ts'
        if not config.get(ts_key):
            refresh_reasons.append('timestamp not set')
        if needs_type_refresh(expected_path):
            refresh_reasons.append('missing Type values')
    if refresh_reasons:
        force_full_refresh = True
        socketio.emit('log', {
            'message': f'🧩 {platform.upper()} full rebuild enabled ({", ".join(refresh_reasons)}).',
            'type': 'info'
        })
    
    def on_complete(result):
        if result:
            df = pd.DataFrame(result)
            df = ensure_type_column(df)
            cols_to_display = [col for col in CORE_COLUMNS if col in df.columns]
            cols_to_keep = set(cols_to_display + [col for col in ESSENTIAL_COLUMNS if col in df.columns])
            display_df = df[list(cols_to_keep)].copy()
            config_user_id = config.get(f'{platform}_user_id')
            is_main_user = str(user_id) == str(config_user_id) if config_user_id else True

            if is_main_user:
                APP_DATA[f'{platform}_csv_path'] = expected_path
                APP_DATA[f'{platform}_df'] = display_df  # Store for pagination
            
            # Extract and store latest record timestamp for incremental sync
            latest_ts = None
            date_col = 'Date Rated'
            if date_col in df.columns:
                try:
                    dates = pd.to_datetime(df[date_col], errors='coerce')
                    valid_dates = dates.dropna()
                    if not valid_dates.empty:
                        latest_ts = valid_dates.max().isoformat()
                except Exception as e:
                    logger.warning(f"Failed to parse dates for {platform}: {e}")
            
            # Only update config timestamp if this is the MAIN user
            if latest_ts and is_main_user:
                cfg = read_config()
                cfg[f'{platform}_latest_record_ts'] = latest_ts
                write_config(cfg)
                socketio.emit('log', {'message': f'📅 {platform.upper()} 最新记录时间: {latest_ts[:10]}', 'type': 'info'})
            elif not is_main_user:
                 socketio.emit('log', {'message': f'👥 已备份好友 ({user_id}) 数据', 'type': 'success'})
            
            page_size = 10
            socketio.emit('fetch_complete', {
                'platform': platform,
                'path': expected_path,
                'sample': safe_df_to_records(display_df.head(page_size)),
                'total_count': len(df),
                'headers': cols_to_display,
                'page': 1,
                'page_size': page_size,
                'total_pages': (len(df) + page_size - 1) // page_size,
                'latest_record_ts': latest_ts
            })
        else:
            socketio.emit('log', {'message': f'❌ 获取 {platform.upper()} 数据失败。', 'type': 'error'})

    if platform == 'douban':
        import threading
        threading.Thread(target=lambda: on_complete(run_douban(
            user_id, cookie, expected_path, socketio, force_full_refresh=force_full_refresh
        ))).start()
    else:
        import threading
        threading.Thread(target=lambda: on_complete(run_imdb(
            user_id, cookie, expected_path, socketio, force_full_refresh=force_full_refresh
        ))).start()

@socketio.on('fetch_wish')
def handle_fetch_wish(data):
    platform = str(data.get('platform') or '').strip().lower()
    config = read_config()
    force_full = bool(data.get('force_full'))

    if not platform:
        emit('log', {'message': '❌ 未指定平台', 'type': 'error'})
        return

    def clear_wish_cache(expected_path, platform_key):
        if not force_full:
            return
        try:
            if expected_path and os.path.exists(expected_path):
                os.remove(expected_path)
            APP_DATA.pop(f'{platform_key}_wish_df', None)
            APP_DATA.pop(f'{platform_key}_wish_path', None)
            APP_DATA.pop(f'{platform_key}_wish_mtime', None)
            socketio.emit('log', {'message': '🧹 已清理本地想看缓存，开始全量重建...', 'type': 'info'})
        except Exception as e:
            logger.error(f"Failed to clear wish cache: {e}")

    def on_complete(result, expected_path, user_id):
        if result is not None:
            df = filter_wish_df(pd.DataFrame(result))
            df = ensure_type_column(df)
            if df is None:
                df = pd.DataFrame()
            count = len(df)

            # Save to APP_DATA only if main user
            if platform == 'tmdb':
                config_user_id = config.get('tmdb_username') or config.get('tmdb_user_id')
            else:
                config_user_id = config.get(f'{platform}_user_id')
            is_main_user = str(user_id) == str(config_user_id) if config_user_id else True

            try:
                if is_main_user:
                    APP_DATA[f'{platform}_wish_df'] = df
                    APP_DATA[f'{platform}_wish_path'] = expected_path or ''
                    try:
                        if expected_path:
                            APP_DATA[f'{platform}_wish_mtime'] = os.path.getmtime(expected_path)
                        else:
                            APP_DATA[f'{platform}_wish_mtime'] = None
                    except Exception:
                        APP_DATA[f'{platform}_wish_mtime'] = None
            except Exception as e:
                logger.error(f"Failed to cache wish data: {e}")

            socketio.emit('log', {'message': f'✅ {platform.upper()} 想看列表获取完成: {count} 部', 'type': 'success'})
            socketio.emit('fetch_wish_complete', {
                'platform': platform,
                'count': count,
                'path': expected_path or '',
                'sample': safe_df_to_records(df.head(5)) if not df.empty else []
            })
        else:
            socketio.emit('log', {'message': f'❌ 获取 {platform.upper()} 想看列表失败。', 'type': 'error'})

    if platform == 'douban':
        user_id = data.get('user_id') or config.get('douban_user_id')
        cookie = config.get('douban_cookie')

        if not (user_id and cookie):
            emit('log', {'message': '❌ 请先在设置中填写 DOUBAN 用户ID和Cookie。', 'type': 'error'})
            return

        expected_path = os.path.join(DATA_DIR, f'douban_{user_id}_wish.csv')
        clear_wish_cache(expected_path, platform)

        import threading
        threading.Thread(target=lambda: on_complete(run_wish_scraper(
            user_id, cookie, expected_path, socketio, force_full_refresh=force_full
        ), expected_path, user_id)).start()
        return

    if platform == 'imdb':
        user_id = data.get('user_id') or config.get('imdb_user_id')
        cookie = config.get('imdb_cookie')

        if not user_id:
            emit('log', {'message': '❌ 请先在设置中填写 IMDb 用户ID。', 'type': 'error'})
            return
        if not cookie:
            emit('log', {'message': '❌ 请先在设置中填写 IMDb Cookie。', 'type': 'error'})
            return

        expected_path = os.path.join(DATA_DIR, f'imdb_{user_id}_wish.csv')
        clear_wish_cache(expected_path, platform)

        def fetch_imdb_wish():
            try:
                records = fetch_imdb_watchlist(cookie, user_id=user_id)
                if records is None:
                    return None
                if records:
                    pd.DataFrame(records).to_csv(expected_path, index=False)
                return records
            except Exception as e:
                logger.error(f"IMDb wish fetch error: {e}")
                return None

        import threading
        threading.Thread(target=lambda: on_complete(fetch_imdb_wish(), expected_path, user_id), daemon=True).start()
        return

    if platform == 'trakt':
        client_id = config.get('trakt_client_id', '')
        client_secret = config.get('trakt_client_secret', '')
        access_token = config.get('trakt_access_token', '')
        refresh_token = config.get('trakt_refresh_token', '')
        token_expires = config.get('trakt_token_expires')

        if not client_id or not access_token:
            emit('log', {'message': '❌ 请先授权 Trakt 账号', 'type': 'error'})
            return

        user_id = config.get('trakt_user_id', 'me')
        expected_path = os.path.join(DATA_DIR, f'trakt_{user_id}_wish.csv')
        clear_wish_cache(expected_path, platform)

        def fetch_trakt_wish():
            try:
                client = TraktClient(client_id, client_secret, access_token, refresh_token, token_expires=token_expires)
                if client.is_token_expired():
                    if client.refresh_access_token():
                        config['trakt_access_token'] = client.access_token
                        config['trakt_refresh_token'] = client.refresh_token
                        config['trakt_token_expires'] = client.token_expires.isoformat()
                        write_config(config)

                records = []
                page = 1
                while True:
                    result = client.get_watchlist('me', item_type='movies', page=page, limit=100)
                    if not result:
                        break
                    items = result.get('items', [])
                    if not items:
                        break
                    for item in items:
                        movie = item.get('movie', {}) or {}
                        ids = movie.get('ids', {}) or {}
                        slug = ids.get('slug') or ''
                        record = {
                            'Title': movie.get('title', ''),
                            'Year': movie.get('year', ''),
                            'tmdb_id': ids.get('tmdb'),
                            'imdb_id': ids.get('imdb'),
                            'trakt_id': ids.get('trakt'),
                            'URL': f"https://trakt.tv/movies/{slug}" if slug else '',
                            'Genres': ', '.join(movie.get('genres', []) or []),
                            'Date Added': item.get('listed_at', '') or '',
                            'status': 'wish',
                            'type': 'movie',
                            'source': 'trakt'
                        }
                        records.append(record)
                    total_pages = result.get('total_pages', 1)
                    if page >= total_pages:
                        break
                    page += 1

                if records:
                    pd.DataFrame(records).to_csv(expected_path, index=False)
                return records
            except Exception as e:
                logger.error(f"Trakt wish fetch error: {e}")
                return None

        import threading
        threading.Thread(target=lambda: on_complete(fetch_trakt_wish(), expected_path, user_id), daemon=True).start()
        return

    if platform == 'tmdb':
        from scrapers.tmdb_client import DEFAULT_TMDB_API_KEY
        api_key = config.get('tmdb_api_key') or DEFAULT_TMDB_API_KEY
        session_id = config.get('tmdb_session_id', '')

        if not session_id:
            emit('log', {'message': '❌ 请先完成 TMDB 用户授权', 'type': 'error'})
            return

        def fetch_tmdb_wish():
            try:
                client = TMDBClient(api_key, session_id)
                if not config.get('tmdb_username'):
                    account = client.get_account_details() or {}
                    username = account.get('username')
                    if username:
                        config['tmdb_username'] = username
                        write_config(config)

                user_id = config.get('tmdb_username') or config.get('tmdb_user_id') or 'tmdb'
                expected_path = os.path.join(DATA_DIR, f'tmdb_{user_id}_wish.csv')
                clear_wish_cache(expected_path, platform)

                records = []
                page = 1
                while True:
                    result = client.get_watchlist(page=page)
                    if not result:
                        break
                    items = result.get('results', [])
                    if not items:
                        break
                    for movie in items:
                        tmdb_id = movie.get('id')
                        poster_path = movie.get('poster_path')
                        cover_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ''
                        record = {
                            'Title': movie.get('title') or movie.get('name') or '',
                            'Year': (movie.get('release_date') or movie.get('first_air_date') or '')[:4],
                            'tmdb_id': tmdb_id,
                            'URL': f"https://www.themoviedb.org/movie/{tmdb_id}" if tmdb_id else '',
                            'Cover URL': cover_url,
                            'Date Added': movie.get('created_at', '') or '',
                            'status': 'wish',
                            'type': 'movie',
                            'source': 'tmdb'
                        }
                        records.append(record)
                    total_pages = result.get('total_pages', 1)
                    if page >= total_pages:
                        break
                    page += 1

                if records:
                    pd.DataFrame(records).to_csv(expected_path, index=False)
                return records, expected_path, user_id
            except Exception as e:
                logger.error(f"TMDB wish fetch error: {e}")
                return None, None, None

        import threading
        def run_tmdb_fetch():
            records, expected_path, user_id = fetch_tmdb_wish()
            on_complete(records, expected_path, user_id)

        threading.Thread(target=run_tmdb_fetch, daemon=True).start()
        return

    emit('log', {'message': f'❌ 未支持的平台: {platform}', 'type': 'error'})


@socketio.on('fetch_cinepersona_watchlist')
def handle_fetch_cinepersona_watchlist(data):
    config = read_config()
    if not config.get('cinepersona_consent'):
        emit('log', {'message': '⚠️ 请先在设置中同意 CinePersona 数据同步', 'type': 'warning'})
        return

    base_url = normalize_cinepersona_url(config.get('cinepersona_url', ''))
    if not base_url:
        emit('log', {'message': '❌ 请先配置 CinePersona 地址', 'type': 'error'})
        return

    session_cookie = config.get('cinepersona_session_cookie', '')
    if not session_cookie:
        emit('log', {'message': '⚠️ 未填写 CinePersona Cookie，无法拉取在线想看', 'type': 'warning'})
        return

    headers = {
        'Cookie': session_cookie,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }

    try:
        resp = requests.get(f'{base_url}/api/watchlist', headers=headers, timeout=30)
        if resp.status_code != 200:
            emit('log', {'message': f'❌ CinePersona 想看获取失败: {resp.status_code}', 'type': 'error'})
            return
        payload = resp.json()
    except Exception as e:
        logger.error(f"CinePersona watchlist fetch error: {e}")
        emit('log', {'message': f'❌ CinePersona 想看获取失败: {e}', 'type': 'error'})
        return

    items = payload.get('items') or []
    records = []
    for item in items:
        movie = item.get('movie') or {}
        title = movie.get('titleLocalized') or movie.get('titleEn') or ''
        release_date = movie.get('releaseDate') or ''
        year = str(release_date)[:4] if release_date else ''
        tmdb_id = movie.get('tmdbId')
        imdb_id = movie.get('imdbId')
        poster_path = movie.get('posterPath') or ''
        cover_url = ''
        if poster_path:
            if str(poster_path).startswith('http'):
                cover_url = poster_path
            else:
                cover_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
        url = ''
        if imdb_id:
            url = f"https://www.imdb.com/title/{imdb_id}/"
        elif tmdb_id:
            url = f"https://www.themoviedb.org/movie/{tmdb_id}"
        records.append({
            'Title': title,
            'Year': year,
            'tmdb_id': tmdb_id,
            'imdb_id': imdb_id,
            'Cover URL': cover_url,
            'URL': url,
            'Date Added': item.get('addedAt') or '',
            'status': 'wish',
            'type': 'movie'
        })

    if records:
        df = pd.DataFrame(records)
        df = ensure_type_column(df)
        save_path = os.path.join(DATA_DIR, 'cinepersona_watchlist.csv')
        df.to_csv(save_path, index=False, encoding='utf-8-sig')
        APP_DATA['cinepersona_wish_df'] = df
        APP_DATA['cinepersona_wish_path'] = save_path
        try:
            APP_DATA['cinepersona_wish_mtime'] = os.path.getmtime(save_path)
        except Exception:
            APP_DATA['cinepersona_wish_mtime'] = None

    emit('log', {'message': f'✅ CinePersona 想看同步完成: {len(records)} 部', 'type': 'success'})
    emit('fetch_wish_complete', {
        'platform': 'cinepersona',
        'count': len(records),
        'path': os.path.join(DATA_DIR, 'cinepersona_watchlist.csv'),
        'sample': safe_df_to_records(pd.DataFrame(records).head(5)) if records else []
    })

@socketio.on('get_wishlist_library')
def handle_get_wishlist_library(data=None):
    """Return aggregated wishlist data for the main user"""
    wishlist_data = []

    try:
        config = read_config()
        df = build_wishlist_df(config)
    except Exception as e:
        df = None
        logger.error(f"[Wishlist] Error loading wishlist data: {e}")

    if df is not None and not df.empty:
        records = safe_df_to_records(df)
        wishlist_data.extend(records)
    else:
        config = read_config()
        user_id = str(config.get('douban_user_id') or '').strip()
        if user_id:
            wish_path = os.path.join(DATA_DIR, f'douban_{user_id}_wish.csv')
            if not os.path.exists(wish_path):
                socketio.emit('log', {'message': f'⚠️ 未找到想看文件: {os.path.basename(wish_path)}', 'type': 'warning'})
            else:
                socketio.emit('log', {'message': '⚠️ 想看文件已读取但无可显示条目', 'type': 'warning'})

    # Media server matching (Emby/Jellyfin)
    try:
        config = read_config()
        library_items, _ = fetch_media_server_library(config)
        wishlist_data = apply_media_server_matching(wishlist_data, library_items)
    except Exception as e:
        logger.warning(f"[Media Server] Matching skipped: {e}")

    emit('wishlist_library_data', {'items': wishlist_data, 'count': len(wishlist_data)})

@socketio.on('get_backups_list')
def handle_get_backups_list(data=None):
    """Scan data directory for backup files (files not belonging to main user)"""
    config = read_config()
    main_users = {
        'douban': str(config.get('douban_user_id', '')),
        'imdb': str(config.get('imdb_user_id', '')),
        # Add other platforms if needed
    }
    
    backups = []
    try:
        if not os.path.exists(DATA_DIR):
             emit('backups_list_data', {'backups': []}); return

        files = os.listdir(DATA_DIR)
        for f in files:
            if not f.endswith('.csv'): continue
            
            # Parse filename: platform_userid_type.csv (type is ratings or wish)
            # Example: douban_123456_ratings.csv
            parts = f.replace('.csv', '').split('_')
            # Handle cases where userid might have underscores? Douban/IMDb IDs usually don't.
            # Usually strict format: [platform]_[userid]_[type].csv
            if len(parts) < 3: continue
            
            platform = parts[0]
            # Assming type is last part ('ratings' or 'wish')
            data_type = parts[-1]
            # UserID is everything in between
            user_id = "_".join(parts[1:-1])
            
            if platform not in ['douban', 'imdb', 'trakt', 'letterboxd', 'tmdb']: continue

            # Check if it is a main user file
            if platform in main_users and str(user_id) == str(main_users[platform]):
                continue
            
            # It is a backup file
            file_path = os.path.join(DATA_DIR, f)
            stat = os.stat(file_path)
            
            backups.append({
                'filename': f,
                'platform': platform,
                'user_id': user_id,
                'type': data_type, # 'ratings' or 'wish'
                'size': stat.st_size,
                'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
            
    except Exception as e:
        logger.error(f"Error listing backups: {e}")
        emit('log', {'message': f'❌ 读取备份列表失败: {e}', 'type': 'error'})
        return

    emit('backups_list_data', {'backups': backups})


@socketio.on('get_my_files_list')
def handle_get_my_files_list(data=None):
    """List current user's platform CSV files"""
    config = read_config()
    my_files = []
    
    # Check each platform's main user files
    platforms_config = {
        'douban': {'user_key': 'douban_user_id', 'types': ['ratings', 'wish']},
        'imdb': {'user_key': 'imdb_user_id', 'types': ['ratings']},
        'trakt': {'user_key': 'trakt_user_id', 'types': ['ratings']},
        'tmdb': {'user_key': 'tmdb_user_id', 'types': ['ratings']},
    }
    
    try:
        for platform, pconfig in platforms_config.items():
            user_id = config.get(pconfig['user_key'], '')
            if not user_id:
                continue
            for ftype in pconfig['types']:
                filename = f'{platform}_{user_id}_{ftype}.csv'
                filepath = os.path.join(DATA_DIR, filename)
                if os.path.exists(filepath):
                    stat = os.stat(filepath)
                    my_files.append({
                        'filename': filename,
                        'platform': platform.upper(),
                        'type': '看过' if ftype == 'ratings' else '想看',
                        'size': stat.st_size,
                        'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    })
        
        # Check Letterboxd diary
        letterboxd_files = ['letterboxd_diary.csv']
        for filename in letterboxd_files:
            filepath = os.path.join(DATA_DIR, filename)
            if os.path.exists(filepath):
                stat = os.stat(filepath)
                my_files.append({
                    'filename': filename,
                    'platform': 'LETTERBOXD',
                    'type': '日记',
                    'size': stat.st_size,
                    'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
                
    except Exception as e:
        logger.error(f"Error listing my files: {e}")
        emit('log', {'message': f'❌ 读取平台文件列表失败: {e}', 'type': 'error'})
        return

    emit('my_files_list_data', {'files': my_files})


@socketio.on('delete_my_file')
def handle_delete_my_file(data):
    """Delete user's own platform CSV file - next fetch will do full refresh"""
    filename = data.get('filename')
    if not filename:
        emit('log', {'message': '❌ 未指定文件名', 'type': 'error'})
        return
    
    # Security check: ensure file is in DATA_DIR
    filepath = os.path.join(DATA_DIR, os.path.basename(filename))
    if not filepath.startswith(DATA_DIR):
        emit('log', {'message': '❌ 无效的文件路径', 'type': 'error'})
        return
    
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            # Clear from APP_DATA
            for key in list(APP_DATA.keys()):
                path_key = f'{key}_path' if not key.endswith('_path') else key
                if path_key in APP_DATA and filename in str(APP_DATA.get(path_key, '')):
                    base_key = key.replace('_path', '').replace('_df', '')
                    APP_DATA.pop(f'{base_key}_df', None)
                    APP_DATA.pop(f'{base_key}_path', None)
            emit('log', {'message': f'✅ 已删除 {filename}，下次获取将全量更新', 'type': 'success'})
            emit('my_file_deleted', {'filename': filename})
        except Exception as e:
            logger.error(f"Error deleting file {filename}: {e}")
            emit('log', {'message': f'❌ 删除失败: {e}', 'type': 'error'})
    else:
        emit('log', {'message': f'⚠️ 文件不存在: {filename}', 'type': 'warning'})

@socketio.on('get_backup_content')
def handle_get_backup_content(data):
    filename = data.get('filename')
    if not filename: return
    
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        emit('log', {'message': f'❌ 文件不存在: {filename}', 'type': 'error'})
        return
        
    try:
        df = pd.read_csv(file_path)
        # Standardize for display
        records = safe_df_to_records(df.head(200)) # Limit to 200 for preview
        
        emit('backup_content_data', {
            'filename': filename,
            'records': records,
            'total_count': len(df),
            'columns': list(df.columns)
        })
    except Exception as e:
        emit('log', {'message': f'❌ 读取文件失败: {e}', 'type': 'error'})

@socketio.on('delete_backup')
def handle_delete_backup(data):
    filename = data.get('filename')
    if not filename: return
    
    # Security check: only allow deleting files in DATA_DIR
    file_path = os.path.join(DATA_DIR, os.path.basename(filename))
    
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            emit('log', {'message': f'🗑️ 已删除备份: {filename}', 'type': 'success'})
            handle_get_backups_list() # Refresh list
        else:
            emit('log', {'message': f'❌ 文件不存在', 'type': 'error'})
    except Exception as e:
        emit('log', {'message': f'❌ 删除失败: {e}', 'type': 'error'})

@socketio.on('start_sync')
def handle_sync(data):
    logger.info(f"🔍 DEBUG: handle_sync called with data: {data}")
    direction = data.get('direction')
    is_dry_run = data.get('is_dry_run', False)
    logger.info(f"🔍 DEBUG: direction={direction}, is_dry_run={is_dry_run}")
    
    # Run sync in a background thread to prevent blocking Socket.IO heartbeat
    def sync_worker(direction, is_dry_run, app_data, options):
        logger.info(f"🔍 DEBUG: sync_worker thread started for {direction}")
        from web.logic import perform_sync_logic
        try:
            # Perform sync logic
            logger.info(f"🔍 DEBUG: Calling perform_sync_logic...")
            result = perform_sync_logic(direction, is_dry_run, socketio, app_data, options=options)
            logger.info(f"🔍 DEBUG: perform_sync_logic returned: {len(result) if result else 0} items")
            
            if is_dry_run:
                # Sanitize data for JSON (handle NaN, dates)
                from web.data_utils import safe_df_to_records
                # import pandas as pd # REMOVED: prevents UnboundLocalError in else block
                preview_items = safe_df_to_records(pd.DataFrame(result)) if result else []
                
                socketio.emit('sync_preview', {
                    'movies': preview_items,
                    'total': len(preview_items)
                })
                logger.info(f"🔍 DEBUG: Emitted sync_preview with {len(preview_items)} items")
            else:
                socketio.emit('finished')
                # Update merged preview
                config = read_config()
                douban_user = config.get('douban_user_id', '')
                imdb_user = config.get('imdb_user_id', '')
                douban_path = os.path.join(DATA_DIR, f'douban_{douban_user}_ratings.csv')
                imdb_path = os.path.join(DATA_DIR, f'imdb_{imdb_user}_ratings.csv')
                
                merged_output = os.path.join(DATA_DIR, f'merged_ratings_{douban_user[:8]}.csv')
                # Attempt lazy merge update
                if os.path.exists(douban_path) and os.path.exists(imdb_path):
                     from utils.merge_data import merge_movie_data
                     from web.data_utils import safe_df_to_records
                     _, _ = merge_movie_data(douban_path, imdb_path, merged_output)
                     if os.path.exists(merged_output):
                        df = pd.read_csv(merged_output)
                        socketio.emit('merged_data_preview', {'sample': safe_df_to_records(df.head()), 'total_count': len(df), 'headers': list(df.columns)})

        except Exception as e:
            logger.exception("Sync fail in thread")
            socketio.emit('log', {'message': f'同步错误: {e}', 'type': 'error'})

    import threading
    # Pass APP_DATA (copy/ref) to thread
    logger.info(f"🔍 DEBUG: Starting sync_worker thread...")
    threading.Thread(target=sync_worker, args=(direction, is_dry_run, APP_DATA, data), daemon=True).start()
    logger.info(f"🔍 DEBUG: sync_worker thread spawned")

@socketio.on('get_page')
def handle_get_page(data):
    """Handle pagination request for movie data"""
    try:
        platform = data.get('platform')
        page = data.get('page', 1)
        page_size = data.get('page_size', 20)
        
        df = APP_DATA.get(f'{platform}_df')
        if df is None or df.empty:
            emit('log', {'message': f'❌ 请先获取 {platform.upper()} 数据。', 'type': 'error'})
            return
        
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, len(df))  # Prevent index out of bounds
        page_data = df.iloc[start_idx:end_idx]
        
        emit('page_data', {
            'platform': platform,
            'sample': safe_df_to_records(page_data),
            'page': page,
            'page_size': page_size,
            'total_count': len(df),
            'total_pages': (len(df) + page_size - 1) // page_size
        })
    except Exception as e:
        logging.error(f"Pagination error for page {data.get('page')}: {e}")
        emit('log', {'message': f'❌ 翻页出错: {e}', 'type': 'error'})

@socketio.on('get_unified_library')
def handle_get_unified_library(data):
    """Get unified movie library merged across all platforms with rich metadata"""
    import math
    logger.info(f"[Unified Library] Request received: filter={data.get('platform')}, page={data.get('page')}")
    try:
        page = data.get('page', 1)
        page_size = data.get('page_size', 20)
        platform_filter = data.get('platform', 'all')
        
        # Ensure APP_DATA is hydrated when running without __main__ entrypoint
        if not APP_DATA or not any(k.endswith('_df') for k in APP_DATA.keys()):
            load_platform_data()
        
        def clean_value(val):
            """Convert NaN/None to empty string for JSON serialization"""
            if val is None:
                return ''
            if isinstance(val, float) and math.isnan(val):
                return ''
            return val
        
        def clean_date(val):
            """Clean date fields - normalize to YYYY-MM-DD format for proper sorting"""
            if val is None:
                return ''
            if isinstance(val, float):
                if math.isnan(val):
                    return ''
                return str(int(val))
            
            date_str = str(val).strip()
            if not date_str:
                return ''
            
            # Try to parse and normalize common date formats
            from datetime import datetime
            formats_to_try = [
                '%m/%d/%y',      # 12/24/25 (MM/DD/YY)
                '%m/%d/%Y',      # 12/24/2025 (MM/DD/YYYY) 
                '%Y-%m-%d',      # 2025-12-24 (ISO format - already correct)
                '%d/%m/%y',      # 24/12/25 (DD/MM/YY) - European format
                '%d/%m/%Y',      # 24/12/2025 (DD/MM/YYYY)
                '%Y/%m/%d',      # 2025/12/24
                '%d %b %Y',      # 24 Dec 2025
                '%b %d, %Y',     # Dec 24, 2025
            ]
            
            for fmt in formats_to_try:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime('%Y-%m-%d')  # Output as YYYY-MM-DD
                except ValueError:
                    continue
            
            # If no format matches, return original string
            return date_str

        def clean_id(val):
            """Clean ID fields - convert NaN/None to empty string"""
            if val is None:
                return ''
            if isinstance(val, float):
                if math.isnan(val):
                    return ''
                return str(int(val))  # Convert float IDs to int string
            return str(val) if val else ''

        # Collect all movies from all platforms
        all_movies = {}  # key -> movie data with sources
        
        def get_merge_key(movie):
            # Try to find IMDb ID - check multiple variations of the column name
            # TMDb CSV uses lowercase 'imdb_id', others use 'Const' or 'IMDb ID'
            imdb_id = (movie.get('Const') or movie.get('imdb_id') or 
                      movie.get('IMDB ID') or movie.get('IMDb ID') or 
                      movie.get('ImdbId'))  # Additional fallback
            
            if imdb_id and not (isinstance(imdb_id, float) and math.isnan(imdb_id)) and str(imdb_id).startswith('tt'):
                return str(imdb_id)
            
            # Fallback to Title + Year
            # Support 'Name' for Letterboxd, 'Title' for most platforms
            title = str(movie.get('Title') or movie.get('title') or movie.get('中文名') or movie.get('Name') or '').strip()
            year = str(movie.get('Year') or movie.get('year') or movie.get('上映年份') or '')[:4]
            return f"{title}_{year}" if title else None
        
        def add_movie(movie, platform):
            key = get_merge_key(movie)
            if not key:
                if platform == 'tmdb':
                    logger.warning(f"[TMDb] Skipped movie - no key: {movie.get('Title')}")
                return
            
            # Debug: Log TMDb key generation and matching
            if platform == 'tmdb':
                exists = key in all_movies
                logger.info(f"[TMDb] Key={key[:50]}, Exists={exists}, Title={movie.get('Title')[:30]}")
            
            # Extract platform-specific data
            # Handle ratings - normalize to 10-point scale
            raw_rating = movie.get('Your Rating') or movie.get('YourRating_douban') or movie.get('YourRating_imdb') or movie.get('rating') or movie.get('评分') or movie.get('Rating')
            
            # Normalize ratings: Douban/Letterboxd may be 5-point; if >5 assume already 10-point
            user_rating = ''
            if raw_rating is not None:
                try:
                    rating_float = float(raw_rating)
                    # Check for NaN - NaN is not valid JSON
                    if not math.isnan(rating_float):
                        if platform in ['douban', 'letterboxd']:
                            user_rating = rating_float * 2 if rating_float <= 5 else rating_float
                        else:
                            user_rating = rating_float
                except:
                    user_rating = clean_value(raw_rating)
            else:
                user_rating = ''

            # Platform ratings (public scores)
            douban_rating_val = clean_value(movie.get('Douban Rating') or movie.get('豆瓣评分') or '')
            imdb_rating_val = clean_value(movie.get('IMDb Rating') or movie.get('IMDB Rating') or '')
            tmdb_rating_val = clean_value(movie.get('vote_average') or movie.get('tmdb_rating') or '')
            # Vote counts - both platforms use 'Num Votes'
            votes = clean_value(movie.get('Num Votes') or movie.get('评价人数') or '')
            # Assign votes based on platform
            douban_votes_val = votes if platform == 'douban' else ''
            imdb_votes_val = votes if platform == 'imdb' else ''
            
            # Extract common IDs and Data first
            # TMDb CSV uses lowercase column names, others vary
            imdb_id = clean_id(movie.get('Const') or movie.get('imdb_id') or movie.get('IMDB ID') or movie.get('IMDb ID'))
            douban_id = clean_id(movie.get('douban_id') or movie.get('movie_id'))
            # TMDb: tmdb_id column, others might use TMDB ID
            tmdb_id = clean_id(movie.get('tmdb_id') or movie.get('TMDB ID') or movie.get('id'))
            trakt_id = clean_id(movie.get('trakt_id') or movie.get('Trakt ID'))
            
            if key not in all_movies:
                # Initialize movie entry
                title = movie.get('Title') or movie.get('title') or movie.get('中文名') or movie.get('Name') or ''
                original_title = movie.get('original_title') or movie.get('Original Title') or movie.get('原名') or ''
                year = movie.get('Year') or movie.get('year') or movie.get('上映年份') or ''
                
                # Priority: poster_url -> poster -> Cover URL -> Cover -> poster_path
                # NOTE: NaN is truthy in Python, so we must check each field individually
                poster = ''
                for poster_field in ['poster_url', 'poster', 'Cover URL', 'Cover', 'poster_path']:
                    raw_poster = movie.get(poster_field)
                    if raw_poster is not None and not (isinstance(raw_poster, float) and math.isnan(raw_poster)):
                        poster = clean_value(raw_poster)
                        if poster:
                            break
                
                date_rated = clean_date(movie.get('Date Rated') or movie.get('date_rated') or movie.get('标记日期') or movie.get('Watched Date') or movie.get('latest_date'))
                
                # Parse URLs
                douban_url = clean_value(movie.get('douban_url') or movie.get('url') or '')
                if not douban_url and douban_id:
                    douban_url = f"https://movie.douban.com/subject/{douban_id}/"
                # IMDB URL - only from IMDB-specific fields or when platform is imdb
                imdb_url = clean_value(movie.get('imdb_url') or '')
                if not imdb_url and platform == 'imdb':
                    imdb_url = clean_value(movie.get('URL') or '')
                if not imdb_url and imdb_id and str(imdb_id).startswith('tt'):
                    imdb_url = f"https://www.imdb.com/title/{imdb_id}/"
                letterboxd_url = clean_value(movie.get('letterboxd_url') or movie.get('Letterboxd URI') or '')
                trakt_url = clean_value(movie.get('trakt_url') or '')
                tmdb_url = ''
                if tmdb_id:
                    tmdb_url = f"https://www.themoviedb.org/movie/{tmdb_id}"

                # Extract metadata
                directors = clean_value(movie.get('Directors') or '')
                actors = clean_value(movie.get('Actors') or '')
                genres = clean_value(movie.get('Genres') or '')
                runtime = clean_value(movie.get('Runtime') or movie.get('Runtime (mins)') or '')

                all_movies[key] = {
                    'title': clean_value(title),
                    'original_title': clean_value(original_title),
                    'year': str(year)[:4] if year else '',
                    'rating': user_rating,  # User's personal rating
                    'poster_url': poster,
                    'date_rated': date_rated,
                    'imdb_id': imdb_id,
                    'douban_id': douban_id,
                    'tmdb_id': tmdb_id,
                    'trakt_id': trakt_id,
                    'douban_url': douban_url,
                    'imdb_url': imdb_url,
                    'letterboxd_url': letterboxd_url,
                    'trakt_url': trakt_url,
                    'tmdb_url': tmdb_url,
                    'sources': [platform],
                    'latest_date': date_rated,
                    # Platform-specific ratings and votes
                    'douban_rating': douban_rating_val,
                    'douban_votes': douban_votes_val,
                    'imdb_rating': imdb_rating_val,
                    'imdb_votes': imdb_votes_val,
                    'letterboxd_rating': user_rating if platform == 'letterboxd' else '',
                    'trakt_rating': user_rating if platform == 'trakt' else '',
                    'tmdb_rating': tmdb_rating_val,
                    # Metadata
                    'directors': directors,
                    'actors': actors,
                    'genres': genres,
                    'runtime': runtime,
                }
            else:
                # Update existing entry - track all sources
                if platform not in all_movies[key]['sources']:
                    all_movies[key]['sources'].append(platform)
                    if platform == 'tmdb':
                        logger.info(f"[TMDb] ADDED to sources for key={key[:50]}, sources now={all_movies[key]['sources']}")
                # Update date if newer
                new_date = clean_date(movie.get('Date Rated') or movie.get('date_rated') or movie.get('标记日期') or movie.get('Watched Date') or movie.get('latest_date'))
                # Safe comparison: both dates must be strings (clean_date returns string)
                existing_date = str(all_movies[key]['latest_date'] or '')
                if new_date and (not existing_date or str(new_date) > existing_date):
                    all_movies[key]['latest_date'] = new_date
                
                # Merge metadata if missing in existing entry
                directors = clean_value(movie.get('Directors') or '')
                actors = clean_value(movie.get('Actors') or '')
                genres = clean_value(movie.get('Genres') or '')
                runtime = clean_value(movie.get('Runtime') or movie.get('Runtime (mins)') or '')
                
                if directors and not all_movies[key].get('directors'):
                    all_movies[key]['directors'] = directors
                if actors and not all_movies[key].get('actors'):
                    all_movies[key]['actors'] = actors
                if genres and not all_movies[key].get('genres'):
                    all_movies[key]['genres'] = genres
                if runtime and not all_movies[key].get('runtime'):
                    all_movies[key]['runtime'] = runtime

                # Extract IDs for this movie from current source
                imdb_id = clean_id(movie.get('Const') or movie.get('imdb_id') or movie.get('IMDB ID') or movie.get('IMDb ID'))
                douban_id = clean_id(movie.get('douban_id') or movie.get('movie_id'))
                tmdb_id = clean_id(movie.get('tmdb_id') or movie.get('TMDB ID') or movie.get('id'))
                trakt_id = clean_id(movie.get('trakt_id') or movie.get('Trakt ID'))

                # Update Platform-Specific info if not set
                if platform == 'douban':
                    if not all_movies[key].get('douban_url'):
                        all_movies[key]['douban_url'] = movie.get('douban_url') or movie.get('url') or ''
                    if douban_rating_val:
                        all_movies[key]['douban_rating'] = douban_rating_val
                    if douban_votes_val:
                        all_movies[key]['douban_votes'] = douban_votes_val
                elif platform == 'imdb':
                    if not all_movies[key].get('imdb_url'):
                        all_movies[key]['imdb_url'] = movie.get('imdb_url') or movie.get('URL') or ''
                    if imdb_rating_val:
                        all_movies[key]['imdb_rating'] = imdb_rating_val
                    if imdb_votes_val:
                        all_movies[key]['imdb_votes'] = imdb_votes_val
                elif platform == 'letterboxd':
                    if not all_movies[key].get('letterboxd_url'):
                        all_movies[key]['letterboxd_url'] = movie.get('letterboxd_url') or movie.get('Letterboxd URI') or ''
                    all_movies[key]['letterboxd_rating'] = user_rating or all_movies[key].get('letterboxd_rating', '')
                elif platform == 'trakt':
                    if not all_movies[key].get('trakt_url'):
                        all_movies[key]['trakt_url'] = movie.get('trakt_url') or ''
                    all_movies[key]['trakt_rating'] = user_rating or all_movies[key].get('trakt_rating', '')
                elif platform == 'tmdb':
                    if not all_movies[key].get('tmdb_url'):
                        if tmdb_id:
                            all_movies[key]['tmdb_url'] = f"https://www.themoviedb.org/movie/{tmdb_id}"
                        else:
                            all_movies[key]['tmdb_url'] = movie.get('URL') or ''
                    all_movies[key]['tmdb_rating'] = tmdb_rating_val or all_movies[key].get('tmdb_rating', '')
                    
                # Merge poster if missing in existing
                if not all_movies[key].get('poster_url'):
                    for poster_field in ['poster_url', 'poster', 'Cover URL', 'Cover', 'poster_path']:
                        raw_poster = movie.get(poster_field)
                        if raw_poster is not None and not (isinstance(raw_poster, float) and math.isnan(raw_poster)):
                            new_poster = clean_value(raw_poster)
                            if new_poster:
                                all_movies[key]['poster_url'] = new_poster
                                break
        
        # Process each platform's data (including TMDB)
        platforms_with_data = []
        all_platforms = ['douban', 'imdb', 'trakt', 'letterboxd', 'tmdb']
        
        for platform in all_platforms:
            # Fix: Ensure key matches fetch logic (tmdb_gawaint_ratings.csv -> tmdb_df)
            df_key = f'{platform}_df'
            df = APP_DATA.get(df_key)
            
            # Debug log to verify data sources
            logger.info(f"[Unified Library] Processing {platform}: {len(df) if df is not None and not df.empty else 0} records")
            
            if df is not None and not df.empty:
                platforms_with_data.append(platform)
                records = df.to_dict('records')
                for movie in records:
                    add_movie(movie, platform)
        
        # Convert to list and sort
        movies_list = list(all_movies.values())
        
        # Fix: Ensure date comparison handles mixed types (str/float/None)
        def safe_date_key(movie):
            date_val = movie.get('latest_date') or ''
            # Convert to string, handling NaN floats
            if isinstance(date_val, float):
                if math.isnan(date_val):
                    return ''
                return str(date_val)
            return str(date_val)
        
        movies_list.sort(key=safe_date_key, reverse=True)
        
        # Debug: Log source distribution
        from collections import Counter
        source_counts = Counter(len(m['sources']) for m in movies_list)
        logger.info(f"[Unified Library] Source distribution: {dict(source_counts)}")
        logger.info(f"[Unified Library] Sample movie sources: {[m['sources'] for m in movies_list[:5]]}")
        
        # Apply platform filter
        required_platforms = {'douban', 'imdb', 'trakt', 'letterboxd', 'tmdb'}
        
        if platform_filter == 'all':
            # Strict 5-platform intersection: Source set must contain ALL 5 platforms
            # Using set comparison to be absolutely sure
            movies_list = [
                m for m in movies_list 
                if set(m['sources']) >= required_platforms
            ]
        else:
            # Specific platform: 
            # 1. Must contain the requested platform
            # 2. Must NOT be a perfect 5-platform match (those go to Shared)
            movies_list = [
                m for m in movies_list 
                if platform_filter in m['sources'] 
                and not (set(m['sources']) >= required_platforms)
            ]
        
        total_count = len(movies_list)
        
        # Calculate platform counts
        all_temp = list(all_movies.values())
        platform_counts = {}
        for platform in all_platforms:
            df = APP_DATA.get(f'{platform}_df')
            if df is not None:
                # Count ALL movies that have this platform (not just exclusive)
                platform_counts[platform] = len([m for m in all_temp if platform in m['sources']])
        # Shared = movies with ALL 5 platforms
        shared_movies = [m for m in all_temp if set(m['sources']) >= required_platforms]
        logger.info(f"[SocketIO DEBUG] required_platforms={required_platforms}")
        logger.info(f"[SocketIO DEBUG] Sample sources: {[m['sources'] for m in all_temp[:5]]}")
        logger.info(f"[SocketIO DEBUG] Shared count={len(shared_movies)}, Sample: {[m.get('title') for m in shared_movies[:3]]}")
        platform_counts['shared'] = len(shared_movies)
        
        # Paginate
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_movies = movies_list[start_idx:end_idx]
        
        logger.info(f"[Unified Library] Sending response: filter={platform_filter}, movies={len(page_movies)}, total={total_count}")
        
        emit('unified_library', {
            'movies': page_movies,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size if total_count > 0 else 0,
            'platform_counts': platform_counts,
            'platforms_with_data': platforms_with_data,
            'filter': platform_filter
        })
        
    except Exception as e:
        logger.exception("Unified Library error")
        emit('log', {'message': f'❌ 获取统一库出错: {str(e)}', 'type': 'error'})
        
        # Convert to list and sort by latest date (newest first)
        movies_list = list(all_movies.values())
        movies_list.sort(key=lambda x: x.get('latest_date') or '', reverse=True)
        
        # Apply platform filter
        # "all" = show SHARED movies (exist on 2+ platforms)
        # specific platform = show EXCLUSIVE movies (only exist on that platform)
        if platform_filter == 'all':
            # Show movies that exist on multiple platforms (shared)
            movies_list = [m for m in movies_list if len(m['sources']) >= 2]
        else:
            # Show exclusive movies for specific platform
            movies_list = [m for m in movies_list if 
                          platform_filter in m['sources'] and len(m['sources']) == 1]
        
        # Calculate stats
        # 'all' count = shared movies (on 2+ platforms)
        # platform count = exclusive movies (only on that platform)
        shared_count = len([m for m in all_movies.values() if len(m['sources']) >= 2])
        total_count = len(movies_list)
        
        platform_counts = {}
        for platform in all_platforms:
            # Count exclusive movies (only exist on this platform)
            platform_counts[platform] = len([m for m in all_movies.values() 
                                            if platform in m['sources'] and len(m['sources']) == 1])
        
        # Paginate
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_movies = movies_list[start_idx:end_idx]
        
        logger.info(f"[Unified Library] Sending response: filter={platform_filter}, movies={len(page_movies)}, total={total_count}")
        response_data = {
            'movies': page_movies,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size if total_count > 0 else 0,
            'platform_counts': platform_counts,
            'platforms_with_data': platforms_with_data,
            'filter': platform_filter
        }
        emit('unified_library', response_data)  # For backward compatibility
        return response_data  # For callback-based response
        
    except Exception as e:
        logger.exception("Unified library error")
        emit('log', {'message': f'❌ 获取统一库失败: {e}', 'type': 'error'})
        return None


@socketio.on('upload_letterboxd_csv')
def handle_letterboxd_upload(data):
    """Handle Letterboxd diary.csv file upload and parsing"""
    import io
    import base64
    import threading
    import time
    import pandas as pd # Ensure pandas is imported
    import os # Ensure os is imported
    
    try:
        csv_content = data.get('content', '')
        filename = data.get('filename', 'diary.csv')
        
        if not csv_content:
            emit('log', {'message': '❌ 未接收到文件内容', 'type': 'error'})
            return
        
        # Ensure APP_DATA is hydrated for local matching
        if not APP_DATA or not any(k.endswith('_df') for k in APP_DATA.keys()):
            load_platform_data()
        
        emit('log', {'message': f'📥 正在解析 {filename}...', 'type': 'info'})
        
        # Parse CSV content
        df = pd.read_csv(io.StringIO(csv_content))
        
        # Map Letterboxd columns to standard format
        # Letterboxd diary.csv: Date, Name, Year, Letterboxd URI, Rating, Rewatch, Tags, Watched Date
        column_mapping = {
            'Name': 'Title',
            'Year': 'Year',
            'Letterboxd URI': 'URL',
            'Rating': 'Rating_letterboxd',
            'Watched Date': 'Date Rated',
            'Rewatch': 'Rewatch',
            'Tags': 'Tags',
            'Date': 'Entry Date'
        }
        
        # Rename columns that exist
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df = df.rename(columns={old_col: new_col})
        
        # Convert Letterboxd rating (0.5-5) to 10-point scale
        if 'Rating_letterboxd' in df.columns:
            def convert_rating(r):
                try:
                    rating = float(r)
                    return int(rating * 2)  # 0.5-5 -> 1-10
                except:
                    return None
            df['Your Rating'] = df['Rating_letterboxd'].apply(convert_rating)
        
        # Calculate stats
        total_count = len(df)
        rated_count = df['Your Rating'].notna().sum() if 'Your Rating' in df.columns else 0
        
        # 后台获取IMDb ID
        def fetch_imdb_ids_background():
            try:
                from adapters.utils.letterboxd_mapper import get_mapper
                import concurrent.futures
                
                # Make sure cached platform data is loaded for local matching
                if not APP_DATA or not any(k.endswith('_df') for k in APP_DATA.keys()):
                    load_platform_data()
                
                # 检查是否需要获取IMDb ID
                uri_column = 'URL' if 'URL' in df.columns else 'Letterboxd URI'
                needs_fetch = uri_column in df.columns and ('IMDb ID' not in df.columns or df['IMDb ID'].isna().any())
                
                if needs_fetch:
                    socketio.emit('log', {'message': f'🔍 正在通过 Letterboxd URI 直接抓取 IMDb/TMDB... (共{total_count}条)', 'type': 'info'})
                    
                    mapper = get_mapper()
                    
                    # 添加IMDb ID列
                    if 'IMDb ID' not in df.columns:
                        df['IMDb ID'] = None
                    if 'TMDB ID' not in df.columns:
                        df['TMDB ID'] = None
                    
                    # 先用缓存命中，减少重复抓取
                    cache_hits = 0
                    for idx, row in df[df['IMDb ID'].isna() & df[uri_column].notna()].iterrows():
                        try:
                            raw_uri = str(row[uri_column]).strip()
                            cached = mapper.mapping.get(raw_uri)
                            if not cached:
                                norm_uri = mapper._normalize_uri(raw_uri, resolve_shortlink=False)
                                cached = mapper.mapping.get(norm_uri)
                            if cached and cached.get('imdb_id'):
                                df.at[idx, 'IMDb ID'] = cached.get('imdb_id')
                                if cached.get('tmdb_id'):
                                    df.at[idx, 'TMDB ID'] = cached.get('tmdb_id')
                                cache_hits += 1
                        except Exception:
                            continue
                    if cache_hits:
                        socketio.emit('log', {'message': f'⚡️ 缓存命中: {cache_hits} 条，无需抓取', 'type': 'success'})
                    
                    # 仅对剩余缺失项做 URI 抓取
                    success_count = 0
                    processed = 0
                    missing_indices = df[df['IMDb ID'].isna() & df[uri_column].notna()].index.tolist()
                    total_missing = len(missing_indices)
                    save_path = os.path.join(DATA_DIR, 'letterboxd_diary.csv')
                    title_matches = 0
                    
                    # 阶段2: 利用 TMDB/Douban 数据通过 Title+Year 匹配
                    if total_missing > 0:
                        title_year_index = {}
                        external_index_count = 0
                        # 从 TMDB 构建索引
                        tmdb_df = APP_DATA.get('tmdb_df')
                        if tmdb_df is not None and 'imdb_id' in tmdb_df.columns:
                            for _, row in tmdb_df.iterrows():
                                title = str(row.get('Title', '')).strip()
                                year = str(row.get('Year', ''))[:4]
                                imdb_id = row.get('imdb_id')
                                tmdb_id = row.get('tmdb_id') or row.get('TMDB ID')
                                if title and imdb_id and str(imdb_id).startswith('tt'):
                                    key = f"{title}|{year}".lower()
                                    title_year_index[key] = {
                                        'imdb_id': str(imdb_id),
                                        'tmdb_id': str(tmdb_id) if tmdb_id else ''
                                    }
                        # 从 Douban 构建索引
                        douban_df = APP_DATA.get('douban_df')
                        if douban_df is not None:
                            const_col = 'Const' if 'Const' in douban_df.columns else 'imdb_id'
                            if const_col in douban_df.columns:
                                for _, row in douban_df.iterrows():
                                    title = str(row.get('Title', '')).strip()
                                    year = str(row.get('Year', ''))[:4]
                                imdb_id = row.get(const_col)
                                if title and imdb_id and str(imdb_id).startswith('tt'):
                                    key = f"{title}|{year}".lower()
                                    if key not in title_year_index:
                                        title_year_index[key] = {
                                            'imdb_id': str(imdb_id),
                                            'tmdb_id': ''
                                        }

                        # 从 Letterboxd 外部缓存构建索引 (Title|:|Year|:|...)
                        for cache_key, cache_value in mapper.mapping.items():
                            if '|:|' not in cache_key:
                                continue
                            parts = [p.strip() for p in cache_key.split('|:|')]
                            if len(parts) < 2:
                                continue
                            title, year = parts[0], parts[1]
                            if not title or not year:
                                continue
                            if not isinstance(cache_value, dict):
                                continue
                            imdb_id = cache_value.get('imdb_id')
                            tmdb_id = cache_value.get('tmdb_id')
                            if not imdb_id or not str(imdb_id).startswith('tt'):
                                continue
                            key = f"{title}|{year}".lower()
                            if key not in title_year_index:
                                title_year_index[key] = {
                                    'imdb_id': str(imdb_id),
                                    'tmdb_id': str(tmdb_id) if tmdb_id else ''
                                }
                                external_index_count += 1
                        
                        socketio.emit('log', {
                            'message': f'📚 已构建 Title+Year 索引: {len(title_year_index)} 条 (外部缓存 +{external_index_count})',
                            'type': 'info'
                        })
                        
                        # 匹配 Letterboxd 条目
                        title_col = 'Name' if 'Name' in df.columns else 'Title'
                        matched_indices = []
                        for idx in missing_indices:
                            title = str(df.at[idx, title_col] if title_col in df.columns else '').strip()
                            year = str(df.at[idx, 'Year'])[:4] if pd.notna(df.at[idx, 'Year']) else ''
                            key = f"{title}|{year}".lower()
                            hit = title_year_index.get(key)
                            if hit:
                                df.at[idx, 'IMDb ID'] = hit.get('imdb_id') if isinstance(hit, dict) else hit
                                if isinstance(hit, dict) and hit.get('tmdb_id'):
                                    df.at[idx, 'TMDB ID'] = hit.get('tmdb_id')
                                matched_indices.append(idx)
                                title_matches += 1
                        
                        # 更新 missing_indices
                        for idx in matched_indices:
                            missing_indices.remove(idx)
                        
                        if title_matches:
                            socketio.emit('log', {'message': f'🎯 Title+Year 匹配成功: {title_matches} 条', 'type': 'success'})
                        
                        total_missing = len(missing_indices)
                    
                    socketio.emit('log', {
                        'message': f'🧭 匹配汇总: 缓存命中 {cache_hits} 条，Title+Year 匹配 {title_matches} 条，需 API 抓取 {total_missing} 条',
                        'type': 'info'
                    })
                    socketio.emit('log', {'message': f'🛰️ 开始纯 URI 抓取: {total_missing} 条', 'type': 'info'})
                    if total_missing == 0:
                        df.to_csv(save_path, index=False)
                        mapper.save()
                        socketio.emit('log', {'message': '✅ 无需抓取，所有条目均已匹配', 'type': 'success'})
                        socketio.emit('letterboxd_imdb_complete', {
                            'success_count': df['IMDb ID'].notna().sum(),
                            'total_count': total_count
                        })
                        return
                    
                    # 使用并发加速纯 URI 抓取
                    import concurrent.futures
                    def fetch_one(idx):
                        uri = df.at[idx, uri_column]
                        if pd.isna(uri) or not uri:
                            return idx, {}
                        ids = mapper.get_platform_ids(str(uri))
                        return idx, ids

                    success_count = 0
                    processed = 0
                    log_step = 25
                    start_time = time.time()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                        futures = {executor.submit(fetch_one, idx): idx for idx in missing_indices}
                        next_log = log_step
                        for future in concurrent.futures.as_completed(futures):
                            try:
                                idx, ids = future.result()
                            except Exception as e:
                                socketio.emit('log', {'message': f'❌ 抓取异常: {e}', 'type': 'error'})
                                continue
                            if ids.get('imdb_id'):
                                df.at[idx, 'IMDb ID'] = ids['imdb_id']
                                success_count += 1
                            if ids.get('tmdb_id'):
                                df.at[idx, 'TMDB ID'] = ids['tmdb_id']
                            processed += 1
                            while processed >= next_log:
                                elapsed = max(time.time() - start_time, 0.001)
                                rate = processed / elapsed
                                remaining = max(total_missing - processed, 0)
                                eta_sec = int(remaining / rate) if rate > 0 else 0
                                eta_str = f"~{eta_sec}s" if eta_sec < 60 else f"~{eta_sec // 60}m {eta_sec % 60}s"
                                socketio.emit('log', {
                                    'message': f'⏳ URI 抓取进度: {processed}/{total_missing} (成功 {success_count}, ETA {eta_str})',
                                    'type': 'info'
                                })
                                next_log += log_step
                            if processed % 200 == 0:
                                df.to_csv(save_path, index=False)
                                mapper.save()
                        # 处理总数不是25的倍数时的尾部进度
                        if processed and processed != total_missing:
                            elapsed = max(time.time() - start_time, 0.001)
                            rate = processed / elapsed
                            remaining = max(total_missing - processed, 0)
                            eta_sec = int(remaining / rate) if rate > 0 else 0
                            eta_str = f"~{eta_sec}s" if eta_sec < 60 else f"~{eta_sec // 60}m {eta_sec % 60}s"
                            socketio.emit('log', {
                                'message': f'⏳ URI 抓取进度: {processed}/{total_missing} (成功 {success_count}, ETA {eta_str})',
                                'type': 'info'
                            })
                    
                    socketio.emit('log', {'message': f'✅ URI 抓取完成: 成功 {success_count}/{total_missing}', 'type': 'success'})
                    mapper.save()
                    
                    # 报告未匹配的样本，便于诊断
                    remaining = [idx for idx in missing_indices if pd.isna(df.at[idx, 'IMDb ID'])]
                    if remaining:
                        sample = []
                        for idx in remaining[:5]:
                            title = df.at[idx, 'Title'] if 'Title' in df.columns else df.at[idx, 'Name']
                            year = df.at[idx, 'Year'] if 'Year' in df.columns else ''
                            uri = df.at[idx, uri_column]
                            sample.append(f"{title} ({year}) -> {uri}")
                        socketio.emit('log', {
                            'message': f'⚠️ 仍有 {len(remaining)} 条未找到 IMDb ID，例如: ' + '; '.join(sample),
                            'type': 'warning'
                        })

                    # 最终保存
                    save_path = os.path.join(DATA_DIR, 'letterboxd_diary.csv')
                    df.to_csv(save_path, index=False)
                    
                    # 更新APP_DATA
                    APP_DATA['letterboxd_df'] = df
                    APP_DATA['letterboxd_csv_path'] = save_path
                    
                    total_success = df['IMDb ID'].notna().sum()
                    
                    socketio.emit('log', {
                        'message': f'✅ 处理完成！总成功: {total_success}/{total_count}',
                        'type': 'success'
                    })
                    
                    # 通知前端刷新
                    socketio.emit('letterboxd_imdb_complete', {
                        'success_count': int(total_success),
                        'total_count': int(total_count)
                    })
                
            except Exception as e:
                logger.exception("Error fetching IMDb IDs")
                socketio.emit('log', {'message': f'❌ 处理过程出错: {e}', 'type': 'error'})
        
        # 先立即保存到磁盘（避免刷新丢失）
        
        # 先立即保存到磁盘（避免刷新丢失）
        save_path = os.path.join(DATA_DIR, 'letterboxd_diary.csv')
        df.to_csv(save_path, index=False)
        
        # Store in APP_DATA
        APP_DATA['letterboxd_df'] = df
        APP_DATA['letterboxd_csv_path'] = save_path
        
        # Prepare display columns
        display_columns = ['Title', 'Year', 'Your Rating', 'Date Rated', 'URL']
        cols_to_keep = [col for col in display_columns if col in df.columns]
        
        page_size = 10
        emit('letterboxd_upload_complete', {
            'platform': 'letterboxd',
            'sample': safe_df_to_records(df[cols_to_keep].head(page_size)),
            'total_count': total_count,
            'rated_count': int(rated_count),
            'headers': cols_to_keep,
            'page': 1,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size
        })
        
        emit('log', {'message': f'✅ Letterboxd 数据导入成功！共 {total_count} 部电影，{rated_count} 部已评分', 'type': 'success'})
        
        # 启动后台线程获取IMDb ID
        thread = threading.Thread(target=fetch_imdb_ids_background, daemon=True)
        thread.start()
        
    except Exception as e:
        logger.exception("Letterboxd CSV parse error")
        emit('log', {'message': f'❌ 解析 Letterboxd CSV 失败: {e}', 'type': 'error'})


@socketio.on('upload_letterboxd_watchlist')
def handle_letterboxd_watchlist_upload(data):
    """Handle Letterboxd watchlist CSV upload and save as wishlist"""
    import io
    import pandas as pd
    import os

    try:
        csv_content = data.get('content', '')
        filename = data.get('filename', 'watchlist.csv')

        if not csv_content:
            emit('log', {'message': '❌ 未接收到文件内容', 'type': 'error'})
            return

        emit('log', {'message': f'📥 正在解析 {filename}...', 'type': 'info'})

        df = pd.read_csv(io.StringIO(csv_content))
        df = normalize_df_columns(df)

        column_mapping = {
            'Name': 'Title',
            'Year': 'Year',
            'Letterboxd URI': 'URL'
        }
        for old_col, new_col in column_mapping.items():
            if old_col in df.columns:
                df = df.rename(columns={old_col: new_col})

        if 'status' not in df.columns:
            df['status'] = 'wish'
        if 'type' not in df.columns:
            df['type'] = 'movie'

        # Enrich IMDb/TMDB IDs if missing
        try:
            from adapters.utils.letterboxd_mapper import get_mapper
            mapper = get_mapper()
            if 'IMDb ID' not in df.columns:
                df['IMDb ID'] = None
            if 'TMDB ID' not in df.columns:
                df['TMDB ID'] = None

            url_col = 'URL' if 'URL' in df.columns else None
            if url_col:
                missing_indices = df[df['IMDb ID'].isna() & df[url_col].notna()].index.tolist()
                total_missing = len(missing_indices)
                if total_missing:
                    emit('log', {'message': f'🔍 正在补充 IMDb/TMDB ID (共{total_missing}条)...', 'type': 'info'})
                for idx, row in enumerate(missing_indices, start=1):
                    ids = mapper.get_platform_ids(str(df.at[row, url_col]).strip()) or {}
                    if ids.get('imdb_id'):
                        df.at[row, 'IMDb ID'] = ids.get('imdb_id')
                    if ids.get('tmdb_id'):
                        df.at[row, 'TMDB ID'] = ids.get('tmdb_id')
                    if idx % 20 == 0:
                        emit('log', {'message': f'... 已处理 {idx}/{total_missing}', 'type': 'info'})
        except Exception:
            pass

        df = filter_wish_df(df)
        df = ensure_type_column(df)

        save_path = os.path.join(DATA_DIR, 'letterboxd_watchlist.csv')
        df.to_csv(save_path, index=False, encoding='utf-8-sig')

        APP_DATA['letterboxd_wish_df'] = df
        APP_DATA['letterboxd_wish_path'] = save_path
        try:
            APP_DATA['letterboxd_wish_mtime'] = os.path.getmtime(save_path)
        except Exception:
            APP_DATA['letterboxd_wish_mtime'] = None

        emit('log', {'message': f'✅ Letterboxd 想看导入成功: {len(df)} 部', 'type': 'success'})
        emit('fetch_wish_complete', {
            'platform': 'letterboxd',
            'count': len(df),
            'path': save_path,
            'sample': safe_df_to_records(df.head(5)) if not df.empty else []
        })
    except Exception as e:
        logger.exception("Letterboxd watchlist CSV parse error")
        emit('log', {'message': f'❌ 解析 Letterboxd 想看失败: {e}', 'type': 'error'})

# ==========================================
# Trakt OAuth Device Flow Handlers
# ==========================================

@socketio.on('trakt_start_auth')
def handle_trakt_start_auth(data):
    """Start Trakt OAuth device flow"""
    # Real CineRecord Trakt API credentials from user's Trakt account
    DEFAULT_TRAKT_CLIENT_ID = "b2505cf6da8f8c8678dac8ecfc43d1a780952c49a658b89a231e7dc567d28b35"
    DEFAULT_TRAKT_CLIENT_SECRET = "33e4fc63d53e483fe988008d1f546efb291299a9ddd079f7e2ebe52965fdf128"
    
    client_id = data.get('client_id', '') or DEFAULT_TRAKT_CLIENT_ID
    client_secret = data.get('client_secret', '') or DEFAULT_TRAKT_CLIENT_SECRET
    
    emit('log', {'message': '🔐 正在启动 Trakt 授权流程...', 'type': 'info'})

    
    try:
        client = TraktClient(client_id, client_secret)
        result = client.start_device_auth()
        
        if result:
            # Store device_code temporarily for polling
            APP_DATA['trakt_device_code'] = result['device_code']
            APP_DATA['trakt_auth_interval'] = result['interval']
            APP_DATA['trakt_client_id'] = client_id
            APP_DATA['trakt_client_secret'] = client_secret
            
            emit('trakt_auth_started', {
                'user_code': result['user_code'],
                'verification_url': result['verification_url'],
                'expires_in': result['expires_in'],
                'interval': result['interval']
            })
            emit('log', {'message': f'📱 请访问 {result["verification_url"]} 并输入代码: {result["user_code"]}', 'type': 'info'})
        else:
            emit('log', {'message': '❌ 无法启动 Trakt 授权，请检查 Client ID', 'type': 'error'})
            
    except Exception as e:
        logger.exception("Trakt auth start error")
        emit('log', {'message': f'❌ Trakt 授权启动失败: {e}', 'type': 'error'})

@socketio.on('trakt_poll_auth')
def handle_trakt_poll_auth(data):
    """Poll for Trakt OAuth device authorization completion"""
    device_code = APP_DATA.get('trakt_device_code')
    client_id = APP_DATA.get('trakt_client_id')
    client_secret = APP_DATA.get('trakt_client_secret')
    
    if not device_code or not client_id:
        emit('trakt_auth_result', {'status': 'error', 'message': 'No active authorization'})
        return
    
    try:
        client = TraktClient(client_id, client_secret)
        result = client.poll_device_auth(device_code)
        
        if result['status'] == 'success':
            # Save tokens to config
            config = read_config()
            config['trakt_client_id'] = client_id
            config['trakt_client_secret'] = client_secret
            config['trakt_access_token'] = result['access_token']
            config['trakt_refresh_token'] = result['refresh_token']
            config['trakt_token_expires'] = result['token_expires']
            write_config(config)
            
            # Clean up temporary data
            APP_DATA.pop('trakt_device_code', None)
            APP_DATA.pop('trakt_auth_interval', None)
            
            # Get user profile
            client.access_token = result['access_token']
            profile = client.get_user_profile()
            stats = client.get_user_stats('me')
            
            if profile:
                config['trakt_user_id'] = profile.get('ids', {}).get('slug') or profile.get('username')
                config['trakt_display_name'] = profile.get('name') or profile.get('username')
                config['trakt_avatar'] = profile.get('images', {}).get('avatar', {}).get('full', '')
                if stats:
                    config['trakt_movies_watched'] = stats.get('movies', {}).get('watched', 0)
                    config['trakt_movies_rated'] = stats.get('movies', {}).get('ratings', 0)
                write_config(config)
            
            emit('trakt_auth_result', {
                'status': 'success',
                'profile': {
                    'user_id': profile.get('ids', {}).get('slug') if profile else None,
                    'username': profile.get('username') if profile else None,
                    'display_name': profile.get('name') if profile else None,
                    'avatar': profile.get('images', {}).get('avatar', {}).get('full') if profile else None,
                    'movies_watched': stats.get('movies', {}).get('watched') if stats else 0,
                    'movies_rated': stats.get('movies', {}).get('ratings') if stats else 0,
                    'profile_link': f"https://trakt.tv/users/{profile.get('ids', {}).get('slug')}" if profile else None
                }
            })
            emit('log', {'message': '✅ Trakt 授权成功！', 'type': 'success'})
            
        elif result['status'] == 'pending':
            emit('trakt_auth_result', {'status': 'pending'})
            
        elif result['status'] == 'slow_down':
            emit('trakt_auth_result', {'status': 'slow_down'})
            
        else:
            # For 'error' status with 'No response from server', treat as transient - keep polling
            if result.get('status') == 'error' and 'No response' in result.get('message', ''):
                # Transient network error - don't stop polling, just log to console
                logger.warning(f"Trakt poll transient error: {result.get('message')}")
                emit('trakt_auth_result', {'status': 'pending'})  # Keep polling
            else:
                emit('trakt_auth_result', result)
                if result.get('message'):
                    emit('log', {'message': f'❌ {result["message"]}', 'type': 'error'})
                
    except Exception as e:
        logger.exception("Trakt poll auth error")
        emit('trakt_auth_result', {'status': 'error', 'message': str(e)})

@socketio.on('trakt_test_connection')
def handle_trakt_test_connection(data):
    """Test Trakt connection with stored credentials"""
    config = read_config()
    client_id = config.get('trakt_client_id', '')
    client_secret = config.get('trakt_client_secret', '')
    access_token = config.get('trakt_access_token', '')
    refresh_token = config.get('trakt_refresh_token', '')
    
    if not client_id or not access_token:
        emit('trakt_test_result', {'success': False, 'error': 'No credentials configured'})
        emit('log', {'message': '❌ 请先授权 Trakt 账号', 'type': 'error'})
        return
    
    try:
        client = TraktClient(client_id, client_secret, access_token, refresh_token)
        
        # Try to refresh token if expired
        if client.is_token_expired():
            if client.refresh_access_token():
                config['trakt_access_token'] = client.access_token
                config['trakt_refresh_token'] = client.refresh_token
                config['trakt_token_expires'] = client.token_expires.isoformat()
                write_config(config)
        
        profile = client.get_user_profile()
        stats = client.get_user_stats('me')
        
        if profile:
            # Handle stats being None to prevent AttributeError
            movies_watched = 0
            movies_rated = 0
            if stats:
                movies_watched = stats.get('movies', {}).get('watched', 0) or 0
                movies_rated = stats.get('movies', {}).get('ratings', 0) or 0
            
            emit('trakt_test_result', {
                'success': True,
                'profile': {
                    'user_id': profile.get('ids', {}).get('slug'),
                    'username': profile.get('username'),
                    'display_name': profile.get('name'),
                    'avatar': profile.get('images', {}).get('avatar', {}).get('full'),
                    'movies_watched': movies_watched,
                    'movies_rated': movies_rated,
                    'profile_link': f"https://trakt.tv/users/{profile.get('ids', {}).get('slug')}"
                }
            })
            emit('log', {'message': f'✅ Trakt 连接成功！{movies_watched} 部已观看', 'type': 'success'})
        else:
            emit('trakt_test_result', {'success': False, 'error': 'Failed to get profile'})
            # emit('log', {'message': '❌ Trakt 连接失败', 'type': 'error'})
            
    except Exception as e:
        logger.exception("Trakt test connection error")
        emit('trakt_test_result', {'success': False, 'error': str(e)})
        # emit('log', {'message': f'❌ Trakt 测试失败: {e}', 'type': 'error'})

@socketio.on('fetch_trakt_data')
def handle_fetch_trakt_data(data):
    """Fetch Trakt movie ratings"""
    config = read_config()
    client_id = config.get('trakt_client_id', '')
    client_secret = config.get('trakt_client_secret', '')
    access_token = config.get('trakt_access_token', '')
    refresh_token = config.get('trakt_refresh_token', '')
    
    if not client_id or not access_token:
        emit('log', {'message': '❌ 请先授权 Trakt 账号', 'type': 'error'})
        return
    
    emit('log', {'message': '📥 正在获取 Trakt 数据...', 'type': 'info'})
    
    def fetch_data():
        try:
            client = TraktClient(client_id, client_secret, access_token, refresh_token)
            
            # Refresh token if needed
            if client.is_token_expired():
                if client.refresh_access_token():
                    config['trakt_access_token'] = client.access_token
                    config['trakt_refresh_token'] = client.refresh_token
                    write_config(config)
            
            # Check for existing cached data
            trakt_user_id = config.get('trakt_user_id', 'unknown')
            trakt_csv_path = os.path.join(DATA_DIR, f'trakt_{trakt_user_id}_ratings.csv')
            existing_df = None
            last_fetch = config.get('trakt_last_fetch')
            
            if os.path.exists(trakt_csv_path) and last_fetch:
                try:
                    existing_df = pd.read_csv(trakt_csv_path)
                    socketio.emit('log', {'message': f'📂 已有缓存数据: {len(existing_df)} 部电影', 'type': 'info'})
                except:
                    pass
            
            # Fetch all watched movies with ratings
            socketio.emit('log', {'message': '📥 正在从 Trakt 获取数据...', 'type': 'info'})
            movies = client.get_all_movies_with_ratings()
            
            if movies:
                new_df = pd.DataFrame(movies)
                
                # If incremental, identify new items (Trakt uses 'imdb_id' not 'Const')
                if existing_df is not None and last_fetch:
                    id_col = 'imdb_id' if 'imdb_id' in new_df.columns else 'Const'
                    added_ids = set()
                    if id_col in existing_df.columns and id_col in new_df.columns:
                        existing_ids = set(existing_df[id_col].dropna().tolist())
                        new_ids = set(new_df[id_col].dropna().tolist())
                        added_ids = new_ids - existing_ids
                    
                    if added_ids:
                        socketio.emit('log', {'message': f'📊 发现 {len(added_ids)} 部新电影', 'type': 'info'})
                    else:
                        socketio.emit('log', {'message': '✅ 数据已是最新', 'type': 'success'})
                
                df = new_df
                APP_DATA['trakt_df'] = df
                
                # Save to disk
                df.to_csv(trakt_csv_path, index=False)
                APP_DATA['trakt_csv_path'] = trakt_csv_path
                
                # Extract and store latest record timestamp for incremental sync
                latest_ts = None
                date_col = 'Date Rated'
                if date_col in df.columns:
                    try:
                        dates = pd.to_datetime(df[date_col], errors='coerce')
                        valid_dates = dates.dropna()
                        if not valid_dates.empty:
                            latest_ts = valid_dates.max().isoformat()
                    except Exception as e:
                        logger.warning(f"Failed to parse Trakt dates: {e}")
                
                # Update config with latest fetch time and record timestamp
                config['trakt_last_fetch'] = datetime.now(timezone.utc).isoformat()
                if latest_ts:
                    config['trakt_latest_record_ts'] = latest_ts
                    socketio.emit('log', {'message': f'📅 Trakt 最新记录时间: {latest_ts[:10]}', 'type': 'info'})
                write_config(config)
                
                logger.info(f"Saved Trakt data to {trakt_csv_path}")
                
                page_size = 10
                socketio.emit('fetch_complete', {
                    'platform': 'trakt',
                    'sample': safe_df_to_records(df.head(page_size)),
                    'total_count': len(df),
                    'headers': ['Title', 'Year', 'Your Rating', 'Date Rated'],
                    'page': 1,
                    'page_size': page_size,
                    'total_pages': (len(df) + page_size - 1) // page_size,
                    'latest_record_ts': latest_ts
                })
                # Count how many have ratings
                rated_count = df['Your Rating'].notna().sum()
                socketio.emit('log', {'message': f'✅ Trakt 数据获取完成: {len(df)} 部电影 ({rated_count} 部已评分)', 'type': 'success'})
            else:
                socketio.emit('log', {'message': '⚠️ 未在 Trakt 上找到观影数据', 'type': 'info'})
                
        except Exception as e:
            logger.exception("Trakt fetch error")
            socketio.emit('log', {'message': f'❌ Trakt 数据获取失败: {e}', 'type': 'error'})
    
    import threading
    threading.Thread(target=fetch_data).start()

@socketio.on('trakt_logout')
def handle_trakt_logout(data):
    """Clear Trakt credentials from config"""
    config = read_config()
    
    # Remove Trakt keys
    keys_to_remove = ['trakt_client_id', 'trakt_client_secret', 'trakt_access_token', 
                      'trakt_refresh_token', 'trakt_token_expires', 'trakt_user_id']
    for key in keys_to_remove:
        config.pop(key, None)
    
    write_config(config)
    
    # Clear from APP_DATA
    APP_DATA.pop('trakt_device_code', None)
    APP_DATA.pop('trakt_auth_interval', None)
    APP_DATA.pop('trakt_client_id', None)
    APP_DATA.pop('trakt_client_secret', None)
    APP_DATA.pop('trakt_df', None)
    
    emit('log', {'message': '🚪 已退出 Trakt', 'type': 'info'})

@socketio.on('platform_logout')
def handle_platform_logout(data):
    """Clear platform credentials from config (Douban/IMDB)"""
    platform = data.get('platform')
    if platform not in ['douban', 'imdb']:
        emit('log', {'message': f'❌ 无效的平台: {platform}', 'type': 'error'})
        return
    
    config = read_config()
    
    # Remove platform-specific keys
    keys_to_remove = [f'{platform}_user_id', f'{platform}_cookie']
    for key in keys_to_remove:
        config.pop(key, None)
    
    write_config(config)
    
    # Clear from APP_DATA
    APP_DATA.pop(f'{platform}_df', None)
    APP_DATA.pop(f'{platform}_csv_path', None)
    
    emit('log', {'message': f'🚪 已退出 {platform.upper()}', 'type': 'info'})
    emit('logout_complete', {'platform': platform})

# ==========================================
# Cross-Platform Sync Handlers
# ==========================================

@socketio.on('sync_imdb_to_trakt')
def handle_sync_imdb_to_trakt(data):
    """Sync IMDB ratings to Trakt (target-first incremental - based on Trakt's latest record time)"""
    config = read_config()
    
    # Check Trakt auth
    client_id = config.get('trakt_client_id', '')
    client_secret = config.get('trakt_client_secret', '')
    access_token = config.get('trakt_access_token', '')
    refresh_token = config.get('trakt_refresh_token', '')
    
    if not client_id or not access_token:
        emit('log', {'message': '❌ 请先授权 Trakt 账号', 'type': 'error'})
        return
    
    # Check IMDB data
    imdb_df = APP_DATA.get('imdb_df')
    if imdb_df is None or imdb_df.empty:
        emit('log', {'message': '❌ 请先获取 IMDB 数据', 'type': 'error'})
        return
    
    is_dry_run = data.get('is_dry_run', False)
    
    emit('log', {'message': '🔄 开始同步 IMDB → Trakt...', 'type': 'info'})
    
    def do_sync():
        try:
            from datetime import datetime, timezone
            
            client = TraktClient(client_id, client_secret, access_token, refresh_token)
            
            # Refresh token if needed
            if client.is_token_expired():
                if client.refresh_access_token():
                    config['trakt_access_token'] = client.access_token
                    config['trakt_refresh_token'] = client.refresh_token
                    write_config(config)
            
            # ========== NEW: Target-first incremental logic ==========
            # Step 1: Fetch Trakt data to find latest record time
            socketio.emit('log', {'message': '📥 正在获取 Trakt 数据以确定增量点...', 'type': 'info'})
            trakt_movies = client.get_all_movies_with_ratings()
            
            target_latest_ts = None
            if trakt_movies:
                trakt_df = pd.DataFrame(trakt_movies)
                APP_DATA['trakt_df'] = trakt_df
                
                # Find latest record time from Trakt
                date_col = 'Date Rated'
                if date_col in trakt_df.columns:
                    try:
                        dates = pd.to_datetime(trakt_df[date_col], errors='coerce')
                        valid_dates = dates.dropna()
                        if not valid_dates.empty:
                            target_latest_ts = valid_dates.max()
                            config['trakt_latest_record_ts'] = target_latest_ts.isoformat()
                            write_config(config)
                            socketio.emit('log', {'message': f'📅 Trakt 最新记录: {target_latest_ts.strftime("%Y-%m-%d")}', 'type': 'info'})
                    except Exception as e:
                        logger.warning(f"Failed to parse Trakt dates: {e}")
            else:
                socketio.emit('log', {'message': '📊 Trakt 暂无数据，将全量同步', 'type': 'info'})
            
            # Step 2: Filter IMDB movies newer than Trakt's latest record
            imdb_movies = imdb_df.to_dict('records')
            total_movies = len(imdb_movies)
            
            if target_latest_ts:
                filtered_movies = []
                for movie in imdb_movies:
                    movie_date = movie.get('Date Rated')
                    if movie_date:
                        try:
                            if 'T' in str(movie_date):
                                movie_dt = datetime.fromisoformat(str(movie_date).replace('Z', '+00:00'))
                            else:
                                movie_dt = datetime.strptime(str(movie_date)[:10], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                            
                            # Compare with target's latest record (use timezone-aware comparison)
                            target_dt = target_latest_ts.replace(tzinfo=timezone.utc) if target_latest_ts.tzinfo is None else target_latest_ts
                            
                            # Robustness: Look back 1 day to handle same-day updates and timezone differences
                            threshold_dt = target_dt - timedelta(days=1)
                            if movie_dt >= threshold_dt:
                                filtered_movies.append(movie)
                        except Exception:
                            # If date parsing fails, include to be safe
                            filtered_movies.append(movie)
                    else:
                        filtered_movies.append(movie)
                
                socketio.emit('log', {
                    'message': f'📊 增量筛选: {len(filtered_movies)}/{total_movies} 部新电影需要同步',
                    'type': 'info'
                })
                imdb_movies = filtered_movies
            else:
                socketio.emit('log', {'message': f'📊 全量同步: {total_movies} 部电影', 'type': 'info'})
            
            if not imdb_movies:
                socketio.emit('log', {'message': '✅ 没有新电影需要同步', 'type': 'success'})
                return
            
            if is_dry_run:
                socketio.emit('log', {
                    'message': f'👀 预览模式: 将同步 {len(imdb_movies)} 部电影',
                    'type': 'info'
                })
                socketio.emit('sync_preview_complete', {
                    'source': 'imdb',
                    'target': 'trakt',
                    'count': len(imdb_movies),
                    'movies': imdb_movies[:100]
                })
                return
            
            socketio.emit('log', {'message': f'📊 正在同步 {len(imdb_movies)} 部电影...', 'type': 'info'})
            
            result = client.sync_from_imdb(imdb_movies)
            
            socketio.emit('log', {
                'message': f'✅ IMDB → Trakt 同步完成: {result["history_added"]} 部新增, {result["ratings_added"]} 个评分',
                'type': 'success'
            })
            socketio.emit('sync_complete', {'source': 'imdb', 'target': 'trakt', 'result': result})
            
        except Exception as e:
            logger.exception("IMDB to Trakt sync error")
            socketio.emit('log', {'message': f'❌ 同步失败: {e}', 'type': 'error'})
    
    import threading
    threading.Thread(target=do_sync).start()

@socketio.on('sync_trakt_to_douban')
def handle_sync_trakt_to_douban(data):
    """Sync Trakt watched movies to Douban (target-first incremental - based on Douban's latest record time)"""
    logger.info(f"[SYNC_TRAKT_DOUBAN] Received sync_trakt_to_douban event with data: {data}")
    config = read_config()
    
    # Check Douban auth
    douban_cookie = config.get('douban_cookie', '')
    douban_user_id = config.get('douban_user_id', '')
    
    if not douban_cookie:
        emit('log', {'message': '❌ 请先登录豆瓣账号', 'type': 'error'})
        return
    
    # Check Trakt data
    trakt_df = APP_DATA.get('trakt_df')
    if trakt_df is None or (hasattr(trakt_df, 'empty') and trakt_df.empty):
        emit('log', {'message': '❌ 请先获取 Trakt 数据', 'type': 'error'})
        return
    
    with_ratings = data.get('with_ratings', True)
    is_dry_run = data.get('is_dry_run', False)
    
    emit('log', {'message': '🔄 开始同步 Trakt → 豆瓣...', 'type': 'info'})
    
    def do_sync():
        try:
            from datetime import datetime, timezone, timedelta
            
            # ========== NEW: Target-first incremental logic ==========
            # Step 1: Try to get Douban's latest record timestamp
            target_latest_ts = None
            douban_ts = config.get('douban_latest_record_ts')
            
            if douban_ts:
                try:
                    target_latest_ts = pd.to_datetime(douban_ts)
                    socketio.emit('log', {'message': f'📅 豆瓣最新记录: {target_latest_ts.strftime("%Y-%m-%d")}', 'type': 'info'})
                except Exception as e:
                    logger.warning(f"Failed to parse Douban latest timestamp: {e}")
            else:
                socketio.emit('log', {'message': '📊 豆瓣无时间戳记录，将全量同步', 'type': 'info'})
            
            # Step 2: Filter Trakt movies newer than Douban's latest record
            trakt_movies = trakt_df.to_dict('records')
            total_movies = len(trakt_movies)
            
            if target_latest_ts:
                filtered_movies = []
                for movie in trakt_movies:
                    movie_date = movie.get('Date Rated') or movie.get('Watched At')
                    if movie_date:
                        try:
                            if 'T' in str(movie_date):
                                movie_dt = datetime.fromisoformat(str(movie_date).replace('Z', '+00:00'))
                            else:
                                movie_dt = datetime.strptime(str(movie_date)[:10], '%Y-%m-%d').replace(tzinfo=timezone.utc)
                            
                            # Compare with target's latest record
                            target_dt = target_latest_ts.replace(tzinfo=timezone.utc) if target_latest_ts.tzinfo is None else target_latest_ts
                            
                            # Robustness: Look back 1 day to handle same-day updates and timezone differences
                            threshold_dt = target_dt - timedelta(days=1)

                            # DEBUG: Log comparison for recent movies (helps debug sync issues)
                            time_diff = (datetime.now(timezone.utc) - movie_dt).days if movie_dt.tzinfo else 999
                            if time_diff < 7: # Only log items from last week
                                log_msg = f"DEBUG_SYNC: '{movie.get('Title')}' Date={movie_dt} Threshold={threshold_dt} Pass={movie_dt >= threshold_dt}"
                                logger.info(log_msg)
                                socketio.emit('log', {'message': log_msg, 'type': 'warning'})

                            if movie_dt >= threshold_dt:
                                filtered_movies.append(movie)
                        except Exception as e:
                            logger.error(f"DEBUG_SYNC conversion error for {movie.get('Title')}: {e}")
                            filtered_movies.append(movie)
                    else:
                        # logger.info(f"DEBUG_SYNC: No date for '{movie.get('Title')}', including")
                        filtered_movies.append(movie)
                
                socketio.emit('log', {
                    'message': f'📊 增量筛选: {len(filtered_movies)}/{total_movies} 部新电影需要同步',
                    'type': 'info'
                })
                trakt_movies = filtered_movies
            else:
                socketio.emit('log', {'message': f'📊 全量同步: {total_movies} 部电影', 'type': 'info'})
            
            # ========== Step 3: Deduplicate against existing Douban records ==========
            douban_df = APP_DATA.get('douban_df')
            if douban_df is not None and not douban_df.empty:
                # Build set of existing IMDb IDs in Douban
                existing_imdb_ids = set()
                if 'Const' in douban_df.columns:
                    existing_imdb_ids = set(douban_df['Const'].dropna().astype(str).str.strip())
                
                # Filter out movies already in Douban
                pre_dedup_count = len(trakt_movies)
                trakt_movies = [
                    m for m in trakt_movies 
                    if str(m.get('IMDb ID', '')).strip() not in existing_imdb_ids
                ]
                deduped_count = pre_dedup_count - len(trakt_movies)
                if deduped_count > 0:
                    socketio.emit('log', {
                        'message': f'🔍 去重: 过滤掉 {deduped_count} 部已在豆瓣的电影',
                        'type': 'info'
                    })
            
            if not trakt_movies:
                socketio.emit('log', {'message': '✅ 没有新电影需要同步', 'type': 'success'})
                return
            
            if is_dry_run:
                logger.info(f"[SYNC_PREVIEW] Preview mode: {len(trakt_movies)} movies to sync")
                socketio.emit('log', {
                    'message': f'👀 预览模式: 将同步 {len(trakt_movies)} 部电影',
                    'type': 'info'
                })
                preview_data = {
                    'source': 'trakt',
                    'target': 'douban',
                    'count': len(trakt_movies),
                    # Use safe serialization to prevent NaN/datetime issues
                    'movies': [{k: (None if v != v else (str(v) if hasattr(v, 'isoformat') else v)) for k, v in movie.items()} for movie in trakt_movies[:100]]
                }
                logger.info(f"[SYNC_PREVIEW] Emitting sync_preview_complete with {len(preview_data['movies'])} movies")
                socketio.emit('sync_preview_complete', preview_data)
                return
            
            result = sync_trakt_to_douban(
                trakt_movies=trakt_movies,
                douban_cookie=douban_cookie,
                douban_user_id=douban_user_id,
                with_ratings=with_ratings,
                socketio=socketio
            )
            
            # Prepare detailed report
            success_list = []
            failed_list = []
            skipped_list = []
            
            # Process details if available, otherwise just use counts (fallback)
            details = result.get('details', [])
            if not details and result.get('synced', 0) > 0:
                # If no details returned but count > 0, we can't show detailed list
                pass 
                
            for item in details:
                status = item.get('status')
                # Map item fields for frontend report
                report_item = {
                    'title': item.get('title', 'Unknown'),
                    'year': item.get('year', ''),
                    'source_url': f"https://www.imdb.com/title/{item.get('imdb_id')}/" if item.get('imdb_id') else '',
                    'target_url': f"https://movie.douban.com/subject/{item.get('douban_id')}/" if item.get('douban_id') else '',
                    'source_rating': item.get('rating', '-'),
                }
                
                if status == 'synced':
                    success_list.append(report_item)
                elif status == 'failed':
                    report_item['error_msg'] = item.get('reason', 'Unknown error')
                    failed_list.append(report_item)
                elif status in ('already_watched', 'filtered'):
                    report_item['reason'] = item.get('reason', 'Skipped')
                    skipped_list.append(report_item)
            
            # Emit detailed report event (matching frontend 'sync_results_data')
            report_data = {
                'source': 'trakt',
                'target': 'douban',
                'summary': {
                    'success': len(success_list),
                    'failed': len(failed_list),
                    'skipped': len(skipped_list)
                },
                'results': {
                    'success': success_list,
                    'failed': failed_list,
                    'skipped': skipped_list
                }
            }
            logger.info(f"[SYNC_REPORT] Emitting sync_results_data: {report_data['summary']}")
            socketio.emit('sync_results_data', report_data)
            
            # Update local CSV with synced movies
            synced_items = [item for item in result.get('details', []) if item.get('status') == 'synced']
            if synced_items:
                try:
                    import datetime
                    csv_path = os.path.join(DATA_DIR, f'douban_{douban_user_id}_ratings.csv')
                    
                    new_rows = []
                    today = datetime.datetime.now().strftime('%Y-%m-%d')
                    
                    for item in synced_items:
                        # Construct record matching Douban CSV format
                        new_rows.append({
                            'Const': item.get('imdb_id', ''),
                            'Your Rating': item.get('rating') or 0,
                            'Date Rated': today,
                            'Title': item.get('title', ''),
                            'Directors': '',  # Metadata not available from simple sync
                            'Actors': '',
                            'Country': '',
                            'Year': item.get('year', ''),
                            'Genres': '',
                            'Douban Rating': 0,
                            'Num Votes': 0,
                            'MyComment': '',
                            'URL': f"https://movie.douban.com/subject/{item.get('douban_id')}/",
                            'Cover URL': '',
                            'douban_id': item.get('douban_id', '')
                        })
                    
                    if new_rows:
                        # Load existing
                        if os.path.exists(csv_path):
                            existing_df = pd.read_csv(csv_path, dtype=str)
                        else:
                            existing_df = pd.DataFrame(columns=['Const', 'Your Rating', 'Date Rated', 'Title', 'Directors', 'Actors', 'Country', 'Year', 'Genres', 'Douban Rating', 'Num Votes', 'MyComment', 'URL', 'Cover URL', 'douban_id'])
                        
                        # Concat
                        new_df = pd.DataFrame(new_rows)
                        combined_df = pd.concat([new_df, existing_df], ignore_index=True)
                        
                        # Dedup by douban_id
                        combined_df.drop_duplicates(subset=['douban_id'], keep='first', inplace=True)
                        
                        # Save
                        combined_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
                        
                        # Update memory cache
                        APP_DATA['douban_df'] = combined_df
                        socketio.emit('log', {'message': f'💾 已更新本地数据: 新增 {len(new_rows)} 条记录', 'type': 'success'})
                        
                except Exception as e:
                    logger.error(f"Failed to update local CSV: {e}")
                    socketio.emit('log', {'message': f'⚠️ 本地数据更新失败: {e}', 'type': 'warning'})
            
            socketio.emit('sync_complete', {'source': 'trakt', 'target': 'douban', 'result': result})
            
        except Exception as e:
            logger.exception("Trakt to Douban sync error")
            socketio.emit('log', {'message': f'❌ 同步失败: {e}', 'type': 'error'})
    
    import threading
    threading.Thread(target=do_sync).start()


@socketio.on('sync_imdb_to_tmdb')
def handle_sync_imdb_to_tmdb(data):
    """Sync IMDB ratings to TMDB"""
    config = read_config()
    
    # Check TMDB auth (needs both API key and session)
    api_key = config.get('tmdb_api_key', '')
    session_id = config.get('tmdb_session_id', '')
    
    if not api_key:
        emit('log', {'message': '❌ 请先配置 TMDB API Key', 'type': 'error'})
        return
    
    if not session_id:
        emit('log', {'message': '❌ 请先完成 TMDB 用户授权', 'type': 'error'})
        return
    
    # Check IMDB data
    imdb_df = APP_DATA.get('imdb_df')
    if imdb_df is None or imdb_df.empty:
        emit('log', {'message': '❌ 请先获取 IMDB 数据', 'type': 'error'})
        return
    
    is_dry_run = data.get('is_dry_run', False)
    
    emit('log', {'message': '🔄 开始同步 IMDB → TMDB...', 'type': 'info'})
    
    def do_sync():
        try:
            client = TMDBClient(api_key, session_id)
            
            # Convert DataFrame to list of dicts
            imdb_movies = imdb_df.to_dict('records')
            total_movies = len(imdb_movies)
            
            if is_dry_run:
                # Preview mode
                socketio.emit('log', {
                    'message': f'👀 预览模式: 将同步 {total_movies} 部电影',
                    'type': 'info'
                })
                socketio.emit('sync_preview_complete', {
                    'source': 'imdb',
                    'target': 'tmdb',
                    'count': total_movies,
                    'movies': imdb_movies[:100]
                })
                return
            
            socketio.emit('log', {'message': f'📊 正在同步 {total_movies} 部电影...', 'type': 'info'})
            
            synced = 0
            failed = 0
            skipped = 0
            
            for i, movie in enumerate(imdb_movies):
                imdb_id = movie.get('Const', movie.get('imdb_id', ''))
                rating = movie.get('Your Rating', movie.get('rating'))
                title = movie.get('Title', movie.get('title', ''))
                
                if not imdb_id:
                    skipped += 1
                    continue
                
                # Find TMDB ID by IMDB ID (find_by_imdb_id returns movie object directly)
                tmdb_movie = client.find_by_imdb_id(imdb_id)
                if tmdb_movie:
                    tmdb_id = tmdb_movie.get('id')
                    
                    # Rate the movie (TMDB uses 0.5-10 scale)
                    if rating:
                        try:
                            tmdb_rating = float(rating)
                            if client.rate_movie(tmdb_id, tmdb_rating):
                                synced += 1
                                if synced % 10 == 0:
                                    socketio.emit('log', {
                                        'message': f'📊 进度: {synced}/{total_movies} ({title})',
                                        'type': 'info'
                                    })
                            else:
                                failed += 1
                        except:
                            failed += 1
                    else:
                        skipped += 1
                else:
                    failed += 1
                
                # Rate limiting
                time.sleep(0.25)  # TMDB allows 40 requests per 10 seconds
            
            socketio.emit('log', {
                'message': f'✅ IMDB → TMDB 同步完成: {synced} 成功, {failed} 失败, {skipped} 跳过',
                'type': 'success'
            })
            socketio.emit('sync_complete', {
                'source': 'imdb',
                'target': 'tmdb',
                'result': {'synced': synced, 'failed': failed, 'skipped': skipped}
            })
            
        except Exception as e:
            logger.exception("IMDB to TMDB sync error")
            socketio.emit('log', {'message': f'❌ 同步失败: {e}', 'type': 'error'})
    
    import threading
    threading.Thread(target=do_sync).start()


@socketio.on('sync_trakt_to_tmdb')
def handle_sync_trakt_to_tmdb(data):
    """Sync Trakt ratings to TMDB"""
    logger.info(f"🔍 DEBUG: handle_sync_trakt_to_tmdb called with data: {data}")
    config = read_config()
    
    # Check TMDB auth
    api_key = config.get('tmdb_api_key', '')
    session_id = config.get('tmdb_session_id', '')
    
    if not api_key:
        emit('log', {'message': '❌ 请先配置 TMDB API Key', 'type': 'error'})
        return
    
    if not session_id:
        emit('log', {'message': '❌ 请先完成 TMDB 用户授权', 'type': 'error'})
        return
    
    # Check Trakt data
    trakt_df = APP_DATA.get('trakt_df')
    if trakt_df is None or trakt_df.empty:
        emit('log', {'message': '❌ 请先获取 Trakt 数据', 'type': 'error'})
        return
    
    is_dry_run = data.get('is_dry_run', False)
    
    emit('log', {'message': '🔄 开始同步 Trakt → TMDB...', 'type': 'info'})
    
    def do_sync():
        logger.info(f"🔍 DEBUG: do_sync thread started for trakt->tmdb")
        try:
            # Use unified diff logic to filter movies
            from web.logic import get_unified_diff, SocketLogger
            socket_logger = SocketLogger(socketio)
            
            movies_to_sync = get_unified_diff('trakt', 'tmdb', socket_logger, APP_DATA)
            
            if not movies_to_sync:
                socketio.emit('log', {'message': '✅ 无需同步，所有数据已一致', 'type': 'success'})
                return
            
            if is_dry_run:
                socketio.emit('log', {
                    'message': f'👀 预览模式: 将同步 {len(movies_to_sync)} 部电影',
                    'type': 'info'
                })
                socketio.emit('sync_preview_complete', {
                    'source': 'trakt',
                    'target': 'tmdb',
                    'count': len(movies_to_sync),
                    'movies': safe_df_to_records(pd.DataFrame(movies_to_sync).head(100))
                })
                return
            
            client = TMDBClient(api_key, session_id)
            
            socketio.emit('log', {'message': f'📊 正在同步 {len(movies_to_sync)} 部电影...', 'type': 'info'})
            
            synced = 0
            failed = 0
            skipped = 0
            
            for i, item in enumerate(movies_to_sync):
                tmdb_id = item.get('target_linking_id')
                rating = item.get('source_rating')
                title = item.get('Title', '')
                
                if not tmdb_id:
                    failed += 1
                    continue
                
                if rating:
                    try:
                        tmdb_rating = float(rating)
                        if client.rate_movie(int(tmdb_id), tmdb_rating):
                            synced += 1
                            if synced % 10 == 0:
                                socketio.emit('log', {
                                    'message': f'📊 进度: {synced}/{len(movies_to_sync)} ({title})',
                                    'type': 'info'
                                })
                        else:
                            failed += 1
                    except:
                        failed += 1
                else:
                    skipped += 1
                
                time.sleep(0.25)
            
            socketio.emit('log', {
                'message': f'✅ Trakt → TMDB 同步完成: {synced} 成功, {failed} 失败, {skipped} 跳过',
                'type': 'success'
            })
            socketio.emit('sync_complete', {
                'source': 'trakt',
                'target': 'tmdb',
                'result': {'synced': synced, 'failed': failed, 'skipped': skipped}
            })
            
        except Exception as e:
            logger.exception("Trakt to TMDB sync error")
            socketio.emit('log', {'message': f'❌ 同步失败: {e}', 'type': 'error'})
    
    import threading
    logger.info(f"🔍 DEBUG: Starting sync_trakt_to_tmdb thread...")
    threading.Thread(target=do_sync, daemon=True).start()
    logger.info(f"🔍 DEBUG: sync_trakt_to_tmdb thread spawned")

@socketio.on('trakt_incremental_fetch')
def handle_trakt_incremental_fetch(data):
    """Fetch only new Trakt data since last sync"""
    config = read_config()
    
    client_id = config.get('trakt_client_id', '')
    client_secret = config.get('trakt_client_secret', '')
    access_token = config.get('trakt_access_token', '')
    refresh_token = config.get('trakt_refresh_token', '')
    
    if not client_id or not access_token:
        emit('log', {'message': '❌ 请先授权 Trakt 账号', 'type': 'error'})
        return
    
    last_sync = config.get('trakt_last_sync')
    
    emit('log', {'message': f'📥 增量获取 Trakt 数据 (自 {last_sync or "首次"})...', 'type': 'info'})
    
    def do_fetch():
        try:
            client = TraktClient(client_id, client_secret, access_token, refresh_token)
            
            # Refresh token if needed
            if client.is_token_expired():
                if client.refresh_access_token():
                    config['trakt_access_token'] = client.access_token
                    config['trakt_refresh_token'] = client.refresh_token
                    write_config(config)
            
            # Fetch incremental data
            from datetime import datetime, timezone
            new_movies = client.get_incremental_watched(since_date=last_sync)
            
            if new_movies:
                # Merge with existing data
                existing_df = APP_DATA.get('trakt_df')
                if existing_df is not None and not existing_df.empty:
                    import pandas as pd
                    new_df = pd.DataFrame(new_movies)
                    # Merge, avoiding duplicates by Trakt ID
                    combined = pd.concat([existing_df, new_df]).drop_duplicates(subset=['Trakt ID'], keep='last')
                    APP_DATA['trakt_df'] = combined
                    total = len(combined)
                else:
                    APP_DATA['trakt_df'] = pd.DataFrame(new_movies)
                    total = len(new_movies)
                
                socketio.emit('log', {
                    'message': f'✅ 增量获取完成: {len(new_movies)} 部新电影, 共 {total} 部',
                    'type': 'success'
                })
            else:
                socketio.emit('log', {'message': '✅ 无新数据', 'type': 'info'})
            
            # Update last sync time
            config['trakt_last_sync'] = datetime.now(timezone.utc).isoformat()
            write_config(config)
            
        except Exception as e:
            logger.exception("Trakt incremental fetch error")
            socketio.emit('log', {'message': f'❌ 获取失败: {e}', 'type': 'error'})
    
    import threading
    threading.Thread(target=do_fetch).start()


@socketio.on('get_config')
def handle_get_config(data=None):
    emit('config_loaded', read_config())

@socketio.on('clear_sync_timestamp')
def handle_clear_sync_timestamp(data):
    """Clear a sync/platform timestamp to force full re-sync or re-fetch"""
    sync_key = data.get('key')
    
    # Valid keys: old sync timestamps + new platform record timestamps
    valid_keys = [
        'imdb_to_trakt_last_sync', 'trakt_to_douban_last_sync',  # Old keys (deprecated)
        'douban_latest_record_ts', 'imdb_latest_record_ts', 'trakt_latest_record_ts',  # New platform timestamps
        'tmdb_latest_record_ts'  # TMDB support
    ]
    
    if sync_key in valid_keys:
        config = read_config()
        if sync_key in config:
            del config[sync_key]
            write_config(config)
            
            # Generate user-friendly message
            platform_name = sync_key.replace('_latest_record_ts', '').upper().replace('_TO_', ' → ')
            emit('log', {'message': f'✅ 已清除 {platform_name} 时间戳，下次将执行全量操作', 'type': 'success'})
            emit('sync_timestamp_cleared', {'key': sync_key})
        else:
            emit('log', {'message': f'ℹ️ {sync_key} 未设置', 'type': 'info'})
    else:
        emit('log', {'message': f'❌ 无效的时间戳键: {sync_key}', 'type': 'error'})


@socketio.on('save_config')
def handle_save_config(data):
    if write_config(data): emit('log', {'message': '✅ 配置已保存。', 'type': 'success'})
    else: emit('log', {'message': '❌ 保存失败。', 'type': 'error'})

@socketio.on('test_connection')
def handle_test_connection(data):
    """Test connection with stored cookie and fetch profile if successful"""
    import requests
    import re
    
    platform = data.get('platform')
    cookie = data.get('cookie', '')
    
    if not cookie:
        emit('test_result', {'platform': platform, 'success': False, 'error': 'No cookie provided'})
        return
    
    headers = {'Cookie': cookie, 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
    profile = {'user_id': None, 'display_name': None, 'avatar': None}
    
    try:
        if platform == 'douban':
            # Test by accessing user page
            resp = requests.get('https://www.douban.com/mine/', headers=headers, timeout=10, allow_redirects=True)
            m = re.search(r'/people/([^/\?"]+)', resp.url)
            if m:
                user_id = m.group(1)
                profile['user_id'] = user_id
                profile['display_name'] = user_id
                
                # Fetch full profile
                profile_resp = requests.get(f'https://www.douban.com/people/{user_id}/', headers=headers, timeout=10)
                if profile_resp.status_code == 200:
                    html = profile_resp.text
                    m = re.search(r'<title>([^<]+?)的首页', html)
                    if m: profile['display_name'] = m.group(1).strip()
                    # Try multiple avatar patterns
                    m = re.search(r'<img[^>]*src="(https?://img\d?.doubanio.com/icon/[^"]+)"[^>]*class="avatar"', html)
                    if not m:
                        m = re.search(r'<img[^>]*class="avatar"[^>]*src="([^"]+)"', html)
                    if not m:
                        m = re.search(r'src="(https?://img\d?.doubanio.com/icon/[^"]+)"', html)
                    if m: profile['avatar'] = m.group(1)
                    # Find join date (look for "加入" pattern)
                    m = re.search(r'(\d{4}-\d{2}-\d{2})\s*加入', html)
                    if m: profile['join_date'] = m.group(1)
                
                # Fetch movie stats
                movie_resp = requests.get(f'https://movie.douban.com/people/{user_id}/', headers=headers, timeout=10)
                if movie_resp.status_code == 200:
                    movie_html = movie_resp.text
                    m = re.search(r'/collect[^>]*>(\d+)', movie_html)
                    if m: profile['watched'] = int(m.group(1))
                    m = re.search(r'/wish[^>]*>(\d+)', movie_html)
                    if m: profile['wish'] = int(m.group(1))
                    m = re.search(r'/do[^>]*>(\d+)', movie_html)
                    if m: profile['doing'] = int(m.group(1))
                    # Set stat links
                    profile['watched_link'] = f'https://movie.douban.com/people/{user_id}/collect'
                    profile['wish_link'] = f'https://movie.douban.com/people/{user_id}/wish'
                    profile['doing_link'] = f'https://movie.douban.com/people/{user_id}/do'
                    profile['profile_link'] = f'https://movie.douban.com/people/{user_id}/'
                
                emit('test_result', {'platform': platform, 'success': True, 'profile': profile})
                emit('log', {'message': f'✅ {platform.upper()} 连接成功！', 'type': 'success'})
                return
                
        elif platform == 'imdb':
            # First try to get user ID from IMDB home page
            home_resp = requests.get('https://www.imdb.com/', headers=headers, timeout=10)
            user_id = None
            if home_resp.status_code == 200:
                # Look for user profile link or user ID patterns in page
                patterns = [
                    r'href="/user/(ur\d+)"',
                    r'/user/(ur\d+)',
                    r'"userId":"(ur\d+)"',
                ]
                for pattern in patterns:
                    m = re.search(pattern, home_resp.text)
                    if m:
                        user_id = m.group(1)
                        break
            
            if user_id:
                profile['user_id'] = user_id
                profile['profile_link'] = f'https://www.imdb.com/user/{user_id}/'
                
                # Fetch user profile page for display name, avatar, and join date
                try:
                    user_page = requests.get(f'https://www.imdb.com/user/{user_id}/', headers=headers, timeout=10)
                    if user_page.status_code == 200:
                        html = user_page.text
                        # Extract display name
                        m = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
                        if m:
                            profile['display_name'] = m.group(1).strip()
                        
                        # Extract avatar - IMDB uses class="ipc-image" in a media container
                        # Pattern from actual HTML: <img... class="ipc-image"... src="...">
                        avatar_patterns = [
                            r'<img[^>]*alt="[^"]*profile[^"]*"[^>]*src="([^"]+)"',  # alt contains "profile"
                            r'<img[^>]*class="ipc-image"[^>]*src="(https://m\.media-amazon\.com/images/[^"]+)"',  # ipc-image class
                            r'srcset="(https://m\.media-amazon\.com/images/[^"]+)\s+\d+w',  # srcset first image
                        ]
                        for pattern in avatar_patterns:
                            m = re.search(pattern, html, re.IGNORECASE)
                            if m:
                                profile['avatar'] = m.group(1)
                                break
                        
                        # If no avatar found, leave as None - using SVG placeholder in HTML is better
                        # Don't set a potentially broken URL
                        
                        # Extract join date - IMDB uses "Joined Month Year" format
                        # Pattern: >Joined Aug 2017</div>
                        join_patterns = [
                            r'>Joined\s+(\w+\s+\d{4})<',  # "Joined Aug 2017"
                            r'Joined\s+(\w+\s+\d{4})',  # Fallback without tags
                            r'Member\s*-\s*(\d+\s*years?)',  # "Member - 8 years"
                        ]
                        for pattern in join_patterns:
                            m = re.search(pattern, html, re.IGNORECASE)
                            if m:
                                profile['join_date'] = m.group(1).strip()
                                break
                        
                        # Try to get ratings count from profile
                        m = re.search(r'(\d+)\s*Ratings', html)
                        if m:
                            profile['watched'] = int(m.group(1))
                            profile['ratings'] = int(m.group(1))
                except Exception as e:
                    logging.error(f"IMDB profile page error: {e}")
                
                # Fallback: get rating count from GraphQL API
                if 'watched' not in profile:
                    api_url = "https://api.graphql.imdb.com/"
                    payload = {
                        "operationName": "userRatings",
                        "variables": {"first": 1, "after": None},
                        "extensions": {"persistedQuery": {"version": 1, "sha256Hash": "ebf2387fd2ba45d62fc54ed2ffe3940086af52e700a1b3929a099d5fce23330a"}}
                    }
                    api_resp = requests.post(api_url, json=payload, headers=headers, timeout=10)
                    if api_resp.status_code == 200:
                        data = api_resp.json()
                        total = data.get('data', {}).get('userRatings', {}).get('total', 0)
                        profile['watched'] = total
                        profile['ratings'] = total
                
                # Fetch IMDB watchlist count
                try:
                    watchlist_url = f'https://www.imdb.com/user/{user_id}/watchlist/'
                    watchlist_resp = requests.get(watchlist_url, headers=headers, timeout=10)
                    if watchlist_resp.status_code == 200:
                        # Look for watchlist count pattern
                        m = re.search(r'(\d+)\s*titles?', watchlist_resp.text, re.IGNORECASE)
                        if m:
                            profile['watchlist'] = int(m.group(1))
                except Exception as e:
                    logging.error(f"IMDB watchlist fetch error: {e}")
                
                emit('test_result', {'platform': platform, 'success': True, 'profile': profile})
                total_str = f"共 {profile.get('watched', 0)} 条评分" if 'watched' in profile else ""
                emit('log', {'message': f'✅ {platform.upper()} 连接成功！{total_str}', 'type': 'success'})
                return
                    
        emit('test_result', {'platform': platform, 'success': False, 'error': 'Invalid cookie or not logged in'})
        emit('log', {'message': f'❌ {platform.upper()} Cookie 无效或已过期', 'type': 'error'})
        
    except Exception as e:
        logging.error(f"Test connection error: {e}")
        emit('test_result', {'platform': platform, 'success': False, 'error': str(e)})
        emit('log', {'message': f'❌ {platform.upper()} 连接测试失败: {e}', 'type': 'error'})

@socketio.on('browser_login')
def handle_browser_login(data):
    """Open system browser with auth bridge page for OAuth-style login"""
    import webbrowser
    import secrets
    import subprocess
    
    logger.info(f"Received browser_login event: {data}")
    
    platform = data.get('platform')
    if platform not in ['douban', 'imdb']:
        emit('log', {'message': '❌ 无效的平台', 'type': 'error'})
        logger.warning(f"Invalid platform: {platform}")
        return
    
    # Generate auth token for security
    token = secrets.token_urlsafe(16)
    AUTH_SESSIONS[token] = {
        'platform': platform,
        'created': time.time()
    }
    
    # Build auth bridge URL
    auth_url = f"http://127.0.0.1:8000/auth/bridge?platform={platform}&token={token}&callback=http://127.0.0.1:8000"
    
    # Try to open browser with multiple methods
    browser_opened = False
    
    # Method 1: Use subprocess on macOS (more reliable)
    if sys.platform == 'darwin':
        try:
            subprocess.Popen(['open', auth_url])
            browser_opened = True
            logger.info(f"Opened browser via 'open' command for {platform}")
        except Exception as e:
            logger.warning(f"Failed to open browser via 'open': {e}")
    
    # Method 2: Fallback to webbrowser module
    if not browser_opened:
        try:
            browser_opened = webbrowser.open(auth_url)
            if browser_opened:
                logger.info(f"Opened browser via webbrowser module for {platform}")
        except Exception as e:
            logger.warning(f"Failed to open browser via webbrowser: {e}")
    
    # Always emit the auth URL so user can click it manually if needed
    logger.info(f"Emitting browser_auth_url event: platform={platform}, opened={browser_opened}, url={auth_url[:50]}...")
    emit('browser_auth_url', {
        'platform': platform,
        'url': auth_url,
        'opened': browser_opened
    })
    logger.info("browser_auth_url event emitted successfully")
    
    if browser_opened:
        emit('log', {'message': f'🌐 已在浏览器中打开授权页面', 'type': 'success'})
    else:
        emit('log', {'message': f'⚠️ 无法自动打开浏览器，请手动点击链接', 'type': 'warning'})

@socketio.on('login_popup')
def handle_login_popup(json_data):
    platform = json_data.get('platform')
    
    def get_username_from_cookie(plat, cookie_str):
        """Extract username by making HTTP request with cookie"""
        if not cookie_str:
            return None
        try:
            import requests
            import re
            headers = {
                'Cookie': cookie_str, 
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            if plat == 'douban':
                resp = requests.get(
                    'https://www.douban.com/mine/',
                    headers=headers,
                    timeout=10,
                    allow_redirects=True
                )
                # Douban sometimes redirects through sec.douban.com with encoded URL
                # Check both the final URL and any encoded URL in query params
                from urllib.parse import unquote
                url_to_check = unquote(resp.url)  # Decode URL-encoded characters
                m = re.search(r'/people/([^/\?"]+)', url_to_check)
                return m.group(1) if m else None
                
            elif plat == 'imdb':
                # IMDB: get homepage and look for user profile link
                resp = requests.get(
                    'https://www.imdb.com/',
                    headers=headers,
                    timeout=10
                )
                # Look for user ID in various patterns
                patterns = [
                    r'/user/(ur\d+)',           # /user/ur79467081/
                    r'ur(\d+)',                  # ur79467081
                    r'"userId":"(ur\d+)"',       # JSON format
                ]
                for pattern in patterns:
                    m = re.search(pattern, resp.text)
                    if m:
                        user_id = m.group(1)
                        if not user_id.startswith('ur'):
                            user_id = f'ur{user_id}'
                        return user_id
        except Exception as e:
            logging.error(f"Username fetch error: {e}")
        return None
    
    def get_user_profile(plat, cookie_str, user_id):
        """Fetch complete user profile including avatar, name, and stats"""
        profile = {'user_id': user_id, 'display_name': user_id, 'avatar': None}
        if not cookie_str or not user_id:
            return profile
        try:
            import requests
            import re
            headers = {
                'Cookie': cookie_str, 
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            if plat == 'douban':
                # Fetch user page for profile info
                resp = requests.get(
                    f'https://www.douban.com/people/{user_id}/',
                    headers=headers,
                    timeout=10
                )
                if resp.status_code == 200:
                    html = resp.text
                    # Extract display name
                    m = re.search(r'<title>([^<]+)的首页', html)
                    if m:
                        profile['display_name'] = m.group(1).strip()
                    # Extract avatar
                    m = re.search(r'<img\s+src="([^"]+)"\s+alt="[^"]*"\s+class="avatar"', html)
                    if m:
                        profile['avatar'] = m.group(1)
                    # Extract movie stats from movie page
                    movie_resp = requests.get(
                        f'https://movie.douban.com/people/{user_id}/',
                        headers=headers,
                        timeout=10
                    )
                    if movie_resp.status_code == 200:
                        movie_html = movie_resp.text
                        # Watched count
                        m = re.search(r'/collect[^>]*>(\d+)', movie_html)
                        if m: profile['watched'] = int(m.group(1))
                        # Wish count
                        m = re.search(r'/wish[^>]*>(\d+)', movie_html)
                        if m: profile['wish'] = int(m.group(1))
                        # Doing count
                        m = re.search(r'/do[^>]*>(\d+)', movie_html)
                        if m: profile['doing'] = int(m.group(1))
                        # Join date from movie page
                        m = re.search(r'(\d{4}-\d{2}-\d{2})加入', movie_html)
                        if m: profile['join_date'] = m.group(1)
                    # Fallback: get profile link
                    profile['profile_link'] = f'https://movie.douban.com/people/{user_id}/'
                    
            elif plat == 'imdb':
                profile['profile_link'] = f'https://www.imdb.com/user/{user_id}/'
                # Fetch IMDB ratings count using GraphQL API
                try:
                    import requests
                    api_url = "https://api.graphql.imdb.com/"
                    payload = {
                        "operationName": "userRatings",
                        "variables": {"first": 1, "after": None},
                        "extensions": {
                            "persistedQuery": {
                                "version": 1,
                                "sha256Hash": "ebf2387fd2ba45d62fc54ed2ffe3940086af52e700a1b3929a099d5fce23330a"
                            }
                        }
                    }
                    imdb_headers = {'Cookie': cookie_str, 'User-Agent': 'Mozilla/5.0'}
                    r = requests.post(api_url, json=payload, headers=imdb_headers, timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        user_ratings = data.get('data', {}).get('userRatings', {})
                        total = user_ratings.get('total', 0)
                        profile['watched'] = total
                        profile['ratings'] = total
                except Exception as e:
                    logging.error(f"IMDB ratings fetch error: {e}")
                
        except Exception as e:
            logging.error(f"Profile fetch error for {plat}: {e}")
        return profile
    
    def on_complete(plat, cookie_string, username):
        # If no username from login process, try to get it now (this also validates the cookie)
        if not username and cookie_string:
            logging.info(f"Validating cookie and fetching username for {plat}...")
            username = get_username_from_cookie(plat, cookie_string)
            logging.info(f"Validation result - Username: {username}")
        
        # If we have a valid username, the cookie is valid
        if username and cookie_string:
            # Save cookie and user_id to config
            config = read_config()
            config[f'{plat}_cookie'] = cookie_string
            config[f'{plat}_user_id'] = username
            write_config(config)
            logging.info(f"Cookie saved to config for {plat}: {username}")
            
            # Get full profile
            profile = get_user_profile(plat, cookie_string, username)
            
            socketio.emit('login_complete', {
                'platform': plat,
                'cookie': cookie_string,
                'user_id': username,
                'profile': profile
            })
            socketio.emit('log', {
                'message': f'✅ {plat.upper()} 登录成功: {username}',
                'type': 'success'
            })
        elif cookie_string:
            # Cookie captured but validation failed
            socketio.emit('login_complete', {
                'platform': plat,
                'cookie': None,
                'user_id': None,
                'profile': {}
            })
            socketio.emit('log', {
                'message': f'❌ {plat.upper()} Cookie 无效，请重试或确保已登录',
                'type': 'error'
            })
        else:
            # No cookie captured
            socketio.emit('login_complete', {
                'platform': plat,
                'cookie': None,
                'user_id': None,
                'profile': {}
            })
            socketio.emit('log', {
                'message': f'❌ {plat.upper()} 登录取消或失败',
                'type': 'error'
            })
    
    run_login_in_thread(platform, socketio, on_complete)


# ==================== TMDB Handlers ====================

@socketio.on('tmdb_connect')
def handle_tmdb_connect(data):
    """Connect to TMDB with API key"""
    api_key = data.get('api_key', '').strip()
    
    if not api_key:
        emit('log', {'message': '❌ 请输入 TMDB API Key', 'type': 'error'})
        return
    
    emit('log', {'message': '🔄 正在验证 TMDB API Key...', 'type': 'info'})
    
    try:
        client = TMDBClient(api_key)
        if client.validate_api_key():
            # Save API key to config
            config = read_config()
            config['tmdb_api_key'] = api_key
            write_config(config)
            
            emit('log', {'message': '✅ TMDB API Key 验证成功', 'type': 'success'})
            emit('tmdb_connected', {
                'success': True,
                'message': 'API Key 有效'
            })
        else:
            emit('log', {'message': '❌ TMDB API Key 无效', 'type': 'error'})
            emit('tmdb_connected', {'success': False, 'error': 'API Key 无效'})
    except Exception as e:
        logger.error(f"TMDB connect error: {e}")
        emit('log', {'message': f'❌ TMDB 连接失败: {e}', 'type': 'error'})
        emit('tmdb_connected', {'success': False, 'error': str(e)})

@socketio.on('tmdb_start_auth')
def handle_tmdb_start_auth(data):
    """Start TMDB session auth flow"""
    from scrapers.tmdb_client import DEFAULT_TMDB_API_KEY
    
    config = read_config()
    api_key = config.get('tmdb_api_key', '')
    
    # Use default API key if not configured
    if not api_key:
        api_key = DEFAULT_TMDB_API_KEY
        config['tmdb_api_key'] = api_key
        write_config(config)
        emit('log', {'message': 'ℹ️ 已使用内置 TMDB API Key', 'type': 'info'})
    
    try:
        client = TMDBClient(api_key)
        request_token = client.create_request_token()
        
        if request_token:
            auth_url = client.get_auth_url(request_token)
            # Save request token for later
            config['tmdb_request_token'] = request_token
            write_config(config)
            
            emit('tmdb_auth_url', {
                'url': auth_url,
                'token': request_token
            })
            emit('log', {'message': '📤 请在打开的页面中授权 TMDB', 'type': 'info'})
        else:
            emit('log', {'message': '❌ 无法创建 TMDB 授权令牌', 'type': 'error'})
    except Exception as e:
        logger.error(f"TMDB auth error: {e}")
        emit('log', {'message': f'❌ TMDB 授权失败: {e}', 'type': 'error'})

@socketio.on('tmdb_complete_auth')
def handle_tmdb_complete_auth(data):
    """Complete TMDB session auth after user approval"""
    config = read_config()
    api_key = config.get('tmdb_api_key', '')
    request_token = config.get('tmdb_request_token', '')
    
    if not api_key or not request_token:
        emit('log', {'message': '❌ 缺少授权信息', 'type': 'error'})
        return
    
    try:
        client = TMDBClient(api_key)
        logger.info(f"Creating TMDB session with request_token: {request_token[:10]}...")
        session_id = client.create_session(request_token)
        logger.info(f"TMDB session result: {session_id is not None}")
        
        if session_id:
            config['tmdb_session_id'] = session_id
            logger.info("TMDB session created successfully, getting account details...")
            
            # Get account details - client.session_id should be set from create_session
            account = client.get_account_details()
            logger.info(f"Account details result: {account}")
            
            username = ''
            account_id = None
            stats = {}
            
            if account:
                account_id = account.get('id')
                username = account.get('username', '')
                config['tmdb_account_id'] = account_id
                config['tmdb_username'] = username
                
                # Fetch account stats (rated count, watchlist count, links)
                stats = client.get_account_stats() or {}
                if stats:
                    config['tmdb_rated_count'] = stats.get('rated_count', 0)
                    config['tmdb_watchlist_count'] = stats.get('watchlist_count', 0)
            
            write_config(config)
            
            emit('log', {'message': '✅ TMDB 授权成功', 'type': 'success'})
            emit('tmdb_auth_complete', {
                'success': True,
                'username': username,
                'account_id': account_id,
                'rated_count': stats.get('rated_count', 0),
                'watchlist_count': stats.get('watchlist_count', 0),
                'profile_link': stats.get('profile_link', f'https://www.themoviedb.org/u/{username}') if username else 'https://www.themoviedb.org/',
                'rated_link': stats.get('rated_link', f'https://www.themoviedb.org/u/{username}/ratings') if username else '#',
                'watchlist_link': stats.get('watchlist_link', f'https://www.themoviedb.org/u/{username}/watchlist') if username else '#'
            })
        else:
            logger.warning("TMDB session creation returned None")
            emit('log', {'message': '❌ TMDB 会话创建失败，请确保已在TMDB页面点击"允许"', 'type': 'error'})
            emit('tmdb_auth_complete', {'success': False})
    except Exception as e:
        logger.error(f"TMDB session error: {e}", exc_info=True)
        emit('log', {'message': f'❌ TMDB 会话创建失败: {e}', 'type': 'error'})
        emit('tmdb_auth_complete', {'success': False})

@socketio.on('fetch_tmdb_data')
def handle_fetch_tmdb_data(data):
    """Fetch TMDB rated movies"""
    config = read_config()
    api_key = config.get('tmdb_api_key', '')
    session_id = config.get('tmdb_session_id', '')
    
    if not api_key:
        emit('log', {'message': '❌ 请先配置 TMDB API Key', 'type': 'error'})
        return
    
    if not session_id:
        emit('log', {'message': '⚠️ 需要授权才能获取评分数据', 'type': 'info'})
        return
    
    emit('log', {'message': '📥 正在获取 TMDB 评分数据...', 'type': 'info'})
    
    def fetch_data():
        try:
            client = TMDBClient(api_key, session_id)
            
            # First get account stats for UI update
            stats = client.get_account_stats()
            if stats:
                config['tmdb_rated_count'] = stats.get('rated_count', 0)
                config['tmdb_watchlist_count'] = stats.get('watchlist_count', 0)
                write_config(config)
                
                # Emit stats update to frontend
                socketio.emit('tmdb_stats_updated', stats)
            
            records = client.export_ratings_to_df_format()
            
            if records:
                df = pd.DataFrame(records)
                APP_DATA['tmdb_df'] = df
                
                # Save to disk
                username = config.get('tmdb_username', 'user')
                csv_path = os.path.join(DATA_DIR, f'tmdb_{username}_ratings.csv')
                df.to_csv(csv_path, index=False)
                APP_DATA['tmdb_csv_path'] = csv_path
                
                # Update last fetch time
                config['tmdb_last_fetch'] = datetime.now(timezone.utc).isoformat()
                write_config(config)
                
                logger.info(f"Saved TMDB data to {csv_path}")
                
                socketio.emit('fetch_complete', {
                    'platform': 'tmdb',
                    'sample': safe_df_to_records(df.head(10)),
                    'total_count': len(df),
                    'headers': ['Title', 'Year', 'Your Rating', 'Date Rated'],
                    'page': 1,
                    'page_size': 10,
                    'total_pages': (len(df) + 9) // 10
                })
                socketio.emit('log', {'message': f'✅ 获取 TMDB 数据成功: {len(df)} 部电影', 'type': 'success'})
            else:
                socketio.emit('log', {'message': '⚠️ 未找到 TMDB 评分数据', 'type': 'info'})
        except Exception as e:
            logger.error(f"TMDB fetch error: {e}")
            socketio.emit('log', {'message': f'❌ TMDB 数据获取失败: {e}', 'type': 'error'})
    
    import threading
    threading.Thread(target=fetch_data, daemon=True).start()

@socketio.on('tmdb_logout')
def handle_tmdb_logout(data):
    """Disconnect TMDB"""
    config = read_config()
    config.pop('tmdb_api_key', None)
    config.pop('tmdb_session_id', None)
    config.pop('tmdb_account_id', None)
    config.pop('tmdb_username', None)
    config.pop('tmdb_request_token', None)
    write_config(config)
    
    APP_DATA.pop('tmdb_df', None)
    APP_DATA.pop('tmdb_csv_path', None)
    
    emit('log', {'message': '✅ 已断开 TMDB 连接', 'type': 'success'})
    emit('tmdb_disconnected', {'success': True})


# ==================== Export to Desktop Handler ====================

@socketio.on('export_to_desktop')
def handle_export_to_desktop(data):
    """Export data directly to user's Desktop folder"""
    source = data.get('source', 'merged')
    
    emit('log', {'message': f'📤 正在导出 {source} 数据到桌面...', 'type': 'info'})
    
    try:
        # Get data
        df = APP_DATA.get(f'{source}_df')
        
        if df is None or (hasattr(df, 'empty') and df.empty):
            config = read_config()
            
            if source == 'merged':
                douban_user = config.get('douban_user_id', '')
                merged_path = os.path.join(DATA_DIR, f'merged_ratings_{douban_user[:8] if douban_user else "data"}.csv')
                if os.path.exists(merged_path):
                    df = pd.read_csv(merged_path)
            else:
                user_id = config.get(f'{source}_user_id', '')
                csv_path = os.path.join(DATA_DIR, f'{source}_{user_id}_ratings.csv')
                if os.path.exists(csv_path):
                    df = pd.read_csv(csv_path)
        
        if df is None or (hasattr(df, 'empty') and df.empty):
            emit('log', {'message': f'❌ 没有找到 {source} 数据', 'type': 'error'})
            return

        df = ensure_export_type_column(df)
        
        # Save to Desktop
        desktop_path = os.path.expanduser('~/Desktop')
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        filename = f'{source}_ratings_{timestamp}.csv'
        output_path = os.path.join(desktop_path, filename)
        
        # Convert integer columns to avoid float representation
        for col in df.columns:
            if df[col].dtype == 'float64':
                # Check if all non-null values are actually integers
                non_null = df[col].dropna()
                if len(non_null) > 0 and (non_null == non_null.astype(int)).all():
                    df[col] = df[col].fillna(0).astype(int)
        
        # Save with UTF-8 BOM for Excel compatibility
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        logger.info(f"Exported {len(df)} records to {output_path}")
        emit('log', {'message': f'✅ 导出成功: {filename}', 'type': 'success'})
        emit('log', {'message': f'📁 文件位置: 桌面/{filename}', 'type': 'info'})
        emit('export_complete', {'success': True, 'path': output_path, 'filename': filename})
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        emit('log', {'message': f'❌ 导出失败: {e}', 'type': 'error'})
        emit('export_complete', {'success': False, 'error': str(e)})


def open_browser(port):
    try:
        webbrowser.open_new(f"http://127.0.0.1:{port}")
    except: pass

def _select_available_port(host, preferred_port, max_tries=10):
    import socket
    port = preferred_port
    last_error = None
    for _ in range(max_tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
            s.close()
            return port
        except OSError as e:
            last_error = e
            try:
                s.close()
            except Exception:
                pass
            port += 1
    if last_error:
        raise last_error
    return preferred_port

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()  # Required for PyInstaller
    
    logger.info("🚀 CineRecord Hub is starting...")
    
    # CRITICAL: Load platform data into APP_DATA before starting server
    logger.info("📂 Loading platform data from CSV files...")
    load_platform_data()
    logger.info(f"✅ Platform data loaded. APP_DATA keys: {list(APP_DATA.keys())}")
    
    # Initialize and start the task scheduler
    logger.info("⏰ Starting task scheduler...")
    scheduler = get_scheduler(socketio)
    scheduler.start()
    logger.info("✅ Task scheduler started")
    
    if getattr(sys, 'frozen', False):
        Timer(1.5, lambda: open_browser(port)).start()
    try:
        # Enable debug in dev, but allow override for production/Docker
        debug_env = os.environ.get('CINERECORD_DEBUG')
        if debug_env is None:
            debug = os.environ.get('FLASK_ENV', '').lower() != 'production'
        else:
            debug = debug_env == '1'

        host = os.environ.get('CINERECORD_HOST', '0.0.0.0')
        preferred_port = int(os.environ.get('CINERECORD_PORT', '8000'))
        port = _select_available_port(host, preferred_port, max_tries=20)

        if port != preferred_port:
            logger.info(f"⚠️  Port {preferred_port} is in use, switching to {port}")
        logger.info(f"🔄 Attempting to bind to {host}:{port} (Debug={debug})...")
        if host == '0.0.0.0':
            logger.info(f"🌍 Server should be accessible from external IPs at http://YOUR_SERVER_IP:{port}")
        
        # Disable reloader to avoid crash:
        # "FATAL: changelist must be an iterable of select.kevent objects"
        socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True, debug=debug, use_reloader=False)
    except Exception as e:
        logger.critical(f"FATAL: {e}")
        sys.exit(1)

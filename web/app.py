# Try to use eventlet for async support, fall back to threading if not available
try:
    import eventlet
    eventlet.monkey_patch()
    ASYNC_MODE = 'eventlet'
except (ImportError, NotImplementedError) as e:
    # eventlet not available or has platform issues, use threading
    ASYNC_MODE = 'threading'
    print(f"Note: eventlet not available ({e}), using threading mode")

import os
import sys

# Ensure project root is in path for imports
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import logging
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from threading import Timer
import webbrowser
import pandas as pd
import time
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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# --- FLASK APP SETUP ---
template_dir = get_resource_path('web/templates')
static_dir = get_resource_path('web/static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=ASYNC_MODE, cors_allowed_origins="*", 
                    ping_timeout=60, ping_interval=25)  # Prevent reconnection during long data fetches

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
from adapters.douban import run_scraper as run_douban
from adapters.imdb import run_scraper as run_imdb
from scrapers.trakt_client import TraktClient  # Keep original for backward compat
from scrapers.tmdb_client import TMDBClient  # TMDB integration
from scrapers.sync_trakt_douban import sync_trakt_to_douban

# Scheduled Sync
from web.scheduler import get_scheduler


# Global state
CORE_COLUMNS = ['Const', 'Title', 'Your Rating', 'Date Rated', 'douban_id']
ESSENTIAL_COLUMNS = ['Const', 'Title', 'Your Rating', 'Date Rated', 'douban_id', 'Year', 'URL', 'Cover URL', 'Douban Rating', 'IMDb Rating', 'Num Votes', 'Genres', 'Directors']
APP_DATA = {}

from web.data_utils import safe_df_to_records

@app.route('/')
def index():
    return render_template('index.html', now=time.time())

# ==========================================
# Browser Auth (OAuth-style) Routes
# ==========================================

# Store pending auth sessions
AUTH_SESSIONS = {}

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
    
    if not platform or not cookie:
        return jsonify({'success': False, 'error': '缺少必要参数'})
    
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
            cron_expression=schedule,
            paused=paused,
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
            cron_expression=data.get('schedule'),
            paused=data.get('paused', False),
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

# ==========================================
# Main Entry Point
# ==========================================

@app.route('/proxy/avatar')
def proxy_avatar():
    """Proxy avatar images to bypass anti-hotlinking protection"""
    import requests
    from flask import request, Response
    
    url = request.args.get('url', '')
    if not url:
        return Response('No URL provided', status=400)
    
    # Only allow proxying from known domains
    allowed_domains = ['doubanio.com', 'douban.com', 'trakt.tv', 'imdb.com', 'media-amazon.com']
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if not any(domain in parsed.netloc for domain in allowed_domains):
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
            # Try to find merged data file
            douban_user = config.get('douban_user_id', '')
            merged_path = os.path.join(DATA_DIR, f'merged_ratings_{douban_user[:8] if douban_user else "data"}.csv')
            
            # If merged file doesn't exist, try to generate it
            if not os.path.exists(merged_path):
                # Try to merge from source files
                imdb_user = config.get('imdb_user_id', '')
                douban_path = os.path.join(DATA_DIR, f'douban_{douban_user}_ratings.csv')
                imdb_path = os.path.join(DATA_DIR, f'imdb_{imdb_user}_ratings.csv')
                
                if os.path.exists(douban_path) and os.path.exists(imdb_path):
                    _, _ = merge_movie_data(douban_path, imdb_path, merged_path)
                    
            if os.path.exists(merged_path):
                df = pd.read_csv(merged_path)
            else:
                return Response("No merged data available. Please fetch both Douban and IMDB data first.", status=404)
        else:
            # Regular platform data
            user_id = config.get(f'{platform}_user_id', '')
            csv_path = os.path.join(DATA_DIR, f'{platform}_{user_id}_ratings.csv')
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
            else:
                return Response("No data available", status=404)
    
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
            # Select only columns that exist
            cols_needed = ['Title', 'Year', 'Your Rating', 'Date Rated']
            available_cols = [c for c in cols_needed if c in df.columns]
            # Also try alternative column names
            if 'Your Rating' not in df.columns and 'YourRating_douban' in df.columns:
                df['Your Rating'] = df['YourRating_douban']
                available_cols.append('Your Rating')
            if 'Date Rated' not in df.columns and 'DateRated_douban' in df.columns:
                df['Date Rated'] = df['DateRated_douban']
                available_cols.append('Date Rated')
            
            lb_df = df[available_cols].copy()
            lb_df.columns = ['Title', 'Year', 'Rating10', 'WatchedDate'][:len(available_cols)]
            
            # Convert Year to int to avoid .0
            if 'Year' in lb_df.columns:
                lb_df['Year'] = pd.to_numeric(lb_df['Year'], errors='coerce').fillna(0).astype(int)
            if 'Rating10' in lb_df.columns:
                lb_df['Rating10'] = pd.to_numeric(lb_df['Rating10'], errors='coerce').fillna(0) * 2
                lb_df['Rating10'] = lb_df['Rating10'].astype(int)
            
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
    
    logger.info(f"[API Library] Request: filter={platform_filter}, page={page}")
    
    try:
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
                return
            
            # Extract platform-specific data
            # Handle ratings - normalize to 10-point scale
            raw_rating = movie.get('Your Rating') or movie.get('YourRating_douban') or movie.get('YourRating_imdb') or movie.get('rating') or movie.get('评分') or movie.get('Rating')
            
            # Normalize ratings: Douban and Letterboxd use 5-star scale, convert to 10-point
            user_rating = ''
            if raw_rating is not None:
                try:
                    rating_float = float(raw_rating)
                    # Check for NaN - NaN is not valid JSON
                    if not math.isnan(rating_float):
                        if platform in ['douban', 'letterboxd']:
                            # 5-star scale -> 10-point scale
                            user_rating = rating_float * 2
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
                tmdb_id = clean_id(movie.get('tmdb_id') or movie.get('TMDB ID'))
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
                # Update date if newer
                new_date = movie.get('Date Rated') or movie.get('date_rated') or movie.get('标记日期') or movie.get('Watched Date') or ''
                if new_date and (not all_movies[key]['latest_date'] or new_date > all_movies[key]['latest_date']):
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

                # Update URLs if not set
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
        for platform, (user_id, path_fn) in platform_configs.items():
            path = None
            if user_id:
                path = path_fn(user_id)
            
            # If path not found or no user_id, try to find any file for this platform (Robust Loading)
            if not path or not os.path.exists(path):
                patterns = []
                if platform == 'letterboxd':
                    patterns = ['letterboxd*diary.csv', 'letterboxd*.csv', '*diary.csv']
                elif platform == 'tmdb':
                    patterns = ['tmdb_*_ratings.csv', 'tmdb*.csv']
                elif platform == 'trakt':
                    patterns = ['trakt_*_ratings.csv', 'trakt*.csv']
                
                for pattern in patterns:
                    matches = glob.glob(os.path.join(DATA_DIR, pattern))
                    if matches:
                        path = matches[0] # Use first match
                        logger.info(f"Auto-discovered {platform} data: {path}")
                        break

            if path and os.path.exists(path):
                try:
                    df = pd.read_csv(path)
                    platforms_with_data.append(platform)
                    for _, row in df.iterrows():
                        add_movie(row.to_dict(), platform)
                except Exception as e:
                    logger.warning(f"Failed to load {platform} data: {e}")
        
        # Convert to list and sort
        movies_list = list(all_movies.values())
        movies_list.sort(key=lambda x: x.get('latest_date') or '', reverse=True)
        
        # Apply platform filter
        if platform_filter == 'all':
            movies_list = [m for m in movies_list if len(m['sources']) >= 2]
        else:
            movies_list = [m for m in movies_list if platform_filter in m['sources'] and len(m['sources']) == 1]
        
        total_count = len(movies_list)
        
        # Calculate platform counts
        all_temp = list(all_movies.values())
        platform_counts = {}
        for platform in platform_configs.keys():
            platform_counts[platform] = len([m for m in all_temp if platform in m['sources'] and len(m['sources']) == 1])
        platform_counts['shared'] = len([m for m in all_temp if len(m['sources']) >= 2])
        
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
    user_id = config.get(f'{platform}_user_id')
    cookie = config.get(f'{platform}_cookie')
    
    if not (user_id and cookie):
        emit('log', {'message': f'❌ 请先在设置中填写 {platform.upper()} 用户ID和Cookie。', 'type': 'error'})
        return

    expected_path = os.path.join(DATA_DIR, f'{platform}_{user_id}_ratings.csv')
    
    def on_complete(result):
        if result:
            df = pd.DataFrame(result)
            cols_to_display = [col for col in CORE_COLUMNS if col in df.columns]
            cols_to_keep = set(cols_to_display + [col for col in ESSENTIAL_COLUMNS if col in df.columns])
            display_df = df[list(cols_to_keep)].copy()
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
            
            if latest_ts:
                cfg = read_config()
                cfg[f'{platform}_latest_record_ts'] = latest_ts
                write_config(cfg)
                socketio.emit('log', {'message': f'📅 {platform.upper()} 最新记录时间: {latest_ts[:10]}', 'type': 'info'})
            
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
        threading.Thread(target=lambda: on_complete(run_douban(user_id, cookie, expected_path, socketio))).start()
    else:
        import threading
        threading.Thread(target=lambda: on_complete(run_imdb(user_id, cookie, expected_path, socketio))).start()

@socketio.on('start_sync')
def handle_sync(data):
    logger.info(f"🔍 DEBUG: handle_sync called with data: {data}")
    direction = data.get('direction')
    is_dry_run = data.get('is_dry_run', False)
    logger.info(f"🔍 DEBUG: direction={direction}, is_dry_run={is_dry_run}")
    
    # Run sync in a background thread to prevent blocking Socket.IO heartbeat
    def sync_worker(direction, is_dry_run, app_data):
        logger.info(f"🔍 DEBUG: sync_worker thread started for {direction}")
        from web.logic import perform_sync_logic
        try:
            # Perform sync logic
            logger.info(f"🔍 DEBUG: Calling perform_sync_logic...")
            result = perform_sync_logic(direction, is_dry_run, socketio, app_data)
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
    threading.Thread(target=sync_worker, args=(direction, is_dry_run, APP_DATA), daemon=True).start()
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
                return
            
            # Extract platform-specific data
            # Handle ratings - normalize to 10-point scale
            raw_rating = movie.get('Your Rating') or movie.get('YourRating_douban') or movie.get('YourRating_imdb') or movie.get('rating') or movie.get('评分') or movie.get('Rating')
            
            # Normalize ratings: Douban and Letterboxd use 5-star scale, convert to 10-point
            user_rating = ''
            if raw_rating is not None:
                try:
                    rating_float = float(raw_rating)
                    # Check for NaN - NaN is not valid JSON
                    if not math.isnan(rating_float):
                        if platform in ['douban', 'letterboxd']:
                            # 5-star scale -> 10-point scale
                            user_rating = rating_float * 2
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
            imdb_id = clean_id(movie.get('Const') or movie.get('imdb_id') or movie.get('IMDB ID') or movie.get('IMDb ID'))
            douban_id = clean_id(movie.get('douban_id') or movie.get('movie_id'))
            tmdb_id = clean_id(movie.get('tmdb_id') or movie.get('TMDB ID'))
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
                # Update date if newer
                new_date = clean_date(movie.get('Date Rated') or movie.get('date_rated') or movie.get('标记日期') or movie.get('Watched Date') or movie.get('latest_date'))
                if new_date and (not all_movies[key]['latest_date'] or new_date > all_movies[key]['latest_date']):
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
            df = APP_DATA.get(f'{platform}_df')
            if df is not None and not df.empty:
                platforms_with_data.append(platform)
                records = df.to_dict('records')
                for movie in records:
                    add_movie(movie, platform)
        
        # Convert to list and sort
        movies_list = list(all_movies.values())
        movies_list.sort(key=lambda x: str(x.get('latest_date') or ''), reverse=True)
        
        # Apply platform filter
        if platform_filter == 'all':
            movies_list = [m for m in movies_list if len(m['sources']) >= 2]
        else:
            movies_list = [m for m in movies_list if platform_filter in m['sources'] and len(m['sources']) == 1]
        
        total_count = len(movies_list)
        
        # Calculate platform counts
        all_temp = list(all_movies.values())
        platform_counts = {}
        for platform in all_platforms:
            df = APP_DATA.get(f'{platform}_df')
            if df is not None:
                platform_counts[platform] = len([m for m in all_temp if platform in m['sources'] and len(m['sources']) == 1])
        platform_counts['shared'] = len([m for m in all_temp if len(m['sources']) >= 2])
        
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
    
    try:
        csv_content = data.get('content', '')
        filename = data.get('filename', 'diary.csv')
        
        if not csv_content:
            emit('log', {'message': '❌ 未接收到文件内容', 'type': 'error'})
            return
        
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
        
        # Store in APP_DATA
        APP_DATA['letterboxd_df'] = df
        APP_DATA['letterboxd_csv_path'] = f'letterboxd_import_{total_count}.csv'
        
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
        
    except Exception as e:
        logger.exception("Letterboxd CSV parse error")
        emit('log', {'message': f'❌ 解析 Letterboxd CSV 失败: {e}', 'type': 'error'})

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
                                logger.info(f"DEBUG_SYNC: '{movie.get('Title')}' Date={movie_dt} Threshold={threshold_dt} Result={movie_dt >= threshold_dt}")

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


def open_browser():
    try:
        webbrowser.open_new("http://127.0.0.1:8000")
    except: pass

if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()  # Required for PyInstaller
    
    logger.info("🚀 CineRecord Hub is starting...")
    Timer(1.5, open_browser).start()
    try:
        socketio.run(app, host='127.0.0.1', port=8000, allow_unsafe_werkzeug=True)
    except Exception as e:
        logger.critical(f"FATAL: {e}")
        sys.exit(1)

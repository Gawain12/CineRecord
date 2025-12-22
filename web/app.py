import eventlet
eventlet.monkey_patch()

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
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# Import helpers after monkey_patch
from web.config_helper import read_config, write_config
from web.logic import perform_sync_logic
from utils.merge_data import merge_movie_data
from scrapers.douban_scraper import run_scraper as run_douban
from scrapers.imdb_scraper import run_scraper as run_imdb
from web.auth_helper import run_login_in_thread

# Global state
CORE_COLUMNS = ['Const', 'Title', 'Your Rating', 'Date Rated', 'douban_id']
ESSENTIAL_COLUMNS = ['Const', 'Title', 'Your Rating', 'Date Rated', 'douban_id', 'Year', 'URL', 'Cover URL']
APP_DATA = {}

def safe_df_to_records(df):
    if df is None or df.empty: return []
    return df.where(pd.notnull(df), None).to_dict('records')

@app.route('/')
def index():
    return render_template('index.html')

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
            socketio.emit('fetch_complete', {
                'platform': platform,
                'path': expected_path,
                'sample': safe_df_to_records(display_df.head()),
                'total_count': len(df),
                'headers': cols_to_display
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
    direction = data.get('direction')
    is_dry_run = data.get('is_dry_run', False)
    config = read_config()
    
    douban_user = config.get('douban_user_id')
    imdb_user = config.get('imdb_user_id')
    
    douban_path = os.path.join(DATA_DIR, f'douban_{douban_user}_ratings.csv')
    imdb_path = os.path.join(DATA_DIR, f'imdb_{imdb_user}_ratings.csv')
    
    if not (os.path.exists(douban_path) and os.path.exists(imdb_path)):
        emit('log', {'message': '❌ 缺失本地数据，同步前请先点击“更新数据”。', 'type': 'error'})
        return

    try:
        result = perform_sync_logic(douban_path, imdb_path, direction, is_dry_run, config.get('douban_cookie'), config.get('imdb_cookie'), socketio)
        if is_dry_run:
            emit('sync_preview', {'movies': result if result else []})
        else:
            emit('finished')
            # Extra: Update merged preview
            merged_output = os.path.join(DATA_DIR, f'merged_ratings_{douban_user[:8]}.csv')
            _, _ = merge_movie_data(douban_path, imdb_path, merged_output)
            if os.path.exists(merged_output):
                df = pd.read_csv(merged_output)
                emit('merged_data_preview', {'sample': safe_df_to_records(df.head()), 'total_count': len(df), 'headers': list(df.columns)})
    except Exception as e:
        logger.exception("Sync fail")
        emit('log', {'message': f'同步错误: {e}', 'type': 'error'})

@socketio.on('get_config')
def handle_get_config():
    emit('config_loaded', read_config())

@socketio.on('save_config')
def handle_save_config(data):
    if write_config(data): emit('log', {'message': '✅ 配置已保存。', 'type': 'success'})
    else: emit('log', {'message': '❌ 保存失败。', 'type': 'error'})

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
                m = re.search(r'/people/([^/\?"]+)', resp.url)
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
    
    def on_complete(plat, cookie_string, username):
        # If no username from login process, try to get it now
        if not username and cookie_string:
            logging.info(f"Fetching username for {plat}...")
            username = get_username_from_cookie(plat, cookie_string)
            logging.info(f"Username: {username}")
        
        socketio.emit('login_complete', {
            'platform': plat,
            'cookie': cookie_string,
            'user_id': username
        })
    
    run_login_in_thread(platform, socketio, on_complete)


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

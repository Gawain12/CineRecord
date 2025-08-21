import eventlet
eventlet.monkey_patch()

import os
import sys
import pandas as pd
import webbrowser
from threading import Timer
from flask import Flask, render_template, request, send_from_directory
from flask_socketio import SocketIO, emit

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils.merge_data import merge_movie_data
from web.logic import perform_sync_logic, safe_df_to_records
from scrapers import douban_scraper, imdb_scraper
from web.config_helper import read_config, write_config

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

CORE_COLUMNS = ['Title', 'Year', 'Your Rating', 'Date Rated']
ESSENTIAL_COLUMNS = ['URL', 'URL_douban', 'URL_imdb']
APP_DATA = {"douban_csv_path": None, "imdb_csv_path": None}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download/<platform>')
def download_file(platform):
    user_id = read_config().get(f'{platform}_user_id')
    if not user_id: return "User ID not configured.", 404
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    filename = f'{platform}_{user_id}_ratings.csv'
    safe_data_dir = os.path.abspath(data_dir)
    try:
        return send_from_directory(safe_data_dir, filename, as_attachment=True)
    except FileNotFoundError:
        return "File not found.", 404

@socketio.on('fetch_data')
def handle_fetch_event(json_data):
    platform = json_data.get('platform')
    cookie = json_data.get('cookie')
    user_id = json_data.get('user_id')
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    os.makedirs(data_dir, exist_ok=True)
    try:
        sample_data, output_path = None, None
        if platform == 'douban':
            if not user_id or not cookie:
                emit('log', {'message': '错误: 豆瓣 User ID 和Cookie是必需的。', 'type': 'error'}); return
            output_path = os.path.join(data_dir, f'douban_{user_id}_ratings.csv')
            APP_DATA['douban_csv_path'] = output_path
            sample_data = douban_scraper.run_scraper(user_id, cookie, output_path, socketio)
            if sample_data is not None: write_config({'douban_user_id': user_id, 'douban_cookie': cookie})
        elif platform == 'imdb':
            if not user_id or not cookie:
                emit('log', {'message': '错误: IMDb User ID和Cookie是必需的。', 'type': 'error'}); return
            output_path = os.path.join(data_dir, f'imdb_{user_id}_ratings.csv')
            APP_DATA['imdb_csv_path'] = output_path
            sample_data = imdb_scraper.run_scraper(user_id, cookie, output_path, socketio)
            if sample_data is not None: write_config({'imdb_user_id': user_id, 'imdb_cookie': cookie})
        
        if sample_data is not None:
            df = pd.read_csv(output_path)
            total_count = len(df)
            cols_to_display = [col for col in CORE_COLUMNS if col in df.columns]
            cols_to_keep = set(cols_to_display + [col for col in ESSENTIAL_COLUMNS if col in df.columns])
            display_df = df[list(cols_to_keep)].copy()
            headers = cols_to_display
            safe_sample_data = safe_df_to_records(display_df.head())
            emit('fetch_complete', {'platform': platform, 'path': output_path, 'sample': safe_sample_data, 'total_count': total_count, 'headers': headers})
        else:
            emit('fetch_complete', {'platform': platform, 'error': '抓取失败，请检查日志。'})
    except Exception as e:
        emit('log', {'message': f'抓取 {platform} 数据时发生错误: {e}', 'type': 'error'})
        emit('fetch_complete', {'platform': platform, 'error': str(e)})

@socketio.on('start_sync')
def handle_sync_event(json_data):
    douban_path, imdb_path = APP_DATA.get("douban_csv_path"), APP_DATA.get("imdb_csv_path")
    if not douban_path or not imdb_path:
        emit('log', {'message': '错误: 请先成功获取豆瓣和IMDb的数据。', 'type': 'error'}); return
    try:
        is_dry_run = json_data.get('dry_run', False)
        douban_cookie, imdb_cookie = json_data.get('douban_cookie'), json_data.get('imdb_cookie')
        preview_data = perform_sync_logic(douban_path, imdb_path, json_data.get('direction'), is_dry_run, douban_cookie, imdb_cookie, socketio)
        if is_dry_run:
            if preview_data is not None: emit('sync_preview', {'movies': preview_data})
        else:
            config_to_save = {}
            if douban_cookie: config_to_save['douban_cookie'] = douban_cookie
            if imdb_cookie: config_to_save['imdb_cookie'] = imdb_cookie
            if config_to_save: write_config(config_to_save)
            emit('log', {'message': '✅ 同步成功！正在生成合并数据预览...', 'type': 'success'})
            data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
            user_id = read_config().get('douban_user_id')
            if not user_id:
                emit('log', {'message': '⚠️ 无法确定用于合并文件名的用户ID。', 'type': 'error'}); return
            merged_path = os.path.join(data_dir, f'merged_ratings_{user_id}.csv')
            _, _ = merge_movie_data(douban_path, imdb_path, merged_path)
            if os.path.exists(merged_path):
                df = pd.read_csv(merged_path)
                emit('merged_data_preview', {'sample': safe_df_to_records(df.head()), 'total_count': len(df), 'headers': list(df.columns)})
            else:
                emit('log', {'message': '⚠️ 未能生成或找到合并后的数据文件。', 'type': 'error'})
        emit('finished', {'message': 'All tasks complete.'})
    except Exception as e:
        emit('log', {'message': f'同步时发生内部错误: {e}', 'type': 'error'})
        emit('finished', {'message': 'Task finished with errors.'})

@socketio.on('get_config')
def handle_get_config():
    config = read_config()
    if config: emit('config_loaded', config)

@socketio.on('check_local_data')
def handle_check_local_data(config):
    if config.get('douban_user_id'):
        load_and_emit_local_data('douban', config['douban_user_id'], socketio)
    if config.get('imdb_user_id'):
        load_and_emit_local_data('imdb', config['imdb_user_id'], socketio)

@socketio.on('save_config')
def handle_save_config(data):
    if write_config(data): emit('log', {'message': '✅ 配置已成功保存。', 'type': 'success'})
    else: emit('log', {'message': '❌ 保存配置失败。', 'type': 'error'})
        
def load_and_emit_local_data(platform, user_id, socketio):
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    expected_path = os.path.join(data_dir, f'{platform}_{user_id}_ratings.csv')
    if os.path.exists(expected_path):
        try:
            df = pd.read_csv(expected_path)
            if not df.empty:
                cols_to_display = [col for col in CORE_COLUMNS if col in df.columns]
                cols_to_keep = set(cols_to_display + [col for col in ESSENTIAL_COLUMNS if col in df.columns])
                display_df = df[list(cols_to_keep)].copy()
                APP_DATA[f'{platform}_csv_path'] = expected_path
                socketio.emit('fetch_complete', {'platform': platform, 'path': expected_path, 'sample': safe_df_to_records(display_df.head()), 'total_count': len(df), 'headers': cols_to_display, 'preloaded': True})
        except Exception as e:
            socketio.emit('log', {'message': f'预加载本地 {platform} 文件失败: {e}', 'type': 'error'})

def open_browser():
    webbrowser.open_new("http://127.0.0.1:8000")

if __name__ == '__main__':
    print("🚀 CineRecord 正在启动...")
    Timer(1, open_browser).start()
    socketio.run(app, host='127.0.0.1', port=8000, allow_unsafe_werkzeug=True)

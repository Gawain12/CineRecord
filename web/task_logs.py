"""
Persistent Task Log System
定时任务日志持久化模块 - 保存日志到文件，刷新页面后仍可查看
"""

import json
import os
from datetime import datetime
from threading import Lock

LOG_FILE = 'data/task_logs.json'
MAX_LOGS = 200  # 最多保留200条日志

_log_lock = Lock()

def _ensure_log_file():
    """确保日志文件存在"""
    os.makedirs('data', exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)

def add_task_log(task_name: str, message: str, log_type: str = 'info', source: str = '', target: str = ''):
    """
    添加任务日志
    
    Args:
        task_name: 任务名称
        message: 日志消息
        log_type: 日志类型 (info, success, error, warning, start, progress)
        source: 源平台
        target: 目标平台
    """
    _ensure_log_file()
    
    entry = {
        'timestamp': datetime.now().isoformat(),
        'time_str': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'task_name': task_name,
        'message': message,
        'type': log_type,
        'source': source,
        'target': target
    }
    
    with _log_lock:
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logs = []
        
        # 插入到开头（最新的在前）
        logs.insert(0, entry)
        
        # 限制日志数量
        if len(logs) > MAX_LOGS:
            logs = logs[:MAX_LOGS]
        
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

def get_task_logs(limit: int = 50) -> list:
    """
    获取任务日志
    
    Args:
        limit: 返回的日志条数
        
    Returns:
        list: 日志列表（最新的在前）
    """
    _ensure_log_file()
    
    with _log_lock:
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            return logs[:limit]
        except (json.JSONDecodeError, FileNotFoundError):
            return []

def clear_task_logs():
    """清空所有日志"""
    _ensure_log_file()
    with _log_lock:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)

"""
Scheduled Sync Tasks
定时同步任务函数
"""

import logging
from web.logic import perform_sync_logic

logger = logging.getLogger(__name__)

def _emit_and_persist_task_log(socketio, task_name, source, target, message, log_type):
    if socketio:
        socketio.emit('scheduled_task_log', {
            'type': log_type,
            'task_name': task_name,
            'source': source,
            'target': target,
            'message': message
        })
    try:
        from web.task_logs import add_task_log
        add_task_log(task_name, message, log_type, source, target)
    except Exception:
        pass

def execute_scheduled_sync(source: str, target: str, **kwargs):
    """
    执行定时同步任务
    
    Args:
        source: 源平台
        target: 目标平台
        **kwargs: 额外参数（如cron_expr, task_name等）
    """
    task_name = kwargs.get('task_name', f'{source}→{target}')
    
    # Build task context for detailed logging
    task_context = {
        'task_name': task_name,
        'source': source,
        'target': target
    }
    
    try:
        logger.info(f"[Scheduled] Starting sync: {source} -> {target}")
        
        # 在运行时获取 app 和 socketio
        try:
            from web.app import app, socketio
        except ImportError:
            try:
                from web.app import app
                socketio = None
            except:
                app = None
                socketio = None
        
        if not app:
            logger.error("Could not import Flask app instance")
            return

        with app.app_context():
            # Emit + persist task start log
            _emit_and_persist_task_log(
                socketio,
                task_name,
                source,
                target,
                f'🚀 开始执行: {source.upper()} → {target.upper()}',
                'start'
            )
            
            # Get APP_DATA from app module
            try:
                from web.app import APP_DATA
            except ImportError:
                APP_DATA = {}
            
            # Check if source data exists, if not try to load from cache
            source_df = APP_DATA.get(f'{source}_df')
            if source_df is None or (hasattr(source_df, 'empty') and source_df.empty):
                _emit_and_persist_task_log(
                    socketio,
                    task_name,
                    source,
                    target,
                    f'⚠️ 源平台 {source.upper()} 缓存为空，尝试加载...',
                    'warning'
                )
                # Try to load cached data from CSV files
                import os
                import pandas as pd
                cache_path = f'data/{source}_ratings.csv'
                if os.path.exists(cache_path):
                    try:
                        APP_DATA[f'{source}_df'] = pd.read_csv(cache_path)
                        _emit_and_persist_task_log(
                            socketio,
                            task_name,
                            source,
                            target,
                            f'✅ 已从缓存加载 {source.upper()} 数据 ({len(APP_DATA[f"{source}_df"])} 条)',
                            'info'
                        )
                    except Exception as load_err:
                        logger.warning(f"Failed to load cache: {load_err}")
            
            # 执行同步（非预览模式）- 传递 task_context 和 app_data
            perform_sync_logic(
                direction=f"{source}-to-{target}",
                is_dry_run=False,
                socketio=socketio,
                app_data=APP_DATA,
                task_context=task_context  # Pass context for detailed logging
            )
            
            logger.info(f"[Scheduled] Sync completed: {source} -> {target}")
            
            # Emit + persist task completion log
            _emit_and_persist_task_log(
                socketio,
                task_name,
                source,
                target,
                f'✅ 完成: {source.upper()} → {target.upper()}',
                'success'
            )
        
    except Exception as e:
        logger.error(f"[Scheduled] Sync failed ({source} -> {target}): {e}")
        
        # Try to report error even if context failed
        try:
            from web.app import socketio
        except ImportError:
            socketio = None
            
        _emit_and_persist_task_log(
            socketio,
            task_name,
            source,
            target,
            f'❌ 失败: {str(e)}',
            'error'
        )
        
        raise

"""
Scheduled Sync Tasks
定时同步任务函数
"""

import logging
from web.logic import perform_sync_logic

logger = logging.getLogger(__name__)

def execute_scheduled_sync(source: str, target: str, socketio=None):
    """
    执行定时同步任务
    
    Args:
        source: 源平台
        target: 目标平台
        socketio: WebSocket实例（用于实时通知）
    """
    try:
        logger.info(f"[Scheduled] Starting sync: {source} -> {target}")
        
        # 创建日志记录器
        if socketio:
            from web.logic import SocketLogger
            task_logger = SocketLogger(socketio)
        else:
            # 使用标准日志
            task_logger = logger
        
        # 执行同步（非预览模式）
        perform_sync_logic(
            direction=f"{source}-{target}",
            is_dry_run=False,
            socketio=socketio
        )
        
        logger.info(f"[Scheduled] Sync completed: {source} -> {target}")
        
    except Exception as e:
        logger.error(f"[Scheduled] Sync failed ({source} -> {target}): {e}")
        raise

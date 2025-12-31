"""
Logger implementations for adapters
统一的日志接口，支持 Socket.IO 和 CLI 两种模式
"""


class SocketLogger:
    """
    Socket.IO 日志记录器
    用于 Web 界面实时显示进度和消息
    """
    
    def __init__(self, socketio, platform: str):
        self.socketio = socketio
        self.platform = platform
    
    def log(self, message: str, type: str = 'info'):
        """
        发送日志消息
        
        Args:
            message: 日志内容
            type: 日志类型 ('info', 'success', 'error', 'warning')
        """
        self.socketio.emit('log', {
            'message': f'[{self.platform.upper()}] {message}',
            'type': type
        })
    
    def progress(self, current: int, total: int, step: str = ""):
        """
        发送进度更新
        
        Args:
            current: 当前进度
            total: 总数
            step: 当前步骤描述
        """
        self.socketio.emit('progress', {
            'platform': self.platform,
            'current': current,
            'total': total,
            'step': step
        })
    
    def info(self, message: str):
        """发送信息日志"""
        self.log(message, 'info')
    
    def success(self, message: str):
        """发送成功日志"""
        self.log(message, 'success')
    
    def error(self, message: str):
        """发送错误日志"""
        self.log(message, 'error')
    
    def warning(self, message: str):
        """发送警告日志"""
        self.log(message, 'warning')


class CLILogger:
    """
    命令行日志记录器
    用于命令行测试和调试
    """
    
    def __init__(self, platform: str = 'CLI'):
        self.platform = platform
    
    def log(self, message: str, type: str = 'info'):
        """打印日志消息"""
        prefix = {
            'info': 'ℹ️',
            'success': '✅',
            'error': '❌',
            'warning': '⚠️'
        }.get(type, 'ℹ️')
        print(f"{prefix} [{self.platform.upper()}] {message}")
    
    def progress(self, current: int, total: int, step: str = ""):
        """打印进度"""
        if total > 0:
            percent = current / total * 100
            print(f"📊 [{self.platform.upper()}] {step} - {current}/{total} ({percent:.1f}%)")
    
    def info(self, message: str):
        self.log(message, 'info')
    
    def success(self, message: str):
        self.log(message, 'success')
    
    def error(self, message: str):
        self.log(message, 'error')
    
    def warning(self, message: str):
        self.log(message, 'warning')


class NullLogger:
    """空日志记录器，用于静默模式"""
    
    def __init__(self, platform: str = ''):
        self.platform = platform
    
    def log(self, message: str, type: str = 'info'):
        pass
    
    def progress(self, current: int, total: int, step: str = ""):
        pass
    
    def info(self, message: str):
        pass
    
    def success(self, message: str):
        pass
    
    def error(self, message: str):
        pass
    
    def warning(self, message: str):
        pass

"""
CineRecord Hub - Scheduled Sync Scheduler
使用APScheduler实现跨平台定时同步任务调度
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
import logging
import os

logger = logging.getLogger(__name__)

class SyncScheduler:
    """定时同步任务调度器"""
    
    def __init__(self, socketio=None):
        """
        初始化调度器
        
        Args:
            socketio: Flask-SocketIO实例，用于发送实时通知
        """
        self.socketio = socketio
        
        # 配置任务存储（持久化到SQLite）
        db_path = os.path.join('data', 'scheduler.db')
        os.makedirs('data', exist_ok=True)
        
        jobstores = {
            'default': SQLAlchemyJobStore(url=f'sqlite:///{db_path}')
        }
        
        # 创建后台调度器
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            timezone='Asia/Shanghai'  # 可配置
        )
        
        # 注册事件监听器
        self.scheduler.add_listener(
            self._job_executed_callback,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED
        )

    def _emit_and_persist_task_log(self, job, message, log_type):
        task_name = getattr(job, 'name', None) or (job.id if job else 'Scheduled Task')
        source = ''
        target = ''
        if job and getattr(job, 'kwargs', None):
            source = job.kwargs.get('source_platform', '')
            target = job.kwargs.get('target_platform', '')

        if self.socketio:
            self.socketio.emit('scheduled_task_log', {
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
    
    def start(self):
        """启动调度器"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started successfully")
    
    def shutdown(self):
        """关闭调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler shutdown")
    
    def add_sync_job(self, job_id: str, source: str, target: str, cron_expr: str, enabled: bool = True, name: str = None):
        """
        添加定时同步任务
        
        Args:
            job_id: 唯一任务ID
            source: 源平台
            target: 目标平台
            cron_expr: Cron表达式 (e.g., "0 2 * * *")
            enabled: 是否启用
            name: 任务名称
            
        Returns:
            bool: 是否添加成功
        """
        try:
            # 解析cron表达式
            trigger = CronTrigger.from_crontab(cron_expr)
            
            # 导入同步任务函数
            from web.tasks.sync_jobs import execute_scheduled_sync
            
            job_name = name if name else f'{source}->{target}'
            
        # 添加任务 - 不传递socketio，因为它不能被序列化
            # execute_scheduled_sync 会在运行时获取 socketio
            # 将元数据存储在 kwargs 中以便检索
            self.scheduler.add_job(
                func=execute_scheduled_sync,
                trigger=trigger,
                id=job_id,
                args=[source, target],  # 位置参数
                kwargs={
                    'cron_expr': cron_expr,
                    'source_platform': source,
                    'target_platform': target,
                    'task_name': job_name  # Pass task name for logging
                }, # 存储元数据
                name=job_name,
                replace_existing=True,
                coalesce=True,  # 错过的任务只执行一次
                max_instances=1,  # 同一任务不并发执行
                misfire_grace_time=3600  # 允许1小时内的错过任务补跑
            )
            
            # 如果不启用，立即暂停
            if not enabled:
                self.pause_job(job_id)
            
            logger.info(f"Added scheduled job: {job_id} ({source}->{target}, cron={cron_expr})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add job {job_id}: {e}")
            return False
    
    def remove_job(self, job_id: str):
        """删除定时任务"""
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove job {job_id}: {e}")
            return False
    
    def pause_job(self, job_id: str):
        """暂停任务"""
        try:
            self.scheduler.pause_job(job_id)
            logger.info(f"Paused job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause job {job_id}: {e}")
            return False
    
    def resume_job(self, job_id: str):
        """恢复任务"""
        try:
            self.scheduler.resume_job(job_id)
            logger.info(f"Resumed job: {job_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to resume job {job_id}: {e}")
            return False
    
    def list_jobs(self):
        """
        列出所有任务
        
        Returns:
            list: 任务列表
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            # 尝试从 kwargs 获取元数据，如果不存在则从 args 推断
            source = job.kwargs.get('source_platform')
            target = job.kwargs.get('target_platform')
            schedule = job.kwargs.get('cron_expr')
            
            if not source and job.args and len(job.args) >= 1:
                source = job.args[0]
            if not target and job.args and len(job.args) >= 2:
                target = job.args[1]
            if not schedule:
                # 尝试从 trigger 还原 cron 表达式 (不完美但可用)
                schedule = str(job.trigger)

            jobs.append({
                'id': job.id,
                'name': job.name,
                'source': source,
                'target': target,
                'schedule': schedule,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger),
                'paused': job.next_run_time is None
            })
        return jobs
    
    def _job_executed_callback(self, event):
        """任务执行事件回调"""
        job = None
        try:
            job = self.scheduler.get_job(event.job_id)
        except Exception:
            job = None

        if event.exception:
            logger.error(f"Job {event.job_id} failed: {event.exception}")
            self._emit_and_persist_task_log(
                job,
                f'❌ 任务失败: {str(event.exception)}',
                'error'
            )
            if self.socketio:
                self.socketio.emit('scheduled_job_failed', {
                    'job_id': event.job_id,
                    'error': str(event.exception)
                })
        elif event.code == EVENT_JOB_MISSED:
            logger.warning(f"Job {event.job_id} missed its run time")
            self._emit_and_persist_task_log(
                job,
                '⚠️ 任务错过执行时间（应用未运行或超出容错时间）',
                'warning'
            )
        else:
            logger.info(f"Job {event.job_id} executed successfully")
            self._emit_and_persist_task_log(
                job,
                '✅ 调度器确认执行完成',
                'success'
            )
            if self.socketio:
                self.socketio.emit('scheduled_job_completed', {
                    'job_id': event.job_id
                })

# 全局调度器实例
_scheduler_instance = None

def get_scheduler(socketio=None):
    """获取或创建全局调度器实例"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = SyncScheduler(socketio)
    elif socketio and _scheduler_instance.socketio is None:
        _scheduler_instance.socketio = socketio
    if not _scheduler_instance.scheduler.running:
        _scheduler_instance.start()
    return _scheduler_instance

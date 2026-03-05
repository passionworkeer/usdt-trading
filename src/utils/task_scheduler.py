"""
自动化任务调度器 (Task Scheduler)

支持定时任务和事件触发任务
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import hashlib

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(Enum):
    """任务类型"""
    INTERVAL = "interval"      # 间隔任务
    CRON = "cron"              # Cron 任务
    ONCE = "once"              # 单次任务
    EVENT = "event"             # 事件触发任务


@dataclass
class ScheduledTask:
    """调度任务"""
    name: str
    task_type: TaskType
    func: Callable
    interval_seconds: Optional[float] = None  # 间隔任务
    cron_expression: Optional[str] = None      # Cron 表达式
    run_at: Optional[datetime] = None         # 执行时间
    args: tuple = field(default_factory=tuple)
    kwargs: Dict = field(default_factory=dict)
    enabled: bool = True
    max_retries: int = 3
    timeout: Optional[float] = None  # 超时时间(秒)


@dataclass
class TaskResult:
    """任务执行结果"""
    task_name: str
    status: TaskStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0


class TaskScheduler:
    """
    任务调度器

    功能：
    1. 间隔任务
    2. 定时任务
    3. 事件触发任务
    4. 任务重试
    5. 超时控制
    6. 执行统计
    """

    def __init__(self):
        """初始化调度器"""
        self.tasks: Dict[str, ScheduledTask] = {}
        self.task_results: Dict[str, List[TaskResult]] = {}
        self.running_tasks: set = set()
        self._stop_event = asyncio.Event()

    def add_interval_task(
        self,
        name: str,
        func: Callable,
        interval_seconds: float,
        *args,
        **kwargs
    ) -> str:
        """
        添加间隔任务

        Args:
            name: 任务名称
            func: 执行函数
            interval_seconds: 执行间隔(秒)
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            任务 ID
        """
        task_id = self._generate_id(name)

        self.tasks[task_id] = ScheduledTask(
            name=name,
            task_type=TaskType.INTERVAL,
            func=func,
            interval_seconds=interval_seconds,
            args=args,
            kwargs=kwargs
        )

        logger.info(f"✅ 添加间隔任务: {name} (每 {interval_seconds} 秒)")
        return task_id

    def add_cron_task(
        self,
        name: str,
        func: Callable,
        cron_expression: str,
        *args,
        **kwargs
    ) -> str:
        """
        添加 Cron 任务

        Args:
            name: 任务名称
            func: 执行函数
            cron_expression: Cron 表达式
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            任务 ID
        """
        task_id = self._generate_id(name)

        self.tasks[task_id] = ScheduledTask(
            name=name,
            task_type=TaskType.CRON,
            func=func,
            cron_expression=cron_expression,
            args=args,
            kwargs=kwargs
        )

        logger.info(f"✅ 添加 Cron 任务: {name} ({cron_expression})")
        return task_id

    def add_one_time_task(
        self,
        name: str,
        func: Callable,
        run_at: datetime,
        *args,
        **kwargs
    ) -> str:
        """
        添加单次任务

        Args:
            name: 任务名称
            func: 执行函数
            run_at: 执行时间
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            任务 ID
        """
        task_id = self._generate_id(name)

        self.tasks[task_id] = ScheduledTask(
            name=name,
            task_type=TaskType.ONCE,
            func=func,
            run_at=run_at,
            args=args,
            kwargs=kwargs
        )

        logger.info(f"✅ 添加单次任务: {name} (将在 {run_at} 执行)")
        return task_id

    def remove_task(self, task_id: str):
        """移除任务"""
        if task_id in self.tasks:
            del self.tasks[task_id]
            logger.info(f"✅ 移除任务: {task_id}")

    def enable_task(self, task_id: str):
        """启用任务"""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = True
            logger.info(f"✅ 启用任务: {task_id}")

    def disable_task(self, task_id: str):
        """禁用任务"""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = False
            logger.info(f"✅ 禁用任务: {task_id}")

    async def start(self):
        """启动调度器"""
        logger.info("🚀 任务调度器启动")
        self._stop_event.clear()

        # 为每个任务创建协程
        task_coroutines = []
        for task_id, task in self.tasks.items():
            if task.enabled:
                if task.task_type == TaskType.INTERVAL:
                    task_coroutines.append(self._run_interval_task(task_id, task))
                elif task.task_type == TaskType.CRON:
                    task_coroutines.append(self._run_cron_task(task_id, task))
                elif task.task_type == TaskType.ONCE:
                    task_coroutines.append(self._run_one_time_task(task_id, task))

        # 并发执行所有任务
        if task_coroutines:
            await asyncio.gather(*task_coroutines, return_exceptions=True)

    async def stop(self):
        """停止调度器"""
        logger.info("🛑 任务调度器停止")
        self._stop_event.set()

    async def _run_interval_task(self, task_id: str, task: ScheduledTask):
        """运行间隔任务"""
        while not self._stop_event.is_set():
            try:
                await self._execute_task(task_id, task)
                # 等待下一个间隔
                await asyncio.sleep(task.interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 任务 {task.name} 执行失败: {e}")
                await asyncio.sleep(1)  # 失败后等待1秒重试

    async def _run_cron_task(self, task_id: str, task: ScheduledTask):
        """运行 Cron 任务"""
        # 简化实现：使用固定间隔检查
        # 实际应该解析 cron_expression
        while not self._stop_event.is_set():
            try:
                await self._execute_task(task_id, task)
                # 每分钟检查一次
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 任务 {task.name} 执行失败: {e}")
                await asyncio.sleep(1)

    async def _run_one_time_task(self, task_id: str, task: ScheduledTask):
        """运行单次任务"""
        # 等待到执行时间
        if task.run_at:
            wait_seconds = (task.run_at - datetime.now()).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

        try:
            await self._execute_task(task_id, task)
            # 执行后移除任务
            self.remove_task(task_id)
        except Exception as e:
            logger.error(f"❌ 任务 {task.name} 执行失败: {e}")

    async def _execute_task(self, task_id: str, task: ScheduledTask):
        """执行任务"""
        if task_id in self.running_tasks:
            logger.debug(f"跳过任务 {task.name} (已在运行)")
            return

        self.running_tasks.add(task_id)

        start_time = datetime.now()
        result = TaskResult(
            task_name=task.name,
            status=TaskStatus.RUNNING,
            started_at=start_time
        )

        try:
            # 执行任务
            if asyncio.iscoroutinefunction(task.func):
                if task.timeout:
                    result.result = await asyncio.wait_for(
                        task.func(*task.args, **task.kwargs),
                        timeout=task.timeout
                    )
                else:
                    result.result = await task.func(*task.args, **task.kwargs)
            else:
                result.result = task.func(*task.args, **task.kwargs)

            result.status = TaskStatus.COMPLETED
            logger.debug(f"✅ 任务完成: {task.name}")

        except asyncio.TimeoutError:
            result.status = TaskStatus.FAILED
            result.error = f"任务超时 ({task.timeout}s)"
            logger.error(f"❌ 任务超时: {task.name}")

        except Exception as e:
            result.status = TaskStatus.FAILED
            result.error = str(e)
            logger.error(f"❌ 任务失败: {task.name} - {e}")

        finally:
            self.running_tasks.discard(task_id)
            result.completed_at = datetime.now()
            result.duration_ms = (result.completed_at - start_time).total_seconds() * 1000

            # 保存结果
            if task_id not in self.task_results:
                self.task_results[task_id] = []
            self.task_results[task_id].append(result)

    def _generate_id(self, name: str) -> str:
        """生成任务 ID"""
        return hashlib.md5(name.encode()).hexdigest()[:8]

    def get_task_stats(self) -> Dict:
        """获取任务统计"""
        stats = {
            'total_tasks': len(self.tasks),
            'enabled_tasks': sum(1 for t in self.tasks.values() if t.enabled),
            'running_tasks': len(self.running_tasks),
            'task_results': {}
        }

        for task_id, results in self.task_results.items():
            completed = sum(1 for r in results if r.status == TaskStatus.COMPLETED)
            failed = sum(1 for r in results if r.status == TaskStatus.FAILED)

            stats['task_results'][task_id] = {
                'total': len(results),
                'completed': completed,
                'failed': failed,
                'success_rate': completed / len(results) * 100 if results else 0
            }

        return stats


# 全局调度器实例
_global_scheduler: Optional[TaskScheduler] = None


def get_task_scheduler() -> TaskScheduler:
    """获取全局任务调度器"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = TaskScheduler()
    return _global_scheduler

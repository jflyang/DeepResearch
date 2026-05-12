"""任务队列服务测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.task_queue_service import (
    TaskQueueItem,
    TaskQueueRepository,
    TaskQueueService,
    reset_queue_repo,
    reset_queue_service,
)


@pytest.fixture(autouse=True)
def clean_queue():
    """每个测试前重置队列。"""
    reset_queue_service()
    reset_queue_repo()
    yield
    reset_queue_service()
    reset_queue_repo()


@pytest.fixture
def repo():
    """创建独立的内存仓库（不读磁盘）。"""
    r = TaskQueueRepository()
    r._items = []  # 清空磁盘加载的数据
    return r


@pytest.fixture
def service(repo):
    """创建使用内存仓库的服务。"""
    return TaskQueueService(repo=repo)


class TestEnqueue:
    """入队测试。"""

    def test_enqueue_task_creates_queued_item(self, service):
        """enqueue_task 创建 queued item。"""
        item = service.enqueue_task("task-001")
        assert item.task_id == "task-001"
        assert item.status == "queued"
        assert item.priority == 100

    def test_enqueue_many(self, service):
        """批量入队。"""
        items = service.enqueue_many(["t1", "t2", "t3"])
        assert len(items) == 3
        assert all(i.status == "queued" for i in items)
        # 优先级递增
        assert items[0].priority < items[1].priority < items[2].priority

    def test_enqueue_duplicate_returns_existing(self, service):
        """重复入队返回已有项。"""
        item1 = service.enqueue_task("task-001")
        item2 = service.enqueue_task("task-001")
        assert item1.id == item2.id

    def test_enqueue_with_priority(self, service):
        """自定义优先级。"""
        item = service.enqueue_task("task-001", priority=50)
        assert item.priority == 50


class TestRunNext:
    """执行测试。"""

    @pytest.mark.asyncio
    async def test_run_next_executes_first_task(self, service):
        """run_next 执行第一个任务。"""
        service.enqueue_task("task-001")

        # Mock _execute_task
        service._execute_task = AsyncMock()

        item = await service.run_next()
        assert item is not None
        assert item.task_id == "task-001"
        service._execute_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_worker_one_at_a_time(self, service):
        """单 worker 同时只跑一个。"""
        service.enqueue_task("task-001")
        service.enqueue_task("task-002")

        # 手动设置第一个为 running
        pending = service._repo.get_pending(limit=1)
        service._repo.update_status(pending[0].id, "running")

        # run_next 应该返回 None（已有 running）
        result = await service.run_next()
        assert result is None

    @pytest.mark.asyncio
    async def test_task_failure_continues_next(self, service):
        """task 失败后下一个任务继续。"""
        service.enqueue_task("task-001")
        service.enqueue_task("task-002")

        # 第一个任务失败
        service._execute_task = AsyncMock(side_effect=Exception("fail"))
        item1 = await service.run_next()
        assert item1.status == "failed"

        # 第二个任务成功
        service._execute_task = AsyncMock()
        item2 = await service.run_next()
        assert item2 is not None
        assert item2.task_id == "task-002"
        assert item2.status == "completed"

    @pytest.mark.asyncio
    async def test_empty_queue_returns_none(self, service):
        """空队列返回 None。"""
        result = await service.run_next()
        assert result is None


class TestCancel:
    """取消测试。"""

    def test_cancel_queued_task(self, service):
        """cancel queued task。"""
        service.enqueue_task("task-001")
        success = service.cancel_task("task-001")
        assert success

        # 验证状态
        item = service._repo.get_by_task_id("task-001")
        assert item.status == "cancelled"

    def test_cancel_running_task_fails(self, service):
        """不能取消正在运行的任务。"""
        service.enqueue_task("task-001")
        # 手动设为 running
        item = service._repo.get_by_task_id("task-001")
        service._repo.update_status(item.id, "running")

        success = service.cancel_task("task-001")
        assert not success

    def test_cancel_nonexistent_task(self, service):
        """取消不存在的任务返回 False。"""
        success = service.cancel_task("nonexistent")
        assert not success


class TestRetry:
    """重试测试。"""

    def test_retry_failed_task(self, service):
        """retry failed task。"""
        service.enqueue_task("task-001")
        item = service._repo.get_by_task_id("task-001")
        service._repo.update_status(item.id, "failed", error_message="some error")

        result = service.retry_task("task-001")
        assert result is not None
        assert result.status == "queued"
        assert result.error_message == ""

    def test_retry_queued_task_fails(self, service):
        """不能重试排队中的任务。"""
        service.enqueue_task("task-001")
        result = service.retry_task("task-001")
        assert result is None


class TestPriority:
    """优先级排序测试。"""

    def test_priority_ordering(self, service):
        """priority 排序生效。"""
        service.enqueue_task("low-priority", priority=200)
        service.enqueue_task("high-priority", priority=50)
        service.enqueue_task("medium-priority", priority=100)

        pending = service.get_pending()
        assert pending[0].task_id == "high-priority"
        assert pending[1].task_id == "medium-priority"
        assert pending[2].task_id == "low-priority"

    @pytest.mark.asyncio
    async def test_highest_priority_runs_first(self, service):
        """最高优先级的任务先执行。"""
        service.enqueue_task("low", priority=200)
        service.enqueue_task("high", priority=10)

        service._execute_task = AsyncMock()
        item = await service.run_next()
        assert item.task_id == "high"


class TestQueueStatus:
    """队列状态测试。"""

    def test_queue_status_groups(self, service):
        """get_queue_status 正确分组。"""
        service.enqueue_task("queued-1")
        service.enqueue_task("queued-2")

        # 手动设置一些状态
        item = service._repo.get_by_task_id("queued-2")
        service._repo.update_status(item.id, "completed")

        status = service.get_queue_status()
        assert status.total_queued == 1
        assert status.total_completed == 1
        assert len(status.queued) == 1
        assert len(status.completed_recent) == 1

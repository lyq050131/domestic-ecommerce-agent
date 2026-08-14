"""后台任务管理器：长任务（自动投放等）提交到守护线程执行，前端轮询状态"""
import threading
import time
import uuid
from typing import Callable, Dict, Optional


class TaskManager:
    """内存任务表 + 守护线程执行；超容量自动清理最旧的已完成任务"""

    def __init__(self, max_tasks: int = 50):
        self._tasks: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._max_tasks = max_tasks

    def submit(self, name: str, fn: Callable, *args, **kwargs) -> str:
        """提交任务，立即返回 task_id；fn 可接收 progress_cb(msg) 回调更新进度"""
        tid = uuid.uuid4().hex[:12]
        with self._lock:
            self._tasks[tid] = {
                "id": tid, "name": name, "status": "running", "progress": "任务已提交",
                "result": None, "error": None,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"), "finished_at": None,
            }
            if len(self._tasks) > self._max_tasks:
                for k in [k for k, t in self._tasks.items() if t["status"] != "running"][: len(self._tasks) - self._max_tasks]:
                    self._tasks.pop(k, None)

        def _progress(msg: str) -> None:
            with self._lock:
                t = self._tasks.get(tid)
                if t:
                    t["progress"] = msg

        def _run() -> None:
            try:
                result = fn(*args, progress_cb=_progress, **kwargs)
                with self._lock:
                    t = self._tasks.get(tid)
                    if t:
                        t["status"] = "success"
                        t["progress"] = "完成"
                        t["result"] = result
                        t["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:  # noqa: BLE001
                with self._lock:
                    t = self._tasks.get(tid)
                    if t:
                        t["status"] = "failed"
                        t["progress"] = "失败"
                        t["error"] = str(e)
                        t["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

        threading.Thread(target=_run, name="task-" + tid, daemon=True).start()
        return tid

    def get(self, tid: str) -> Optional[dict]:
        with self._lock:
            t = self._tasks.get(tid)
            return dict(t) if t else None


task_manager = TaskManager()

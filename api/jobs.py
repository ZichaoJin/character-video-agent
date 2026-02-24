"""
线程安全的任务状态管理（内存存储）。
生产环境可替换为 Redis。
"""
import threading
from typing import Optional

_lock = threading.Lock()
_store: dict = {}


def create(job_id: str):
    with _lock:
        _store[job_id] = {
            "status": "queued",   # queued | running | done | error
            "progress": 0,
            "step": "",
            "video_url": None,
            "error": None,
        }


def update(job_id: str, **kwargs):
    with _lock:
        if job_id in _store:
            _store[job_id].update(kwargs)


def get(job_id: str) -> Optional[dict]:
    with _lock:
        return dict(_store.get(job_id, {}))


def exists(job_id: str) -> bool:
    with _lock:
        return job_id in _store

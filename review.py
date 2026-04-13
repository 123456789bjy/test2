"""
待审核任务存储：
- redis：Hash 存任务体；Sorted Set 按时间排序 / 区分 pending；List 作待复核消息队列（LPUSH，供 BRPOP 消费）。
- json：本地 JSON 文件（无 Redis 时将 review_tasks_backend 设为 "json"）。
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from typing import Any

import config_data as config

_DEFAULT_PATH = config.review_tasks_path
_BACKEND = getattr(config, "review_tasks_backend", "redis").lower()
_PREFIX = getattr(config, "review_tasks_redis_prefix", "review")

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    import redis

    pw = getattr(config, "redis_password", None)
    _redis_client = redis.Redis(
        host=getattr(config, "redis_host", "127.0.0.1"),
        port=int(getattr(config, "redis_port", 6379)),
        db=int(getattr(config, "redis_db", 0)),
        password=pw if pw else None,
        decode_responses=True,
    )
    return _redis_client


def _k_task(task_id: str) -> str:
    return f"{_PREFIX}:task:{task_id}"


def _k_z_all() -> str:
    return f"{_PREFIX}:z:all"


def _k_z_pending() -> str:
    return f"{_PREFIX}:z:pending"


def _k_mq_pending() -> str:
    return f"{_PREFIX}:mq:pending"


def _task_to_hash_row(d: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        if v is None:
            out[k] = ""
        else:
            out[k] = str(v)
    return out


def _hash_to_task(h: dict[str, str]) -> dict[str, Any]:
    t: dict[str, Any] = dict(h)
    if t.get("reviewed_at") == "":
        t["reviewed_at"] = None
    return t


# --- JSON backend ---


def _ensure_path(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)


def _load_all(path: str | None = None) -> list[dict[str, Any]]:
    path = path or _DEFAULT_PATH
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _save_all(rows: list[dict[str, Any]], path: str | None = None) -> None:
    path = path or _DEFAULT_PATH
    _ensure_path(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def append_pending_task(
    *,
    session_id: str,
    question: str,
    answer: str,
    basis: str,
    path: str | None = None,
) -> str:
    if _BACKEND == "json":
        return _append_pending_task_json(
            session_id=session_id,
            question=question,
            answer=answer,
            basis=basis,
            path=path,
        )
    return _append_pending_task_redis(
        session_id=session_id,
        question=question,
        answer=answer,
        basis=basis,
    )


def _append_pending_task_json(
    *,
    session_id: str,
    question: str,
    answer: str,
    basis: str,
    path: str | None = None,
) -> str:
    path = path or _DEFAULT_PATH
    rows = _load_all(path)
    task_id = str(uuid.uuid4())
    rows.append(
        {
            "task_id": task_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "question": question,
            "answer": answer,
            "basis": basis,
            "status": "pending",
            "reviewed_at": None,
            "reviewer_note": "",
        }
    )
    _save_all(rows, path)
    return task_id


def _append_pending_task_redis(
    *,
    session_id: str,
    question: str,
    answer: str,
    basis: str,
) -> str:
    r = _get_redis()
    task_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat(timespec="seconds")
    score = time.time()
    row = {
        "task_id": task_id,
        "created_at": created_at,
        "session_id": session_id,
        "question": question,
        "answer": answer,
        "basis": basis,
        "status": "pending",
        "reviewed_at": "",
        "reviewer_note": "",
    }
    pipe = r.pipeline()
    pipe.hset(_k_task(task_id), mapping=_task_to_hash_row(row))
    pipe.zadd(_k_z_all(), {task_id: score})
    pipe.zadd(_k_z_pending(), {task_id: score})
    mq_payload = json.dumps(
        {"task_id": task_id, "created_at": created_at, "session_id": session_id, "kind": "pending_review"},
        ensure_ascii=False,
    )
    pipe.lpush(_k_mq_pending(), mq_payload)
    pipe.execute()
    return task_id


def list_tasks(status: str | None = None, path: str | None = None) -> list[dict[str, Any]]:
    if _BACKEND == "json":
        rows = _load_all(path)
        if status:
            return [r for r in rows if r.get("status") == status]
        return rows
    return _list_tasks_redis(status)


def _list_tasks_redis(status: str | None) -> list[dict[str, Any]]:
    r = _get_redis()
    if status == "pending":
        ids = r.zrange(_k_z_pending(), 0, -1)
    elif status is None:
        ids = r.zrange(_k_z_all(), 0, -1)
    else:
        ids = r.zrange(_k_z_all(), 0, -1)
        out: list[dict[str, Any]] = []
        for tid in ids:
            h = r.hgetall(_k_task(tid))
            if not h:
                continue
            t = _hash_to_task(h)
            if t.get("status") == status:
                out.append(t)
        return out

    out = []
    for tid in ids:
        h = r.hgetall(_k_task(tid))
        if h:
            out.append(_hash_to_task(h))
    return out


def update_task(
    task_id: str,
    *,
    status: str,
    reviewer_note: str = "",
    path: str | None = None,
) -> bool:
    if _BACKEND == "json":
        return _update_task_json(task_id, status=status, reviewer_note=reviewer_note, path=path)
    return _update_task_redis(task_id, status=status, reviewer_note=reviewer_note)


def _update_task_json(
    task_id: str,
    *,
    status: str,
    reviewer_note: str = "",
    path: str | None = None,
) -> bool:
    path = path or _DEFAULT_PATH
    rows = _load_all(path)
    for row in rows:
        if row.get("task_id") == task_id:
            row["status"] = status
            row["reviewed_at"] = datetime.now().isoformat(timespec="seconds")
            row["reviewer_note"] = reviewer_note
            _save_all(rows, path)
            return True
    return False


def _update_task_redis(task_id: str, *, status: str, reviewer_note: str = "") -> bool:
    r = _get_redis()
    key = _k_task(task_id)
    if not r.exists(key):
        return False
    reviewed_at = datetime.now().isoformat(timespec="seconds")
    r.hset(
        key,
        mapping={
            "status": status,
            "reviewed_at": reviewed_at,
            "reviewer_note": reviewer_note or "",
        },
    )
    r.zrem(_k_z_pending(), task_id)
    return True


def store_diagnostics() -> dict[str, Any]:
    """供界面展示：存储后端类型、Redis 是否连通。"""
    out: dict[str, Any] = {"backend": _BACKEND, "redis_ok": None, "redis_error": None}
    if _BACKEND != "redis":
        return out
    try:
        r = _get_redis()
        r.ping()
        out["redis_ok"] = True
    except Exception as e:
        out["redis_ok"] = False
        out["redis_error"] = str(e)
    return out


def brpop_pending_queue(timeout: int = 0) -> dict[str, Any] | None:
    """
    阻塞式从待复核消息队列取一条（与 append 时 LPUSH 对应，使用 BRPOP）。
    timeout：0 表示一直阻塞；正整数为秒。供独立复核消费者进程演示。
    """
    if _BACKEND != "redis":
        return None
    r = _get_redis()
    out = r.brpop(_k_mq_pending(), timeout=timeout)
    if not out:
        return None
    _, payload = out
    return json.loads(payload)

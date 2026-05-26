import os
import queue
import threading
from datetime import datetime
from app.shared import (
    task_queue, processing_event, pause_event, abort_event,
    cancelled_task_ids, CANCELLED_TASK_LOCK,
    send_sse, logger,
    set_current_mode,
    get_interrupted, clear_interrupted,
    UPLOAD_DIR,
)
from app.processor import process_file

_worker_stop_event = threading.Event()

def queue_worker():
    while not _worker_stop_event.is_set():
        if pause_event.is_set():
            pause_event.wait(1)
            continue
        try:
            if get_interrupted():
                raw_item = get_interrupted()
                clear_interrupted()
            else:
                raw_item = task_queue.get(timeout=1)

            result = _extract_task_from_queue_item(raw_item)
            if result[0] is None:
                task_id = result[8]
                parent_id = None
                try:
                    from app.task_store import get as ts_get
                    t = ts_get(task_id)
                    if t:
                        parent_id = t.parent_task_id
                except Exception:
                    pass
                with CANCELLED_TASK_LOCK:
                    if task_id in cancelled_task_ids:
                        cancelled_task_ids.discard(task_id)
                send_sse("result", {
                    "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                    "file": task_id[:8],
                    "queue_id": task_id,
                    "task_id": task_id,
                    "status": "cancelled",
                    "message": "已从队列中移除",
                    "parent_group_id": parent_id,
                })
                processing_event.clear()
                send_sse("status", {"queue_size": task_queue.qsize(), "processing": False, "paused": pause_event.is_set()})
                continue
            filepath, original_name, enqueued_mode, group_id, chunk_index, total_chunks, chunk_ext, queue_id = result

            if filepath is None or not os.path.exists(filepath):
                send_sse("result", {
                    "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                    "file": original_name or (queue_id or '')[:8],
                    "queue_id": queue_id,
                    "task_id": queue_id,
                    "status": "error",
                    "message": "文件不存在或已被清理"
                })
                processing_event.clear()
                send_sse("status", {"queue_size": task_queue.qsize(), "processing": False, "paused": pause_event.is_set()})
                continue

            if enqueued_mode:
                set_current_mode(enqueued_mode)
            processing_event.set()
            send_sse("status", {"queue_size": task_queue.qsize(), "processing": True, "paused": False})
            process_file(filepath, original_name, queue_id, group_id, chunk_index, total_chunks, chunk_ext)
            processing_event.clear()
            send_sse("status", {"queue_size": task_queue.qsize(), "processing": False, "paused": pause_event.is_set()})
            if task_queue.qsize() == 0:
                send_sse("log", {"level": "success", "message": "队列已清空，所有文件处理完毕"})
        except queue.Empty:
            continue
        except Exception as e:
            logger.exception(f"Queue worker error: {e}")
            processing_event.clear()
            send_sse("status", {"queue_size": task_queue.qsize(), "processing": False, "paused": pause_event.is_set()})

def start_worker():
    _worker_stop_event.clear()
    threading.Thread(target=queue_worker, daemon=True).start()

def stop_worker():
    _worker_stop_event.set()

def cleanup_upload_dir(keep=20):
    if not UPLOAD_DIR.exists():
        return 0
    active = set()
    try:
        from app.task_store import get_active_filepaths
        active = set(os.path.abspath(p) for p in get_active_filepaths())
    except Exception:
        pass

    def _safe_mtime(p):
        try:
            return p.stat().st_mtime
        except OSError:
            return 0

    files = sorted(UPLOAD_DIR.glob("*"), key=_safe_mtime, reverse=True)
    removed = 0
    for f in files[keep:]:
        if os.path.abspath(str(f)) in active:
            continue
        try:
            f.unlink()
            removed += 1
        except OSError:
            pass
    return removed

def start_cleanup_scheduler(interval=300, keep=20):
    def _run():
        while not _worker_stop_event.is_set():
            _worker_stop_event.wait(interval)
            if _worker_stop_event.is_set():
                break
            cleanup_upload_dir(keep=keep)
    threading.Thread(target=_run, daemon=True).start()

def get_queue_info():
    return {
        "queue_size": task_queue.qsize(),
        "processing": processing_event.is_set(),
        "paused": pause_event.is_set(),
    }

def get_queue_info_v2():
    """新队列系统的状态查询"""
    return {
        "state": "paused" if pause_event.is_set() else ("processing" if processing_event.is_set() else "idle"),
        "size": task_queue.qsize(),
        "processing": processing_event.is_set(),
        "paused": pause_event.is_set(),
    }

def enqueue_task_id(task_id):
    """新体系入队：将 task_id 字符串放入队列"""
    with CANCELLED_TASK_LOCK:
        if task_id in cancelled_task_ids:
            cancelled_task_ids.discard(task_id)
            return False
    task_queue.put(task_id)
    return True

def purge_cancelled_from_queue():
    """清空排队通道中所有已标记为'已取消'的排队票，以免挡到新票"""
    with CANCELLED_TASK_LOCK:
        cancelled = set(cancelled_task_ids)
    if not cancelled:
        return 0
    removed = 0
    kept = []
    while not task_queue.empty():
        try:
            item = task_queue.get_nowait()
        except queue.Empty:
            break
        if isinstance(item, str) and item in cancelled:
            removed += 1
        else:
            kept.append(item)
    for item in kept:
        task_queue.put(item)
    return removed

def _extract_task_from_queue_item(item):
    """兼容处理：识别队列中的任务是旧元组还是新 task_id 字符串"""
    if isinstance(item, str):
        with CANCELLED_TASK_LOCK:
            if item in cancelled_task_ids:
                cancelled_task_ids.discard(item)
                parent_id = None
                try:
                    from app.task_store import get as ts_get
                    t = ts_get(item)
                    if t:
                        parent_id = t.parent_task_id
                except Exception:
                    pass
                send_sse("result", {
                    "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
                    "file": item[:8],
                    "queue_id": item,
                    "task_id": item,
                    "status": "cancelled",
                    "message": "已从队列中移除",
                    "parent_group_id": parent_id,
                })
                processing_event.clear()
                send_sse("status", {"queue_size": task_queue.qsize(), "processing": False, "paused": pause_event.is_set()})
                return None, None, None, None, None, None, None, None, item
        from app.task_store import get as task_store_get
        task = task_store_get(item)
        if task is None:
            return None, None, None, None, None, None, None, None, item
        if task.status.value in ("cancelled", "failed"):
            return None, None, None, None, None, None, None, None, item
        chunk_ext = task.file_ext or None
        return (task.filepath, task.display_name, task.mode.value,
                task.parent_task_id, task.chunk_index, task.total_chunks,
                chunk_ext, task.task_id)
    filepath, original_name = item[0], item[1]
    enqueued_mode = item[2] if len(item) >= 3 else "desensitize"
    group_id = item[3] if len(item) >= 4 and item[3] is not None else None
    chunk_index = item[4] if len(item) >= 5 and item[4] is not None else 0
    total_chunks = item[5] if len(item) >= 6 and item[5] is not None else 1
    chunk_ext = item[6] if len(item) >= 7 and item[6] is not None else None
    queue_id = item[7] if len(item) >= 8 else None
    return filepath, original_name, enqueued_mode, group_id, chunk_index, total_chunks, chunk_ext, queue_id

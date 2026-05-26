import json
import sqlite3
import threading
from datetime import datetime
from app.shared import BASE_DIR, logger, TaskState, TaskStatus, QueueMode

DB_PATH = BASE_DIR / "task_store.db"
_LOCK = threading.Lock()

def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_store (
                    task_id TEXT PRIMARY KEY,
                    parent_task_id TEXT,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'waiting',
                    display_name TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    filepath TEXT,
                    is_chunk INTEGER DEFAULT 0,
                    chunk_index INTEGER DEFAULT 0,
                    total_chunks INTEGER DEFAULT 1,
                    file_ext TEXT DEFAULT '',
                    checkpoint TEXT DEFAULT '',
                    checkpoint_data TEXT,
                    error_message TEXT DEFAULT '',
                    result_json TEXT,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    started_at TEXT,
                    completed_at TEXT
                )
            """)
            conn.commit()
            logger.info("task_store.db 初始化完成")
        finally:
            conn.close()

def save(task):
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO task_store
                    (task_id, parent_task_id, mode, status, display_name,
                     original_name, filepath, is_chunk, chunk_index, total_chunks,
                     file_ext, checkpoint, checkpoint_data, error_message, result_json,
                     created_at, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.task_id,
                task.parent_task_id,
                task.mode.value,
                task.status.value,
                task.display_name,
                task.original_name,
                task.filepath,
                1 if task.is_chunk else 0,
                task.chunk_index,
                task.total_chunks,
                task.file_ext,
                task.checkpoint,
                json.dumps(task.checkpoint_data, ensure_ascii=False) if task.checkpoint_data else None,
                task.error_message,
                json.dumps(task.result, ensure_ascii=False) if task.result else None,
                task.created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                task.started_at,
                task.completed_at,
            ))
            conn.commit()
        finally:
            conn.close()

def update_status(task_id, status, error_message=""):
    with _LOCK:
        conn = _get_conn()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if status == TaskStatus.PROCESSING:
                conn.execute(
                    "UPDATE task_store SET status=?, started_at=? WHERE task_id=?",
                    (status.value, now, task_id)
                )
            elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                conn.execute(
                    "UPDATE task_store SET status=?, completed_at=? WHERE task_id=?",
                    (status.value, now, task_id)
                )
            else:
                conn.execute(
                    "UPDATE task_store SET status=? WHERE task_id=?",
                    (status.value, task_id)
                )
            if error_message:
                conn.execute(
                    "UPDATE task_store SET error_message=? WHERE task_id=?",
                    (error_message, task_id)
                )
            conn.commit()
        finally:
            conn.close()

def update_checkpoint(task_id, checkpoint, checkpoint_data):
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE task_store SET checkpoint=?, checkpoint_data=? WHERE task_id=?",
                (checkpoint, json.dumps(checkpoint_data, ensure_ascii=False) if checkpoint_data else None, task_id)
            )
            conn.commit()
        finally:
            conn.close()

def update_result(task_id, result):
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE task_store SET result_json=? WHERE task_id=?",
                (json.dumps(result, ensure_ascii=False) if result else None, task_id)
            )
            conn.commit()
        finally:
            conn.close()

def get(task_id):
    with _LOCK:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM task_store WHERE task_id=?", (task_id,)).fetchone()
            if not row:
                return None
            return _row_to_task(row)
        finally:
            conn.close()

def get_children(parent_task_id):
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM task_store WHERE parent_task_id=? ORDER BY chunk_index ASC",
                (parent_task_id,)
            ).fetchall()
            return [_row_to_task(r) for r in rows]
        finally:
            conn.close()

def get_by_mode(mode, status=None, limit=100):
    with _LOCK:
        conn = _get_conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM task_store WHERE mode=? AND status=? AND is_chunk=0 ORDER BY created_at DESC LIMIT ?",
                    (mode.value if isinstance(mode, QueueMode) else mode, status.value if isinstance(status, TaskStatus) else status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM task_store WHERE mode=? AND is_chunk=0 ORDER BY created_at DESC LIMIT ?",
                    (mode.value if isinstance(mode, QueueMode) else mode, limit)
                ).fetchall()
            return [_row_to_task(r) for r in rows]
        finally:
            conn.close()

def get_recent_completed(mode, limit=50):
    return get_by_mode(mode, TaskStatus.COMPLETED, limit)

def get_active_filepaths():
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT filepath FROM task_store WHERE status IN (?, ?)",
                (TaskStatus.WAITING.value, TaskStatus.PROCESSING.value)
            ).fetchall()
            return list(set(r["filepath"] for r in rows if r["filepath"]))
        finally:
            conn.close()

def delete(task_id):
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM task_store WHERE task_id=?", (task_id,))
            conn.commit()
        finally:
            conn.close()

def delete_children(parent_task_id):
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM task_store WHERE parent_task_id=?", (parent_task_id,))
            conn.commit()
        finally:
            conn.close()

def _row_to_task(row):
    cp_data = None
    if row["checkpoint_data"]:
        try:
            cp_data = json.loads(row["checkpoint_data"])
        except (json.JSONDecodeError, TypeError):
            cp_data = None

    result = None
    if row["result_json"]:
        try:
            result = json.loads(row["result_json"])
        except (json.JSONDecodeError, TypeError):
            result = None

    return TaskState(
        task_id=row["task_id"],
        display_name=row["display_name"],
        original_name=row["original_name"],
        filepath=row["filepath"] or "",
        mode=QueueMode(row["mode"]),
        status=TaskStatus(row["status"]),
        is_chunk=bool(row["is_chunk"]),
        parent_task_id=row["parent_task_id"],
        chunk_index=row["chunk_index"] or 0,
        total_chunks=row["total_chunks"] or 1,
        file_ext=row["file_ext"] or "",
        checkpoint=row["checkpoint"] or "",
        checkpoint_data=cp_data,
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        error_message=row["error_message"] or "",
        result=result,
    )

init_db()

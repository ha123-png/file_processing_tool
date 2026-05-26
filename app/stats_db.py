import sqlite3
import threading
from pathlib import Path
from app.shared import BASE_DIR, logger

DB_PATH = BASE_DIR / "stats.db"
_LOCK = threading.Lock()

def _get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_db():
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT UNIQUE,
                    file_name TEXT,
                    mode TEXT,
                    duration INTEGER,
                    regex_count INTEGER,
                    llm_count INTEGER,
                    replacement_total INTEGER,
                    original_length INTEGER,
                    desensitized_length INTEGER,
                    is_large INTEGER DEFAULT 0,
                    total_chunks INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'completed',
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.commit()
            logger.info("stats.db 初始化完成")
        finally:
            conn.close()

def insert_stats(task_id, file_name, mode, duration, regex_count, llm_count,
                 replacement_total, original_length, desensitized_length,
                 is_large=0, total_chunks=1, status="completed"):
    try:
        with _LOCK:
            conn = _get_conn()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO stats
                        (task_id, file_name, mode, duration, regex_count, llm_count,
                         replacement_total, original_length, desensitized_length,
                         is_large, total_chunks, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (task_id, file_name, mode, duration, regex_count, llm_count,
                      replacement_total, original_length, desensitized_length,
                      is_large, total_chunks, status))
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        logger.warning(f"stats 写入失败（非致命）: {e}")

def get_dashboard_data(mode=None):
    mode_filter = "AND mode = ?" if mode else ""
    params = (mode,) if mode else ()
    with _LOCK:
        conn = _get_conn()
        try:
            cur = conn.execute(f"SELECT COUNT(*) FROM stats WHERE status='completed' {mode_filter}", params)
            total_files = cur.fetchone()[0] or 0

            cur = conn.execute(f"SELECT COALESCE(SUM(replacement_total),0) FROM stats WHERE status='completed' {mode_filter}", params)
            total_replacements = cur.fetchone()[0] or 0

            cur = conn.execute(f"SELECT COALESCE(AVG(duration), 0) FROM stats WHERE status='completed' {mode_filter}", params)
            avg_duration = round(cur.fetchone()[0] or 0, 1)

            cur = conn.execute(f"SELECT COALESCE(SUM(duration), 0) FROM stats WHERE status='completed' {mode_filter}", params)
            total_duration = cur.fetchone()[0] or 0

            cur = conn.execute(f"SELECT COUNT(*) FROM stats WHERE status='error' {mode_filter}", params)
            error_count = cur.fetchone()[0] or 0

            cur = conn.execute(f"SELECT COUNT(*) FROM stats WHERE is_large=1 AND status='completed' {mode_filter}", params)
            large_task_count = cur.fetchone()[0] or 0

            total_tasks = total_files + error_count
            error_rate = round(error_count / total_tasks, 3) if total_tasks > 0 else 0

            today_expr = "date(created_at) = date('now','localtime')"
            today_mode = f"AND mode = ?" if mode else ""
            cur = conn.execute(f"SELECT COUNT(*), COALESCE(SUM(replacement_total),0), COALESCE(AVG(duration),0), COUNT(CASE WHEN status='error' THEN 1 END) FROM stats WHERE {today_expr} {today_mode} AND status IN ('completed','error')", params)
            t = cur.fetchone()
            today_files = t[0] or 0
            today_replacements = t[1] or 0
            today_avg_duration = round(t[2] or 0, 1)
            today_errors = t[3] or 0

            trend_mode = f"AND mode = '{mode}'" if mode else ""
            cur = conn.execute(f"""
                SELECT date(created_at) as d, COUNT(*) as cnt, COALESCE(SUM(replacement_total),0) as rep
                FROM stats
                WHERE status='completed' {trend_mode} AND created_at >= datetime('now','localtime','-30 days')
                GROUP BY d
                ORDER BY d ASC
            """)
            trend = [{"date": r[0], "count": r[1], "replacements": r[2]} for r in cur.fetchall()]

            return {
                "summary": {
                    "total_files": total_files,
                    "total_replacements": total_replacements,
                    "avg_duration": avg_duration,
                    "total_duration": total_duration,
                    "error_count": error_count,
                    "error_rate": error_rate,
                    "large_task_count": large_task_count
                },
                "today": {
                    "files": today_files,
                    "replacements": today_replacements,
                    "avg_duration": today_avg_duration,
                    "errors": today_errors
                },
                "trend_30d": trend
            }
        finally:
            conn.close()

def clear_stats():
    with _LOCK:
        conn = _get_conn()
        try:
            cur = conn.execute("SELECT COUNT(*) FROM stats")
            count = cur.fetchone()[0] or 0
            conn.execute("DELETE FROM stats")
            conn.commit()
            return count
        finally:
            conn.close()

init_db()

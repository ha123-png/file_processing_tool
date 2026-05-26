import os
import sys
import uuid
import json
import time
import threading
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.shared import TaskStatus, QueueMode, TaskState


@pytest.fixture
def isolated_db():
    import app.task_store as ts

    orig_db_path = ts.DB_PATH
    orig_lock = ts._LOCK

    fd, tmp_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    ts.DB_PATH = tmp_db
    ts._LOCK = threading.Lock()
    ts.init_db()

    yield ts

    ts.DB_PATH = orig_db_path
    ts._LOCK = orig_lock
    ts.init_db()

    if os.path.exists(tmp_db):
        os.unlink(tmp_db)
        wal = tmp_db + "-wal"
        shm = tmp_db + "-shm"
        if os.path.exists(wal):
            os.unlink(wal)
        if os.path.exists(shm):
            os.unlink(shm)


def _make_task(task_id=None, mode=None, status=None, display_name="test.txt",
               original_name="test.txt", filepath="/tmp/test.txt", **kwargs):
    if mode is None:
        mode = QueueMode.DESENSITIZE
    if status is None:
        status = TaskStatus.WAITING
    if task_id is None:
        task_id = uuid.uuid4().hex

    defaults = {
        "task_id": task_id,
        "display_name": display_name,
        "original_name": original_name,
        "filepath": filepath,
        "mode": mode,
        "status": status,
    }
    defaults.update(kwargs)
    return TaskState(**defaults)


class TestInitDb:
    def test_table_exists(self, isolated_db):
        ts = isolated_db
        conn = ts._get_conn()
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='task_store'"
            )
            row = cursor.fetchone()
            assert row is not None
            assert row["name"] == "task_store"
        finally:
            conn.close()

    def test_table_has_required_columns(self, isolated_db):
        ts = isolated_db
        conn = ts._get_conn()
        try:
            cursor = conn.execute("PRAGMA table_info(task_store)")
            columns = {row["name"] for row in cursor.fetchall()}
            required = {
                "task_id", "parent_task_id", "mode", "status", "display_name",
                "original_name", "filepath", "is_chunk", "chunk_index",
                "total_chunks", "file_ext", "checkpoint", "checkpoint_data",
                "error_message", "result_json", "created_at", "started_at", "completed_at"
            }
            assert required.issubset(columns)
        finally:
            conn.close()


class TestSave:
    def test_save_and_retrieve(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)

        retrieved = ts.get(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id
        assert retrieved.display_name == "test.txt"
        assert retrieved.status == TaskStatus.WAITING
        assert retrieved.mode == QueueMode.DESENSITIZE

    def test_save_preserves_created_at_on_update(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)

        first = ts.get(task.task_id)
        original_created_at = first.created_at

        time.sleep(1.1)

        first.status = TaskStatus.PROCESSING
        ts.save(first)

        second = ts.get(task.task_id)
        assert second.created_at == original_created_at, \
            f"created_at 被覆盖！原值={original_created_at}, 新值={second.created_at}"

    def test_save_updates_status(self, isolated_db):
        ts = isolated_db
        task = _make_task(status=TaskStatus.WAITING)
        ts.save(task)

        task.status = TaskStatus.PROCESSING
        ts.save(task)

        retrieved = ts.get(task.task_id)
        assert retrieved.status == TaskStatus.PROCESSING

    def test_save_stores_checkpoint_data(self, isolated_db):
        ts = isolated_db
        checkpoint_data = {"stage": "llm_round1", "cursor": 150, "items": [1, 2, 3]}
        task = _make_task(checkpoint="llm_round1", checkpoint_data=checkpoint_data)
        ts.save(task)

        retrieved = ts.get(task.task_id)
        assert retrieved.checkpoint == "llm_round1"
        assert retrieved.checkpoint_data == checkpoint_data

    def test_save_stores_result_json(self, isolated_db):
        ts = isolated_db
        result = {"replacements": [{"from": "张三", "to": "xxx"}], "count": 1}
        task = _make_task(result=result, status=TaskStatus.COMPLETED)
        ts.save(task)

        retrieved = ts.get(task.task_id)
        assert retrieved.result == result

    def test_save_none_checkpoint_data(self, isolated_db):
        ts = isolated_db
        task = _make_task(checkpoint_data=None)
        ts.save(task)

        retrieved = ts.get(task.task_id)
        assert retrieved.checkpoint_data is None

    def test_save_none_result(self, isolated_db):
        ts = isolated_db
        task = _make_task(result=None)
        ts.save(task)

        retrieved = ts.get(task.task_id)
        assert retrieved.result is None

    def test_save_chunk_task(self, isolated_db):
        ts = isolated_db
        task = _make_task(
            is_chunk=True, parent_task_id="parent-001",
            chunk_index=2, total_chunks=5, file_ext=".txt"
        )
        ts.save(task)

        retrieved = ts.get(task.task_id)
        assert retrieved.is_chunk is True
        assert retrieved.parent_task_id == "parent-001"
        assert retrieved.chunk_index == 2
        assert retrieved.total_chunks == 5
        assert retrieved.file_ext == ".txt"


class TestUpdateStatus:
    def test_update_to_processing_sets_started_at(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)

        ts.update_status(task.task_id, TaskStatus.PROCESSING)

        retrieved = ts.get(task.task_id)
        assert retrieved.status == TaskStatus.PROCESSING
        assert retrieved.started_at is not None

    def test_update_to_completed_sets_completed_at(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)
        ts.update_status(task.task_id, TaskStatus.PROCESSING)

        ts.update_status(task.task_id, TaskStatus.COMPLETED)

        retrieved = ts.get(task.task_id)
        assert retrieved.status == TaskStatus.COMPLETED
        assert retrieved.completed_at is not None

    def test_update_to_failed_sets_completed_at(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)
        ts.update_status(task.task_id, TaskStatus.PROCESSING)

        ts.update_status(task.task_id, TaskStatus.FAILED,
                         error_message="processing failed")

        retrieved = ts.get(task.task_id)
        assert retrieved.status == TaskStatus.FAILED
        assert retrieved.completed_at is not None
        assert retrieved.error_message == "processing failed"

    def test_update_to_cancelled_sets_completed_at(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)
        ts.update_status(task.task_id, TaskStatus.PROCESSING)

        ts.update_status(task.task_id, TaskStatus.CANCELLED)

        retrieved = ts.get(task.task_id)
        assert retrieved.status == TaskStatus.CANCELLED
        assert retrieved.completed_at is not None

    def test_update_waiting_no_timestamp_change(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)
        ts.update_status(task.task_id, TaskStatus.PROCESSING)
        first = ts.get(task.task_id)

        ts.update_status(task.task_id, TaskStatus.WAITING)
        second = ts.get(task.task_id)

        assert second.started_at == first.started_at
        assert second.completed_at == first.completed_at

    def test_update_with_error_message(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)

        ts.update_status(task.task_id, TaskStatus.FAILED,
                         error_message="file format not supported")

        retrieved = ts.get(task.task_id)
        assert retrieved.error_message == "file format not supported"


class TestUpdateCheckpoint:
    def test_update_checkpoint(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)

        new_data = {"stage": "regex_done", "cursor": 500}
        ts.update_checkpoint(task.task_id, "regex_done", new_data)

        retrieved = ts.get(task.task_id)
        assert retrieved.checkpoint == "regex_done"
        assert retrieved.checkpoint_data == new_data

    def test_update_checkpoint_none_data(self, isolated_db):
        ts = isolated_db
        task = _make_task(checkpoint_data={"stage": "old"})
        ts.save(task)

        ts.update_checkpoint(task.task_id, "", None)

        retrieved = ts.get(task.task_id)
        assert retrieved.checkpoint == ""
        assert retrieved.checkpoint_data is None


class TestUpdateResult:
    def test_update_result(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)

        result = {"extracted": [{"field": "amount", "value": "100.00"}]}
        ts.update_result(task.task_id, result)

        retrieved = ts.get(task.task_id)
        assert retrieved.result == result

    def test_update_result_none(self, isolated_db):
        ts = isolated_db
        task = _make_task(result={"data": "old"})
        ts.save(task)

        ts.update_result(task.task_id, None)

        retrieved = ts.get(task.task_id)
        assert retrieved.result is None


class TestGet:
    def test_get_nonexistent(self, isolated_db):
        ts = isolated_db
        assert ts.get("nonexistent-id") is None

    def test_get_existing(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)

        retrieved = ts.get(task.task_id)
        assert retrieved.task_id == task.task_id
        assert retrieved.display_name == task.display_name


class TestGetChildren:
    def test_no_children(self, isolated_db):
        ts = isolated_db
        assert ts.get_children("no-parent") == []

    def test_returns_children_ordered(self, isolated_db):
        ts = isolated_db
        parent_id = "parent-001"

        for i in [2, 0, 1]:
            chunk = _make_task(
                task_id=f"chunk-{i}",
                parent_task_id=parent_id,
                is_chunk=True,
                chunk_index=i,
                total_chunks=3,
            )
            ts.save(chunk)

        children = ts.get_children(parent_id)
        assert len(children) == 3
        assert children[0].chunk_index == 0
        assert children[1].chunk_index == 1
        assert children[2].chunk_index == 2


class TestGetByMode:
    def test_filter_by_mode(self, isolated_db):
        ts = isolated_db
        ts.save(_make_task(task_id="t1", mode=QueueMode.DESENSITIZE))
        ts.save(_make_task(task_id="t2", mode=QueueMode.EXTRACT))

        desensitize = ts.get_by_mode(QueueMode.DESENSITIZE)
        extract = ts.get_by_mode(QueueMode.EXTRACT)

        assert all(t.mode == QueueMode.DESENSITIZE for t in desensitize)
        assert all(t.mode == QueueMode.EXTRACT for t in extract)

    def test_filter_by_mode_and_status(self, isolated_db):
        ts = isolated_db
        ts.save(_make_task(task_id="t1", mode=QueueMode.DESENSITIZE, status=TaskStatus.COMPLETED))
        ts.save(_make_task(task_id="t2", mode=QueueMode.DESENSITIZE, status=TaskStatus.WAITING))

        completed = ts.get_by_mode(QueueMode.DESENSITIZE, TaskStatus.COMPLETED)
        assert len(completed) == 1
        assert completed[0].task_id == "t1"

    def test_excludes_chunks(self, isolated_db):
        ts = isolated_db
        ts.save(_make_task(task_id="main", is_chunk=False))
        ts.save(_make_task(task_id="chunk1", is_chunk=True, parent_task_id="main"))

        results = ts.get_by_mode(QueueMode.DESENSITIZE)
        task_ids = [t.task_id for t in results]
        assert "main" in task_ids
        assert "chunk1" not in task_ids

    def test_limit(self, isolated_db):
        ts = isolated_db
        for i in range(5):
            ts.save(_make_task(task_id=f"t{i}"))

        results = ts.get_by_mode(QueueMode.DESENSITIZE, limit=3)
        assert len(results) == 3


class TestGetRecentCompleted:
    def test_returns_only_completed(self, isolated_db):
        ts = isolated_db
        ts.save(_make_task(task_id="t1", status=TaskStatus.COMPLETED))
        ts.save(_make_task(task_id="t2", status=TaskStatus.PROCESSING))
        ts.save(_make_task(task_id="t3", status=TaskStatus.WAITING))

        results = ts.get_recent_completed(QueueMode.DESENSITIZE)
        assert len(results) == 1
        assert results[0].task_id == "t1"


class TestDelete:
    def test_delete_existing(self, isolated_db):
        ts = isolated_db
        task = _make_task()
        ts.save(task)

        ts.delete(task.task_id)
        assert ts.get(task.task_id) is None

    def test_delete_nonexistent_no_error(self, isolated_db):
        ts = isolated_db
        ts.delete("nonexistent-id")


class TestDeleteChildren:
    def test_delete_children_only(self, isolated_db):
        ts = isolated_db
        parent = _make_task(task_id="parent")
        ts.save(parent)
        ts.save(_make_task(task_id="child1", parent_task_id="parent"))
        ts.save(_make_task(task_id="child2", parent_task_id="parent"))

        ts.delete_children("parent")

        assert ts.get("parent") is not None
        assert ts.get("child1") is None
        assert ts.get("child2") is None

    def test_delete_children_no_children_no_error(self, isolated_db):
        ts = isolated_db
        parent = _make_task(task_id="parent-no-kids")
        ts.save(parent)

        ts.delete_children("parent-no-kids")
        assert ts.get("parent-no-kids") is not None


class TestRowToTask:
    def test_invalid_json_checkpoint_data(self, isolated_db):
        ts = isolated_db
        conn = ts._get_conn()
        try:
            conn.execute(
                "INSERT INTO task_store (task_id, mode, status, display_name, original_name, checkpoint_data) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("bad-json", "desensitize", "waiting", "test", "test", "not valid json")
            )
            conn.commit()
        finally:
            conn.close()

        task = ts.get("bad-json")
        assert task is not None
        assert task.checkpoint_data is None

    def test_invalid_json_result(self, isolated_db):
        ts = isolated_db
        conn = ts._get_conn()
        try:
            conn.execute(
                "INSERT INTO task_store (task_id, mode, status, display_name, original_name, result_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("bad-result", "desensitize", "waiting", "test", "test", "bad json")
            )
            conn.commit()
        finally:
            conn.close()

        task = ts.get("bad-result")
        assert task is not None
        assert task.result is None

import os
import sys
import uuid
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.shared import (
    pause_event, abort_event, cancelled_task_ids, CANCELLED_TASK_LOCK,
    TaskState, TaskStatus, QueueMode
)
import app.task_store as ts


@pytest.fixture(autouse=True)
def isolated_task_store(temp_config):
    import tempfile
    import app.shared as shared
    old_db = ts.DB_PATH
    fd, tmp_db = tempfile.mkstemp(suffix=".db", prefix="test_api_")
    os.close(fd)
    ts.DB_PATH = tmp_db
    ts._LOCK = type(ts._LOCK)()
    ts.init_db()
    yield
    ts.DB_PATH = old_db
    try:
        os.unlink(tmp_db)
    except OSError:
        pass


@pytest.fixture(autouse=True)
def reset_events():
    pause_event.clear()
    abort_event.clear()
    with CANCELLED_TASK_LOCK:
        cancelled_task_ids.clear()
    yield


class TestQueueInfoAPI:
    def test_get_queue_info(self, client):
        r = client.get("/api/queue/info")
        assert r.status_code == 200
        data = r.get_json()
        assert data["state"] == "idle"
        assert data["size"] == 0


class TestQueuePauseResumeAPI:
    def test_pause(self, client):
        r = client.post("/api/queue/pause")
        assert r.status_code == 200
        data = r.get_json()
        assert data["paused"] is True

    def test_resume(self, client):
        client.post("/api/queue/pause")
        r = client.post("/api/queue/resume")
        assert r.status_code == 200
        data = r.get_json()
        assert data["paused"] is False


class TestQueueTasksAPI:
    def test_empty(self, client):
        r = client.get("/api/queue/tasks?mode=desensitize")
        assert r.status_code == 200
        data = r.get_json()
        assert data["tasks"] == []

    def test_with_tasks(self, client):
        tid = str(uuid.uuid4())
        ts.save(TaskState(task_id=tid, display_name="t.txt", original_name="t.txt",
                          filepath="/tmp/t.txt", mode=QueueMode.DESENSITIZE,
                          status=TaskStatus.WAITING))
        r = client.get("/api/queue/tasks?mode=desensitize")
        assert r.status_code == 200
        tasks = r.get_json()["tasks"]
        assert len(tasks) >= 1
        found = [t for t in tasks if t["task_id"] == tid]
        assert len(found) == 1


class TestBatchCancelRetryAPI:
    def test_batch_cancel(self, client):
        tid = str(uuid.uuid4())
        ts.save(TaskState(task_id=tid, display_name="t.txt", original_name="t.txt",
                          filepath="/tmp/t.txt", mode=QueueMode.DESENSITIZE,
                          status=TaskStatus.WAITING))
        r = client.post("/api/queue/tasks/batch-cancel",
                        json={"task_ids": [tid]})
        assert r.status_code == 200
        data = r.get_json()
        assert data["cancelled"] == 1
        t = ts.get(tid)
        assert t.status == TaskStatus.CANCELLED

    def test_batch_cancel_empty(self, client):
        r = client.post("/api/queue/tasks/batch-cancel", json={"task_ids": []})
        assert r.status_code == 400

    def test_batch_retry(self, client):
        tid = str(uuid.uuid4())
        ts.save(TaskState(task_id=tid, display_name="t.txt", original_name="t.txt",
                          filepath="/tmp/t.txt", mode=QueueMode.DESENSITIZE,
                          status=TaskStatus.FAILED, error_message="LLM error"))
        r = client.post("/api/queue/tasks/batch-retry",
                        json={"task_ids": [tid]})
        assert r.status_code == 200
        data = r.get_json()
        assert data["retrying"] == 1
        t = ts.get(tid)
        assert t.status == TaskStatus.WAITING

    def test_batch_retry_empty(self, client):
        r = client.post("/api/queue/tasks/batch-retry", json={"task_ids": []})
        assert r.status_code == 400


class TestParentMergedAPI:
    def test_merged_partial(self, client):
        pid = str(uuid.uuid4())
        ts.save(TaskState(task_id=pid, display_name="parent.pdf", original_name="parent.pdf",
                          filepath="/tmp/parent.pdf", mode=QueueMode.DESENSITIZE))

        c1 = str(uuid.uuid4())
        ts.save(TaskState(task_id=c1, display_name="p (1/2)", original_name="p (1/2)",
                          filepath="/tmp/c1.png", mode=QueueMode.DESENSITIZE,
                          status=TaskStatus.COMPLETED, is_chunk=True,
                          parent_task_id=pid, chunk_index=0, total_chunks=2,
                          result={"text": "chunk1 text", "replacements": [{"a": 1}]}))

        c2 = str(uuid.uuid4())
        ts.save(TaskState(task_id=c2, display_name="p (2/2)", original_name="p (2/2)",
                          filepath="/tmp/c2.png", mode=QueueMode.DESENSITIZE,
                          status=TaskStatus.WAITING, is_chunk=True,
                          parent_task_id=pid, chunk_index=1, total_chunks=2))

        r = client.get(f"/api/queue/parent/{pid}/merged")
        assert r.status_code == 200
        data = r.get_json()
        assert data["completed"] == 1
        assert data["total"] == 2
        assert data["text"] == "chunk1 text"
        assert data["parent_display_name"] == "parent.pdf"

    def test_merged_not_found(self, client):
        r = client.get("/api/queue/parent/nonexistent/merged")
        assert r.status_code == 404


class TestLogsAPI:
    def test_logs(self, client):
        r = client.get("/api/logs?last=5")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data["logs"], list)
        assert isinstance(data["count"], int)

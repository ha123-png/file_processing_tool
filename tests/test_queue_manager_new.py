import os
import sys
import uuid
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.shared import (
    task_queue, processing_event, pause_event, abort_event,
    cancelled_task_ids, CANCELLED_TASK_LOCK,
    TaskState, TaskStatus, QueueMode
)
from app.queue_manager import (
    enqueue_task_id, _extract_task_from_queue_item, get_queue_info_v2
)
import app.task_store as ts


@pytest.fixture(autouse=True)
def isolated_task_store(temp_config):
    import tempfile
    import app.shared as shared
    old_db = ts.DB_PATH
    fd, tmp_db = tempfile.mkstemp(suffix=".db", prefix="test_qm_")
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
def drain_queue():
    while not task_queue.empty():
        try:
            task_queue.get_nowait()
        except:
            break
    processing_event.clear()
    pause_event.clear()
    abort_event.clear()
    with CANCELLED_TASK_LOCK:
        cancelled_task_ids.clear()
    yield


class TestEnqueueTaskId:
    def test_enqueue_and_get(self):
        tid = str(uuid.uuid4())
        result = enqueue_task_id(tid)
        assert result is True
        assert task_queue.qsize() == 1
        assert task_queue.get() == tid

    def test_enqueue_cancelled_rejected(self):
        tid = str(uuid.uuid4())
        with CANCELLED_TASK_LOCK:
            cancelled_task_ids.add(tid)
        result = enqueue_task_id(tid)
        assert result is False
        assert task_queue.qsize() == 0


class TestExtractFromQueueItem:
    def test_old_tuple(self):
        item = ("/tmp/f.txt", "file.txt", "desensitize", "gid", 0, 3, ".txt", "qid123")
        r = _extract_task_from_queue_item(item)
        assert r[0] == "/tmp/f.txt"
        assert r[1] == "file.txt"
        assert r[2] == "desensitize"
        assert r[3] == "gid"
        assert r[7] == "qid123"

    def test_old_tuple_minimal(self):
        item = ("/tmp/f.txt", "file.txt")
        r = _extract_task_from_queue_item(item)
        assert r[0] == "/tmp/f.txt"
        assert r[1] == "file.txt"
        assert r[2] == "desensitize"

    def test_new_string_found(self):
        tid = str(uuid.uuid4())
        t = TaskState(task_id=tid, display_name="f.txt", original_name="f.txt",
                      filepath="/tmp/f.txt", mode=QueueMode.EXTRACT, status=TaskStatus.WAITING)
        ts.save(t)
        r = _extract_task_from_queue_item(tid)
        assert r[0] == "/tmp/f.txt"
        assert r[1] == "f.txt"
        assert r[2] == "extract"

    def test_new_string_not_found(self):
        tid = str(uuid.uuid4())
        r = _extract_task_from_queue_item(tid)
        assert r[0] is None
        assert r[8] == tid


class TestGetQueueInfoV2:
    def test_idle(self):
        info = get_queue_info_v2()
        assert info["state"] == "idle"
        assert info["size"] == 0

    def test_processing(self):
        processing_event.set()
        info = get_queue_info_v2()
        assert info["state"] == "processing"
        assert info["processing"] is True
        processing_event.clear()

    def test_paused(self):
        pause_event.set()
        info = get_queue_info_v2()
        assert info["state"] == "paused"
        assert info["paused"] is True
        pause_event.clear()

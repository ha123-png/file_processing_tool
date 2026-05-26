import os
import sys
import uuid
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.shared import (
    pause_event, abort_event,
    TaskState, TaskStatus, QueueMode
)
from app.processor import (
    _is_paused, _is_aborted, _check_paused,
    _save_checkpoint, _save_checkpoint_data, _restore_checkpoint
)
import app.task_store as ts


@pytest.fixture(autouse=True)
def isolated_task_store(temp_config):
    import tempfile
    import app.shared as shared
    old_db = ts.DB_PATH
    fd, tmp_db = tempfile.mkstemp(suffix=".db", prefix="test_cp_")
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
    abort_event.clear()
    yield


class TestPauseDetection:
    def test_not_paused(self):
        assert _is_paused() is False

    def test_paused(self):
        pause_event.set()
        assert _is_paused() is True

    def test_check_paused_raises(self):
        pause_event.set()
        with pytest.raises(RuntimeError, match="任务已被用户终止"):
            _check_paused()

    def test_check_paused_noop(self):
        _check_paused()


class TestAbortDetection:
    def test_neither_set(self):
        assert _is_aborted() is False

    def test_abort_event(self):
        abort_event.set()
        assert _is_aborted() is True

    def test_abort_event(self):
        abort_event.set()
        assert _is_aborted() is True

    def test_both_set(self):
        abort_event.set()
        abort_event.set()
        assert _is_aborted() is True


class TestCheckpointOps:
    def test_save_checkpoint_data(self):
        tid = str(uuid.uuid4())
        ts.save(TaskState(task_id=tid, display_name="t.txt", original_name="t.txt",
                          filepath="/tmp/t.txt", mode=QueueMode.DESENSITIZE))
        _save_checkpoint_data("regex_done", {"text": "hello", "count": 1}, tid)
        r = ts.get(tid)
        assert r.checkpoint == "regex_done"
        assert r.checkpoint_data == {"text": "hello", "count": 1}

    def test_save_checkpoint_via_taskstate(self):
        tid = str(uuid.uuid4())
        t = TaskState(task_id=tid, display_name="t.txt", original_name="t.txt",
                      filepath="/tmp/t.txt", mode=QueueMode.DESENSITIZE)
        ts.save(t)
        _save_checkpoint(t, "llm1_done", {"replacements": [1, 2, 3]})
        r = ts.get(tid)
        assert r.checkpoint == "llm1_done"

    def test_restore_checkpoint(self):
        tid = str(uuid.uuid4())
        t = TaskState(task_id=tid, display_name="t.txt", original_name="t.txt",
                      filepath="/tmp/t.txt", mode=QueueMode.DESENSITIZE,
                      checkpoint="text_extracted", checkpoint_data={"text": "abc"})
        ts.save(t)
        cp, data = _restore_checkpoint(t)
        assert cp == "text_extracted"
        assert data == {"text": "abc"}

    def test_restore_empty_checkpoint(self):
        tid = str(uuid.uuid4())
        t = TaskState(task_id=tid, display_name="t.txt", original_name="t.txt",
                      filepath="/tmp/t.txt", mode=QueueMode.DESENSITIZE)
        ts.save(t)
        cp, data = _restore_checkpoint(t)
        assert cp == ""
        assert data is None

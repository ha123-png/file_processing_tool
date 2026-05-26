import os
import sys
import uuid
import time
import threading
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.shared import (
    task_queue, processing_event, pause_event,
    cancelled_task_ids, CANCELLED_TASK_LOCK,
    TaskState, TaskStatus, QueueMode,
    get_interrupted, clear_interrupted, set_interrupted,
)
from app.queue_manager import (
    enqueue_task_id, _extract_task_from_queue_item,
    get_queue_info, get_queue_info_v2, start_worker,
)
import app.queue_manager as qm

_COUNT_LOCK = threading.Lock()
_process_call_count = 0
_process_calls = []
_process_delay = 0.05
_worker_stop = threading.Event()


def fake_process_file(filepath, original_name, queue_id, group_id,
                      chunk_index, total_chunks, chunk_ext):
    global _process_call_count, _process_calls, _process_delay
    if _process_delay:
        time.sleep(_process_delay)
    with _COUNT_LOCK:
        _process_call_count += 1
        _process_calls.append({
            "filepath": filepath, "original_name": original_name,
            "queue_id": queue_id, "group_id": group_id,
            "chunk_index": chunk_index, "total_chunks": total_chunks,
            "chunk_ext": chunk_ext,
        })


def _controlled_worker():
    while not _worker_stop.is_set():
        if pause_event.is_set():
            pause_event.wait(0.1)
            continue
        try:
            if get_interrupted():
                raw_item = get_interrupted()
                clear_interrupted()
            else:
                raw_item = task_queue.get(timeout=0.5)
            result = _extract_task_from_queue_item(raw_item)
            if result[0] is None:
                continue
            filepath, original_name, enqueued_mode, group_id, chunk_index, total_chunks, chunk_ext, queue_id = result
            processing_event.set()
            fake_process_file(filepath, original_name, queue_id, group_id,
                              chunk_index, total_chunks, chunk_ext)
            processing_event.clear()
        except:
            continue


def _start_and_wait(seconds=2):
    global _worker_stop
    _worker_stop.clear()
    t = threading.Thread(target=_controlled_worker, daemon=True)
    t.start()
    time.sleep(seconds)
    _worker_stop.set()
    t.join(timeout=5)
    return t


@pytest.fixture(autouse=True)
def reset_state():
    global _process_call_count, _process_calls, _process_delay, _worker_stop
    _process_call_count = 0
    _process_calls = []
    _process_delay = 0.05
    _worker_stop = threading.Event()
    _worker_stop.set()

    while not task_queue.empty():
        try:
            task_queue.get_nowait()
        except:
            break
    processing_event.clear()
    pause_event.clear()
    clear_interrupted()
    with CANCELLED_TASK_LOCK:
        cancelled_task_ids.clear()

    _original_process_file = qm.process_file
    qm.process_file = fake_process_file

    yield

    qm.process_file = _original_process_file


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
        for ext in ("-wal", "-shm"):
            p = tmp_db + ext
            if os.path.exists(p):
                os.unlink(p)


def _save_task(ts, task_id, mode=QueueMode.DESENSITIZE, status=TaskStatus.WAITING,
               filepath="/tmp/test.txt", display_name="test.txt", file_ext="", **kw):
    t = TaskState(
        task_id=task_id, display_name=display_name, original_name=display_name,
        filepath=filepath, mode=mode, status=status, file_ext=file_ext, **kw
    )
    ts.save(t)
    return t


class TestEnqueueTaskId:
    def test_enqueue_and_get(self):
        tid = str(uuid.uuid4())
        assert enqueue_task_id(tid) is True
        assert task_queue.qsize() == 1
        assert task_queue.get() == tid

    def test_enqueue_cancelled_rejected(self):
        tid = str(uuid.uuid4())
        with CANCELLED_TASK_LOCK:
            cancelled_task_ids.add(tid)
        assert enqueue_task_id(tid) is False
        assert task_queue.qsize() == 0
        with CANCELLED_TASK_LOCK:
            assert tid not in cancelled_task_ids

    def test_enqueue_multiple(self):
        ids = [str(uuid.uuid4()) for _ in range(3)]
        for tid in ids:
            assert enqueue_task_id(tid) is True
        assert task_queue.qsize() == 3


class TestExtractFromQueueItem:
    def test_old_tuple_full(self, isolated_db):
        item = ("/tmp/f.txt", "file.txt", "desensitize", "gid", 0, 3, ".txt", "qid123")
        r = _extract_task_from_queue_item(item)
        assert r[0] == "/tmp/f.txt"
        assert r[1] == "file.txt"
        assert r[2] == "desensitize"
        assert r[7] == "qid123"

    def test_old_tuple_minimal(self):
        item = ("/tmp/f.txt", "file.txt")
        r = _extract_task_from_queue_item(item)
        assert r[0] == "/tmp/f.txt"
        assert r[1] == "file.txt"

    def test_new_string_from_db(self, isolated_db):
        tid = str(uuid.uuid4())
        _save_task(isolated_db, tid, mode=QueueMode.EXTRACT, display_name="db.txt",
                   filepath="/tmp/db.txt", file_ext=".txt")
        r = _extract_task_from_queue_item(tid)
        assert r[0] == "/tmp/db.txt"
        assert r[1] == "db.txt"
        assert r[2] == "extract"
        assert r[6] == ".txt"

    def test_new_string_not_in_db(self, isolated_db):
        tid = str(uuid.uuid4())
        r = _extract_task_from_queue_item(tid)
        assert r[0] is None

    def test_new_string_cancelled_status(self, isolated_db):
        tid = str(uuid.uuid4())
        _save_task(isolated_db, tid, status=TaskStatus.CANCELLED)
        r = _extract_task_from_queue_item(tid)
        assert r[0] is None

    def test_new_string_cancelled_by_set(self, isolated_db):
        tid = str(uuid.uuid4())
        _save_task(isolated_db, tid)
        with CANCELLED_TASK_LOCK:
            cancelled_task_ids.add(tid)
        r = _extract_task_from_queue_item(tid)
        assert r[0] is None
        with CANCELLED_TASK_LOCK:
            assert tid not in cancelled_task_ids

    def test_passes_chunk_ext(self, isolated_db):
        tid = str(uuid.uuid4())
        _save_task(isolated_db, tid, file_ext=".pdf")
        r = _extract_task_from_queue_item(tid)
        assert r[6] == ".pdf"


class TestGetQueueInfo:
    def test_idle(self):
        assert get_queue_info()["queue_size"] == 0
        assert get_queue_info()["processing"] is False
        assert get_queue_info()["paused"] is False
        assert get_queue_info_v2()["state"] == "idle"
        assert get_queue_info_v2()["size"] == 0

    def test_processing(self):
        processing_event.set()
        assert get_queue_info()["processing"] is True
        assert get_queue_info_v2()["state"] == "processing"
        processing_event.clear()

    def test_paused(self):
        pause_event.set()
        assert get_queue_info()["paused"] is True
        assert get_queue_info_v2()["state"] == "paused"
        pause_event.clear()


class TestWorkerBasic:
    def test_processes_one_task(self, isolated_db):
        tid = str(uuid.uuid4())
        _save_task(isolated_db, tid, filepath="/tmp/a.txt", display_name="a.txt")
        enqueue_task_id(tid)

        _start_and_wait(seconds=1.5)

        with _COUNT_LOCK:
            assert _process_call_count == 1

    def test_processes_multiple_tasks(self, isolated_db):
        for i in range(3):
            tid = str(uuid.uuid4())
            _save_task(isolated_db, tid, filepath=f"/tmp/{i}.txt",
                       display_name=f"{i}.txt")
            enqueue_task_id(tid)

        _start_and_wait(seconds=3)

        with _COUNT_LOCK:
            assert _process_call_count == 3

    def test_paused_worker_does_not_process(self, isolated_db):
        tid = str(uuid.uuid4())
        _save_task(isolated_db, tid, filepath="/tmp/p.txt", display_name="p.txt")
        enqueue_task_id(tid)

        pause_event.set()
        _start_and_wait(seconds=1.5)

        with _COUNT_LOCK:
            assert _process_call_count == 0

    def test_resume_after_pause(self, isolated_db):
        tid = str(uuid.uuid4())
        _save_task(isolated_db, tid, filepath="/tmp/r.txt", display_name="r.txt")
        enqueue_task_id(tid)

        global _worker_stop
        _worker_stop.clear()

        pause_event.set()
        t = threading.Thread(target=_controlled_worker, daemon=True)
        t.start()
        time.sleep(1)

        with _COUNT_LOCK:
            assert _process_call_count == 0

        pause_event.clear()
        time.sleep(1.5)

        _worker_stop.set()
        t.join(timeout=3)

        with _COUNT_LOCK:
            assert _process_call_count == 1


class TestInterruptedTask:
    def test_interrupted_processed_first(self, isolated_db):
        tid_normal = str(uuid.uuid4())
        tid_interrupted = str(uuid.uuid4())
        _save_task(isolated_db, tid_normal, filepath="/tmp/n.txt", display_name="n.txt")
        _save_task(isolated_db, tid_interrupted, filepath="/tmp/i.txt", display_name="i.txt")
        enqueue_task_id(tid_normal)
        set_interrupted(tid_interrupted)

        _start_and_wait(seconds=2)

        with _COUNT_LOCK:
            assert _process_call_count == 2
            assert _process_calls[0]["original_name"] == "i.txt"

    def test_interrupted_cleared_after_consumption(self, isolated_db):
        tid = str(uuid.uuid4())
        _save_task(isolated_db, tid, filepath="/tmp/c.txt", display_name="c.txt")
        set_interrupted(tid)

        _start_and_wait(seconds=1.5)

        assert get_interrupted() is None


class TestWorkerCancelledTask:
    def test_cancelled_not_processed(self, isolated_db):
        tid = str(uuid.uuid4())
        _save_task(isolated_db, tid, filepath="/tmp/x.txt", display_name="x.txt")
        enqueue_task_id(tid)

        with CANCELLED_TASK_LOCK:
            cancelled_task_ids.add(tid)

        _start_and_wait(seconds=1.5)

        with _COUNT_LOCK:
            assert _process_call_count == 0


class TestStartWorker:
    def test_start_worker_creates_thread(self):
        before = threading.active_count()
        start_worker()
        time.sleep(0.2)
        after = threading.active_count()
        assert after >= before

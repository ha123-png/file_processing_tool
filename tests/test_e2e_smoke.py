import os
import sys
import uuid
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.shared import (
    task_queue, processing_event, pause_event, abort_event, abort_event,
    TaskState, TaskStatus, QueueMode,
    cancelled_task_ids, CANCELLED_TASK_LOCK,
)
import app.task_store as ts
import app.shared as shared


@pytest.fixture(autouse=True)
def isolated_task_store(temp_config):
    import tempfile
    import app.shared as shared
    old_db = ts.DB_PATH
    fd, tmp_db = tempfile.mkstemp(suffix=".db", prefix="test_e2e_")
    os.close(fd)
    ts.DB_PATH = tmp_db
    ts._LOCK = type(ts._LOCK)()
    ts.init_db()
    old_upload = shared.UPLOAD_DIR
    old_output = shared.OUTPUT_DIR
    import tempfile as _tf
    from pathlib import Path as _Path
    upload_dir = _Path(_tf.mkdtemp(prefix="test_upload_"))
    output_dir = _Path(_tf.mkdtemp(prefix="test_output_"))
    output_dir.mkdir(parents=True, exist_ok=True)
    shared.UPLOAD_DIR = upload_dir
    shared.OUTPUT_DIR = output_dir
    yield
    ts.DB_PATH = old_db
    shared.UPLOAD_DIR = old_upload
    shared.OUTPUT_DIR = old_output
    try:
        os.unlink(tmp_db)
    except OSError:
        pass
    try:
        import shutil
        shutil.rmtree(upload_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)
    except:
        pass


@pytest.fixture(autouse=True)
def drain_and_reset():
    while not task_queue.empty():
        try:
            task_queue.get_nowait()
        except:
            break
    processing_event.clear()
    pause_event.clear()
    abort_event.clear()
    abort_event.clear()
    with CANCELLED_TASK_LOCK:
        cancelled_task_ids.clear()
    shared.clear_interrupted()
    yield


def _make_fixture_txt(content, name="contract.txt"):
    path = os.path.join(shared.UPLOAD_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestUploadDesensitizeQuick:
    def test_upload_quick_no_llm(self, client):
        content = (
            "甲方：北京测试科技有限公司\n"
            "统一社会信用代码：91110108MA01TEST1\n"
            "联系人：张三，手机号：13800138000\n"
            "邮箱：zhangsan@test.com\n"
            "合同金额：¥500,000.00元\n"
            "签订日期：2024年1月15日\n"
        )
        fixture_path = _make_fixture_txt(content, "test_contract.txt")

        r = client.post("/api/upload", data={"file": (open(fixture_path, "rb"), "test_contract.txt")})
        assert r.status_code == 200
        data = r.get_json()
        assert "task_id" in data
        task_id = data["task_id"]

        max_wait = 20
        t = None
        for _ in range(max_wait):
            t = ts.get(task_id)
            if t and t.status != TaskStatus.WAITING:
                break
            time.sleep(0.5)

        assert t is not None
        assert t.status in (TaskStatus.WAITING, TaskStatus.PROCESSING, TaskStatus.COMPLETED)
        assert t.mode == QueueMode.DESENSITIZE
        assert t.display_name == "test_contract.txt"
        import os as _os
        assert _os.path.exists(t.filepath), f"upload file missing: {t.filepath}"


class TestUploadUnsupported:
    def test_rejects_exe(self, client):
        import tempfile
        fd, exe_path = tempfile.mkstemp(suffix=".exe")
        os.close(fd)
        try:
            with open(exe_path, "wb") as f:
                f.write(b"MZ\x00\x00")
            r = client.post("/api/upload",
                            data={"file": (open(exe_path, "rb"), "test.exe")})
            assert r.status_code == 400
        finally:
            try:
                os.unlink(exe_path)
            except OSError:
                pass

    def test_rejects_empty_filename(self, client):
        r = client.post("/api/upload",
                        data={"file": (open(__file__, "rb"), "")})
        assert r.status_code == 400


class TestUploadLargeFile:
    def test_large_file_splits_into_chunks(self, client):
        content = ("甲方：北京市海淀区测试科技有限公司\n" * 350 + "签订日期：2024年1月15日\n" * 50)
        assert len(content) >= 5000, f"content too short: {len(content)}"
        fixture_path = _make_fixture_txt(content, "large_contract.txt")

        r = client.post("/api/upload",
                        data={"file": (open(fixture_path, "rb"), "large_contract.txt")})
        assert r.status_code == 200
        data = r.get_json()
        assert data.get("is_large") is True
        assert data.get("total_chunks", 0) > 1
        assert "task_id" in data
        parent_id = data["task_id"]

        children = ts.get_children(parent_id)
        assert len(children) == data["total_chunks"]
        for c in children:
            assert c.is_chunk is True
            assert c.parent_task_id == parent_id
            assert c.file_ext != ""


class TestPauseResume:
    def test_pause_sets_events(self, client):
        r = client.post("/api/queue/pause")
        assert r.status_code == 200
        assert pause_event.is_set()

        r = client.post("/api/queue/resume")
        assert r.status_code == 200
        assert not pause_event.is_set()

    def test_pause_resume_workflow(self, client):
        content = "test line 1\ntest line 2\n"
        fixture_path = _make_fixture_txt(content, "pause_test.txt")

        r = client.post("/api/upload",
                        data={"file": (open(fixture_path, "rb"), "pause_test.txt")})
        assert r.status_code == 200
        task_id = r.get_json()["task_id"]

        time.sleep(0.5)
        client.post("/api/queue/pause")
        time.sleep(0.5)

        t = ts.get(task_id)
        assert t is not None
        client.post("/api/queue/resume")


class TestCrossModeIsolation:
    def test_upload_returns_mode(self, client):
        content = "test line 1\ntest line 2\n"
        fixture_path = _make_fixture_txt(content, "mode_test.txt")
        r = client.post("/api/upload",
                        data={"file": (open(fixture_path, "rb"), "mode_test.txt")})
        assert r.status_code == 200
        data = r.get_json()
        assert "task_id" in data


class TestQueueFull:
    def test_queue_full_rejected(self, client):
        for _ in range(105):
            try:
                tid = str(uuid.uuid4())
                task_queue.put_nowait(tid)
            except:
                break

        content = "test\n"
        fixture_path = _make_fixture_txt(content, "full_test.txt")
        r = client.post("/api/upload",
                        data={"file": (open(fixture_path, "rb"), "full_test.txt")})
        assert r.status_code == 429

class TestCheckpointRecovery:
    def test_checkpoint_persists_after_pause(self, client):
        content = "甲方：测试科技有限公司\n手机号：13800138000\n合同金额：500000元\n"
        fixture_path = _make_fixture_txt(content, "cp_test.txt")

        r = client.post("/api/upload",
                        data={"file": (open(fixture_path, "rb"), "cp_test.txt")})
        assert r.status_code == 200
        task_id = r.get_json()["task_id"]

        time.sleep(1.0)
        client.post("/api/queue/pause")
        time.sleep(0.5)

        t = ts.get(task_id)
        assert t is not None
        if t.checkpoint:
            assert t.checkpoint in ("text_extracted", "regex_done", "llm1_done", "llm2_done")
            assert t.checkpoint_data is not None

        client.post("/api/queue/resume")

    def test_checkpoint_recovery_skips_stages(self, client):
        import app.task_store as ts_mod
        tid = str(uuid.uuid4())
        ts_mod.save(TaskState(task_id=tid, display_name="skip.txt", original_name="skip.txt",
                               filepath="/tmp/skip.txt", mode=QueueMode.DESENSITIZE,
                               status=TaskStatus.WAITING,
                               checkpoint="regex_done",
                               checkpoint_data={"text": "hello world", "replacements": [{"sensitive": "test", "source": "regex"}]}))

        task_queue.put(tid)
        time.sleep(1.0)

        t = ts_mod.get(tid)
        assert t is not None
        assert t.status in (TaskStatus.WAITING, TaskStatus.PROCESSING, TaskStatus.COMPLETED)

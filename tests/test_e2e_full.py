import os, sys, time, uuid, json, tempfile
import pytest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.task_store as ts
import app.shared as shared
from app.shared import (
    task_queue, processing_event, pause_event, abort_event, abort_event,
    cancelled_task_ids, CANCELLED_TASK_LOCK,
    set_current_mode, get_current_mode,
    TaskState, TaskStatus, QueueMode,
)
from app.queue_manager import start_worker, stop_worker

_MOCK_LLM_TEXT = "【内容开始】\n{张三的身份证号}\n{李四的手机}\n【内容结束】"

def _mock_stream(url, payload, timeout, api_key=""):
    return _MOCK_LLM_TEXT


@pytest.fixture(autouse=True)
def patch_llm():
    with patch("app.processor.call_lm_studio", side_effect=_mock_stream):
        with patch("app.processor.call_lm_studio_multimodal", side_effect=_mock_stream):
            with patch("app.llm_client._stream_llm", side_effect=_mock_stream):
                yield


@pytest.fixture(scope="session")
def e2e_dirs():
    import shutil
    upload_dir = Path(tempfile.mkdtemp(prefix="e2e_up_"))
    output_dir = Path(tempfile.mkdtemp(prefix="e2e_out_"))
    output_dir.mkdir(parents=True, exist_ok=True)
    yield upload_dir, output_dir
    shutil.rmtree(str(upload_dir), ignore_errors=True)
    shutil.rmtree(str(output_dir), ignore_errors=True)


@pytest.fixture(autouse=True)
def e2e_reset(e2e_dirs, temp_config):
    upload_dir, output_dir = e2e_dirs

    old_db = ts.DB_PATH
    fd, tmp_db = tempfile.mkstemp(suffix=".db", prefix="e2e_ts_")
    os.close(fd)
    ts.DB_PATH = tmp_db
    ts._LOCK = type(ts._LOCK)()
    ts.init_db()

    old_upload = shared.UPLOAD_DIR
    old_output = shared.OUTPUT_DIR
    shared.UPLOAD_DIR = upload_dir
    shared.OUTPUT_DIR = output_dir

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
    set_current_mode("desensitize")
    start_worker()

    yield

    stop_worker()
    ts.DB_PATH = old_db
    shared.UPLOAD_DIR = old_upload
    shared.OUTPUT_DIR = old_output
    try:
        os.unlink(tmp_db)
    except OSError:
        pass


def _up(client, content, name="t.txt"):
    p = os.path.join(str(shared.UPLOAD_DIR), name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    with open(p, "rb") as f:
        return client.post("/api/upload", data={"file": (f, name)})


def _wait(tid, status, timeout=15):
    for _ in range(timeout * 2):
        t = ts.get(tid)
        if t and t.status == status:
            return t
        time.sleep(0.5)
    return ts.get(tid)


def _wait_proc(timeout=3):
    for _ in range(timeout * 2):
        if processing_event.is_set():
            return True
        time.sleep(0.5)
    return False


STD = (
    "甲方：北京测试科技有限公司\n"
    "统一社会信用代码：91110108MA01TEST1\n"
    "联系人：张三，手机号：13800138000\n"
    "邮箱：zhangsan@test.com\n"
    "合同金额：¥500,000.00元\n"
    "签订日期：2024年1月15日\n"
)

BIG = (
    "甲方：北京测试科技有限公司\n"
    "第一条 合同标的\n" + ("A" * 80 + "\n") * 100 +
    "联系人：张三，手机号：13800138000\n"
    "签订日期：2024年1月15日\n"
)


class TestA_Upload:
    def test_a1_single(self, client):
        r = _up(client, STD, "a1.txt")
        assert r.status_code == 200
        tid = r.get_json()["task_id"]
        t = _wait(tid, TaskStatus.COMPLETED, timeout=15)
        assert t is not None and t.status == TaskStatus.COMPLETED

    def test_a2_three_files(self, client):
        ids = []
        for n in ("a2_a.txt", "a2_b.txt", "a2_c.txt"):
            r = _up(client, STD, n)
            assert r.status_code == 200
            ids.append(r.get_json()["task_id"])
        for tid in ids:
            t = _wait(tid, TaskStatus.COMPLETED, timeout=30)
            assert t is not None and t.status == TaskStatus.COMPLETED

    def test_a3_large(self, client):
        r = _up(client, BIG, "a3_large.txt")
        assert r.status_code == 200
        data = r.get_json()
        assert data.get("is_large") is True
        assert data["total_chunks"] > 1
        parent_id = data["task_id"]
        children = ts.get_children(parent_id)
        assert len(children) == data["total_chunks"]
        for c in children:
            _wait(c.task_id, TaskStatus.COMPLETED, timeout=45)
        for c in ts.get_children(parent_id):
            assert c.status == TaskStatus.COMPLETED


class TestB_Pause:
    def test_b1_pause_order(self, client):
        _up(client, STD, "b1_a.txt")
        _up(client, STD, "b1_b.txt")
        _up(client, STD, "b1_c.txt")

        _wait_proc(timeout=3)
        time.sleep(0.3)
        client.post("/api/queue/pause")
        time.sleep(0.5)
        assert pause_event.is_set()

    def test_b2_resume(self, client):
        r1 = _up(client, STD, "b2_a.txt")
        r2 = _up(client, STD, "b2_b.txt")
        _wait(r1.get_json()["task_id"], TaskStatus.COMPLETED, timeout=15)

        client.post("/api/queue/pause")
        time.sleep(0.3)
        client.post("/api/queue/resume")
        t = _wait(r2.get_json()["task_id"], TaskStatus.COMPLETED, timeout=15)
        assert t.status == TaskStatus.COMPLETED


class TestC_Cancel:
    def test_c1_cancel_then_retry(self, client):
        _up(client, STD, "c1_a.txt")
        _up(client, STD, "c1_b.txt")
        _up(client, STD, "c1_c.txt")

        client.post("/api/queue/pause")
        time.sleep(0.5)

        tasks = client.get("/api/queue/tasks?mode=desensitize").get_json()
        waiting_tasks = [t for t in tasks["tasks"] if t["status"] == "waiting"]
        if waiting_tasks:
            tid = waiting_tasks[0]["task_id"]
            client.post("/api/queue/tasks/batch-cancel", json={"task_ids": [tid]})
            t = ts.get(tid)
            assert t.status == TaskStatus.CANCELLED

            client.post("/api/queue/tasks/batch-retry", json={"task_ids": [tid]})
            t = ts.get(tid)
            assert t.status == TaskStatus.WAITING

        client.post("/api/queue/resume")

    def test_c2_large_cancel(self, client):
        r = _up(client, BIG, "c2_large.txt")
        parent_id = r.get_json()["task_id"]
        children = ts.get_children(parent_id)
        assert len(children) >= 2

        _wait_proc(timeout=3)
        time.sleep(0.5)
        client.post("/api/queue/pause")
        time.sleep(0.3)
        client.post("/api/queue/tasks/batch-cancel", json={"task_ids": [parent_id]})

        for c in ts.get_children(parent_id):
            assert c.status in (TaskStatus.CANCELLED, TaskStatus.COMPLETED)


class TestD_Recovery:
    def test_d1_queue_info(self, client):
        _up(client, STD, "d1_a.txt")
        r = client.get("/api/queue/info")
        assert r.status_code == 200
        info = r.get_json()
        assert "state" in info
        assert "size" in info

    def test_d2_task_list(self, client):
        _up(client, STD, "d2_a.txt")
        from app.task_store import get_by_mode
        tasks = get_by_mode(QueueMode.DESENSITIZE, limit=10)
        assert any(t.display_name == "d2_a.txt" for t in tasks)


class TestE_Mixed:
    def test_e1_large_small(self, client):
        _up(client, BIG, "e1_large.txt")
        r = _up(client, STD, "e1_small.txt")
        _wait(r.get_json()["task_id"], TaskStatus.COMPLETED, timeout=30)


class TestF_CrossMode:
    def test_f1_switch_no_block(self, client):
        _up(client, STD, "f1_desen.txt")
        r = client.post("/api/mode", json={"mode": "extract"})
        assert r.status_code == 200


class TestG_Composite:
    def test_g1_cycle(self, client):
        r1 = _up(client, STD, "g_a.txt")
        tid_a = r1.get_json()["task_id"]
        _wait(tid_a, TaskStatus.COMPLETED, timeout=15)
        assert ts.get(tid_a).status == TaskStatus.COMPLETED

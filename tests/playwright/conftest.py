import os, sys, time, json, tempfile, socket
import threading
import pytest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_MOCK_LLM = "【内容开始】\n{张三的身份证号}\n{李四的手机}\n【内容结束】"

SMALL_TXT = "甲方：北京测试科技有限公司\n统一社会信用代码：91110108MA01TEST1\n联系人：张三，手机号：13800138000\n邮箱：zhangsan@test.com\n合同金额：¥500,000.00元\n签订日期：2024年1月15日\n"

BIG_CONTENT = "甲方：北京测试科技有限公司\n" + ("B" * 500) + "\n联系人：张三，手机号：13800138000\n签订日期：2024年1月15日\n"

def _mock_stream(url, payload, timeout, api_key=""):
    return _MOCK_LLM


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    port = _find_free_port()
    return f"http://127.0.0.1:{port}"


@pytest.fixture(scope="session", autouse=True)
def flask_server(base_url):
    import app.shared as shared
    from app.routes import app as flask_app
    from app.queue_manager import start_worker, stop_worker, start_cleanup_scheduler

    with patch("app.llm_client.call_lm_studio", side_effect=_mock_stream):
        with patch("app.llm_client._stream_llm", side_effect=_mock_stream):
            port = int(base_url.split(":")[-1])

            import shutil
            upload_dir = Path(tempfile.mkdtemp(prefix="pw_up_"))
            output_dir = Path(tempfile.mkdtemp(prefix="pw_out_"))
            output_dir.mkdir(parents=True, exist_ok=True)

            old_upload = shared.UPLOAD_DIR
            old_output = shared.OUTPUT_DIR
            shared.UPLOAD_DIR = upload_dir
            shared.OUTPUT_DIR = output_dir

            import app.task_store as ts
            old_db = ts.DB_PATH
            ts_db = Path(tempfile.mkdtemp(prefix="pw_ts_")) / "test.db"
            ts.DB_PATH = str(ts_db)
            ts.init_db()

            start_worker()
            start_cleanup_scheduler(interval=60, keep=10)

            def _run():
                flask_app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

            t = threading.Thread(target=_run, daemon=True)
            t.start()

            import requests
            for _ in range(15):
                try:
                    r = requests.get(f"http://127.0.0.1:{port}/api/status", timeout=2)
                    if r.status_code == 200:
                        break
                except Exception:
                    pass
                time.sleep(1.0)
            yield base_url

            stop_worker()
            ts.DB_PATH = old_db
            shared.UPLOAD_DIR = old_upload
            shared.OUTPUT_DIR = old_output
            try:
                shutil.rmtree(str(upload_dir), ignore_errors=True)
                shutil.rmtree(str(output_dir), ignore_errors=True)
            except Exception:
                pass

            with shared.sse_clients_lock:
                shared.sse_clients.clear()
            while not shared.task_queue.empty():
                try:
                    shared.task_queue.get_nowait()
                except Exception:
                    break
            shared.processing_event.clear()
            shared.pause_event.clear()
            shared.abort_event.clear()
            with shared.CANCELLED_TASK_LOCK:
                shared.cancelled_task_ids.clear()


@pytest.fixture(autouse=True)
def e2e_reset():
    import app.shared as shared
    import app.task_store as ts

    while not shared.task_queue.empty():
        try:
            shared.task_queue.get_nowait()
        except Exception:
            break
    shared.processing_event.clear()
    shared.pause_event.clear()
    shared.abort_event.clear()
    with shared.CANCELLED_TASK_LOCK:
        shared.cancelled_task_ids.clear()
    shared.clear_interrupted()
    shared.set_current_mode("desensitize")

    conn = ts._get_conn()
    conn.execute("DELETE FROM task_store")
    conn.commit()

    yield

    shared.processing_event.clear()
    shared.pause_event.clear()
    shared.abort_event.clear()


@pytest.fixture
def page(browser, base_url):
    context = browser.new_context()
    page = context.new_page()
    page.goto(base_url, wait_until="domcontentloaded")
    page.wait_for_selector("#logPanel", timeout=10000)
    time.sleep(0.3)
    yield page
    context.close()


def _upload_via_dom(page, content, filename="test.txt"):
    import base64
    b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    page.evaluate(f"""
        const b64 = "{b64}";
        const name = "{filename}";
        const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
        const blob = new Blob([bytes], {{type: 'text/plain'}});
        const file = new File([blob], name, {{type: 'text/plain'}});
        const dt = new DataTransfer();
        dt.items.add(file);
        const input = document.querySelector('input[type="file"]');
        if (input) {{ input.files = dt.files; input.dispatchEvent(new Event('change')); }}
    """)

    time.sleep(0.5)
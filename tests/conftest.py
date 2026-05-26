import os
import sys
import json
import copy
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_CONFIG = {
    "mode": "desensitize",
    "extraction": {
        "auto_merge": True, "multimodal": True, "templates": [],
        "active_template_index": 0, "export_path": "", "docx_image_extract": False
    },
    "llm": {
        "provider": "lm_studio", "base_url": "http://127.0.0.1:1234/v1",
        "api_key": "", "model": "qwen/qwen3-v1-8b",
        "temperature": 0.3, "max_tokens": 2048, "timeout": 300,
        "multimodal": True, "reasoning_effort": None, "enable_thinking": False
    },
    "lm_studio": {
        "host": "127.0.0.1", "port": "1234", "model": "qwen/qwen3-v1-8b",
        "api_key": "", "temperature": 0.3, "max_tokens": 2048, "timeout": 300,
        "reasoning_effort": None, "enable_thinking": False
    },
    "server": {"host": "0.0.0.0", "port": 5000, "debug": False},
    "desensitization": {
        "depth": "quick", "placeholder": "xxx",
        "date_format": "YYYY-MM-DD", "output_dir": "output"
    },
    "prompt": {"first_pass": "", "second_pass": ""},
    "llm_profiles": {"profiles": []}
}


@pytest.fixture
def temp_config():
    td = tempfile.mkdtemp()
    cfg_path = os.path.join(td, "test_config.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(copy.deepcopy(TEST_CONFIG), f)

    import app.shared as shared
    old_path = shared.CONFIG_PATH
    old_config = copy.deepcopy(shared.config)
    old_output = shared.OUTPUT_DIR

    shared.CONFIG_PATH = cfg_path
    shared.reload_config()
    shared.OUTPUT_DIR = shared.BASE_DIR / "output"

    yield cfg_path

    import shutil
    shared.CONFIG_PATH = old_path
    shared.config = old_config
    shared.OUTPUT_DIR = old_output
    shutil.rmtree(td, ignore_errors=True)


@pytest.fixture
def app(temp_config):
    from app.routes import app as flask_app
    flask_app.config["TESTING"] = True
    flask_app.config["SERVER_NAME"] = None
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()

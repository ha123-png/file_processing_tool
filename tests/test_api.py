import json
import pytest


class TestConfigAPI:
    def test_get_config_returns_all_sections(self, client):
        r = client.get("/api/config")
        assert r.status_code == 200
        d = r.json
        assert "llm" in d
        assert "desensitization" in d
        assert "extraction" in d
        assert "server" in d

    def test_get_config_masks_api_key(self, client):
        r = client.get("/api/config")
        assert r.status_code == 200
        api_key = r.json["llm"]["api_key"]
        assert api_key == ""

    def test_post_config_rejects_disallowed_key(self, client):
        r = client.post("/api/config", json={"bad_key": {}})
        assert r.status_code == 400
        assert "不允许" in r.json["error"]

    def test_post_config_updates_llm(self, client):
        r = client.post("/api/config", json={"llm": {"provider": "openai", "api_key": "sk-test-12345"}})
        assert r.status_code == 200
        r = client.get("/api/config")
        cfg = r.json
        assert cfg["llm"]["provider"] == "openai"
        assert "***" in cfg["llm"]["api_key"] or cfg["llm"]["api_key"] == ""

    def test_post_config_preserves_key_on_mask(self, client):
        client.post("/api/config", json={"llm": {"api_key": "sk-original-key"}})
        r = client.post("/api/config", json={"llm": {"api_key": "sk-o***al-key"}})
        assert r.status_code == 200
        r = client.get("/api/config")
        assert "***" in r.json["llm"]["api_key"]

    def test_post_config_unknown_endpoint(self, client):
        r = client.post("/api/config", json={})
        assert r.status_code in (200, 400)


class TestProfilesAPI:
    def test_get_empty_profiles(self, client):
        r = client.get("/api/llm_profiles")
        assert r.status_code == 200
        assert r.json["profiles"] == []

    def test_create_and_get_profiles(self, client):
        data = {"profiles": [
            {"name": "TestProfile", "provider": "ollama", "base_url": "http://localhost:11434/v1",
             "api_key": "", "model": "llama3", "max_tokens": 4096, "timeout": 300,
             "multimodal": False, "enable_thinking": False}
        ]}
        r = client.post("/api/llm_profiles", json=data)
        assert r.status_code == 200
        r = client.get("/api/llm_profiles")
        assert len(r.json["profiles"]) == 1
        assert r.json["profiles"][0]["name"] == "TestProfile"

    def test_profile_api_key_masked(self, client):
        data = {"profiles": [
            {"name": "CloudX", "provider": "openai", "base_url": "https://api.openai.com/v1",
             "api_key": "sk-long-key-12345", "model": "gpt-4o", "max_tokens": 4096,
             "timeout": 300, "multimodal": True, "enable_thinking": False}
        ]}
        client.post("/api/llm_profiles", json=data)
        r = client.get("/api/llm_profiles")
        for p in r.json["profiles"]:
            if p["name"] == "CloudX":
                assert "***" in p["api_key"]

    def test_delete_profile(self, client):
        client.post("/api/llm_profiles", json={"profiles": [
            {"name": "ToDelete", "provider": "ollama", "base_url": "http://localhost:11434/v1",
             "api_key": "", "model": "llama3", "max_tokens": 4096, "timeout": 300,
             "multimodal": False, "enable_thinking": False}
        ]})
        r = client.post("/api/llm_profiles", json={"profiles": []})
        assert r.status_code == 200
        r = client.get("/api/llm_profiles")
        assert r.json["profiles"] == []

    def test_profile_missing_name(self, client):
        r = client.post("/api/llm_profiles", json={"profiles": [{"provider": "ollama"}]})
        assert r.status_code == 400


class TestStaticPages:
    def test_index_page_loads(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "脱敏" in r.data.decode("utf-8")

    def test_static_css(self, client):
        r = client.get("/static/style.css")
        assert r.status_code == 200

    @pytest.mark.parametrize("js_file", [
        "app.js", "extract.js", "settings.js", "dashboard.js"
    ])
    def test_js_files_load(self, client, js_file):
        r = client.get(f"/static/js/{js_file}")
        assert r.status_code == 200
        assert len(r.data) > 100


class TestModeAPI:
    def test_get_default_mode(self, client):
        r = client.get("/api/mode")
        assert r.status_code == 200
        assert "mode" in r.json

    def test_set_mode(self, client):
        r = client.post("/api/mode", json={"mode": "extract"})
        assert r.status_code == 200
        r = client.get("/api/mode")
        assert r.json["mode"] == "extract"

    def test_set_invalid_mode(self, client):
        r = client.post("/api/mode", json={"mode": "invalid"})
        assert r.status_code == 400


class TestCleanUploads:
    def test_cleanup(self, client):
        r = client.post("/api/cleanup_uploads", json={"keep": 10})
        assert r.status_code == 200
        assert "清理" in r.json["message"] or "removed" in r.json


class TestSaveSettings:
    def test_save_settings_partial(self, client):
        body = {
            "config": {
                "desensitization": {"placeholder": "***"},
                "llm": {"multimodal": False}
            }
        }
        r = client.post("/api/save_settings", json=body)
        assert r.status_code == 200

    def test_save_settings_with_prompt(self, client):
        body = {
            "config": {"desensitization": {"depth": "standard"}},
            "prompt": {"first_pass": "你是安全专家"}
        }
        r = client.post("/api/save_settings", json=body)
        assert r.status_code == 200


class TestQueueAPI:
    def test_pause(self, client):
        r = client.post("/api/queue/pause")
        assert r.status_code == 200


class TestExcelRoutes:
    def test_list_sheets_empty(self, client):
        r = client.get("/api/list_sheets")
        assert r.status_code == 200
        assert r.json["active"] is None
        assert r.json["sheets"] == NotImplemented or r.json["sheets"] == []


class TestDownload:
    def test_download_nonexistent(self, client):
        r = client.get("/api/download/nonexistent.txt")
        assert r.status_code in (200, 404)

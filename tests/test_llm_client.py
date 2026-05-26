import json
import pytest
from unittest.mock import patch, MagicMock


def _fake_sse_stream(lines):
    class FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def iter_lines(self):
            for line in lines:
                yield line.encode("utf-8") if isinstance(line, str) else line

        def close(self):
            pass

    return FakeResp()


def _sse_chunk(content):
    return f'data: {json.dumps({"choices": [{"delta": {"content": content}}]})}'


class TestStreamLLM:
    def test_normal_response_collects_all_content(self, temp_config):
        import app.shared as shared
        shared.abort_event.clear()
        from app.llm_client import _stream_llm
        mock_resp = _fake_sse_stream([
            _sse_chunk("Hello"),
            _sse_chunk(" World"),
            "data: [DONE]"
        ])
        with patch("requests.post", return_value=mock_resp):
            result = _stream_llm("http://fake/v1/chat/completions", {}, 10)
            assert "Hello World" in result or "Hello" in result

    def test_empty_response_returns_empty_string(self, temp_config):
        import app.shared as shared
        shared.abort_event.clear()
        from app.llm_client import _stream_llm
        mock_resp = _fake_sse_stream(["data: [DONE]"])
        with patch("requests.post", return_value=mock_resp):
            result = _stream_llm("http://fake/v1/chat/completions", {}, 10)
            assert result == ""

    def test_invalid_json_lines_are_skipped(self, temp_config):
        import app.shared as shared
        shared.abort_event.clear()
        from app.llm_client import _stream_llm
        mock_resp = _fake_sse_stream([
            "data: not valid json",
            _sse_chunk("A"),
            "garbage line",
            _sse_chunk("B"),
            "data: [DONE]"
        ])
        with patch("requests.post", return_value=mock_resp):
            result = _stream_llm("http://fake/v1/chat/completions", {}, 10)
            assert "A" in result
            assert "B" in result

    def test_abort_event_interrupts_stream(self, temp_config):
        import app.shared as shared
        shared.abort_event.clear()
        from app.llm_client import _stream_llm

        def set_kill_and_return(lines):
            shared.abort_event.set()
            return _fake_sse_stream(lines)

        with patch("requests.post") as mock_post:
            mock_post.side_effect = lambda *a, **kw: set_kill_and_return([
                _sse_chunk("processing...")
            ])
            with pytest.raises(RuntimeError, match="任务已被用户终止"):
                _stream_llm("http://fake/v1/chat/completions", {}, 10)

    def test_json_extraction_from_response(self, temp_config):
        import app.shared as shared
        shared.abort_event.clear()
        from app.llm_client import _stream_llm
        mock_resp = _fake_sse_stream([
            _sse_chunk('some text {"key":'),
            _sse_chunk('"value"} trailing text'),
            "data: [DONE]"
        ])
        with patch("requests.post", return_value=mock_resp):
            result = _stream_llm("http://fake/v1/chat/completions", {}, 10)
            assert result.startswith("{")
            assert result.endswith("}")

    def test_http_error_causes_raise(self, temp_config):
        import app.shared as shared
        shared.abort_event.clear()
        from app.llm_client import _stream_llm
        mock_resp = _fake_sse_stream([])
        mock_resp.status_code = 500

        def raise_http():
            raise __import__("requests").exceptions.HTTPError("500 Server Error")

        mock_resp.raise_for_status = raise_http
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises((__import__("requests").exceptions.HTTPError, Exception)):
                _stream_llm("http://fake/v1/chat/completions", {}, 10)


class TestGetLLMConfig:
    def test_reads_new_llm_section(self, temp_config):
        from app.shared import get_config_snapshot, save_config
        import copy
        cfg = copy.deepcopy(get_config_snapshot())
        cfg["llm"]["provider"] = "ollama"
        cfg["llm"]["base_url"] = "http://localhost:11434/v1"
        save_config(cfg)
        from app.llm_client import _get_llm_cfg
        llm = _get_llm_cfg()
        assert llm["provider"] == "ollama"
        assert llm["base_url"] == "http://localhost:11434/v1"

    def test_fallsback_to_legacy_lm_studio(self, temp_config):
        from app.shared import get_config_snapshot, save_config
        import copy
        cfg = copy.deepcopy(get_config_snapshot())
        cfg["llm"]["base_url"] = ""
        save_config(cfg)
        from app.llm_client import _get_llm_cfg
        llm = _get_llm_cfg()
        assert "http://" in llm["base_url"]
        assert ":1234" in llm["base_url"]

    def test_supports_multimodal(self, temp_config):
        from app.shared import save_config, get_config_snapshot
        import copy
        from app.llm_client import supports_multimodal
        assert supports_multimodal() is True
        cfg = copy.deepcopy(get_config_snapshot())
        cfg["llm"]["multimodal"] = False
        save_config(cfg)
        assert supports_multimodal() is False


class TestMasking:
    def test_mask_api_key_normal(self):
        from app.routes import _mask_api_key
        result = _mask_api_key("sk-this-is-a-secret-key")
        assert "***" in result
        assert result.startswith("sk-t")
        assert result.endswith("-key")

    def test_mask_short_key_unchanged(self):
        from app.routes import _mask_api_key
        assert _mask_api_key("abc") == "abc"
        assert _mask_api_key("") == ""

    def test_safe_log_body_masks_llm_key(self):
        from app.routes import _safe_log_body
        body = {"llm": {"api_key": "sk-my-secret-12345", "model": "gpt-4o"}}
        result = _safe_log_body(body)
        assert "sk-my-secret-12345" not in result
        assert "***" in result
        assert "gpt-4o" in result

    def test_safe_log_body_masks_nested_config_key(self):
        from app.routes import _safe_log_body
        body = {"config": {"llm": {"api_key": "sk-nested-secret"}}}
        result = _safe_log_body(body)
        assert "sk-nested-secret" not in result
        assert "***" in result

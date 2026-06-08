import json
import base64
import threading
import requests
from pathlib import Path
from app.shared import get_config_snapshot, abort_event

def _is_aborted():
    return abort_event.is_set()

def _get_llm_cfg():
    cfg = get_config_snapshot()
    llm = cfg.get("llm")
    if llm and llm.get("base_url"):
        return llm
    legacy = cfg.get("lm_studio", {})
    return {
        "provider": "lm_studio",
        "base_url": f"http://{legacy.get('host', '127.0.0.1')}:{legacy.get('port', '1234')}/v1",
        "api_key": legacy.get("api_key", ""),
        "model": legacy.get("model", ""),
        "temperature": legacy.get("temperature", 0.3),
        "max_tokens": legacy.get("max_tokens", 2048),
        "timeout": legacy.get("timeout", 300),
        "multimodal": True,
        "enable_thinking": legacy.get("enable_thinking", True),
        "reasoning_effort": legacy.get("reasoning_effort")
    }

def supports_multimodal():
    return _get_llm_cfg().get("multimodal", True)

def _stream_llm(url, payload, timeout, api_key=""):
    """流式调用 LLM API，iter_content + 手动缓冲避免 Windows 下 iter_lines 的编码问题"""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=timeout)
    resp.raise_for_status()

    resp_ref = [resp]
    def _watchdog():
        while not _is_aborted():
            abort_event.wait(0.5)
        try:
            resp_ref[0].close()
        except Exception:
            pass
    watcher = threading.Thread(target=_watchdog, daemon=True)
    watcher.start()

    full_content = ""
    last_chunk = ""
    repeat_count = 0
    try:
        for raw_line in resp.iter_lines():
            if _is_aborted():
                resp.close()
                raise RuntimeError("任务已被用户终止")
            if not raw_line:
                continue
            line = raw_line.decode("utf-8")
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_content += content
                        if len(content) >= 3:
                            if content == last_chunk:
                                repeat_count += 1
                                if repeat_count >= 5:
                                    resp.close()
                                    break
                            else:
                                repeat_count = 0
                            last_chunk = content
                except (json.JSONDecodeError, IndexError, KeyError):
                    pass
    except Exception:
        if _is_aborted():
            try: resp.close()
            except Exception: pass
            raise RuntimeError("任务已被用户终止")
        raise

    if _is_aborted():
        try: resp.close()
        except Exception: pass
        raise RuntimeError("任务已被用户终止")
    full_content = full_content.strip()
    return full_content

def call_lm_studio(text, system_prompt):
    if _is_aborted():
        raise RuntimeError("任务已被用户终止")
    llm = _get_llm_cfg()
    url = f"{llm['base_url'].rstrip('/')}/chat/completions"
    payload = {
        "model": llm.get("model", ""),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "temperature": llm.get("temperature", 0.3),
        "max_tokens": llm.get("max_tokens", 2048),
        "stream": True
    }
    reasoning = llm.get("reasoning_effort")
    if reasoning and reasoning in ("low", "medium", "high"):
        payload["reasoning_effort"] = reasoning
    if llm.get("enable_thinking") is False:
        payload["enable_thinking"] = False
    return _stream_llm(url, payload, llm.get("timeout", 300), llm.get("api_key", ""))

def call_lm_studio_multimodal_multi(image_paths, system_prompt):
    """多张图片合并为一次多模态请求。image_paths: 图片路径列表"""
    if _is_aborted():
        raise RuntimeError("任务已被用户终止")
    if not supports_multimodal():
        raise RuntimeError("当前模型不支持多模态")
    llm = _get_llm_cfg()
    url = f"{llm['base_url'].rstrip('/')}/chat/completions"
    user_content = []
    for img_path in image_paths:
        try:
            with open(img_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
        except FileNotFoundError:
            raise RuntimeError(f"图片文件不存在: {img_path}")
        ext = Path(img_path).suffix.lower().lstrip(".")
        if ext == "jpg":
            ext = "jpeg"
        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{img_b64}"}})
    user_content.append({"type": "text", "text": "请提取以上所有图片中的结构化信息。"})
    payload = {
        "model": llm.get("model", ""),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.1,
        "max_tokens": llm.get("max_tokens", 4096),
        "stream": True
    }
    if llm.get("enable_thinking") is False:
        payload["enable_thinking"] = False
    return _stream_llm(url, payload, llm.get("timeout", 300), llm.get("api_key", ""))

def call_lm_studio_multimodal(image_path, system_prompt):
    if _is_aborted():
        raise RuntimeError("任务已被用户终止")
    if not supports_multimodal():
        raise RuntimeError("当前模型不支持多模态（图片/PDF识别），请在设置中开启多模态支持")
    llm = _get_llm_cfg()
    url = f"{llm['base_url'].rstrip('/')}/chat/completions"
    try:
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
    except FileNotFoundError:
        raise RuntimeError(f"图片文件不存在: {image_path}")
    except Exception as e:
        raise RuntimeError(f"读取图片文件失败: {image_path}, {e}")
    ext = Path(image_path).suffix.lower().lstrip(".")
    if ext == "jpg":
        ext = "jpeg"
    payload = {
        "model": llm.get("model", ""),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{img_b64}"}},
                {"type": "text", "text": "请提取这张图片中的结构化信息。"}
            ]}
        ],
        "temperature": 0.1,
        "max_tokens": llm.get("max_tokens", 2048),
        "stream": True
    }
    if llm.get("enable_thinking") is False:
        payload["enable_thinking"] = False
    return _stream_llm(url, payload, llm.get("timeout", 300), llm.get("api_key", ""))

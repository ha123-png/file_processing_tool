import os
import re
import json
import time
import threading
from datetime import datetime
from pathlib import Path

try:
    import fitz
except ImportError:
    fitz = None

from app.shared import (
    get_config_snapshot, send_sse, logger,
    IMAGE_FORMATS, TEXT_FORMATS, DOCX_FORMATS, PDF_FORMATS, OUTPUT_DIR, CACHE_DIR,
    pause_event, abort_event, task_queue,
    processing_event, _prompt_override, _PROMPT_LOCK,
    PROMPT_FOOTER_FIRST, PROMPT_FOOTER_SECOND, get_current_mode,
    set_interrupted, TaskStatus
)
from app.llm_client import call_lm_studio, call_lm_studio_multimodal, call_lm_studio_multimodal_multi, supports_multimodal
from app.file_handler import (
    read_text_file, read_docx_file, _docx_has_images, read_docx_with_images
)
from app.regex_rules import (
    preprocess_ocr_text, ensure_plain_text, clean_ocr_text, normalize_date_format,
    match_regex_sensitive, flag_ambiguous, strip_ambiguity_markers,
    normalize_spaced_numbers
)
from app.excel_manager import merge_to_excel
from app.stats_db import insert_stats
def get_active_template():
    cfg = get_config_snapshot()
    templates = cfg.get("extraction", {}).get("templates", [])
    if not templates:
        return None
    idx = cfg.get("extraction", {}).get("active_template_index", 0)
    if idx < 0 or idx >= len(templates):
        idx = 0
    return templates[idx]

def make_prompt(pass_index=0):
    footer = PROMPT_FOOTER_SECOND if pass_index == 1 else PROMPT_FOOTER_FIRST
    key = "second_pass" if pass_index == 1 else "first_pass"
    with _PROMPT_LOCK:
        override = _prompt_override.get(key)
    if override:
        return override + footer
    cfg = get_config_snapshot()
    default = cfg.get("prompt", {}).get(key, "")
    if default:
        return default + footer
    return (
        "你是法务脱敏专家。在提供的文本中找出所有敏感信息，一个不漏。包括：\n"
        "- 金额、价格、所有数字\n"
        "- 公司名、人名、地名、机构名\n"
        "- 手机号、身份证号、邮箱、联系方式\n"
        "- 日期、合同编号、证件编号\n"
        "- 《》「」【】（）[]内的全部内容\n"
        "注意：以上所有类别都必须完整识别，缺一不可。"
    ) + footer

def parse_sensitive_items(sensitive_str):
    text = sensitive_str.strip()
    items = []
    pos = 0
    while True:
        start = text.find('{', pos)
        if start == -1:
            break
        depth = 0
        end = -1
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end == -1:
            break
        try:
            chunk = text[start:end+1]
            data = json.loads(chunk)
            chunk_items = data.get("sensitive_info", [])
            for x in chunk_items:
                s = str(x).strip()
                if s and s not in items:
                    items.append(s)
        except (json.JSONDecodeError, Exception):
            pass
        pos = end + 1
    if items:
        return items
    if text and text != "已脱敏":
        fallback = [s.strip() for s in re.split(r"[，,、\s]+", text) if s.strip()]
        if fallback and fallback[-1] == "已脱敏":
            fallback = fallback[:-1]
        return fallback
    return []

def apply_replacement(original, sensitive_str):
    placeholder = get_config_snapshot()["desensitization"]["placeholder"]
    items = parse_sensitive_items(sensitive_str)
    result = original
    for item in items:
        if item and item != placeholder:
            result = result.replace(item, placeholder)
    return result

def build_extraction_prompt(template):
    if not template:
        return ""
    fields = template.get("fields", [])
    header_fields = [f for f in fields if f.get("section") == "header"]
    item_fields = [f for f in fields if f.get("section") == "item"]
    parts = ["你是票据提取专家，从以下文本提取结构化信息。"]
    parts.append(f"模板：{template.get('name', '')}")
    if header_fields:
        hf_parts = []
        for f in header_fields:
            hf_parts.append(f'"{f["label"]}"')
        parts.append("抬头字段：" + "、".join(hf_parts))
    if item_fields:
        it_parts = []
        for f in item_fields:
            it_parts.append(f'"{f["label"]}"')
        parts.append("明细字段：每个item对象包含 " + "、".join(it_parts))
    parts.append("输出JSON：抬头字段名直接使用上面的中文名称作为JSON的key，明细放入items数组中，每个item对应一条明细。找不到的字段值设为null。")
    parts.append('示例格式：{"购买方名称":"某某公司","纳税人识别号":"91110...","items":[{"项目名称":"货物A","数量":"1"}],"item_count":1}')
    parts.append("严格使用【内容开始】和【内容结束】包裹你的JSON输出。仅输出JSON，不要任何解释。")
    return "\n".join(parts)

def deduplicate_items(items, item_keys):
    if len(items) <= 1:
        return items
    result = []
    skip = set()
    for i in range(len(items)):
        if i in skip:
            continue
        cur = items[i]
        if not isinstance(cur, dict):
            continue
        filled = sum(1 for k in item_keys if cur.get(k))
        total = len(item_keys) if item_keys else 1
        if filled >= total * 0.5:
            result.append(cur)
            continue
        merged = False
        for j in range(i + 1, len(items)):
            if j in skip:
                continue
            nxt = items[j]
            if not isinstance(nxt, dict):
                continue
            merged_item = dict(cur)
            for k in item_keys:
                if not merged_item.get(k) and nxt.get(k):
                    merged_item[k] = nxt[k]
            new_filled = sum(1 for k in item_keys if merged_item.get(k))
            if new_filled > filled:
                result.append(merged_item)
                skip.add(j)
                merged = True
                break
        if not merged:
            result.append(cur)
    return result

def _clean_numeric_field(val, is_tax_rate=False):
    if not val or not isinstance(val, str):
        return val
    v = val.strip()
    import re as _re
    if is_tax_rate:
        v = _re.sub(r'[¥￥$€]', '', v)
        v = v.replace('RMB', '').replace('CNY', '').replace('USD', '').replace('EUR', '')
        v = v.strip()
        if v.endswith('%'):
            try:
                num = float(v[:-1].strip())
                return str(num / 100)
            except (ValueError, TypeError):
                pass
        try:
            num = float(v)
            return str(num)
        except (ValueError, TypeError):
            return val
    v = _re.sub(r'[¥￥$€]', '', v)
    v = v.replace('万元', '').replace('元', '').replace('RMB', '').replace('CNY', '').replace('USD', '').replace('EUR', '')
    v = _re.sub(r'[,\s]', '', v)
    v = v.strip()
    try:
        num = float(v)
        if num == int(num):
            return str(int(num))
        return str(num)
    except (ValueError, TypeError):
        return val

NUMERIC_KEYS = {"价税合计", "数量", "单价", "金额", "税率/征收率", "税额"}

def _extract_all_json_objects(text):
    """从文本中逐个提取所有合法JSON对象，跳过中间的非JSON内容。"""
    results = []
    decoder = json.JSONDecoder()
    idx = 0
    text_len = len(text)
    while idx < text_len:
        brace_idx = text.find('{', idx)
        if brace_idx == -1:
            break
        try:
            obj, end_idx = decoder.raw_decode(text, brace_idx)
            if isinstance(obj, dict):
                results.append(obj)
            idx = brace_idx + end_idx
        except json.JSONDecodeError:
            idx = brace_idx + 1
    return results

def parse_extraction_result(raw_json_str, template):
    json_str = _extract_between_markers(raw_json_str)
    json_str = json_str.strip()
    if json_str.startswith("```"):
        json_str = json_str.split("\n", 1)[-1]
        json_str = json_str.rsplit("```", 1)[0]

    # 优先 json.loads 直接解析，失败则用 _extract_all_json_objects 兜底取第一个 dict
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        objs = _extract_all_json_objects(json_str)
        data = objs[0] if objs else {"item_count": 0, "items": []}
    # 鲁棒处理：展平嵌套 {"header":{...}} → 顶层字段
    if isinstance(data.get("header"), dict):
        nested = data["header"]
        for k, v in nested.items():
            if data.get(k) in (None, "", [], {}):
                data[k] = v
        del data["header"]
    header_keys = [f["label"] for f in (template or {}).get("fields", []) if f.get("section") == "header"]
    item_keys = [f["label"] for f in (template or {}).get("fields", []) if f.get("section") == "item"]
    tpl_name = (template or {}).get("name", "")
    is_invoice = "发票" in tpl_name
    header = {}
    for k in header_keys:
        val = data.get(k)
        if val and str(val).strip():
            v = str(val).strip()
            if is_invoice and k in NUMERIC_KEYS:
                v = _clean_numeric_field(v, is_tax_rate=(k == "税率/征收率"))
            header[k] = v
        else:
            header[k] = ""
    items = data.get("items", [])
    if not isinstance(items, list):
        items = []
    deduped = deduplicate_items(items, item_keys)
    if is_invoice:
        for item in deduped:
            for k in list(item.keys()):
                if k in NUMERIC_KEYS and isinstance(item[k], str):
                    item[k] = _clean_numeric_field(item[k], is_tax_rate=(k == "税率/征收率"))
    date_format = get_config_snapshot().get("desensitization", {}).get("date_format", "YYYY年MM月DD日")
    date_pattern = re.compile(r'^\d{4}\s*[-/\.年]\s*\d{1,2}\s*[-/\.月]\s*\d{1,2}')
    for k in header:
        if date_pattern.match(header[k]):
            header[k] = normalize_date_format(header[k], date_format)
    for item in deduped:
        for k in item:
            if isinstance(item[k], str) and date_pattern.match(item[k]):
                item[k] = normalize_date_format(item[k], date_format)
    return {"header": header, "items": deduped, "item_count": len(deduped)}

def _extract_between_markers(raw):
    if not raw or not isinstance(raw, str):
        return raw
    start = raw.find("【内容开始】")
    end = raw.find("【内容结束】")
    if start != -1 and end != -1 and end > start:
        return raw[start + 6:end].strip()
    return raw

def _is_paused():
    return pause_event.is_set()

def _is_aborted():
    return abort_event.is_set()

def _check_paused():
    if _is_paused():
        raise RuntimeError("任务已被用户终止")

def _save_checkpoint(task_state, cp_name, cp_data):
    task_state.checkpoint = cp_name
    task_state.checkpoint_data = cp_data
    from app.task_store import update_checkpoint
    update_checkpoint(task_state.task_id, cp_name, cp_data)

def _save_checkpoint_data(cp_name, cp_data, task_id):
    from app.task_store import update_checkpoint
    update_checkpoint(task_id, cp_name, cp_data)

def _restore_checkpoint(task_state):
    return task_state.checkpoint, task_state.checkpoint_data

def process_file_extraction(filepath, original_name, queue_id=None, group_id=None):
    task_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    _start_time = time.time()
    abort_event.clear()
    template = get_active_template()
    if not template:
        send_sse("result", {"id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "error", "message": "未配置提取模板"})
        return
    ext_lower = Path(original_name).suffix.lower()
    is_image = ext_lower in IMAGE_FORMATS or ext_lower in PDF_FORMATS
    if is_image and not supports_multimodal():
        send_sse("log", {"level": "warning", "message": f"[{original_name}] 当前模型未开启多模态支持，已跳过（可在设置中开启）"})
        send_sse("result", {"id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "error", "message": "当前模型不支持多模态（图片/PDF），请在设置中开启多模态支持"})
        return
    original_file_url = ""
    if ext_lower in IMAGE_FORMATS:
        orig_copy = CACHE_DIR / f"__orig_{task_id}{Path(original_name).suffix}"
        try:
            import shutil
            shutil.copy2(filepath, orig_copy)
            original_file_url = f"__orig_{task_id}{Path(original_name).suffix}"
        except:
            pass
    elif ext_lower in PDF_FORMATS:
        try:
            doc = fitz.open(filepath)
            page = doc[0]
            mat = fitz.Matrix(1.5, 1.5)
            pix = page.get_pixmap(matrix=mat)
            orig_copy = CACHE_DIR / f"__orig_{task_id}.png"
            pix.save(str(orig_copy))
            doc.close()
            original_file_url = f"__orig_{task_id}.png"
        except:
            pass
    try:
        send_sse("log", {"level": "info", "message": f"[{original_name}] 开始提取..."})
        is_image = ext_lower in IMAGE_FORMATS or ext_lower in PDF_FORMATS
        if is_image:
            if ext_lower in PDF_FORMATS:
                send_sse("log", {"level": "info", "message": f"[{original_name}] 检测为PDF，使用多模态模型提取（多页合并）..."})
                doc = fitz.open(filepath)
                prompt = build_extraction_prompt(template)
                total_pages = len(doc)
                page_jsons = []
                page_imgs = []
                for page_idx in range(total_pages):
                    page_img = None
                    try:
                        mat = fitz.Matrix(2, 2)
                        pix = doc[page_idx].get_pixmap(matrix=mat)
                        page_img = str(filepath) + f"_ext_page{page_idx}.png"
                        pix.save(page_img)
                        page_imgs.append(page_img)
                        raw_page = call_lm_studio_multimodal(page_img, prompt)
                        # 解析该页JSON
                        all_jsons = _extract_all_json_objects(raw_page)
                        if all_jsons:
                            field_keys = [f["label"] for f in (template or {}).get("fields", [])]
                            best = max(all_jsons, key=lambda o: sum(1 for k in field_keys if o.get(k) not in (None, "", [], {})))
                            # 展平嵌套header
                            if isinstance(best.get("header"), dict):
                                for k, v in best["header"].items():
                                    if best.get(k) in (None, "", [], {}):
                                        best[k] = v
                                del best["header"]
                            page_jsons.append(best)
                        else:
                            page_jsons.append({"items": []})
                    except Exception as page_err:
                        send_sse("log", {"level": "warning", "message": f"[{original_name}] PDF第{page_idx+1}页提取失败: {page_err}"})
                        page_jsons.append({"items": []})
                doc.close()
                # 清理临时图片
                for pi in page_imgs:
                    try: os.remove(pi)
                    except OSError: pass
                if not page_jsons:
                    raise RuntimeError(f"PDF共{total_pages}页，全部提取失败")
                # 智能合并：header取各页中非空值，items拼接
                merged = {}
                for pj in page_jsons:
                    for k, v in pj.items():
                        if k == "items":
                            merged.setdefault("items", []).extend(v if isinstance(v, list) else [])
                        elif v not in (None, "", [], {}):
                            if k not in merged or merged[k] in (None, "", [], {}):
                                merged[k] = v
                if "items" not in merged:
                    merged["items"] = []
                raw_result = json.dumps(merged, ensure_ascii=False)
                raw = raw_result
                send_sse("log", {"level": "info", "message": f"[{original_name}] PDF共{total_pages}页，多模态提取完成"})
            else:
                send_sse("log", {"level": "info", "message": f"[{original_name}] 检测为图片，使用多模态模型直接识别..."})
                prompt = build_extraction_prompt(template)
                raw_result = call_lm_studio_multimodal(filepath, prompt)
                raw = raw_result
        else:
            if ext_lower in TEXT_FORMATS:
                raw = read_text_file(filepath)
            elif ext_lower in DOCX_FORMATS:
                docx_img_extract = get_config_snapshot().get("extraction", {}).get("docx_image_extract", False)
                if docx_img_extract and _docx_has_images(filepath):
                    send_sse("log", {"level": "info", "message": f"[{original_name}] 检测为Word文档(含图片)，尝试转为PDF处理..."})
                    tmp_pdf = str(filepath) + f"_conv_{task_id}.pdf"
                    pdf_ok = False
                    try:
                        from docx2pdf import convert
                        convert(filepath, tmp_pdf)
                        if os.path.exists(tmp_pdf) and os.path.getsize(tmp_pdf) > 0:
                            pdf_ok = True
                    except Exception as e:
                        send_sse("log", {"level": "warning", "message": f"[{original_name}] Word转PDF失败({e})，改用图片逐张识别"})
                    if pdf_ok:
                        try:
                            send_sse("log", {"level": "info", "message": f"[{original_name}] 已转为PDF，使用多模态模型逐页提取..."})
                            doc = fitz.open(tmp_pdf)
                            prompt = build_extraction_prompt(template)
                            raw_results = []
                            total_pages = len(doc)
                            for page_idx in range(total_pages):
                                mat = fitz.Matrix(2, 2)
                                pix = doc[page_idx].get_pixmap(matrix=mat)
                                page_img = str(filepath) + f"_docx_page{page_idx}.png"
                                pix.save(page_img)
                                raw_result = call_lm_studio_multimodal(page_img, prompt)
                                raw_results.append(raw_result)
                                os.remove(page_img)
                            doc.close()
                            raw = "\n\n".join(raw_results) if len(raw_results) > 1 else (raw_results[0] if raw_results else "")
                            raw_result = raw
                            send_sse("log", {"level": "info", "message": f"[{original_name}] Word(PDF)共{total_pages}页，多模态提取完成"})
                        finally:
                            try: os.remove(tmp_pdf)
                            except OSError: pass
                    else:
                        send_sse("log", {"level": "info", "message": f"[{original_name}] 降级为图片逐张识别..."})
                        para_text, image_infos = read_docx_with_images(filepath)
                        text_parts = [para_text] if para_text.strip() else []
                        for info in image_infos:
                            img_path = info.get("path")
                            if not img_path:
                                continue
                            prompt = "请完整提取这张图片中的所有文字内容。用【内容开始】和【内容结束】包裹你的输出。"
                            ctx = []
                            if info.get("before"):
                                ctx.append(f"位于以下段落之后：【{info['before']}】")
                            if info.get("after"):
                                ctx.append(f"后续段落：【{info['after']}】")
                            if ctx:
                                prompt += " " + "。".join(ctx) + "。"
                            try:
                                ocr = call_lm_studio_multimodal(img_path, prompt)
                                img_t = ensure_plain_text(ocr)
                                img_t = clean_ocr_text(img_t)
                                if img_t.strip():
                                    text_parts.append(img_t)
                            except Exception as e:
                                send_sse("log", {"level": "warning", "message": f"[{original_name}] 文档内图片识别失败: {e}"})
                            finally:
                                try: os.remove(img_path)
                                except OSError: pass
                        raw = "\n\n".join(text_parts) if text_parts else para_text
                else:
                    raw = read_docx_file(filepath)
            else:
                raise RuntimeError(f"不支持的文件格式: {ext_lower}")
            if not raw.strip():
                raise RuntimeError("未能提取到任何文本内容")
            text = preprocess_ocr_text(raw)
            send_sse("log", {"level": "info", "message": f"[{original_name}] 文本读取完成 ({len(text)}字符)，正在调用大模型..."})
            prompt = build_extraction_prompt(template)
            raw_result = call_lm_studio(text, prompt)
        send_sse("log", {"level": "info", "message": f"[{original_name}] 模型返回，正在解析..."})
        parsed = parse_extraction_result(raw_result, template)
        validation = _run_invoice_validation(template, parsed)
        auto = get_config_snapshot().get("extraction", {}).get("auto_merge", False)
        if auto:
            merge_to_excel(parsed, template, file_key=original_name)
            send_sse("log", {"level": "success", "message": f"[{original_name}] 已自动合并到Excel表格 ({parsed['item_count']}条)"})
        else:
            send_sse("log", {"level": "info", "message": f"[{original_name}] 提取完成：{parsed['item_count']} 条明细"})
        field_labels = {f["label"]: f["label"] for f in template.get("fields", [])}
        header_fields = [f for f in template.get("fields", []) if f.get("section") == "header"]
        item_fields = [f for f in template.get("fields", []) if f.get("section") == "item"]
        header_display = {}
        for k, v in parsed["header"].items():
            header_display[k] = {"label": k, "value": v}
        all_field_labels = [f["label"] for f in (header_fields + item_fields)]
        all_field_keys = [f["label"] for f in (header_fields + item_fields)]
        all_field_sections = [f.get("section") for f in (header_fields + item_fields)]
        limit = 8000
        _duration = int(round(time.time() - _start_time))
        send_sse("result", {
            "id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "completed",
            "mode": "extract",
            "parent_task_id": group_id,
            "duration": _duration,
            "original_preview": (raw[:limit] + "..." if len(raw) > limit else raw) if raw else "",
            "extract_header": parsed["header"],
            "extract_header_labels": header_display,
            "extract_fields": all_field_labels,
            "extract_field_keys": all_field_keys,
            "extract_field_sections": all_field_sections,
            "extract_items": parsed["items"],
            "item_count": parsed["item_count"],
            "original_length": len(raw) if raw else 0,
            "auto_merged": auto,
            "original_file_url": original_file_url,
            "invoice_validation": validation
        })
        logger.info(f"Extraction completed: {original_name} ({parsed['item_count']} items)")
        insert_stats(task_id, original_name, "extract", _duration, 0, 1,
                     parsed["item_count"], (len(raw) if raw else 0), 0, 0, 1, "completed")
    except Exception as e:
        err_msg = f"[{original_name}] 提取失败: {str(e)}"
        if _is_paused() or _is_aborted():
            if _is_paused():
                set_interrupted(queue_id)
                if queue_id:
                    try:
                        from app.task_store import update_status as _us
                        _us(queue_id, TaskStatus.WAITING)
                    except Exception:
                        pass
                send_sse("log", {"level": "warning", "message": f"[{original_name}] 已暂停，保留在队列中"})
                send_sse("result", {"id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "paused", "message": "已暂停"})
            else:
                if queue_id:
                    try:
                        from app.task_store import update_status as _us2
                        _us2(queue_id, TaskStatus.CANCELLED)
                    except Exception:
                        pass
                send_sse("log", {"level": "warning", "message": f"[{original_name}] 已取消"})
                send_sse("result", {"id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "cancelled", "message": "已取消"})
        else:
            send_sse("log", {"level": "error", "message": err_msg})
            send_sse("result", {"id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "error", "message": err_msg})
            logger.exception(f"Extraction error {original_name}")
            insert_stats(task_id, original_name, "extract", int(round(time.time() - _start_time)), 0, 0,
                         0, 0, 0, 0, 1, "error")
    finally:
        processing_event.clear()
        send_sse("status", {"queue_size": task_queue.qsize(), "processing": False, "paused": pause_event.is_set()})

def process_file_desensitization(filepath, original_name, queue_id=None, group_id=None, chunk_index=0, total_chunks=1, chunk_ext=None):
    task_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    _start_time = time.time()
    preview_limit = 8000
    abort_event.clear()

    import requests
    try:
        send_sse("log", {"level": "info", "message": f"[{original_name}] 开始处理..."})

        ext_lower = chunk_ext or Path(original_name).suffix.lower()
        if (ext_lower in IMAGE_FORMATS or ext_lower in PDF_FORMATS) and not supports_multimodal():
            send_sse("log", {"level": "warning", "message": f"[{original_name}] 当前模型未开启多模态支持，已跳过（可在设置中开启）"})
            send_sse("result", {"id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "error", "message": "当前模型不支持多模态，请在设置中开启多模态支持"})
            return
        if ext_lower in TEXT_FORMATS:
            send_sse("log", {"level": "info", "message": f"[{original_name}] 检测为文本文件，直接读取..."})
            text = read_text_file(filepath)
        elif ext_lower in DOCX_FORMATS:
            docx_img_extract = get_config_snapshot().get("extraction", {}).get("docx_image_extract", False)
            if docx_img_extract and _docx_has_images(filepath):
                send_sse("log", {"level": "info", "message": f"[{original_name}] 检测为Word文档(含图片)，提取文字+图片..."})
                para_text, img_paths = read_docx_with_images(filepath)
                text_parts = [para_text] if para_text.strip() else []
                for img_path in img_paths:
                    try:
                        ocr = call_lm_studio_multimodal(img_path, "请完整提取这张图片中的所有文字内容。")
                        img_t = ensure_plain_text(ocr)
                        img_t = clean_ocr_text(img_t)
                        if img_t.strip():
                            text_parts.append(img_t)
                    except Exception as e:
                        send_sse("log", {"level": "warning", "message": f"[{original_name}] 文档内图片识别失败: {e}"})
                    finally:
                        try: os.remove(img_path)
                        except OSError: pass
                text = "\n\n".join(text_parts) if text_parts else para_text
            else:
                send_sse("log", {"level": "info", "message": f"[{original_name}] 检测为Word文档，直接读取..."})
                text = read_docx_file(filepath)
        elif ext_lower in IMAGE_FORMATS:
            send_sse("log", {"level": "info", "message": f"[{original_name}] 检测为图片，使用多模态模型提取文本后脱敏..."})
            try:
                prompt = "请完整提取这张图片中的所有文字内容。"
                raw = call_lm_studio_multimodal(filepath, prompt)
                text = ensure_plain_text(raw)
                text = clean_ocr_text(text)
            except Exception as e:
                raise RuntimeError(f"多模态识别失败: {e}")
        elif ext_lower in PDF_FORMATS:
            send_sse("log", {"level": "info", "message": f"[{original_name}] 检测为PDF，使用多模态模型逐页提取文本后脱敏..."})
            try:
                doc = fitz.open(filepath)
                page_texts = []
                total_pages = len(doc)
                for page_idx in range(total_pages):
                    try:
                        mat = fitz.Matrix(2, 2)
                        pix = doc[page_idx].get_pixmap(matrix=mat)
                        page_img = str(filepath) + f"_page{page_idx}.png"
                        pix.save(page_img)
                        prompt = f"请完整提取PDF第{page_idx+1}/{total_pages}页中的所有文字内容。"
                        raw = call_lm_studio_multimodal(page_img, prompt)
                        page_text = ensure_plain_text(raw)
                        page_text = clean_ocr_text(page_text)
                        page_texts.append(page_text)
                        os.remove(page_img)
                    except Exception as page_err:
                        send_sse("log", {"level": "warning", "message": f"[{original_name}] PDF第{page_idx+1}页处理失败: {page_err}"})
                        try: os.remove(page_img)
                        except OSError: pass
                doc.close()
                text = "\n\n".join(page_texts)
            except Exception as e:
                raise RuntimeError(f"PDF多模态识别失败: {e}")
        else:
            raise RuntimeError(f"不支持的文件格式: {ext_lower}")

        if not text.strip():
            raise RuntimeError("未能提取到任何文本内容，请检查文件是否有效")

        send_sse("log", {"level": "info", "message": f"[{original_name}] 文本提取完毕"})
        text = normalize_spaced_numbers(text)
        _cp_state = {"text": text}
        _cp_cid = queue_id or task_id
        _cp_original_name = original_name
        _cp_filepath = filepath
        _cp_mode = get_current_mode()
        _cp_group_id = group_id
        _cp_chunk_index = chunk_index
        _cp_total_chunks = total_chunks
        _cp_chunk_ext = chunk_ext
        _cp_queue_id = queue_id

        if queue_id:
            from app.task_store import update_status as _ts_update
            try:
                _ts_update(queue_id, TaskStatus.PROCESSING)
            except Exception:
                pass

        _recovered_cp, _recovered_data = None, None
        if queue_id:
            from app.task_store import get as _ts_get
            _ts_task = _ts_get(queue_id)
            if _ts_task and _ts_task.checkpoint:
                _recovered_cp = _ts_task.checkpoint
                _recovered_data = _ts_task.checkpoint_data
                send_sse("log", {"level": "info", "message": f"[{original_name}] 从检查点恢复 ({_recovered_cp})"})

        if _recovered_cp and _recovered_cp in ("text_extracted", "regex_done", "llm1_done", "llm2_done"):
            if _recovered_data and _recovered_data.get("text"):
                text = _recovered_data["text"]
                _cp_state["text"] = text
            all_replacements = _recovered_data.get("replacements", []) if _recovered_data else []
        else:
            all_replacements = []
        _save_checkpoint_data("text_extracted", _cp_state, queue_id or task_id)

        ds_cfg = get_config_snapshot()["desensitization"]
        depth = ds_cfg.get("depth", "standard")
        placeholder = ds_cfg["placeholder"]

        _skip_regex = _recovered_cp in ("regex_done", "llm1_done", "llm2_done")
        _skip_llm1 = _recovered_cp in ("llm1_done", "llm2_done")
        _skip_llm2 = _recovered_cp == "llm2_done"

        if _skip_regex:
            send_sse("log", {"level": "info", "message": f"[{original_name}] 跳过正则（从检查点恢复）"})
        else:
            send_sse("log", {"level": "info", "message": f"[{original_name}] 正则匹配（第1层）..."})
            regex_matches = match_regex_sensitive(text)
            for m in regex_matches:
                all_replacements.append({"sensitive": m["item"], "source": "正则", "category": m.get("category", "")})
            send_sse("log", {"level": "success", "message": f"[{original_name}] 正则匹配 {len(regex_matches)} 项"})
            _cp_state["replacements"] = all_replacements
        _save_checkpoint_data("regex_done", _cp_state, queue_id or task_id)

        known_entities = {m["sensitive"] for m in all_replacements
                          if m.get("category", "").startswith("标签_")
                          and len(m["sensitive"]) >= 4}
        if known_entities:
            send_sse("log", {"level": "success", "message": f"[{original_name}] 已知实体 {len(known_entities)} 项（将全文扩散）"})

        STRUCTURE_WORDS = {
            "甲方", "乙方", "出卖人", "买受人", "委托人", "受托人",
            "本合同", "双方", "卖方", "买方", "出售方", "购买方"
        }

        if depth in ("standard", "deep"):
            if total_chunks > 1 and depth == "deep":
                send_sse("log", {"level": "warning", "message": f"[{original_name}] 大文件不支持深度脱敏，已自动降为standard"})
                depth = "standard"

            if not _skip_llm1:
                flagged_text = flag_ambiguous(text)
                send_sse("log", {"level": "info", "message": f"[{original_name}] LLM大模型识别（第2层）..."})
                prompt_first = make_prompt(0)
                first_raw = _extract_between_markers(call_lm_studio(flagged_text, prompt_first))
                first_items = parse_sensitive_items(first_raw)
                regex_set = {r["sensitive"] for r in all_replacements}
                llm_added = []
                for item in first_items:
                    if item and item != placeholder and item not in regex_set:
                        all_replacements.append({"sensitive": item, "source": "大模型1", "category": ""})
                        llm_added.append(item)
                send_sse("log", {"level": "success", "message": f"[{original_name}] LLM第1轮新增 {len(llm_added)} 项"})
                _cp_state["replacements"] = all_replacements
            else:
                send_sse("log", {"level": "info", "message": f"[{original_name}] 跳过LLM第1轮（从检查点恢复）"})
            _save_checkpoint_data("llm1_done", _cp_state, queue_id or task_id)

            if depth == "deep":
                if not _skip_llm2:
                    desensitized = text
                    for r in all_replacements:
                        s = r["sensitive"] if isinstance(r, dict) else r
                        desensitized = desensitized.replace(s, placeholder)
                    flagged_desensitized = flag_ambiguous(desensitized)
                    send_sse("log", {"level": "info", "message": f"[{original_name}] LLM补漏检查（第3层）..."})
                    prompt_second = make_prompt(1)
                    second_raw = _extract_between_markers(call_lm_studio(flagged_desensitized, prompt_second))
                    second_items = parse_sensitive_items(second_raw)
                    all_so_far = {r["sensitive"] if isinstance(r, dict) else r for r in all_replacements}
                    deep_added = []
                    for item in second_items:
                        if item and item != placeholder and item not in all_so_far:
                            all_replacements.append({"sensitive": item, "source": "大模型2", "category": ""})
                            deep_added.append(item)
                    if deep_added:
                        send_sse("log", {"level": "success", "message": f"[{original_name}] LLM第2轮补充 {len(deep_added)} 项"})
                    _cp_state["replacements"] = all_replacements
                    _save_checkpoint_data("llm2_done", _cp_state, queue_id or task_id)
                else:
                    send_sse("log", {"level": "info", "message": f"[{original_name}] 跳过LLM第2轮（从检查点恢复）"})

        deduped = []
        seen = set()
        for r in all_replacements:
            s = r["sensitive"] if isinstance(r, dict) else r
            if s and s != placeholder and s not in seen and s not in STRUCTURE_WORDS:
                seen.add(s)
                deduped.append(r if isinstance(r, dict) else {"sensitive": s, "source": "LLM", "category": ""})

        EXPANDABLE_CATEGORIES = {"金额", "金额_大额", "金额_小数万", "数量", "数量_中文"}
        for r in deduped:
            s = r["sensitive"]
            if not s or not re.search(r'\d', s):
                continue
            if r.get("category", "") not in EXPANDABLE_CATEGORIES:
                continue
            pat = re.escape(s)
            for m in re.finditer(pat, text):
                start, end = m.start(), m.end()
                while start > 0 and text[start - 1].isdigit():
                    start -= 1
                while end < len(text) and text[end].isdigit():
                    end += 1
                if end - start > len(s) and start == m.start():
                    r["sensitive"] = text[start:end]
                    break

        output_filename = f"{Path(original_name).stem}（已脱敏待审查）.txt"
        output_path = OUTPUT_DIR / output_filename
        final_result = text
        for r in deduped:
            s = r["sensitive"]
            if s and s != placeholder:
                final_result = final_result.replace(s, placeholder)
        final_result = strip_ambiguity_markers(final_result)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_result)

        summary = {"regex": 0, "大模型1": 0, "大模型2": 0}
        for r in deduped:
            src = r.get("source", "大模型")
            summary[src] = summary.get(src, 0) + 1
        send_sse("log", {"level": "success", "message": f"[{original_name}] 脱敏完成！共 {len(deduped)} 项（正则{summary.get('regex',0)} + 大模型{summary.get('大模型1',0)+summary.get('大模型2',0)}）"})

        replace_list = []
        for r in deduped:
            replace_list.append({
                "sensitive": r["sensitive"],
                "replaced_with": placeholder,
                "source": r.get("source", ""),
                "category": r.get("category", "")
            })

        if group_id:
            _duration = int(round(time.time() - _start_time))
            chunk_data = {
                "text": final_result,
                "original_text": text,
                "replacements": replace_list,
                "original_length": len(text),
                "duration": _duration,
            }
            from app.task_store import update_result as ts_update_result
            ts_update_result(queue_id, chunk_data)

        logger.info(f"Completed: {original_name} -> {output_filename} ({len(deduped)} items)")
        _duration = int(round(time.time() - _start_time))
        _regex_c = summary.get('regex', 0)
        _llm_c = summary.get('大模型1', 0) + summary.get('大模型2', 0)
        _large = 1 if total_chunks > 1 else 0
        insert_stats(task_id, original_name, "desensitize", _duration, _regex_c, _llm_c,
                     len(deduped), len(text), len(final_result), _large, total_chunks, "completed")

        if queue_id:
            try:
                from app.task_store import update_status as _ts
                _ts(queue_id, TaskStatus.COMPLETED)
            except Exception:
                pass

        send_sse("result", {
            "id": task_id,
            "file": original_name,
            "queue_id": queue_id,
            "task_id": queue_id,
            "chunk_index": chunk_index,
            "status": "completed",
            "duration": int(round(time.time() - _start_time)),
            "mode": "desensitize",
            "parent_task_id": group_id,
            "original_preview": text[:preview_limit] + ("..." if len(text) > preview_limit else ""),
            "desensitized_preview": final_result[:preview_limit] + ("..." if len(final_result) > preview_limit else ""),
            "output_file": output_filename,
            "original_length": len(text),
            "desensitized_length": len(final_result),
            "replacements": replace_list
        })

    except requests.exceptions.ConnectionError as e:
        err_msg = f"[{original_name}] 连接 LM Studio 失败，请检查 LM Studio 是否已启动并加载模型"
        send_sse("log", {"level": "error", "message": err_msg})
        send_sse("result", {"id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "error", "message": err_msg})
        logger.error(f"{err_msg} 详情: {e}")
        insert_stats(task_id, original_name, "desensitize", int(round(time.time() - _start_time)), 0, 0,
                     0, 0, 0, 0, 1, "error")
    except requests.exceptions.Timeout as e:
        err_msg = f"[{original_name}] LM Studio 请求超时，模型正在推理或已卡死"
        send_sse("log", {"level": "error", "message": err_msg})
        send_sse("result", {"id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "error", "message": err_msg})
        logger.error(f"{err_msg} 详情: {e}")
        insert_stats(task_id, original_name, "desensitize", int(round(time.time() - _start_time)), 0, 0,
                     0, 0, 0, 0, 1, "error")
    except Exception as e:
        err_msg = f"[{original_name}] 处理失败: {str(e)}"
        if _is_paused() or _is_aborted():
            if _is_paused():
                set_interrupted(queue_id)
                if queue_id:
                    try:
                        from app.task_store import update_status as _us3
                        _us3(queue_id, TaskStatus.WAITING)
                    except Exception:
                        pass
                send_sse("log", {"level": "warning", "message": f"[{original_name}] 已暂停，保留在队列中"})
                send_sse("result", {"id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "paused", "message": "已暂停"})
            else:
                if queue_id:
                    try:
                        from app.task_store import update_status as _us4
                        _us4(queue_id, TaskStatus.CANCELLED)
                    except Exception:
                        pass
                send_sse("log", {"level": "warning", "message": f"[{original_name}] 已取消"})
                send_sse("result", {"id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "cancelled", "message": "已取消"})
        else:
            send_sse("log", {"level": "error", "message": err_msg})
            send_sse("result", {"id": task_id, "file": original_name, "queue_id": queue_id, "task_id": queue_id, "status": "error", "message": err_msg})
            logger.exception(f"Error processing {original_name}")
            insert_stats(task_id, original_name, "desensitize", int(round(time.time() - _start_time)), 0, 0,
                         0, 0, 0, 0, 1, "error")
    finally:
        processing_event.clear()
        send_sse("status", {"queue_size": task_queue.qsize(), "processing": False, "paused": pause_event.is_set()})

def process_file(filepath, original_name, queue_id=None, group_id=None, chunk_index=0, total_chunks=1, chunk_ext=None):
    mode = get_current_mode()
    abort_event.clear()
    if mode == "extract":
        process_file_extraction(filepath, original_name, queue_id, group_id)
    else:
        process_file_desensitization(filepath, original_name, queue_id, group_id, chunk_index, total_chunks, chunk_ext)

def _run_invoice_validation(template, parsed):
    if not template:
        return None
    tpl_name = (template.get("name") or "")
    if "发票" not in tpl_name:
        return None
    from app.invoice_validator import validate_invoice_items
    cfg = get_config_snapshot()
    tolerance = cfg.get("extraction", {}).get("invoice_tolerance", 0.02)
    rules = cfg.get("extraction", {}).get("invoice_rules", None)
    return validate_invoice_items(parsed.get("items", []), parsed.get("header", {}), tolerance, rules)

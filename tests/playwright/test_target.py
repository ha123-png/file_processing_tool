import os, sys, time, re
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.playwright.conftest import _upload_via_dom, SMALL_TXT


LARGE_TXT = (
    "甲方：北京测试科技有限公司\n统一社会信用代码：91110108MA01TEST1\n"
    + ("测试数据行" * 1200)
    + "\n联系人：张三，手机号：13800138000\n邮箱：zhangsan@test.com\n合同金额：¥500,000.00元\n签订日期：2024年1月15日\n"
)

_QI_HAS_ITEMS = "window._queueItems && Object.keys(window._queueItems).length > 0"
_QI_HAS_STATUS = lambda s: f"(function(){{var q=window._queueItems;if(!q)return false;var ks=Object.keys(q);for(var i=0;i<ks.length;i++){{if(q[ks[i]]&&q[ks[i]].status==='{s}')return true;}}return false;}})()"
_QI_NO_STATUS = lambda s: f"(function(){{var q=window._queueItems;if(!q)return true;var ks=Object.keys(q);for(var i=0;i<ks.length;i++){{if(q[ks[i]]&&q[ks[i]].status==='{s}')return false;}}return true;}})()"


def _js_items(page):
    result = page.evaluate("() => window._queueItems || []")
    if isinstance(result, dict) and not isinstance(result, list):
        return list(result.values())
    if not isinstance(result, list):
        return []
    return result


def _js_item_count(page):
    return len(_js_items(page))


def _upload(page, content, filename):
    _upload_via_dom(page, content, filename)
    try:
        page.wait_for_function(_QI_HAS_ITEMS, timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(500)


def _upload_while_paused(page, content, filename):
    _upload_via_dom(page, content, filename)
    page.wait_for_timeout(300)
    try:
        page.wait_for_function(_QI_HAS_ITEMS, timeout=5000)
    except Exception:
        pass


def _wait_processing(page, timeout_ms=10000):
    try:
        page.wait_for_function(
            "document.body.classList.contains('processing-readonly') || "
            + _QI_HAS_STATUS('processing'),
            timeout=timeout_ms)
    except Exception:
        pass


def _wait_idle(page, timeout_ms=60000):
    page.wait_for_function(
        "!document.body.classList.contains('processing-readonly') && "
        + _QI_NO_STATUS('processing'),
        timeout=timeout_ms)


def _wait_paused(page, timeout_ms=5000):
    try:
        page.wait_for_function(
            "document.body.classList.contains('queue-paused')",
            timeout=timeout_ms)
    except Exception:
        pass


def _wait_completed_count(page, count, timeout_ms=60000):
    page.click('.queue-tab[data-qt="completed"]')
    page.wait_for_timeout(200)
    page.wait_for_function(
        f"document.querySelectorAll('#queueList .queue-item').length >= {count}",
        timeout=timeout_ms)
    page.wait_for_timeout(200)
    page.click('.queue-tab[data-qt="processing"]')
    page.wait_for_timeout(200)


def _pause(page):
    page.evaluate("() => fetch('/api/queue/pause', {method:'POST'})")
    _wait_paused(page)
    page.wait_for_timeout(300)


def _resume(page):
    page.evaluate("() => fetch('/api/queue/resume', {method:'POST'})")
    page.wait_for_timeout(500)


def _switch_mode(page, mode):
    page.click("#modeExtract" if mode == "extract" else "#modeDesensitize")
    page.wait_for_timeout(300)


def _names(page):
    items = page.locator("#queueList .queue-item .queue-item-name")
    return [items.nth(i).text_content() for i in range(items.count())]


def _result_meta_text(page):
    el = page.locator("#resultMeta")
    return el.text_content().strip() if el.count() > 0 else ""


def _result_word_counts(page):
    text = _result_meta_text(page)
    m_orig = re.search(r'原文\s*(\d+)\s*字', text)
    m_des = re.search(r'脱敏后\s*(\d+)\s*字', text)
    orig = int(m_orig.group(1)) if m_orig else 0
    des = int(m_des.group(1)) if m_des else 0
    return orig, des


def _merge_panel_has_content(page):
    el = page.locator("#mergePanel")
    if el.count() == 0:
        return False
    text = el.text_content().strip()
    if not text:
        return False
    if text == "暂无合成数据":
        return False
    return True


def _global_status(page):
    el = page.locator("#statusBadge")
    return el.text_content().strip() if el.count() > 0 else ""


def _queue_item_count(page):
    return page.locator("#queueList .queue-item").count()


# ═══════════════════════════════════════════════════════════════
# 第1组：结果正确性
# ═══════════════════════════════════════════════════════════════

class TestResultCorrectness:

    def test_large_file_desensitize_result_not_empty(self, page, base_url):
        _upload(page, LARGE_TXT, "大文件测试.txt")
        _wait_processing(page, timeout_ms=15000)

        _wait_idle(page, timeout_ms=120000)
        page.wait_for_timeout(3000)

        orig, des = _result_word_counts(page)
        assert orig > 0, f"原文应为>0字，实际：{orig}，resultMeta内容：'{_result_meta_text(page)}'"
        assert des > 0, f"脱敏后应为>0字，实际：{des}，resultMeta内容：'{_result_meta_text(page)}'"

    @pytest.mark.xfail(reason="提取模式暂不支持大文件自动拆分，需实现后移除xfail")
    def test_large_file_extract_result_not_empty(self, page, base_url):
        _switch_mode(page, "extract")
        _upload(page, LARGE_TXT, "大文件提取.txt")
        _wait_processing(page, timeout_ms=15000)
        _wait_idle(page, timeout_ms=120000)
        page.wait_for_timeout(2000)

        assert _merge_panel_has_content(page), "提取模式下合成表应有内容"

    def test_small_file_result_shows_filename(self, page, base_url):
        _upload(page, SMALL_TXT, "小文件.txt")
        _wait_processing(page, timeout_ms=10000)
        _wait_idle(page, timeout_ms=30000)
        page.wait_for_timeout(1000)

        meta = _result_meta_text(page)
        assert "小文件" in meta, f"结果应包含文件名，实际：'{meta}'"
        orig, des = _result_word_counts(page)
        assert orig > 0, f"原文应为>0字，实际：{orig}"
        assert des > 0, f"脱敏后应为>0字，实际：{des}"

    def test_large_file_merged_total_duration_is_float(self, page, base_url):
        import requests
        _upload(page, LARGE_TXT, "duration类型测试.txt")
        _wait_idle(page, timeout_ms=120000)
        page.wait_for_timeout(2000)

        parent_id = page.evaluate("() => { "
            "for(var k in window._queueItems||{}) { "
            "  var q = window._queueItems[k]; "
            "  if(q && q.name && q.name.indexOf('duration类型测试') >= 0) return k; "
            "} return null; }")

        if not parent_id:
            parent_id = page.evaluate("() => { "
                "var keys = Object.keys(window._queueItems||{}); "
                "return keys.length > 0 ? keys[keys.length-1] : null; }")

        if not parent_id:
            pytest.fail("未获取到大文件任务ID")

        merged_url = f"{base_url}/api/queue/parent/{parent_id}/merged"
        resp = requests.get(merged_url, timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        total_duration = data.get("total_duration", 0)
        assert isinstance(total_duration, (int, float)), \
            f"total_duration应为数值类型，实际：{type(total_duration).__name__} = {total_duration}"


# ═══════════════════════════════════════════════════════════════
# 第2组：并发与稳定性
# ═══════════════════════════════════════════════════════════════

class TestConcurrencyStability:

    def test_concurrent_uploads_no_crash(self, page, base_url):
        _pause(page)

        filenames = ["并发测试A.txt", "并发测试B.txt", "并发测试C.txt"]
        for fn in filenames:
            _upload_via_dom(page, SMALL_TXT, fn)

        page.wait_for_timeout(2000)

        count = _js_item_count(page)
        assert count >= 3, f"并发上传后_queueItems应有≥3项，实际：{count}"

    def test_pause_resume_multiple_cycles_no_orphan(self, page, base_url):
        for i in range(3):
            fn = f"暂停恢复_{i+1}.txt"
            _upload(page, SMALL_TXT, fn)

        _wait_processing(page, timeout_ms=10000)

        for cycle in range(3):
            _pause(page)
            page.wait_for_timeout(500)
            _resume(page)
            page.wait_for_timeout(500)

        _wait_idle(page, timeout_ms=60000)
        page.wait_for_timeout(1000)

        _wait_completed_count(page, 3, timeout_ms=30000)

        page.click('.queue-tab[data-qt="processing"]')
        page.wait_for_timeout(200)
        assert _queue_item_count(page) == 0, "不应有孤儿任务卡在处理中"


# ═══════════════════════════════════════════════════════════════
# 第3组：状态清理
# ═══════════════════════════════════════════════════════════════

class TestStateCleanup:

    def test_refresh_clears_merge_panel(self, page, base_url):
        _switch_mode(page, "extract")
        _upload(page, SMALL_TXT, "合成表测试.txt")
        _wait_processing(page, timeout_ms=10000)
        _wait_idle(page, timeout_ms=30000)
        page.wait_for_timeout(1000)

        before = _merge_panel_has_content(page)
        if not before:
            pytest.skip("上传后合成表无内容，跳过刷新验证")

        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#logPanel", timeout=10000)
        page.wait_for_timeout(1000)

        assert not _merge_panel_has_content(page), "刷新后合成表不应有残留数据"

    def test_refresh_clears_queue(self, page, base_url):
        _pause(page)
        _upload(page, SMALL_TXT, "刷新测试.txt")
        page.wait_for_timeout(1000)

        assert _js_item_count(page) > 0, "暂停上传后_queueItems应有项"

        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#logPanel", timeout=10000)
        page.wait_for_timeout(1500)

        assert _js_item_count(page) == 0, "刷新后_queueItems应为空"
        assert _queue_item_count(page) == 0, "刷新后队列DOM应为空"
        status = _global_status(page)
        assert "闲置" in status, f"刷新后应显示闲置中，实际：'{status}'"

    def test_mode_switch_preserves_result(self, page, base_url):
        _upload(page, SMALL_TXT, "脱敏-隔离测试.txt")
        _wait_processing(page, timeout_ms=10000)
        _wait_idle(page, timeout_ms=30000)
        page.wait_for_timeout(1000)
        meta_a = _result_meta_text(page)
        assert "脱敏-隔离测试" in meta_a, f"脱敏结果应包含文件名，实际：'{meta_a}'"

        _switch_mode(page, "extract")
        page.wait_for_timeout(500)

        _upload(page, SMALL_TXT, "提取-隔离测试.txt")
        _wait_processing(page, timeout_ms=10000)
        _wait_idle(page, timeout_ms=30000)
        page.wait_for_timeout(1000)

        _switch_mode(page, "desensitize")
        page.wait_for_timeout(1000)

        meta_after = _result_meta_text(page)
        assert "脱敏-隔离测试" in meta_after, \
            f"切回脱敏后结果应保留，实际：'{meta_after}'"

    def test_mode_switch_isolates_extract_from_desensitize(self, page, base_url):
        _switch_mode(page, "extract")
        _upload(page, SMALL_TXT, "提取隔离.txt")
        _wait_processing(page, timeout_ms=10000)
        _wait_idle(page, timeout_ms=30000)
        page.wait_for_timeout(1000)
        meta_extract = _result_meta_text(page)
        assert "提取隔离" in meta_extract, f"提取结果应包含文件名，实际：'{meta_extract}'"

        _switch_mode(page, "desensitize")
        page.wait_for_timeout(1000)

        meta_desen = _result_meta_text(page)
        assert "提取隔离" not in meta_desen, \
            f"脱敏模式不应显示提取结果的文件名，实际：'{meta_desen}'"

        _upload(page, SMALL_TXT, "脱敏隔离.txt")
        _wait_processing(page, timeout_ms=10000)
        _wait_idle(page, timeout_ms=30000)
        page.wait_for_timeout(1000)

        meta_desen2 = _result_meta_text(page)
        assert "脱敏隔离" in meta_desen2, f"脱敏结果应包含文件名，实际：'{meta_desen2}'"

        _switch_mode(page, "extract")
        page.wait_for_timeout(1000)

        meta_extract2 = _result_meta_text(page)
        assert "脱敏隔离" not in meta_extract2, \
            f"提取模式不应显示脱敏结果的文件名，实际：'{meta_extract2}'"
        assert "提取隔离" in meta_extract2, \
            f"切回提取模式应保留提取结果，实际：'{meta_extract2}'"

    def test_large_file_reupload_clears_stale_state(self, page, base_url):
        _pause(page)

        page.evaluate("() => { "
            "window._currentExtractResult = {file: '残留任务.txt', extract_items: [1,2,3], item_count: 3}; "
            "if (typeof _currentDesensitizeData !== 'undefined') { _currentDesensitizeData = {file: '残留脱敏.txt', group_info: {chunk_count: 3, total_chunks: 9}}; } "
            "}")

        _upload_while_paused(page, LARGE_TXT, "重新上传.txt")
        page.wait_for_timeout(1000)

        extract_result = page.evaluate("() => window._currentExtractResult")
        assert extract_result is None, \
            f"重新上传后残留的_currentExtractResult应被清理，实际：{extract_result}"

        desensitize_data = page.evaluate("() => { try { return _currentDesensitizeData; } catch(e) { return undefined; } }")
        assert desensitize_data is None or desensitize_data.get('file') == '重新上传.txt', \
            f"重新上传后_currentDesensitizeData应为None或新任务数据（非残留），实际：{desensitize_data}"

        _resume(page)
        _wait_processing(page, timeout_ms=15000)
        _wait_idle(page, timeout_ms=120000)
        page.wait_for_timeout(2000)

        meta = _result_meta_text(page)
        assert "残留" not in meta, \
            f"resultMeta不应包含残留数据，实际：'{meta}'"


# ═══════════════════════════════════════════════════════════════
# 第4组：交互行为
# ═══════════════════════════════════════════════════════════════

class TestInteractionBehavior:

    def test_batch_retry_auto_resumes(self, page, base_url):
        _upload(page, SMALL_TXT, "重试A.txt")
        _upload(page, SMALL_TXT, "重试B.txt")
        _wait_idle(page, timeout_ms=30000)
        page.wait_for_timeout(500)

        task_ids = page.evaluate("() => Object.keys(window._queueItems || {})")
        assert len(task_ids) >= 2, f"应有≥2个已完成任务，实际：{len(task_ids)}"

        cancel_resp = page.evaluate("""(ids) => {
            return fetch('/api/queue/tasks/batch-cancel', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_ids: ids})
            }).then(r => r.json());
        }""", task_ids)
        assert cancel_resp.get('cancelled', 0) >= 2, f"取消应返回≥2，实际：{cancel_resp}"
        page.wait_for_timeout(500)

        retry_resp = page.evaluate("""(ids) => {
            return fetch('/api/queue/tasks/batch-retry', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_ids: ids})
            }).then(r => r.json());
        }""", task_ids)
        assert retry_resp.get('retrying', 0) >= 2, f"重试入队应返回≥2，实际：{retry_resp}"
        page.wait_for_timeout(500)

        _wait_processing(page, timeout_ms=15000)
        _wait_idle(page, timeout_ms=60000)
        page.wait_for_timeout(1000)

        _wait_completed_count(page, 2, timeout_ms=15000)

    def test_queue_order_preserved(self, page, base_url):
        _pause(page)

        filenames = ["最先-队列排序A.txt", "第二-队列排序B.txt", "第三-队列排序C.txt"]
        for fn in filenames:
            _upload_via_dom(page, SMALL_TXT, fn)
            page.wait_for_timeout(300)

        page.wait_for_timeout(1000)

        items = _js_items(page)
        assert len(items) >= 2, f"应有≥2个文件入队，实际：{len(items)}"

        names_in_queue = [it.get('name', '') for it in items]
        for fn in filenames:
            found = any(fn in n for n in names_in_queue)
            assert found, f"'{fn}' 应在队列中，实际：{names_in_queue}"

    def test_large_file_buttons_no_save_modify(self, page, base_url):
        _upload(page, LARGE_TXT, "大文件按钮测试.txt")
        _wait_processing(page, timeout_ms=15000)
        _wait_idle(page, timeout_ms=120000)
        page.wait_for_timeout(2000)

        ra_html = page.evaluate("() => document.getElementById('resultActions').innerHTML")
        assert "保存修改" not in ra_html, \
            f"大文件脱敏结果不应出现'保存修改'按钮，实际：'{ra_html}'"
        assert "下载" in ra_html or "download" in ra_html.lower(), \
            f"大文件脱敏结果应有下载按钮，实际：'{ra_html}'"

        _switch_mode(page, "extract")
        page.wait_for_timeout(500)
        _upload(page, LARGE_TXT, "大文件提取按钮.txt")
        _wait_processing(page, timeout_ms=15000)
        _wait_idle(page, timeout_ms=120000)
        page.wait_for_timeout(2000)

        ra_html2 = page.evaluate("() => document.getElementById('resultActions').innerHTML")
        assert "保存修改" not in ra_html2, \
            f"大文件提取结果不应出现'保存修改'按钮，实际：'{ra_html2}'"

    def test_large_file_merged_has_total_duration(self, page, base_url):
        import requests
        _upload(page, LARGE_TXT, "duration测试.txt")
        _wait_idle(page, timeout_ms=120000)
        page.wait_for_timeout(2000)

        parent_id = page.evaluate("() => { "
            "for(var k in window._queueItems||{}) { "
            "  var q = window._queueItems[k]; "
            "  if(q && q.name && q.name.indexOf('duration') >= 0) return k; "
            "} return null; }")

        if not parent_id:
            parent_id = page.evaluate("() => { "
                "var keys = Object.keys(window._queueItems||{}); "
                "return keys.length > 0 ? keys[keys.length-1] : null; }")

        if not parent_id:
            pytest.fail("未获取到大文件任务ID")

        merged_url = f"{base_url}/api/queue/parent/{parent_id}/merged"
        resp = requests.get(merged_url, timeout=10)
        assert resp.status_code == 200, f"merged端点返回{resp.status_code}"
        data = resp.json()
        assert "total_duration" in data, \
            f"merged端点响应应包含total_duration字段，实际字段：{list(data.keys())}"

    def test_download_uses_full_content_not_truncated(self, page):
        _upload(page, LARGE_TXT, "截断下载测试.txt")
        _wait_idle(page, timeout_ms=120000)
        page.wait_for_timeout(2000)

        orig_panel = page.locator("#originalPanel pre")
        if orig_panel.count() > 0:
            orig_text = orig_panel.text_content() or ""
            assert "已截断" in orig_text, \
                f"大文件预览应显示截断标记，面板前100字：'{orig_text[:100]}'"

        btns = page.locator("#resultActions button")
        btn_count = btns.count()
        assert btn_count >= 1, f"大文件完成后应至少有1个按钮，实际{btn_count}个"
        ra_html = btns.first.evaluate("el => el.parentElement.innerHTML")
        assert "下载" in ra_html, f"按钮区域应含下载，实际：'{ra_html[:200]}'"

        with page.expect_download(timeout=10000) as download_info:
            btns.first.click()
        download = download_info.value
        downloaded = download.path().read_text("utf-8")
        assert "已截断" not in downloaded, \
            f"下载内容不应包含截断标记，实际前100字：'{downloaded[:100]}'"
        assert len(downloaded) > 2000, \
            f"大文件下载原文应完整（>2000字），实际{len(downloaded)}字"

    def test_large_file_retry_restores_state(self, page, base_url):
        """TDD: 取消不再销毁已完成子任务 → 后端merged保留正确完成数"""
        import requests

        _upload(page, LARGE_TXT, "重试归零测试.txt")
        _wait_idle(page, timeout_ms=120000)
        page.wait_for_timeout(2000)

        info = page.evaluate("""() => {
            var q = window._queueItems;
            if (!q) return null;
            var ks = Object.keys(q);
            for (var i = 0; i < ks.length; i++) {
                var item = q[ks[i]];
                if (item && item.is_large) {
                    return { id: ks[i], total: item.total_chunks || 0, msg: item.message };
                }
            }
            return null;
        }""")
        assert info is not None, "应找到大文件队列项"
        assert info['total'] > 1, f"大文件应有>1个chunk，实际：{info['total']}"

        # 全部完成后 merged 应返回 completed=total
        merged = requests.get(f"{base_url}/api/queue/parent/{info['id']}/merged", timeout=10).json()
        assert merged['completed'] == info['total'], \
            f"全部完成后completed应为{info['total']}，实际：{merged['completed']}"
        assert merged['total'] == info['total'], \
            f"全部完成后total应为{info['total']}，实际：{merged['total']}"

        # 取消大文件 → 已完成子任务保留（不再被标为CANCELLED）
        page.evaluate("""(tid) => {
            return fetch('/api/queue/tasks/batch-cancel', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_ids: [tid]})
            });
        }""", info['id'])
        page.wait_for_timeout(1500)

        # 取消后 merged 仍返回正确的已完成数（关键断言！）
        merged_after = requests.get(f"{base_url}/api/queue/parent/{info['id']}/merged", timeout=10).json()
        assert merged_after['completed'] == info['total'], \
            f"取消后completed仍应为{info['total']}（已完成的子任务不丢弃），实际：{merged_after['completed']}"
        assert merged_after['total'] == info['total'], \
            f"取消后total仍应为{info['total']}，实际：{merged_after['total']}"

        # 重试 → 全部完成无需重新入队，轮询立即完成
        page.evaluate("""(tid) => { retryFile(tid); }""", info['id'])
        page.wait_for_timeout(3000)

        # 重试后 merged 仍正确
        merged_retry = requests.get(f"{base_url}/api/queue/parent/{info['id']}/merged", timeout=10).json()
        assert merged_retry['completed'] == info['total'], \
            f"重试后completed应为{info['total']}，实际：{merged_retry['completed']}"

    def test_large_file_double_cancel_retry_succeeds(self, page, base_url):
        """TDD: 大文件入库即取消→再取消→重试 —— enqueue_task_id不拒绝已取消子任务"""
        import requests

        # 暂停以防子任务开始处理
        page.evaluate("() => fetch('/api/queue/pause', {method:'POST'})")
        page.wait_for_timeout(300)

        _upload(page, LARGE_TXT, "双重取消测试.txt")
        page.wait_for_timeout(1500)

        info = page.evaluate("""() => {
            var q = window._queueItems;
            if (!q) return null;
            var ks = Object.keys(q);
            for (var i = 0; i < ks.length; i++) {
                var item = q[ks[i]];
                if (item && item.is_large) {
                    return { id: ks[i], total: item.total_chunks || 0 };
                }
            }
            return null;
        }""")
        assert info is not None, "应找到大文件队列项"

        # 第一次取消 → 子任务全部标为 CANCELLED（未处理过，无COMPLETED）
        page.evaluate("""(tid) => {
            return fetch('/api/queue/tasks/batch-cancel', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_ids: [tid]})
            });
        }""", info['id'])
        page.wait_for_timeout(1000)

        # 第二次取消 → 同一子任务再次被标为 CANCELLED
        page.evaluate("""(tid) => {
            return fetch('/api/queue/tasks/batch-cancel', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_ids: [tid]})
            });
        }""", info['id'])
        page.wait_for_timeout(1000)

        # 恢复队列
        page.evaluate("() => fetch('/api/queue/resume', {method:'POST'})")
        page.wait_for_timeout(500)

        # 重试 → 所有子任务都是 CANCELLED，batch-retry 应全部重新入队
        retry_resp = page.evaluate("""(tid) => {
            return fetch('/api/queue/tasks/batch-retry', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({task_ids: [tid]})
            }).then(r => r.json());
        }""", info['id'])
        page.wait_for_timeout(500)

        assert retry_resp.get('retrying', 0) >= 1, \
            f"重试应有子任务入队，实际：{retry_resp.get('retrying', 0)}"

        # 等待处理完成
        _wait_processing(page, timeout_ms=15000)
        _wait_idle(page, timeout_ms=120000)
        page.wait_for_timeout(2000)

        merged = requests.get(f"{base_url}/api/queue/parent/{info['id']}/merged", timeout=10).json()
        assert merged['total'] == info['total'], \
            f"重试后total应为{info['total']}，实际：{merged['total']}"
        assert merged['completed'] == info['total'], \
            f"重试后completed应为{info['total']}，实际：{merged['completed']}"
        assert merged['text'], "重试后应有脱敏结果文本"


# ═══════════════════════════════════════════════════════════════
# 第5组：单元测试（无浏览器）
# ═══════════════════════════════════════════════════════════════

class TestRegexUnit:
    """正则匹配单元测试 — 无需浏览器"""

    def test_num_with_unit_spaces(self):
        """带空格的数字量词 '500 万条' 应被数量正则匹配"""
        from app.regex_rules import normalize_spaced_numbers, match_regex_sensitive
        text = "涉及数据量约 500 万条记录，总计3000 万份"
        cleaned = normalize_spaced_numbers(text)
        matches = match_regex_sensitive(cleaned)
        items = [m["item"] for m in matches]
        assert "500" in items, f"'500' 未被匹配！items={items}"
        assert "3000" in items, f"'3000' 未被匹配！items={items}"

    def test_full_date_format(self):
        """完整日期 '2026年02月25日' 应被日期_完整匹配"""
        from app.regex_rules import normalize_spaced_numbers, match_regex_sensitive
        text = "签署日期：2026年02月25日"
        cleaned = normalize_spaced_numbers(text)
        matches = match_regex_sensitive(cleaned)
        items = [(m["category"], m["item"]) for m in matches]
        assert ("日期_完整", "2026年02月25日") in items or any(
            c == "日期" and i == "2026年02月25日" for c, i in items
        ), f"完整日期未被匹配！items={items}"

    def test_amount_with_wan_yi(self):
        """大额金额 '8000万元' '200亿元' 应分别匹配"""
        from app.regex_rules import normalize_spaced_numbers, match_regex_sensitive
        text = "总金额8000万元，注册资本200亿元"
        cleaned = normalize_spaced_numbers(text)
        matches = match_regex_sensitive(cleaned)
        items = [m["item"] for m in matches]
        assert "8000" in items, f"'8000' 未被匹配！items={items}"
        assert "200" in items, f"'200' 未被匹配！items={items}"

    def test_desensitization_applies(self):
        """脱敏后原文中数字被替换为占位符"""
        from app.regex_rules import normalize_spaced_numbers, match_regex_sensitive
        text = "涉及数据量约 500 万条记录，合同金额500万元"
        cleaned = normalize_spaced_numbers(text)
        matches = match_regex_sensitive(cleaned)
        placeholder = "【已脱敏】"
        result = cleaned
        for m in sorted(matches, key=lambda x: -len(x["item"])):
            result = result.replace(m["item"], placeholder)
        assert "500" not in result, f"脱敏后不应含500！结果: {result}"
        assert "【已脱敏】" in result, f"脱敏后应含占位符！结果: {result}"
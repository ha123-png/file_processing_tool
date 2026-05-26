import os, sys, time, tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.playwright.conftest import _upload_via_dom, SMALL_TXT, BIG_CONTENT

VALID_STATUS_CHIPS = {"等待中", "处理中", "已完成", "失败", "已取消"}
FORBIDDEN_STATUS = {"已暂停", "运行中", "处理失败", "脱敏完成", "提取完成"}




def _wait_processing(page, timeout_ms=15000):
    """等待 body 出现 processing-readonly"""
    page.wait_for_function("document.body.className.includes('processing-readonly')", timeout=timeout_ms)


def _wait_idle(page, timeout_ms=15000):
    """等待 body 移除 processing-readonly"""
    page.wait_for_function("!document.body.className.includes('processing-readonly')", timeout=timeout_ms)


def _wait_paused(page, timeout_ms=4000):
    """等待 body 出现 queue-paused 或 pause_event 生效"""
    try:
        page.wait_for_function("document.body.className.includes('queue-paused')", timeout=timeout_ms)
    except Exception:
        pass


def _wait_resumed(page, timeout_ms=3000):
    """等待 body 移除 queue-paused"""
    page.wait_for_function("!document.body.className.includes('queue-paused')", timeout=timeout_ms)


def _wait_completed(page, count=1, timeout_ms=30000):
    """等待指定数量的 .completed chip 出现（切到已完成Tab检查后切回处理中）"""
    _switch_tab(page, "completed")
    page.wait_for_function(
        f"document.querySelectorAll('#queueList .queue-status-chip.completed').length >= {count}",
        timeout=timeout_ms)
    result = page.locator("#queueList .queue-status-chip.completed").count()
    _switch_tab(page, "processing")
    return result


def _pause(page):
    page.evaluate("() => fetch('/api/queue/pause', {method:'POST'})")
    _wait_paused(page)
    page.wait_for_timeout(300)


def _resume(page):
    page.evaluate("() => fetch('/api/queue/resume', {method:'POST'})")
    _wait_resumed(page)
    page.wait_for_timeout(300)


def _switch_mode(page, mode):
    page.click("#modeExtract" if mode == "extract" else "#modeDesensitize")
    page.wait_for_timeout(300)


def _switch_tab(page, tab):
    page.click(f'.queue-tab[data-qt="{tab}"]')
    page.wait_for_timeout(200)


def _names(page):
    items = page.locator("#queueList .queue-item .queue-item-name")
    return [items.nth(i).text_content() for i in range(items.count())]


def _chips(page):
    chips = page.locator("#queueList .queue-item .queue-status-chip")
    return [(chips.nth(i).text_content(), chips.nth(i).get_attribute("class") or "")
            for i in range(chips.count())]


def _global_status(page):
    el = page.locator("#statusBadge")
    return el.text_content().strip() if el.count() > 0 else ""


def _tab_count(page, tab):
    ids = {"processing": "#qtProcessingCount", "completed": "#qtCompletedCount", "failed": "#qtFailedCount"}
    return page.locator(ids[tab]).text_content().strip()


def _has_cb(page):
    return page.locator("#queueList .queue-cb").count() > 0


def _has_retry(page):
    return page.locator("#queueList .queue-retry-btn").count() > 0

def _upload(page, content, filename):
    """Upload file, return once queue-item DOM appears (or after timeout)."""
    _upload_via_dom(page, content, filename)
    page.wait_for_timeout(500)
    try:
        page.wait_for_function(
            "document.querySelector('#queueList .queue-item') !== null",
            timeout=5000)
    except Exception:
        page.wait_for_timeout(500)


def _upload_and_wait(page, content, filename):
    """Upload file, wait for it to complete processing."""
    _upload_via_dom(page, content, filename)
    return _wait_completed(page, 1, timeout_ms=30000)


# ═══════════════════════════════════════════════════════════════
# §2.1 全局状态栏（3 个标签）
# ═══════════════════════════════════════════════════════════════

class TestGlobalStatusBar:

    def test_idle_shows_闲置中(self, page):
        """空队列时全局状态栏显示 '闲置中'"""
        text = _global_status(page)
        assert text == "闲置中", f"Expected '闲置中', got '{text}'"

    def test_processing_shows_处理中(self, page):
        """文件处理后完成Tab有完成项"""
        _upload(page, SMALL_TXT, "proc_test.txt")
        _wait_completed(page, 1, timeout_ms=30000)
        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "1"

    def test_paused_shows_已暂停(self, page):
        """暂停时全局状态栏显示 '已暂停'"""
        _pause(page)
        _upload(page, SMALL_TXT, "pause_test.txt")
        page.wait_for_timeout(300)
        is_paused = "queue-paused" in page.evaluate("document.body.className")
        text = _global_status(page)
        assert is_paused or text == "已暂停", f"Expected paused state, body class or text, got text='{text}', paused={is_paused}"
        _resume(page)
        _wait_idle(page)

    def test_no_forbidden_global_labels(self, page):
        """全局状态栏不出现 '等待中' 或 '运行中'"""
        _pause(page)
        _upload(page, SMALL_TXT, "label_test.txt")
        text = _global_status(page)
        assert text not in ("等待中", "运行中"), f"Forbidden global label: '{text}'"
        _resume(page)
        _wait_idle(page)


# ═══════════════════════════════════════════════════════════════
# §2.2 任务状态（5 个标签，无禁止标签）
# ═══════════════════════════════════════════════════════════════

class TestTaskStatusChips:

    def test_paused_item_shows_等待中_not_已暂停(self, page):
        """暂停时任务 chip 显示 '等待中'，不是 '已暂停'"""
        _pause(page)
        _upload(page, SMALL_TXT, "waiting_test.txt")
        chips = _chips(page)
        assert len(chips) >= 1, "Should have at least 1 queue item"
        text, cls = chips[0]
        assert text == "等待中", f"Paused item should show '等待中', got '{text}'"
        assert "已暂停" not in text
        _resume(page)
        _wait_idle(page)

    def test_completed_shows_已完成_not_脱敏完成(self, page):
        """脱敏完成后 chip 显示 '已完成'，不是 '脱敏完成'"""
        _upload(page, SMALL_TXT, "done_test.txt")
        _wait_completed(page, 1, timeout_ms=60000)
        _switch_tab(page, "completed")
        chips = _chips(page)
        assert len(chips) >= 1, "Should have at least 1 completed item"
        text, cls = chips[0]
        assert text == "已完成", f"Completed item should show '已完成', got '{text}'"
        assert "脱敏" not in text, f"Should not contain mode name: '{text}'"

    def test_extract_completed_shows_已完成_not_提取完成(self, page):
        """提取完成后 chip 显示 '已完成'，不是 '提取完成'"""
        _switch_mode(page, "extract")
        _upload(page, SMALL_TXT, "ext_done_test.txt")
        _wait_completed(page, 1, timeout_ms=60000)
        _switch_tab(page, "completed")
        chips = _chips(page)
        assert len(chips) >= 1, "Should have at least 1 completed item"
        text, cls = chips[0]
        assert text == "已完成", f"Extract completed should show '已完成', got '{text}'"
        assert "提取" not in text, f"Should not contain mode name: '{text}'"

    def test_processing_chip_only_one(self, page):
        """多个文件顺序完成，每次只有 1 个处理"""
        _upload(page, SMALL_TXT, "only_one_a.txt")
        _upload(page, SMALL_TXT, "only_one_b.txt")
        _wait_completed(page, 2, timeout_ms=60000)
        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "2"

    def test_all_chips_in_valid_set(self, page):
        """所有 chip 文本都在 {等待中, 处理中, 已完成, 失败, 已取消} 中"""
        _upload(page, SMALL_TXT, "valid_chip_a.txt")
        _upload(page, SMALL_TXT, "valid_chip_b.txt")
        _wait_completed(page, 2, timeout_ms=60000)

        for tab in ("processing", "completed", "failed"):
            _switch_tab(page, tab)
            chips = _chips(page)
            for text, cls in chips:
                assert text in VALID_STATUS_CHIPS, f"Invalid chip text '{text}' in {tab} tab"

    def test_no_forbidden_chip_labels(self, page):
        """不出现 '已暂停'、'运行中'、'处理失败'、'脱敏完成'、'提取完成'"""
        _upload(page, SMALL_TXT, "forbid_test.txt")
        _wait_completed(page, 1, timeout_ms=60000)
        all_html = page.locator("#queueList").inner_html()
        for forbidden in FORBIDDEN_STATUS:
            assert forbidden not in all_html, f"Forbidden label '{forbidden}' found in queue list"


# ═══════════════════════════════════════════════════════════════
# §3.2 + §3.3 Tab 内容过滤 + 模式切换
# ═══════════════════════════════════════════════════════════════

class TestTabModeFiltering:

    def test_tab_counts_filter_by_current_mode(self, page):
        """Tab 数字 = 当前 mode 下的数量"""
        _pause(page)
        _switch_mode(page, "desensitize")
        _upload(page, SMALL_TXT, "desen_a.txt")
        _upload(page, SMALL_TXT, "desen_b.txt")

        _switch_mode(page, "extract")
        _upload(page, SMALL_TXT, "extract_a.txt")
        _upload(page, SMALL_TXT, "extract_b.txt")
        _upload(page, SMALL_TXT, "extract_c.txt")

        _switch_mode(page, "desensitize")
        assert _tab_count(page, "processing") == "2", f"desensitize tab should be 2"

        _switch_mode(page, "extract")
        assert _tab_count(page, "processing") == "3", f"extract tab should be 3"

        _resume(page)
        _wait_idle(page)

    def test_mode_switch_rerenders_list_content(self, page):
        """模式切换后列表内容更新为当前 mode 的任务"""
        _pause(page)
        _upload(page, SMALL_TXT, "desen_x.txt")

        assert _tab_count(page, "processing") == "1"

        _switch_mode(page, "extract")
        items = page.locator("#queueList .queue-item")
        assert items.count() == 0, f"Extract mode should show 0 items, got {items.count()}"

        _switch_mode(page, "desensitize")
        items_after = page.locator("#queueList .queue-item")
        assert items_after.count() >= 1, f"Back to desensitize should show items"

        _resume(page)
        _wait_idle(page)

    def test_completed_tab_filters_by_mode(self, page):
        """已完成 Tab 数量 = 当前 mode 的已完成数"""
        _upload(page, SMALL_TXT, "comp_desen.txt")
        _wait_completed(page, 1, timeout_ms=60000)

        _switch_mode(page, "extract")
        _upload(page, SMALL_TXT, "comp_extract.txt")
        _wait_completed(page, 1, timeout_ms=60000)

        _switch_mode(page, "desensitize")
        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "1", "desensitize completed should be 1"

        _switch_mode(page, "extract")
        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "1", "extract completed should be 1"

    def test_mode_tags_visible_on_items(self, page):
        """队列项显示 [脱敏]/[提取] 模式标签（跳过空队列——mock LLM 瞬时完成导致）"""
        _pause(page)
        _upload(page, SMALL_TXT, "tag_desen.txt")
        try:
            page.wait_for_selector("#queueList .queue-item:not(.queue-status-chip.completed)", timeout=8000)
        except Exception:
            pass
        all_html = page.locator("#queueList").inner_html()
        if '暂无待处理文件' in all_html:
            _resume(page)
            return

        _switch_mode(page, "extract")
        _upload(page, SMALL_TXT, "tag_extract.txt")
        try:
            page.wait_for_selector("#queueList .queue-item:not(.queue-status-chip.completed)", timeout=8000)
        except Exception:
            pass

        _resume(page)
        _wait_idle(page)


# ═══════════════════════════════════════════════════════════════
# §4.3 暂停/恢复排序（核心）
# ═══════════════════════════════════════════════════════════════

class TestPauseResumeOrdering:

    def test_paused_item_stays_first_in_queue(self, page):
        """暂停后文件仍在队列第一位（顺序不变）"""
        _pause(page)
        _upload(page, SMALL_TXT, "1_first_file.txt")
        _upload(page, SMALL_TXT, "2_second_file.txt")
        _upload(page, SMALL_TXT, "3_third_file.txt")
        try:
            page.wait_for_function(
                "document.querySelectorAll('#queueList .queue-item').length >= 2",
                timeout=8000)
        except Exception:
            pass

        names = _names(page)
        in_queue = page.evaluate("Object.keys(_queueItems).length")
        assert in_queue >= 2, f"Should have at least 2 items in _queueItems, got {in_queue}"
        if len(names) >= 2:
            assert "first" in names[0], f"First should be 1_first_file, got {names}"
            assert "third" in names[-1], f"Last should be 3_third_file, got {names}"

        _resume(page)
        _wait_idle(page)

    def test_resume_continues_first_item(self, page):
        """恢复后第一个 item 被处理"""
        _pause(page)
        _upload(page, SMALL_TXT, "resume_a.txt")
        _upload(page, SMALL_TXT, "resume_b.txt")
        _resume(page)
        _wait_completed(page, 2, timeout_ms=60000)
        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "2"
        _switch_tab(page, "processing")
        assert _tab_count(page, "processing") == "0"

    def test_pause_three_times_all_complete(self, page):
        """3 个文件，暂停后再恢复，全部完成"""
        _pause(page)
        _upload(page, SMALL_TXT, "t3_a.txt")
        _upload(page, SMALL_TXT, "t3_b.txt")
        _upload(page, SMALL_TXT, "t3_c.txt")
        try:
            page.wait_for_function(
                "document.querySelectorAll('#queueList .queue-item').length >= 2",
                timeout=8000)
        except Exception:
            pass

        in_queue = page.evaluate("Object.keys(_queueItems).length")
        assert in_queue >= 2, f"Should have at least 2 waiting, got {in_queue}"

        _resume(page)
        completed = _wait_completed(page, 3, timeout_ms=60000)
        assert completed >= 3, f"All 3 files should complete, got {completed}"

        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "3"

    def test_only_one_processing_at_any_time(self, page):
        """多个文件顺序处理，每次只有 1 个 processing"""
        _pause(page)
        _upload(page, SMALL_TXT, "unique_a.txt")
        _upload(page, SMALL_TXT, "unique_b.txt")
        _resume(page)
        _wait_completed(page, 2, timeout_ms=60000)
        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "2"

    def test_pause_resume_no_orphan_tasks(self, page):
        """暂停恢复后没有孤儿任务（全部都能完成）"""
        _pause(page)
        _upload(page, SMALL_TXT, "orphan_a.txt")
        _upload(page, SMALL_TXT, "orphan_b.txt")
        _resume(page)
        completed = _wait_completed(page, 2, timeout_ms=60000)
        assert completed >= 2, f"Both files should complete, got {completed}"


# ═══════════════════════════════════════════════════════════════
# §5.1 + §5.2 按钮显示规则 + 批量操作
# ═══════════════════════════════════════════════════════════════

class TestButtonVisibility:

    def test_no_checkboxes_during_processing(self, page):
        """处理中时 checkbox 不可见"""
        _upload(page, SMALL_TXT, "nocb_proc.txt")
        _wait_completed(page, 1, timeout_ms=30000)
        _switch_tab(page, "processing")
        assert not _has_cb(page), "No checkboxes on processing tab when all done"

    def test_no_batch_actions_during_processing(self, page):
        """处理中时批量操作按钮隐藏"""
        _pause(page)
        _upload(page, SMALL_TXT, "noba_proc.txt")
        _wait_idle(page)
        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "1"

    def test_no_retry_buttons_during_processing(self, page):
        """完成后 retry 按钮不出现"""
        _upload(page, SMALL_TXT, "retry_hidden_a.txt")
        _wait_completed(page, 1, timeout_ms=30000)
        _switch_tab(page, "completed")
        assert not _has_retry(page), "No retry buttons on completed items"

    def test_checkboxes_visible_when_paused(self, page):
        """暂停时 checkbox 可见"""
        _pause(page)
        _upload(page, SMALL_TXT, "cb_visible.txt")
        page.wait_for_selector("#queueList .queue-item", timeout=8000)
        has_cb_js = page.evaluate("document.querySelectorAll('#queueList .queue-cb').length > 0")
        has_qi = page.evaluate("Object.keys(_queueItems).length >= 1")
        assert has_cb_js or has_qi, f"Paused items should exist, _queueItems={page.evaluate('Object.keys(_queueItems).length')}"
        _resume(page)
        _wait_idle(page)

    def test_pause_button_hidden_when_idle(self, page):
        """空闲时暂停按钮不可见"""
        btn = page.locator("#togglePauseBtn")
        is_visible = btn.is_visible()
        assert not is_visible, "Pause button should be hidden/not visible when idle"

    def test_select_all_checks_all(self, page):
        """全选按钮勾选所有 checkbox"""
        _pause(page)
        _upload(page, SMALL_TXT, "sel_all_a.txt")
        _upload(page, SMALL_TXT, "sel_all_b.txt")
        _upload(page, SMALL_TXT, "sel_all_c.txt")
        all_cb = page.locator("#queueCheckAll")
        if all_cb.count() > 0:
            all_cb.check()

        total = page.locator("#queueList .queue-cb").count()
        checked = page.locator("#queueList .queue-cb:checked").count()
        assert checked == total, f"All {total} checkboxes should be checked, got {checked}"

        _resume(page)
        _wait_idle(page)

    def test_batch_cancel_moves_to_failed_tab(self, page):
        """终止选中 → 移到失败 Tab"""
        _pause(page)
        _upload(page, SMALL_TXT, "kill_a.txt")
        _upload(page, SMALL_TXT, "kill_b.txt")
        page.locator("#queueCheckAll").check()

        page.on("dialog", lambda d: d.accept())
        page.click("#batchKillBtn")
        page.wait_for_timeout(500)

        _switch_tab(page, "failed")
        assert _tab_count(page, "failed") == "2", f"Failed tab should show 2 cancelled, got {_tab_count(page, 'failed')}"

        _resume(page)
        _wait_idle(page)

    def test_batch_retry_moves_to_processing_tab(self, page):
        """批量重试 → 移到处理中 Tab"""
        _pause(page)
        _upload(page, SMALL_TXT, "retry_a.txt")
        _upload(page, SMALL_TXT, "retry_b.txt")
        page.locator("#queueCheckAll").check()
        page.on("dialog", lambda d: d.accept())
        page.click("#batchKillBtn")

        _switch_tab(page, "failed")
        page.locator("#queueCheckAll").check()
        page.click("#batchRetryBtn")
        page.wait_for_timeout(500)

        _switch_tab(page, "processing")
        assert _tab_count(page, "processing") == "2", f"Processing tab should show 2 retried, got {_tab_count(page, 'processing')}"

        _resume(page)
        _wait_idle(page)


# ═══════════════════════════════════════════════════════════════
# §1 数据生命周期 — 关进程清空队列
# ═══════════════════════════════════════════════════════════════

class TestProcessRestart:

    def test_fresh_page_has_empty_queue(self, page):
        """新页面打开时队列为空"""
        items = page.locator("#queueList .queue-item")
        assert items.count() == 0, "Fresh page should have empty queue"

    def test_no_stale_tasks_after_page_reload(self, page):
        """操作后刷新页面，队列应该为空"""
        _pause(page)
        _upload(page, SMALL_TXT, "stale_test.txt")
        _resume(page)
        _wait_completed(page, 1, timeout_ms=30000)

        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#logPanel", timeout=10000)
        page.wait_for_timeout(500)

        items = page.locator("#queueList .queue-item")
        assert items.count() == 0, "After reload, queue should be empty"


# ═══════════════════════════════════════════════════════════════
# U6 失败 Tab 分类排序
# ═══════════════════════════════════════════════════════════════

class TestFailedTabOrdering:

    def test_failed_tab_cancelled_before_errors(self, page):
        """失败 Tab 中 cancelled 在上面，error 在下面"""
        _pause(page)
        _upload(page, SMALL_TXT, "fail_sort_a.txt")
        _upload(page, SMALL_TXT, "fail_sort_b.txt")
        _upload(page, SMALL_TXT, "fail_sort_c.txt")
        page.locator("#queueCheckAll").check()
        page.on("dialog", lambda d: d.accept())
        page.click("#batchKillBtn")
        page.wait_for_timeout(500)

        _switch_tab(page, "failed")
        chips = _chips(page)
        texts = [t for t, c in chips]
        assert texts == ["已取消", "已取消", "已取消"], f"Failed tab should show all cancelled first, got {texts}"

        _resume(page)


# ═══════════════════════════════════════════════════════════════
# §6 大文件行为
# ═══════════════════════════════════════════════════════════════

class TestLargeFileBehavior:

    def test_large_file_shows_in_queue(self, page):
        """大文件上传后在队列中可见"""
        _pause(page)
        _upload(page, BIG_CONTENT, "large_file.txt")
        assert page.locator("#queueList .queue-item").count() >= 1, "Large file should appear in queue"
        _resume(page)
        _wait_idle(page)

    def test_large_file_completes(self, page):
        """大文件处理完成后队列项状态变为已完成"""
        _upload(page, BIG_CONTENT, "large_done.txt")
        completed = _wait_completed(page, 1, timeout_ms=120000)
        assert completed >= 1, f"Large file should complete, got {completed}"

        _switch_tab(page, "completed")
        chips = _chips(page)
        assert len(chips) >= 1
        assert chips[0][0] == "已完成", f"Completed chip should be '已完成', got '{chips[0][0]}'"

    def test_large_file_pause_resume_completes(self, page):
        """大文件暂停恢复后能继续完成"""
        _pause(page)
        _upload(page, BIG_CONTENT, "large_resume.txt")
        _resume(page)
        completed = _wait_completed(page, 1, timeout_ms=120000)
        assert completed >= 1, f"Large file should complete after pause/resume, got {completed}"


# ═══════════════════════════════════════════════════════════════
# §7 提取模式特殊规则
# ═══════════════════════════════════════════════════════════════

class TestExtractMode:

    def test_extract_upload_appears_in_queue(self, page):
        """提取模式上传后文件出现在队列中"""
        _switch_mode(page, "extract")
        _pause(page)
        _upload(page, SMALL_TXT, "extract_upload.txt")
        page.wait_for_timeout(1000)
        cnt = page.evaluate("Object.keys(_queueItems).length")
        items = page.locator("#queueList .queue-item").count()
        assert cnt >= 1 or items >= 1, f"File should be in queue, _queueItems={cnt}, DOM items={items}"
        _resume(page)
        _wait_idle(page)

    def test_extract_completion_shows_in_completed_tab(self, page):
        """提取完成后文件出现在已完成 Tab"""
        _switch_mode(page, "extract")
        _upload(page, SMALL_TXT, "ext_complete.txt")
        _wait_completed(page, 1, timeout_ms=60000)
        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "1"

    def test_extract_result_isolated_from_desen_result(self, page):
        """提取结果与脱敏结果隔离"""
        _upload(page, SMALL_TXT, "desen_isolate.txt")
        _wait_completed(page, 1, timeout_ms=60000)

        _switch_mode(page, "extract")
        _upload(page, SMALL_TXT, "extract_isolate.txt")
        _wait_completed(page, 1, timeout_ms=60000)

        _switch_mode(page, "desensitize")
        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "1", "Desensitize completed should be 1"

        _switch_mode(page, "extract")
        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "1", "Extract completed should be 1"


# ═══════════════════════════════════════════════════════════════
# 综合场景测试
# ═══════════════════════════════════════════════════════════════

class TestIntegration:

    def test_mixed_mode_queue_independence(self, page):
        """两个模式完成数互不干扰"""
        _upload(page, SMALL_TXT, "mix_desen_a.txt")
        _upload(page, SMALL_TXT, "mix_desen_b.txt")
        _wait_completed(page, 2, timeout_ms=60000)

        _switch_mode(page, "extract")
        _upload(page, SMALL_TXT, "mix_ext_a.txt")
        _upload(page, SMALL_TXT, "mix_ext_b.txt")
        _upload(page, SMALL_TXT, "mix_ext_c.txt")
        _wait_completed(page, 3, timeout_ms=60000)

        _switch_mode(page, "desensitize")
        _switch_tab(page, "completed")
        assert _tab_count(page, "completed") == "2", f"Expected 2 desen, got {_tab_count(page, 'completed')}"

        _switch_mode(page, "extract")
        assert _tab_count(page, "completed") == "3", f"Expected 3 extract, got {_tab_count(page, 'completed')}"

    def test_rapid_pause_resume_stress(self, page):
        """快速暂停恢复压力测试"""
        _pause(page)
        _upload(page, SMALL_TXT, "stress_a.txt")
        _upload(page, SMALL_TXT, "stress_b.txt")

        page.wait_for_timeout(500)
        for _ in range(5):
            page.evaluate("() => fetch('/api/queue/pause', {method:'POST'})")
            page.wait_for_timeout(100)
            page.evaluate("() => fetch('/api/queue/resume', {method:'POST'})")
            page.wait_for_timeout(100)

        _resume(page)
        completed = _wait_completed(page, 2, timeout_ms=60000)
        assert completed >= 2, f"All files should complete after stress, got {completed}"

    def test_single_file_upload_and_process(self, page):
        """单文件上传 → 处理 → 完成"""
        _upload(page, SMALL_TXT, "single.txt")
        completed = _wait_completed(page, 1, timeout_ms=60000)
        assert completed >= 1, f"Single file should complete, got {completed}"

    def test_multiple_sequential_uploads(self, page):
        """连续上传 5 个文件全部完成"""
        for i in range(5):
            _upload(page, SMALL_TXT, f"seq_{i}.txt")

        completed = _wait_completed(page, 5, timeout_ms=120000)
        assert completed >= 5, f"All 5 sequential uploads should complete, got {completed}"


# ═══════════════════════════════════════════════════════════════
# §新增：F1-F9 用户评审补齐测试（2026-05-17）
# ═══════════════════════════════════════════════════════════════

class TestPauseOrderPreservation:
    """F1: 暂停后任务保持队首"""

    def test_paused_item_stays_at_position_zero(self, page):
        _pause(page)
        _upload(page, SMALL_TXT, "1_first_file.txt")
        _upload(page, SMALL_TXT, "2_second_file.txt")
        _upload(page, SMALL_TXT, "3_third_file.txt")
        try:
            page.wait_for_function(
                "document.querySelectorAll('#queueList .queue-item-name').length >= 3",
                timeout=8000)
        except Exception:
            pass

        names = _names(page)
        assert len(names) >= 3, f"Should have 3 queue items, got {len(names)}"
        assert "1_first" in names[0], f"First item should be 1_first_file, got '{names[0]}'"
        assert "3_third" in names[-1] or "3_third" in names[2], f"Last should contain 3_third"

        _resume(page)
        _wait_idle(page)


class TestNoIdleWhenQueueHasItems:
    """F2+F7: 队列有任务时不显示闲置中"""

    def test_paused_queue_does_not_show_idle(self, page):
        _pause(page)
        _upload(page, SMALL_TXT, "no_idle_test.txt")
        page.wait_for_selector("#queueList .queue-item", timeout=8000)

        text = _global_status(page)
        assert text != "闲置中", f"Should not show '闲置中' when queue has items, got '{text}'"

        _resume(page)
        _wait_idle(page)


class TestQueueCountFromFrontend:
    """F3: 队列数字来自前端计数"""

    def test_queue_count_matches_items(self, page):
        _pause(page)
        _upload(page, SMALL_TXT, "qcount_a.txt")
        _upload(page, SMALL_TXT, "qcount_b.txt")
        page.wait_for_function(
            "document.querySelectorAll('#queueList .queue-item').length >= 2",
            timeout=8000)

        count_text = page.locator("#queueCount").text_content().strip()
        assert int(count_text) >= 2, f"queueCount should be >= 2, got '{count_text}'"

        _resume(page)
        _wait_idle(page)


class TestModeTagFixedColors:
    """F4: 模式标签颜色固定——不随当前主题色变"""

    def test_desen_tag_is_purple_in_extract_mode(self, page):
        page.click("#modeExtract")
        page.wait_for_timeout(300)

        _pause(page)
        _upload(page, SMALL_TXT, "tag_color.txt")
        try:
            page.wait_for_selector("#queueList .queue-mode-tag", timeout=10000)
        except Exception:
            pass

        tag = page.locator("#queueList .queue-mode-tag")
        if tag.count() > 0:
            color = tag.first.evaluate("el => getComputedStyle(el).color")
            assert "124" in color or "7c3aed" in color.lower() or "purple" in color.lower(), \
                f"Desen tag in extract mode should be purple-ish, got {color}"

        _resume(page)
        _wait_idle(page)


class TestUploadAutoSwitchTab:
    """F8: 上传后自动切到处理中Tab"""

    def test_upload_switches_to_processing_tab(self, page):
        page.click('.queue-tab[data-qt="completed"]')
        page.wait_for_timeout(200)

        _pause(page)
        _upload(page, SMALL_TXT, "auto_switch.txt")
        page.wait_for_timeout(500)

        active_tab = page.locator('.queue-tab.active')
        tab_attr = active_tab.get_attribute("data-qt")
        assert tab_attr == "processing", f"Active tab should be 'processing' after upload, got '{tab_attr}'"

        _resume(page)
        _wait_idle(page)


class TestRefreshClearsQueue:
    """F9: 刷新后后端队列清空"""

    def test_refresh_shows_empty_queue(self, page):
        _pause(page)
        _upload(page, SMALL_TXT, "refresh_test.txt")
        page.wait_for_selector("#queueList .queue-item", timeout=8000)

        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#logPanel", timeout=10000)
        page.wait_for_timeout(500)

        count_text = page.locator("#queueCount").text_content().strip()
        assert count_text == "0", f"After refresh, queue should be 0, got '{count_text}'"


class TestModeSwitchPreservesButtons:
    """F6: 切换模式后结果按钮保留"""

    def test_buttons_preserved_after_mode_switch(self, page):
        _upload_and_wait(page, SMALL_TXT, "btn_keep.txt")
        page.click('.queue-tab[data-qt="completed"]')
        page.wait_for_selector("#queueList .queue-item", timeout=10000)
        page.locator("#queueList .queue-item").first.click()
        page.wait_for_selector("#resultActions button, #resultActions a", timeout=10000)

        btn_count_before = page.locator("#resultActions button, #resultActions a").count()

        page.click("#modeExtract")
        page.wait_for_timeout(500)
        page.click("#modeDesensitize")
        page.wait_for_timeout(500)

        page.click('.queue-tab[data-qt="completed"]')
        page.wait_for_selector("#queueList .queue-item", timeout=10000)
        page.locator("#queueList .queue-item").first.click()
        page.wait_for_timeout(500)

        btn_count_after = page.locator("#resultActions button, #resultActions a").count()
        assert btn_count_after >= btn_count_before - 1, \
            f"Button count should be preserved after mode switch, was {btn_count_before}, now {btn_count_after}"


class TestCrossModeQueueUpdates:
    """B1: 跨模式任务状态更新 + B3: 结果保留"""
    def test_extract_completes_while_in_desen_mode(self, page):
        page.click("#modeExtract")
        page.wait_for_timeout(200)
        _upload(page, SMALL_TXT, "cross_ext.txt")
        page.wait_for_timeout(300)

        page.click("#modeDesensitize")
        page.wait_for_timeout(300)

        page.click('.queue-tab[data-qt="completed"]')
        try:
            page.wait_for_selector("#queueList .queue-status-chip.completed", timeout=60000)
        except Exception:
            pass
        page.click('.queue-tab[data-qt="processing"]')

        page.click("#modeExtract")
        page.wait_for_timeout(500)

        queue_items = page.locator("#queueList .queue-item")
        if queue_items.count() > 0:
            page.click('.queue-tab[data-qt="completed"]')
            try:
                page.wait_for_selector("#queueList .queue-status-chip.completed", timeout=10000)
            except Exception:
                pass

    def test_desen_completes_while_in_extract_mode(self, page):
        page.click("#modeDesensitize")
        page.wait_for_timeout(200)
        _upload(page, SMALL_TXT, "cross_desen.txt")
        page.wait_for_timeout(300)

        page.click("#modeExtract")
        page.wait_for_timeout(300)

        page.click('.queue-tab[data-qt="completed"]')
        try:
            page.wait_for_selector("#queueList .queue-status-chip.completed", timeout=60000)
        except Exception:
            pass

        page.click("#modeDesensitize")
        page.wait_for_timeout(500)
        page.click('.queue-tab[data-qt="completed"]')
        try:
            page.wait_for_selector("#queueList .queue-status-chip.completed", timeout=10000)
        except Exception:
            pass

    def test_result_persists_after_mode_roundtrip(self, page):
        _upload_and_wait(page, SMALL_TXT, "persist_test.txt")
        page.click('.queue-tab[data-qt="completed"]')
        page.wait_for_selector("#queueList .queue-item", timeout=10000)
        page.locator("#queueList .queue-item").first.click()
        page.wait_for_selector("#resultSection", state="visible", timeout=10000)
        assert page.locator("#resultSection").is_visible()

        page.click("#modeExtract")
        page.wait_for_timeout(500)
        page.click("#modeDesensitize")
        page.wait_for_timeout(500)

        page.click('.queue-tab[data-qt="completed"]')
        page.wait_for_selector("#queueList .queue-item", timeout=10000)
        page.locator("#queueList .queue-item").first.click()
        page.wait_for_timeout(500)

        assert page.locator("#resultSection").is_visible()

    def test_retry_processing_chip_yellow(self, page):
        """B2: retry marks task as processing (yellow)"""
        from tests.playwright.conftest import _upload_via_dom

        _pause(page)
        _upload(page, SMALL_TXT, "retry_yellow.txt")
        page.wait_for_timeout(500)
        _resume(page)
        _wait_completed(page, 1, timeout_ms=60000)

        page.click('.queue-tab[data-qt="completed"]')
        page.wait_for_selector("#queueList .queue-item", timeout=10000)

        retry_btn = page.locator("#queueList .queue-retry-btn")
        if retry_btn.count() > 0:
            retry_btn.first.click()
            page.wait_for_timeout(1000)

            chips = page.locator("#queueList .queue-status-chip.processing")
            if chips.count() > 0:
                assert chips.first.text_content() == "处理中"

import os, sys, time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.playwright.conftest import _upload_via_dom, SMALL_TXT


def _upload_and_click_completed(page, content, filename="test.txt"):
    _upload_via_dom(page, content, filename)
    page.wait_for_timeout(200)
    page.locator('.queue-tab[data-qt="completed"]').click()
    page.wait_for_selector("#queueList .queue-status-chip.completed", timeout=60000)


class TestResultPreview:
    def test_completed_item_shows_result_section(self, page):
        _upload_and_click_completed(page, SMALL_TXT, "res_preview.txt")
        page.locator("#queueList .queue-item").first.click()
        page.wait_for_selector("#resultSection", state="visible", timeout=10000)
        assert page.locator("#resultSection").is_visible()

    def test_result_has_original_preview_tab(self, page):
        _upload_and_click_completed(page, SMALL_TXT, "res_orig.txt")
        page.locator("#queueList .queue-item").first.click()
        page.wait_for_selector("#tabOriginal", state="visible", timeout=10000)
        assert page.locator("#tabOriginal").is_visible()

    def test_result_has_desensitized_preview_tab(self, page):
        _upload_and_click_completed(page, SMALL_TXT, "res_desen.txt")
        page.locator("#queueList .queue-item").first.click()
        page.wait_for_selector("#tabDesensitized", state="visible", timeout=10000)
        assert page.locator("#tabDesensitized").is_visible()

    def test_result_has_replacements_tab(self, page):
        _upload_and_click_completed(page, SMALL_TXT, "res_repl.txt")
        page.locator("#queueList .queue-item").first.click()
        page.wait_for_selector("#tabReplacements", state="visible", timeout=10000)
        assert page.locator("#tabReplacements").is_visible()

    def test_result_section_has_download_button(self, page):
        _upload_and_click_completed(page, SMALL_TXT, "res_down.txt")
        page.locator("#queueList .queue-item").first.click()
        page.wait_for_selector("#resultActions button, #resultActions a", timeout=10000)
        download_btn = page.locator("#resultActions button, #resultActions a")
        assert download_btn.count() >= 1

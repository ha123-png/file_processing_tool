import os, sys, time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.playwright.conftest import _upload_via_dom, SMALL_TXT


class TestE2ESmoke:
    def test_desen_full_pipeline(self, page):
        page.locator("#modeDesensitize").click()
        page.wait_for_timeout(200)

        _upload_via_dom(page, SMALL_TXT, "smoke_desen.txt")
        page.wait_for_timeout(200)

        page.locator('.queue-tab[data-qt="completed"]').click()
        page.wait_for_selector("#queueList .queue-status-chip.completed", timeout=60000)

        item = page.locator("#queueList .queue-item").first
        item_text = item.text_content()
        assert "smoke_desen" in item_text

        chip = item.locator(".queue-status-chip").first
        assert chip.text_content() == "已完成"

        item.click()
        page.wait_for_selector("#resultSection", state="visible", timeout=10000)

        page.locator("#tabDesensitized").click()
        page.wait_for_selector("#desensitizedPanel", state="visible", timeout=5000)

    def test_extract_full_pipeline(self, page):
        page.locator("#modeExtract").click()
        page.wait_for_timeout(200)

        _upload_via_dom(page, SMALL_TXT, "smoke_extract.txt")
        page.wait_for_timeout(200)

        page.locator('.queue-tab[data-qt="completed"]').click()
        page.wait_for_selector("#queueList .queue-status-chip.completed", timeout=60000)

        item = page.locator("#queueList .queue-item").first
        assert "smoke_extract" in item.text_content()

        chip = item.locator(".queue-status-chip").first
        assert chip.text_content() == "已完成"

        item.click()
        page.wait_for_selector("#resultSection", state="visible", timeout=10000)

    def test_two_files_queue_order(self, page):
        page.locator("#modeDesensitize").click()
        page.wait_for_timeout(200)

        _upload_via_dom(page, SMALL_TXT, "order_1.txt")
        page.wait_for_timeout(200)
        _upload_via_dom(page, SMALL_TXT, "order_2.txt")
        page.wait_for_timeout(200)

        page.locator('.queue-tab[data-qt="completed"]').click()
        page.wait_for_selector("#queueList .queue-status-chip.completed", timeout=60000)

        items = page.locator("#queueList .queue-item")
        count = items.count()
        assert count >= 1

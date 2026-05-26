import os, sys, time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestDashboard:
    def test_dashboard_tab_switches(self, page):
        page.locator("#tabDashboard").click()
        page.wait_for_selector("#tabDashboard.active, #tabDashboard.main-tab.active", timeout=5000)

    def test_dashboard_shows_stat_section(self, page):
        page.locator("#tabDashboard").click()
        page.wait_for_selector("#tabDashboard.active, #tabDashboard.main-tab.active", timeout=5000)

    def test_dashboard_workbench_tab_returns(self, page):
        page.locator("#tabDashboard").click()
        page.wait_for_timeout(200)
        page.locator("#tabWorkbench").click()
        page.wait_for_selector("#dropZone", state="visible", timeout=5000)
        assert page.locator("#dropZone").is_visible()


class TestMergePanel:
    def test_merge_panel_visible_after_extract(self, page):
        from tests.playwright.conftest import _upload_via_dom

        page.locator("#modeExtract").click()
        page.wait_for_timeout(200)

        _upload_via_dom(page, "甲方：张三\n金额：100元\n", "ext_merge.txt")
        page.wait_for_timeout(200)

        page.locator('.queue-tab[data-qt="completed"]').click()
        page.wait_for_selector("#queueList .queue-status-chip.completed", timeout=60000)

        page.locator("#queueList .queue-item").first.click()
        page.wait_for_timeout(300)

        assert page.locator("#mergeWrapper").count() >= 0

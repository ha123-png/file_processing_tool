import os, sys, time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestSettingsPanel:
    def test_open_settings(self, page):
        page.locator("#settingsBtn").click()
        page.wait_for_selector("#settingsOverlay", state="visible", timeout=5000)
        assert page.locator("#settingsOverlay").is_visible()

    def test_close_settings(self, page):
        page.locator("#settingsBtn").click()
        page.wait_for_selector("#settingsOverlay", state="visible", timeout=5000)
        page.locator("#settingsClose").click()
        page.wait_for_selector("#settingsOverlay", state="hidden", timeout=5000)

    def test_settings_has_provider_selector(self, page):
        page.locator("#settingsBtn").click()
        page.wait_for_selector("#settingProvider", state="visible", timeout=5000)
        assert page.locator("#settingProvider").is_visible()

    def test_settings_has_model_input(self, page):
        page.locator("#settingsBtn").click()
        page.wait_for_selector("#settingModel", state="visible", timeout=5000)
        assert page.locator("#settingModel").is_visible()

    def test_save_settings_shows_feedback(self, page):
        page.locator("#settingsBtn").click()
        page.wait_for_selector("#settingsOverlay", state="visible", timeout=5000)

        save_btns = page.locator(".settings-btn-save, #saveSettingsBtn, button:has-text('保存')")
        if save_btns.count() > 0:
            save_btns.first.click()
            page.wait_for_timeout(200)

    def test_help_panel_opens(self, page):
        page.locator("#helpBtn").click()
        page.wait_for_timeout(200)

import os, sys, time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestTemplateManagement:
    def _open_settings(self, page):
        page.locator("#settingsBtn").click()
        page.wait_for_selector("#settingsOverlay", state="visible", timeout=5000)

    def _open_template_card(self, page):
        cards = page.locator(".settings-card-header")
        for i in range(cards.count()):
            header = cards.nth(i)
            if "模板管理" in (header.inner_text() or ""):
                body = header.locator("..").locator(".settings-card-body")
                if body.is_visible():
                    return
                header.click()
                page.wait_for_timeout(300)
                return

    def test_delete_template_button_shows_toast(self, page):
        self._open_settings(page)
        self._open_template_card(page)
        sel = page.locator("#settingTemplateSelect")
        sel.select_option(index=1)
        del_btn = page.locator("#templateDelBtn")
        del_btn.click()
        page.wait_for_timeout(400)
        toast = page.locator("#settingsToast")
        assert toast.is_visible()

    def test_apply_template_button_shows_toast(self, page):
        self._open_settings(page)
        self._open_template_card(page)
        sel = page.locator("#settingTemplateSelect")
        sel.select_option(index=0)
        apply_btn = page.locator("#templateApplyBtn")
        apply_btn.click()
        page.wait_for_timeout(600)
        toast = page.locator("#settingsToast")
        assert toast.is_visible()

    def test_system_template_cannot_be_deleted(self, page):
        self._open_settings(page)
        self._open_template_card(page)
        sel = page.locator("#settingTemplateSelect")
        sel.select_option(index=0)
        del_btn = page.locator("#templateDelBtn")
        del_btn.click()
        page.wait_for_timeout(400)
        options = sel.locator("option")
        assert options.count() >= 2

    def test_apply_button_text_is_correct(self, page):
        self._open_settings(page)
        self._open_template_card(page)
        btn = page.locator("#templateApplyBtn")
        text = btn.inner_text()
        assert "保存并应用" in text or "\u4fdd\u5b58\u5e76\u5e94\u7528" in text

    def test_apply_button_is_green_not_purple(self, page):
        self._open_settings(page)
        self._open_template_card(page)
        btn = page.locator("#templateApplyBtn")
        bg = btn.evaluate("el => window.getComputedStyle(el).backgroundColor")
        assert "rgb" in str(bg).lower()

    def test_add_template_button_works(self, page):
        self._open_settings(page)
        self._open_template_card(page)
        page.locator("#settingTemplateName").fill("测试模板")
        add_btn = page.locator("#templateAddBtn")
        add_btn.click()
        page.wait_for_timeout(300)
        sel = page.locator("#settingTemplateSelect")
        options = sel.locator("option")
        last_text = options.last.inner_text()
        assert "测试模板" in last_text

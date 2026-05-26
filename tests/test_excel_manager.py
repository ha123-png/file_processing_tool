import pytest
import tempfile
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestExcelManager:
    @pytest.fixture(autouse=True)
    def setup_excel(self, temp_config):
        import app.shared as shared
        import app.excel_manager as em
        shared._excel_active = None
        shared._excel_sheets.clear()
        yield
        shared._excel_active = None
        shared._excel_sheets.clear()

    def test_init_session_creates_workbook(self):
        from app.excel_manager import init_excel_session
        name = init_excel_session(None, "test_sheet")
        assert name == "test_sheet"
        from app.excel_manager import get_excel_state
        state = get_excel_state()
        assert state is not None
        assert state["ws"].title == "提取结果"

    def test_init_session_with_template(self):
        template = {
            "name": "测试模板",
            "fields": [
                {"label": "列A", "section": "header"},
                {"label": "列B", "section": "item"},
            ]
        }
        from app.excel_manager import init_excel_session
        name = init_excel_session(template)
        assert name is not None
        from app.excel_manager import get_excel_state
        state = get_excel_state()
        assert state["keys"] == ["列A", "列B"]
        assert state["labels"] == ["列A", "列B"]

    def test_save_and_get_state(self):
        from app.excel_manager import init_excel_session, save_current_sheet, get_excel_state
        init_excel_session(None, "save_test")
        state = get_excel_state()
        state["ws"].cell(row=2, column=1, value="hello")
        save_current_sheet()
        state2 = get_excel_state()
        assert state2["ws"].cell(row=2, column=1).value == "hello"

    def test_excel_state_none_when_cleared(self):
        from app.excel_manager import get_excel_state
        assert get_excel_state() is None

    def test_merge_to_excel_with_data(self):
        from app.excel_manager import init_excel_session, merge_to_excel, get_excel_state
        template = {
            "name": "测试",
            "fields": [
                {"label": "名称", "section": "header"},
                {"label": "数值", "section": "item"},
            ]
        }
        init_excel_session(template, "merge_test")
        result = {
            "header": {"名称": "测试数据"},
            "items": [{"数值": "100"}, {"数值": "200"}]
        }
        merge_to_excel(result, template)
        state = get_excel_state()
        ws = state["ws"]
        assert ws.cell(row=1, column=1).value == "名称"
        assert ws.cell(row=2, column=1).value == "测试数据"
        assert ws.cell(row=2, column=2).value == "100"
        assert ws.cell(row=3, column=2).value == "200"

    def test_merge_to_excel_auto_inits(self):
        from app.excel_manager import merge_to_excel, get_excel_state
        template = {
            "fields": [
                {"label": "A", "section": "header"},
                {"label": "B", "section": "item"},
            ]
        }
        result = {"header": {"a": "h"}, "items": [{"b": "v1"}, {"b": "v2"}]}
        merge_to_excel(result, template)
        state = get_excel_state()
        assert state is not None
        assert state["ws"].max_row >= 3

    def test_multiple_sessions(self):
        from app.excel_manager import init_excel_session, get_excel_state
        name1 = init_excel_session(None, "sheet1")
        name2 = init_excel_session(None, "sheet2")
        assert name1 == "sheet1"
        assert name2 == "sheet2"
        state = get_excel_state()
        assert state is not None


class TestExcelBatchUpdate:
    @pytest.fixture(autouse=True)
    def setup(self, temp_config):
        import app.shared as shared
        shared._excel_active = None
        shared._excel_sheets.clear()
        yield
        shared._excel_active = None
        shared._excel_sheets.clear()

    def test_batch_update_cells(self):
        from app.excel_manager import init_excel_session, get_excel_state
        template = {
            "fields": [
                {"label": "C1", "section": "header"},
                {"label": "C2", "section": "item"},
            ]
        }
        init_excel_session(template, "update_test")
        from app.excel_manager import get_excel_state
        state = get_excel_state()
        ws = state["ws"]
        ws.cell(row=2, column=1, value="old")
        ws.cell(row=2, column=2, value="old2")

        import app.shared as shared
        cells = [
            {"row_index": 1, "col_index": 1, "value": "new"},
            {"row_index": 1, "col_index": 2, "value": "new2"},
        ]
        with shared._EXCEL_LOCK:
            for cell in cells:
                ws.cell(row=cell["row_index"] + 1, column=cell["col_index"], value=cell["value"])

        assert ws.cell(row=2, column=1).value == "new"
        assert ws.cell(row=2, column=2).value == "new2"

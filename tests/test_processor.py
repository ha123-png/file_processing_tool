import json
import pytest
import tempfile
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestCleanNumericField:
    def test_strips_yuan_symbol(self):
        from app.processor import _clean_numeric_field
        assert _clean_numeric_field("¥1000.00") == "1000"
        assert _clean_numeric_field("￥1000.00") == "1000"
        assert _clean_numeric_field("$500.55") == "500.55"

    def test_removes_yuan_text(self):
        from app.processor import _clean_numeric_field
        assert _clean_numeric_field("1000.00元") == "1000"
        assert _clean_numeric_field("1,234.56") == "1234.56"

    def test_handles_wan_yuan(self):
        from app.processor import _clean_numeric_field
        assert _clean_numeric_field("1万元") == "1"

    def test_returns_non_string_unchanged(self):
        from app.processor import _clean_numeric_field
        assert _clean_numeric_field(None) is None
        assert _clean_numeric_field(123) == 123

    def test_empty_string(self):
        from app.processor import _clean_numeric_field
        assert _clean_numeric_field("") == ""

    def test_invalid_number_returns_original(self):
        from app.processor import _clean_numeric_field
        assert _clean_numeric_field("N/A") == "N/A"

    def test_int_keeps_as_int(self):
        from app.processor import _clean_numeric_field
        assert _clean_numeric_field("1000.00") == "1000"

    def test_tax_rate_percent_to_decimal(self):
        from app.processor import _clean_numeric_field
        assert _clean_numeric_field("13%", is_tax_rate=True) == "0.13"
        assert _clean_numeric_field("6%", is_tax_rate=True) == "0.06"

    def test_tax_rate_already_decimal(self):
        from app.processor import _clean_numeric_field
        assert _clean_numeric_field("0.13", is_tax_rate=True) == "0.13"

    def test_tax_rate_with_yen_symbol(self):
        from app.processor import _clean_numeric_field
        result = _clean_numeric_field("¥13%", is_tax_rate=True)
        assert "0.13" in result

    def test_tax_rate_invalid_returns_original(self):
        from app.processor import _clean_numeric_field
        assert _clean_numeric_field("免税", is_tax_rate=True) == "免税"


class TestParseExtractionResult:
    @pytest.fixture
    def invoice_template(self):
        return {
            "name": "增值税发票",
            "fields": [
                {"key": "发票号码", "label": "发票号码", "section": "header"},
                {"key": "价税合计", "label": "价税合计", "section": "header"},
                {"key": "税率/征收率", "label": "税率", "section": "item"},
                {"key": "金额", "label": "金额", "section": "item"},
                {"key": "数量", "label": "数量", "section": "item"},
                {"key": "单价", "label": "单价", "section": "item"},
                {"key": "税额", "label": "税额", "section": "item"},
            ]
        }

    @pytest.fixture
    def non_invoice_template(self):
        return {
            "name": "送货单",
            "fields": [
                {"key": "company", "label": "公司名", "section": "header"},
                {"key": "金额", "label": "金额", "section": "item"},
                {"key": "数量", "label": "数量", "section": "item"},
            ]
        }

    def test_parses_basic_json(self, invoice_template):
        from app.processor import parse_extraction_result
        raw = json.dumps({
            "发票号码": "12345678",
            "价税合计": "1000.00",
            "items": [
                {"税率/征收率": "13%", "金额": "800", "数量": "2", "单价": "400", "税额": "104"}
            ]
        })
        result = parse_extraction_result(raw, invoice_template)
        assert result["header"]["发票号码"] == "12345678"
        assert result["header"]["价税合计"] == "1000"
        assert len(result["items"]) == 1
        assert result["items"][0]["税率/征收率"] == "0.13"
        assert result["items"][0]["金额"] == "800"
        assert result["items"][0]["数量"] == "2"

    def test_invoice_total_amount_strips_symbol(self, invoice_template):
        from app.processor import parse_extraction_result
        raw = json.dumps({
            "价税合计": "¥1000.00",
            "items": [{"金额": "500", "数量": "1", "税率/征收率": "13%"}]
        })
        result = parse_extraction_result(raw, invoice_template)
        assert result["header"]["价税合计"] == "1000"

    def test_non_invoice_does_not_strip_amount(self, non_invoice_template):
        from app.processor import parse_extraction_result
        raw = json.dumps({
            "company": "测试公司",
            "items": [{"金额": "¥1000", "数量": "5"}]
        })
        result = parse_extraction_result(raw, non_invoice_template)
        assert "¥" in result["items"][0]["金额"]

    def test_empty_json_returns_default(self, invoice_template):
        from app.processor import parse_extraction_result
        result = parse_extraction_result("{invalid}", invoice_template)
        assert result["item_count"] == 0
        assert result["items"] == []

    def test_json_with_markdown_wrapper(self, invoice_template):
        from app.processor import parse_extraction_result
        raw = '```json\n{"发票号码": "NO001", "items": []}\n```'
        result = parse_extraction_result(raw, invoice_template)
        assert result["header"]["发票号码"] == "NO001"

    def test_json_with_text_prefix(self, invoice_template):
        from app.processor import parse_extraction_result
        raw = '以下是提取结果：{"发票号码": "NO001", "items": []}'
        result = parse_extraction_result(raw, invoice_template)
        assert result["header"]["发票号码"] == "NO001"

    def test_items_not_list_returns_empty(self, invoice_template):
        from app.processor import parse_extraction_result
        raw = json.dumps({"发票号码": "NO001", "items": "not_a_list"})
        result = parse_extraction_result(raw, invoice_template)
        assert result["items"] == []

    def test_date_normalization_in_header(self, invoice_template):
        from app.processor import parse_extraction_result
        invoiceno_tpl = {
            "name": "发票",
            "fields": [
                {"key": "开票日期", "label": "开票日期", "section": "header"},
                {"key": "金额", "label": "金额", "section": "item"},
            ]
        }
        raw = json.dumps({"开票日期": "2024-01-15", "items": [{"金额": "100"}]})
        result = parse_extraction_result(raw, invoiceno_tpl)
        assert "2024" in result["header"]["开票日期"]

    def test_date_normalization_in_items(self, invoice_template):
        from app.processor import parse_extraction_result
        date_tpl = {
            "name": "发票",
            "fields": [
                {"key": "date", "label": "日期", "section": "item"},
            ]
        }
        raw = json.dumps({"items": [{"date": "2024-01-15"}]})
        result = parse_extraction_result(raw, date_tpl)
        assert "2024" in result["items"][0]["date"]

    def test_null_template(self):
        from app.processor import parse_extraction_result
        raw = json.dumps({"some_key": "some_value", "items": [{"a": "1"}]})
        result = parse_extraction_result(raw, None)
        assert result["header"] == {}
        assert result["item_count"] >= 0

    def test_markers_extraction(self, invoice_template):
        from app.processor import parse_extraction_result
        raw = '前缀内容【内容开始】{"发票号码": "X001", "items": []}【内容结束】后缀内容'
        result = parse_extraction_result(raw, invoice_template)
        assert result["header"]["发票号码"] == "X001"

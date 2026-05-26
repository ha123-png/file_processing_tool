import json
import pytest
import tempfile
import os
import sys
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestExtractBetweenMarkers:
    def test_extracts_with_markers(self):
        from app.processor import _extract_between_markers
        raw = "some prefix【内容开始】{\"key\": \"value\"}【内容结束】some suffix"
        result = _extract_between_markers(raw)
        assert "【内容开始】" not in result
        assert "【内容结束】" not in result
        assert "key" in result

    def test_no_markers_returns_original(self):
        from app.processor import _extract_between_markers
        raw = '{"key": "value"}'
        result = _extract_between_markers(raw)
        assert "key" in result

    def test_only_start_marker(self):
        from app.processor import _extract_between_markers
        raw = "prefix【内容开始】{\"key\": \"value\"}"
        result = _extract_between_markers(raw)
        assert "key" in result

    def test_only_end_marker(self):
        from app.processor import _extract_between_markers
        raw = "{\"key\": \"value\"}【内容结束】"
        result = _extract_between_markers(raw)
        assert "key" in result

    def test_empty_between_markers(self):
        from app.processor import _extract_between_markers
        raw = "【内容开始】【内容结束】"
        result = _extract_between_markers(raw)
        assert result == ""

    def test_multiple_marker_pairs_takes_first_pair(self):
        """first start + first end: extracts only the first wrapped content"""
        from app.processor import _extract_between_markers
        raw = "【内容开始】first【内容结束】middle【内容开始】second【内容结束】"
        result = _extract_between_markers(raw)
        assert result == "first"


class TestDeduplicateItems:
    def test_single_item_returns_same(self):
        from app.processor import deduplicate_items
        items = [{"name": "test", "amount": "100"}]
        keys = ["name", "amount"]
        result = deduplicate_items(items, keys)
        assert len(result) == 1
        assert result[0]["name"] == "test"

    def test_different_items_all_kept(self):
        from app.processor import deduplicate_items
        items = [
            {"name": "a", "amount": "100"},
            {"name": "b", "amount": "200"},
        ]
        keys = ["name", "amount"]
        result = deduplicate_items(items, keys)
        assert len(result) == 2

    def test_empty_items(self):
        from app.processor import deduplicate_items
        result = deduplicate_items([], ["key"])
        assert result == []

    def test_non_dict_items_skipped(self):
        from app.processor import deduplicate_items
        items = ["not_a_dict", {"name": "a", "amount": "100"}]
        keys = ["name", "amount"]
        result = deduplicate_items(items, keys)
        assert len(result) == 1
        assert result[0]["name"] == "a"

    def test_sparse_items_below_50pct_merged(self):
        from app.processor import deduplicate_items
        items = [
            {"a": "1", "b": "", "c": "", "d": "", "e": ""},
            {"a": "", "b": "2", "c": "", "d": "", "e": ""},
        ]
        keys = ["a", "b", "c", "d", "e"]
        result = deduplicate_items(items, keys)
        assert len(result) == 1
        assert result[0]["a"] == "1"
        assert result[0]["b"] == "2"


class TestBuildExtractionPrompt:
    @pytest.fixture
    def invoice_template(self):
        return {
            "name": "增值税发票",
            "description": "提取增值税发票信息",
            "fields": [
                {"key": "invoice_no", "label": "发票号码", "section": "header"},
                {"key": "total_amount", "label": "价税合计", "section": "header"},
                {"key": "name", "label": "名称", "section": "item"},
                {"key": "amount", "label": "金额", "section": "item"},
                {"key": "tax_rate", "label": "税率", "section": "item"},
            ]
        }

    def test_prompt_contains_field_labels(self, invoice_template):
        from app.processor import build_extraction_prompt
        prompt = build_extraction_prompt(invoice_template)
        assert "发票号码" in prompt
        assert "价税合计" in prompt

    def test_prompt_contains_json_format_instructions(self, invoice_template):
        from app.processor import build_extraction_prompt
        prompt = build_extraction_prompt(invoice_template)
        assert "JSON" in prompt or "json" in prompt
        assert "【内容开始】" in prompt

    def test_prompt_with_non_invoice_template(self):
        from app.processor import build_extraction_prompt
        tpl = {
            "name": "送货单",
            "fields": [
                {"key": "company", "label": "公司名称", "section": "header"},
                {"key": "product", "label": "产品", "section": "item"},
            ]
        }
        prompt = build_extraction_prompt(tpl)
        assert "公司名称" in prompt
        assert "产品" in prompt


class TestParseSensitiveItems:
    def test_parses_sensitive_info_block(self):
        from app.processor import parse_sensitive_items
        raw = '{"sensitive_info": ["张三", "李四", "王五"]}'
        result = parse_sensitive_items(raw)
        assert len(result) >= 2
        assert "张三" in result

    def test_empty_input_returns_empty(self):
        from app.processor import parse_sensitive_items
        result = parse_sensitive_items("")
        assert result == []

    def test_non_json_text(self):
        from app.processor import parse_sensitive_items
        result = parse_sensitive_items("just some random text")
        assert isinstance(result, list)

    def test_multiple_blocks(self):
        from app.processor import parse_sensitive_items
        raw = '{"sensitive_info": ["A"]}\n{"sensitive_info": ["B", "C"]}'
        result = parse_sensitive_items(raw)
        assert len(result) >= 2
        assert "A" in result
        assert "B" in result


class TestMakePrompt:
    def test_first_pass_uses_first_prompt(self):
        from app.processor import make_prompt
        result = make_prompt(0)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_second_pass_uses_second_prompt(self):
        from app.processor import make_prompt
        result = make_prompt(1)
        assert isinstance(result, str)
        assert len(result) > 0


class TestFullRegexExtractionOnRealText:
    """核心回归: 用真实合同文本验证正则匹配能找到所有已知 PII"""

    def test_contract_finds_ids(self):
        from app.regex_rules import match_regex_sensitive
        text = open(
            os.path.join(os.path.dirname(__file__),
                         "..", "测试", "测试数据", "脱敏", "合同_含个人信息.txt"),
            encoding="utf-8"
        ).read()
        matches = match_regex_sensitive(text)
        sensitive_values = [m["item"] for m in matches]
        assert "110101199003071234" in sensitive_values
        assert "13800138001" in sensitive_values

    def test_contract_finds_emails(self):
        from app.regex_rules import match_regex_sensitive
        text = open(
            os.path.join(os.path.dirname(__file__),
                         "..", "测试", "测试数据", "脱敏", "合同_含个人信息.txt"),
            encoding="utf-8"
        ).read()
        matches = match_regex_sensitive(text)
        sensitive_values = [m["item"] for m in matches]
        assert "zhangsan@example.com" in sensitive_values
        assert "alice.wang@customer.com.cn" in sensitive_values

    def test_contract_finds_phone_numbers(self):
        from app.regex_rules import match_regex_sensitive
        text = open(
            os.path.join(os.path.dirname(__file__),
                         "..", "测试", "测试数据", "脱敏", "合同_含个人信息.txt"),
            encoding="utf-8"
        ).read()
        matches = match_regex_sensitive(text)
        sensitive_values = [m["item"] for m in matches]
        assert "13912345678" in sensitive_values
        assert "18612345678" in sensitive_values

    def test_contract_finds_bank_cards(self):
        from app.regex_rules import match_regex_sensitive
        text = open(
            os.path.join(os.path.dirname(__file__),
                         "..", "测试", "测试数据", "脱敏", "合同_含个人信息.txt"),
            encoding="utf-8"
        ).read()
        matches = match_regex_sensitive(text)
        sensitive_values = [m["item"] for m in matches]
        assert "6222021001123456789" in sensitive_values

    def test_contract_finds_ip_addresses(self):
        from app.regex_rules import match_regex_sensitive
        text = open(
            os.path.join(os.path.dirname(__file__),
                         "..", "测试", "测试数据", "脱敏", "合同_含个人信息.txt"),
            encoding="utf-8"
        ).read()
        matches = match_regex_sensitive(text)
        sensitive_values = [m["item"] for m in matches]
        assert "192.168.1.100" in sensitive_values

    def test_contract_finds_uscc(self):
        from app.regex_rules import match_regex_sensitive
        text = open(
            os.path.join(os.path.dirname(__file__),
                         "..", "测试", "测试数据", "脱敏", "合同_含个人信息.txt"),
            encoding="utf-8"
        ).read()
        matches = match_regex_sensitive(text)
        sensitive_values = [m["item"] for m in matches]
        assert "91110108MA01ABCD1E" in sensitive_values
        assert "91310115MA1K2EFGH3" in sensitive_values

    def test_contract_finds_urls(self):
        from app.regex_rules import match_regex_sensitive
        text = open(
            os.path.join(os.path.dirname(__file__),
                         "..", "测试", "测试数据", "脱敏", "合同_含个人信息.txt"),
            encoding="utf-8"
        ).read()
        matches = match_regex_sensitive(text)
        sensitive_values = [m["item"] for m in matches]
        assert "https://www.chuanglian-tech.com" in sensitive_values

    def test_contract_match_categories(self):
        from app.regex_rules import match_regex_sensitive
        text = open(
            os.path.join(os.path.dirname(__file__),
                         "..", "测试", "测试数据", "脱敏", "合同_含个人信息.txt"),
            encoding="utf-8"
        ).read()
        matches = match_regex_sensitive(text)
        categories = {m.get("category", "") for m in matches}
        assert "身份证号" in categories
        assert "银行卡号" in categories
        assert "手机号" in categories


class TestLargeFileRegex:
    """大文件正则匹配——验证不会因为文本长度扩散而漏掉正则"""

    def test_large_file_finds_all_pii_types(self):
        from app.regex_rules import match_regex_sensitive
        text = open(
            os.path.join(os.path.dirname(__file__),
                         "..", "测试", "测试数据", "脱敏", "合同_大文件.txt"),
            encoding="utf-8"
        ).read()
        assert len(text) > 10000
        matches = match_regex_sensitive(text)
        sensitive_values = [m["item"] for m in matches]
        assert any("91110108" in v for v in sensitive_values)
        assert any("@zhiyuan" in v for v in sensitive_values)
        assert any("192.168.10" in v for v in sensitive_values)
        assert len(matches) >= 30

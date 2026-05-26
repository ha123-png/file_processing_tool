import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app.regex_rules import match_regex_sensitive, clean_ocr_text, normalize_date_format

def _cats(matches):
    return [m["category"] for m in matches]

def _items(matches):
    return [m["item"] for m in matches]

def _count(text, cat):
    m = match_regex_sensitive(text)
    return sum(1 for x in m if x["category"] == cat)

def _any(text, cat):
    return _count(text, cat) > 0


class TestEmail:
    def test_standard(self):
        assert _any("联系 test@example.com", "邮箱")

    def test_multiple(self):
        r = match_regex_sensitive("a@b.com and x@y.org")
        assert len([x for x in r if x["category"] == "邮箱"]) == 2

    def test_no_match_on_incomplete(self):
        assert not _any("test@com", "邮箱")


class TestPhone:
    def test_standard(self):
        assert _any("手机 13812345678 联系", "手机号")

    def test_with_dash_not_matched(self):
        assert not _any("号码 138-1234-5678", "手机号")

    def test_too_long_not_phone(self):
        assert not _any("138123456789", "手机号")

    def test_not_inside_number(self):
        assert not _any("013812345678", "手机号")


class TestIDCard:
    def test_valid_18_digit(self):
        assert _any("身份证 110101199001011234", "身份证号")

    def test_valid_with_X(self):
        r = match_regex_sensitive("身份证 11010119900101123X")
        assert any(x["category"] == "身份证号" and "11010119900101123X" in x["item"]
                   for x in r)

    def test_invalid_all_digits_matches_number_code(self):
        r = match_regex_sensitive("编号 123456789012345678")
        assert not any(x["category"] == "身份证号" for x in r)

    def test_not_inside_longer_number(self):
        assert not _any("5110101199001011234", "身份证号")


class TestLicensePlate:
    def test_standard(self):
        assert _any("车牌 京A12345", "车牌号")

    def test_green_plate(self):
        assert _any("沪AD12345", "车牌号")

    def test_no_match(self):
        assert not _any("编号 ABC123", "车牌号")


class TestIPv4:
    def test_standard(self):
        assert _any("地址 192.168.1.1", "IPv4地址")

    def test_multiple(self):
        assert _count("10.0.0.1 and 172.16.0.1", "IPv4地址") == 2

    def test_invalid(self):
        assert not _any("999.999.999.999", "IPv4地址")

    def test_no_match(self):
        assert not _any("版本 1.2.3", "IPv4地址")


class TestURL:
    def test_http(self):
        assert _any("访问 https://example.com/path", "URL")

    def test_multiple(self):
        assert _count("http://a.com and https://b.org/p?q=1", "URL") == 2

    def test_no_match(self):
        assert not _any("ftp://example.com", "URL")


class TestUSCC:
    def test_valid(self):
        r = match_regex_sensitive("信用代码 91350100M000100Y43")
        assert any(x["category"] == "统一社会信用代码" and "91350100M000100Y43" == x["item"]
                   for x in r)

    def test_not_partial(self):
        r = match_regex_sensitive("代码 X91350100M000100Y43X")
        assert not any(x["category"] == "统一社会信用代码" for x in r)

    def test_not_inside_word(self):
        r = match_regex_sensitive("test91350100M000100Y43test")
        assert not any(x["category"] == "统一社会信用代码" for x in r)

    def test_invalid_chars(self):
        assert not _any("ABCDEFGHIJKLMNOPQR", "统一社会信用代码")


class TestLandline:
    def test_with_area_code(self):
        r = match_regex_sensitive("电话 010-12345678")
        assert any(x["category"] == "座机号" for x in r)

    def test_without_dash(self):
        assert _any("电话 02112345678", "座机号")

    def test_no_area_code_no_match(self):
        assert not _any("电话 12345678", "座机号")


class TestDate:
    def test_standard(self):
        assert _any("日期 2024-01-15", "日期")

    def test_chinese_format(self):
        assert _any("日期 2024年1月15日", "日期")

    def test_dot_format(self):
        assert _any("日期 2024.01.15", "日期")

    def test_partial_dates_not_matched(self):
        assert not _any("编号 2024.13.1", "日期")
        assert not _any("编号 20240101", "日期")

    def test_not_inside_number(self):
        assert not _any("12024-01-15", "日期")


class TestAmount:
    def test_yuan(self):
        assert _any("金额 123.45 元", "金额")

    def test_yen_prefix(self):
        assert _any("金额 ￥1,234.56", "金额")

    def test_usd(self):
        assert _any("金额 USD 100.00", "金额")

    def test_no_currency_no_match(self):
        assert not _any("数字 123.45", "金额")


class TestBankCard:
    def test_standard(self):
        assert _any("卡号 6222021234567890123", "银行卡号")

    def test_no_match_short(self):
        assert not _any("编号 123456789012345", "银行卡号")


class TestNumberCode:
    def test_long_code(self):
        assert _any("合同号 12345678", "纯数字编号")

    def test_long_code_in_text(self):
        assert _any("订单编号：87654321", "纯数字编号")

    def test_no_match_short(self):
        assert not _any("序号 12345", "纯数字编号")

    def test_leading_zero_matched_as_number_code(self):
        assert _any("编号 012345678", "纯数字编号")


class TestCleanOcrText:
    def test_preserves_numbered_list(self):
        text = "1. 第一条内容\n2. 第二条内容\n3. 第三条内容"
        result = clean_ocr_text(text)
        assert "1." in result
        assert "2." in result
        assert "3." in result

    def test_cleans_markdown_bold(self):
        result = clean_ocr_text("这是 **重要** 内容")
        assert "**" not in result
        assert "重要" in result

    def test_cleans_horizontal_rules(self):
        result = clean_ocr_text("---")
        assert "---" not in result

    def test_cleans_heading_markers(self):
        result = clean_ocr_text("## 标题文字")
        assert "##" not in result
        assert "标题文字" in result

    def test_strips_bullet_markers(self):
        result = clean_ocr_text("- 项目一\n* 项目二\n+ 项目三")
        assert "-" not in result
        assert "*" not in result
        assert "+" not in result


class TestNormalizeDateFormat:
    def test_standardize(self):
        result = normalize_date_format("日期 2024-01-15 和 2024/02/28", "YYYY-MM-DD")
        assert "2024-01-15" in result
        assert "2024-02-28" in result

    def test_chinese_format(self):
        result = normalize_date_format("2024年01月15日", "YYYY年MM月DD日")
        assert "2024年01月15日" in result

    def test_default_format(self):
        result = normalize_date_format("2024.01.15")
        assert "2024年01月15日" in result

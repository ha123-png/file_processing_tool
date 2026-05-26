import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from app.invoice_validator import validate_invoice_items, _safe_decimal, _safe_rate


class TestSafeDecimal:
    def test_normal(self):
        assert _safe_decimal("123.45") == Decimal("123.45")

    def test_int(self):
        assert _safe_decimal(100) == Decimal("100")

    def test_empty_string(self):
        assert _safe_decimal("") is None

    def test_none(self):
        assert _safe_decimal(None) is None

    def test_invalid(self):
        assert _safe_decimal("abc") is None


class TestSafeRate:
    def test_percent_13(self):
        assert _safe_rate("13%") == Decimal("0.13")

    def test_percent_6(self):
        assert _safe_rate("6%") == Decimal("0.06")

    def test_decimal_already(self):
        assert _safe_rate("0.13") == Decimal("0.13")

    def test_empty(self):
        assert _safe_rate("") is None

    def test_invalid(self):
        assert _safe_rate("abc%") is None


class TestR1:
    def test_pass_exact(self):
        items = [{"数量": "2", "单价": "1.50", "金额": "3.00"}]
        r = validate_invoice_items(items, {}, tolerance=0.02)
        assert r["status"] == "ok"

    def test_fail(self):
        items = [{"数量": "1.2", "单价": "3.5", "金额": "4.17"}]
        r = validate_invoice_items(items, {}, tolerance=0.02)
        assert r["status"] == "has_errors"

    def test_pass_within_tolerance(self):
        items = [{"数量": "1.2", "单价": "3.5", "金额": "4.20"}]
        r = validate_invoice_items(items, {}, tolerance=0.03)
        assert r["status"] == "ok"

    def test_disabled_rule_skips(self):
        items = [{"数量": "1.2", "单价": "3.5", "金额": "4.17"}]
        r = validate_invoice_items(items, {}, tolerance=0.02, rules={"R1": False, "R2": True, "R3": True})
        assert r["status"] == "ok"


class TestR2:
    def test_pass_decimal_rate(self):
        items = [{"金额": "100", "税率/征收率": "0.13", "税额": "13.00"}]
        r = validate_invoice_items(items, {}, tolerance=0.02)
        assert r["status"] == "ok"

    def test_pass_percent_rate(self):
        items = [{"金额": "100", "税率/征收率": "13%", "税额": "13.00"}]
        r = validate_invoice_items(items, {}, tolerance=0.02)
        assert r["status"] == "ok"

    def test_fail(self):
        items = [{"金额": "100", "税率/征收率": "0.13", "税额": "12.00"}]
        r = validate_invoice_items(items, {}, tolerance=0.02)
        assert r["status"] == "has_errors"


class TestR3:
    def test_pass(self):
        items = [{"金额": "100", "税额": "13.00"}, {"金额": "50", "税额": "6.50"}]
        header = {"价税合计": "169.50"}
        r = validate_invoice_items(items, header, tolerance=0.02)
        assert r["status"] == "ok"

    def test_fail(self):
        items = [{"金额": "100", "税额": "13.00"}]
        header = {"价税合计": "120.00"}
        r = validate_invoice_items(items, header, tolerance=0.02)
        assert r["status"] == "has_errors"


class TestRulesSkipped:
    def test_missing_qty_skips_r1(self):
        items = [{"数量": "", "单价": "1.5", "金额": "3.0", "税率/征收率": "13%", "税额": "0.39"}]
        r = validate_invoice_items(items, {"价税合计": "3.39"}, tolerance=0.02)
        assert r["rules_skipped"] == 1

    def test_two_lines_missing_qty_skips_r1_twice(self):
        items = [
            {"数量": "", "单价": "1.5", "金额": "3.0", "税率/征收率": "13%", "税额": "0.39"},
            {"数量": "", "单价": "2.0", "金额": "4.0", "税率/征收率": "13%", "税额": "0.52"}
        ]
        r = validate_invoice_items(items, {"价税合计": "7.91"}, tolerance=0.02)
        assert r["rules_skipped"] == 2

    def test_missing_amount_skips_r1_and_r2(self):
        items = [{"数量": "2", "单价": "1.5", "金额": "", "税率/征收率": "13%", "税额": ""}]
        r = validate_invoice_items(items, {"价税合计": "3.0"}, tolerance=0.02)
        assert r["rules_skipped"] == 2

    def test_two_lines_missing_amount_skips_r1_r2_per_line(self):
        items = [
            {"数量": "2", "单价": "1.5", "金额": "", "税率/征收率": "13%", "税额": ""},
            {"数量": "3", "单价": "2.0", "金额": "", "税率/征收率": "13%", "税额": ""}
        ]
        r = validate_invoice_items(items, {"价税合计": "10.0"}, tolerance=0.02)
        assert r["rules_skipped"] == 4

    def test_missing_header_skips_r3_once(self):
        items = [{"数量": "2", "单价": "1.5", "金额": "3.0", "税率/征收率": "13%", "税额": "0.39"}]
        r = validate_invoice_items(items, {}, tolerance=0.02)
        assert r["rules_skipped"] == 1

    def test_all_empty_not_counted(self):
        items = [{"数量": "", "单价": "", "金额": "", "税率/征收率": "", "税额": ""}]
        r = validate_invoice_items(items, {}, tolerance=0.02)
        assert r["skipped_empty"] == 1
        assert r["rules_skipped"] == 0

    def test_all_filled_no_skip(self):
        items = [{"数量": "2", "单价": "1.5", "金额": "3.0", "税率/征收率": "13%", "税额": "0.39"}]
        r = validate_invoice_items(items, {"价税合计": "3.39"}, tolerance=0.02)
        assert r["rules_skipped"] == 0
        assert r["status"] == "ok"


class TestEdgeCases:
    def test_empty_items_list(self):
        r = validate_invoice_items([], {"价税合计": "100"}, tolerance=0.02)
        assert r["status"] == "ok"

    def test_non_invoice_template_no_validation(self):
        from app.processor import _run_invoice_validation
        template = {"name": "送货单信息提取", "fields": []}
        parsed = {"header": {}, "items": [{"金额": "100"}]}
        r = _run_invoice_validation(template, parsed)
        assert r is None

    def test_invoice_template_triggers_validation(self):
        from app.processor import _run_invoice_validation
        template = {"name": "发票信息提取", "fields": []}
        parsed = {"header": {}, "items": []}
        r = _run_invoice_validation(template, parsed)
        assert r is not None

    def test_only_marks_amount_tax_total(self):
        items = [{"数量": "1", "单价": "2", "金额": "5"}]
        r = validate_invoice_items(items, {"价税合计": "10"}, tolerance=0.02)
        for e in r["errors"]:
            assert e["field"] in ("金额", "税额", "价税合计"), f"unexpected: {e['field']}"

    def test_tooltip_suggests_upstream_fields_r1(self):
        items = [{"数量": "1", "单价": "2", "金额": "5"}]
        r = validate_invoice_items(items, {}, tolerance=0.02)
        r1_errs = [e for e in r["errors"] if e["rule"] == "R1"]
        assert any("数量" in e["reason"] and "单价" in e["reason"] for e in r1_errs)

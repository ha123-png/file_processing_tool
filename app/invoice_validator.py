from decimal import Decimal, InvalidOperation


def validate_invoice_items(items, header, tolerance=0.02, rules=None):
    if rules is None:
        rules = {"R1": True, "R2": True, "R3": True}
    errors = []
    skipped_empty = 0
    rules_skipped = 0

    tol = Decimal(str(tolerance))
    header_total = None
    if header.get("价税合计"):
        try:
            header_total = Decimal(str(header["价税合计"]))
        except (InvalidOperation, ValueError):
            errors.append({
                "rule": "R_HEADER", "item_index": None, "field": "价税合计",
                "reason": "数据格式错误，无法校验"
            })

    sum_amount = Decimal("0")
    sum_tax = Decimal("0")

    for i, item in enumerate(items):
        qty = _safe_decimal(item.get("数量"))
        up = _safe_decimal(item.get("单价"))
        amt = _safe_decimal(item.get("金额"))
        rate = _safe_rate(item.get("税率/征收率"))
        tax = _safe_decimal(item.get("税额"))

        if amt is not None:
            sum_amount += amt
        if tax is not None:
            sum_tax += tax

        if _all_fields_empty(item):
            skipped_empty += 1
            continue

        if rules.get("R1", True):
            if qty is not None and up is not None and amt is not None:
                expected_r1 = qty * up
                diff_r1 = abs(expected_r1 - amt)
                if diff_r1 > tol:
                    errors.append({
                        "rule": "R1", "item_index": i, "field": "金额",
                        "expected": str(expected_r1), "actual": str(amt),
                        "reason": f"数量×单价={expected_r1} ≠ 金额={amt}，差{diff_r1}。可能数量/单价提取错误，建议比对数量、单价字段"
                    })
            else:
                rules_skipped += 1

        if rules.get("R2", True):
            if amt is not None and rate is not None and tax is not None:
                expected_r2 = amt * rate
                diff_r2 = abs(expected_r2 - tax)
                if diff_r2 > tol:
                    errors.append({
                        "rule": "R2", "item_index": i, "field": "税额",
                        "expected": str(expected_r2), "actual": str(tax),
                        "reason": f"金额×税率={expected_r2} ≠ 税额={tax}，差{diff_r2}。可能金额/税率提取错误，建议比对金额、税率字段"
                    })
            else:
                rules_skipped += 1

    if rules.get("R3", True):
        has_nonempty = any(not _all_fields_empty(item) for item in items)
        if has_nonempty:
            if header_total is None:
                rules_skipped += 1
            else:
                expected_r3 = sum_amount + sum_tax
                diff_r3 = abs(expected_r3 - header_total)
                if diff_r3 > tol:
                    errors.append({
                        "rule": "R3", "item_index": None, "field": "价税合计",
                        "expected": str(expected_r3), "actual": str(header_total),
                        "reason": f"Σ(金额+税额)={expected_r3} ≠ 价税合计={header_total}，差{diff_r3}。可能金额/税额有提取遗漏或重复，建议比对明细金额列"
                    })

    return {
        "errors": errors,
        "error_count": len(errors),
        "skipped_empty": skipped_empty,
        "rules_skipped": rules_skipped,
        "status": "ok" if not errors else "has_errors"
    }


def _all_fields_empty(item):
    for f in [item.get("数量"), item.get("单价"), item.get("金额"),
              item.get("税率/征收率"), item.get("税额")]:
        if f is not None and (not isinstance(f, str) or f.strip() != ""):
            return False
    return True


def _safe_decimal(val):
    if val is None:
        return None
    if isinstance(val, str) and val.strip() == "":
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _safe_rate(val):
    if val is None:
        return None
    if isinstance(val, str) and val.strip() == "":
        return None
    s = str(val).strip()
    if s.endswith("%"):
        try:
            num = Decimal(s[:-1])
            return num / Decimal("100")
        except (InvalidOperation, ValueError):
            return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None

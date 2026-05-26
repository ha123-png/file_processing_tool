import re

def preprocess_ocr_text(raw_text):
    lines = raw_text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        line = re.sub(r'\s+', ' ', line)
        if line:
            cleaned.append(line)
    return "\n".join(cleaned)

def flatten_json_to_text(obj, indent=0):
    prefix = "  " * indent
    parts = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, (dict, list)):
                parts.append(f"{prefix}{key}：")
                parts.append(flatten_json_to_text(value, indent + 1))
            else:
                parts.append(f"{prefix}{key}：{value}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                parts.append(flatten_json_to_text(item, indent))
            else:
                parts.append(f"{prefix}{i + 1}. {item}")
    else:
        parts.append(str(obj))
    return "\n".join(parts)

def ensure_plain_text(raw):
    import json as _json
    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            parsed = _json.loads(stripped)
            return flatten_json_to_text(parsed)
        except (_json.JSONDecodeError, Exception):
            pass
    return raw

def clean_ocr_text(text):
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r'^[-=*_]{3,}$', line):
            continue
        if re.match(r'^#+\s', line):
            line = re.sub(r'^#+\s*', '', line)
        if re.match(r'^[-*+]\s+', line):
            line = re.sub(r'^[-*+]\s+', '', line)
        if not line.strip():
            continue
        line = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
        line = re.sub(r'\*(.+?)\*', r'\1', line)
        line = re.sub(r'__(.+?)__', r'\1', line)
        line = re.sub(r'_(.+?)_', r'\1', line)
        line = re.sub(r'`(.+?)`', r'\1', line)
        line = line.strip()
        if not line:
            continue
        cleaned.append(line)
    result = "\n".join(cleaned)
    result = _strip_markers(result)
    result = _strip_meta_text(result)
    return result

def _strip_markers(s):
    start = s.find("【内容开始】")
    end = s.find("【内容结束】")
    if start != -1 and end != -1 and end > start:
        return s[start + 6:end].strip()
    return s

def _strip_meta_text(s):
    patterns = [
        r'^以下[是为][^。\n]{0,30}(?:提取|识别|内容|结构|信息|结果)[^{}\[\n]*\n?',
        r'^以上[是为][^。\n]{0,30}(?:提取|识别|内容|结构|信息|结果)[^{}\[\n]*\n?',
        r'^图片中[^。\n]{0,30}(?:提取|识别|内容|结构|信息|结果)[^{}\[\n]*\n?',
        r'^这是[^。\n]{0,15}(?:提取|识别|结果)[^{}\[\n]*\n?',
        r'^(?:注意|注)[：:]\s*(?:表格中的部分数据|图片中|此处|上述|以下|以上|当前|OCR).*\n?',
        r'^(?:注意|注)[：:]\s*[^。\n]*?(?:建议|可能|模糊|排版|格式|错误|缺失|不完整|校对).*\n?',
    ]
    for p in patterns:
        s = re.sub(p, '', s, flags=re.MULTILINE)
    return s.strip()

def _apply_date_format(year, month, day, fmt):
    result = fmt.replace('YYYY', str(year))
    result = result.replace('MM', f'{int(month):02d}')
    result = result.replace('DD', f'{int(day):02d}')
    return result

def normalize_date_format(text, date_format=None):
    if date_format is None:
        date_format = "YYYY年MM月DD日"
    text = re.sub(
        r'(\d{4})\s*[-/\.年]\s*(\d{1,2})\s*[-/\.月]\s*(\d{1,2})\s*日?',
        lambda m: _apply_date_format(m.group(1), m.group(2), m.group(3), date_format),
        text
    )
    return text

def normalize_spaced_numbers(text):
    for _ in range(5):
        new_text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)
        new_text = re.sub(r'([,，.])\s+(\d)', r'\1\2', new_text)
        if new_text == text:
            break
        text = new_text
    text = re.sub(r'(\d)\s+([个只台套项件张本份支辆艘栋幢间日用年月份秒时字])', r'\1\2', text)
    text = re.sub(r'(\d)\s+([万亿])([个只台套项件张本份支辆艘栋幢间把根颗粒片块条段位名次回届期卷册页])', r'\1\2\3', text)
    text = re.sub(r'(\d)\s+([万亿])\s+([个只台套项件张本份支辆艘栋幢间把根颗粒片块条段位名次回届期卷册页])', r'\1\2\3', text)
    text = re.sub(r'(\d)\s+个\s+(工作|自然|日历)(日)', r'\1个\2\3', text)
    return text

REGEX_PATTERNS_FULL = [
    ("邮箱", r'(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z])'),
    ("手机号", r'(?<!\d)1[3-9]\d{9}(?!\d)'),
    ("身份证号", r'(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)'),
    ("车牌号", r'[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤川青藏宁琼][A-Z][A-Z0-9]{4,5}[A-Z0-9挂学警港澳]'),
    ("IPv4地址", r'(?<!\d)(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)(?!\d)'),
    ("URL", r'https?://[^\s\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"<>\[\]{}|\\^`]+'),
    ("统一社会信用代码", r'(?<!\w)[0-9A-HJ-NPQRTUWXY]{18}(?!\w)'),
    ("座机号", r'(?<!\d)0\d{2,3}[- ]?\d{7,8}(?!\d)'),
    ("日期", r'(?<!\d)\d{4}\s*[-/\.年]\s*(?:0?[1-9]|1[0-2])\s*[-/\.月]\s*(?:0?[1-9]|[12]\d|3[01])\s*日?(?!\d)'),
    ("银行卡号", r'(?<!\d)\d{16,19}(?!\d)'),
    ("纯数字编号", r'(?<!\d)\d{8,12}(?!\d)'),
    ("金额", r'(?:¥|￥|CNY|USD|EUR|RMB)\s*\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*(?:元|万元|美元|美金|欧元|整)?'),
    ("中文大写金额", r'[零壹贰叁肆伍陆柒捌玖拾佰仟万亿两]+元[零壹贰叁肆伍陆柒捌玖拾佰仟万亿两角分]*整?'),
    ("百分比", r'(?<!\d)\d+(?:\.\d+)?\s*%'),
    ("中文百分比", r'百分之[一二三四五六七八九十百]+'),
    ("标签_人名", r'(?:法定代表人|联系人|授权代表|负责人|项目负责人|签字人|采购部经理|大客户经理|经理|委托代理人)[：:]\s*([^\n]{2,10})'),
    ("标签_公司名", r'(?:公司名称|单位名称|企业名称|开户名称)[：:]\s*([^\n]{4,30})'),
    ("标签_地址", r'(?:注册地址|通讯地址|地址|住所|办公地址|交货地点|签订地点|交货地)[：:]\s*([^\n]{5,50})'),
    ("标签_银行名", r'(?:开户银行|开户行)[：:]\s*([^\n]{4,30})'),
    ("标签_编号", r'(?:合同编号|合同号|项目编号|编号)[：:]\s*([A-Z0-9a-z-]{5,30})'),
    ("标签_产品名", r'产品[一二三四五六七八九十\d]+[：:]\s*([^\n]{2,40})'),
    ("标签_对方公司名", r'(?:甲方|乙方|出卖人|买受人|委托人|受托人)[（(][^）)]+[）)][：:]\s*([^\n]{4,30})'),
]

REGEX_PATTERNS_NUM = [
    ("金额", r'(?<!\d)(\d{1,3}(?:,\d{3})*(?:\.\d{2,3})?)(?=\s*[元万元角分](?!\s*[个只台套项件张本份支辆艘栋幢间把根颗粒片块条段位名次回届期卷册页]))'),
    ("金额_大额", r'(?<!\d)(\d{1,3}(?:,\d{3})*|\d{4,})(?:\.\d+)?(?=\s*[万亿元千百](?!\s*[个只台套项件张本份支辆艘栋幢间把根颗粒片块条段位名次回届期卷册页]))'),
    ("金额_小数万", r'(?<!\d)(\d+(?:\.\d+)?)(?=\s*[万亿元千百](?!\s*[个只台套项件张本份支辆艘栋幢间把根颗粒片块条段位名次回届期卷册页]))'),
    ("数量", r'(?<!\d)(\d{2,})(?=\s*[万亿]?\s*[个只台套项件张本份支辆艘栋幢间把根颗粒片块条段位名次回届期卷册页])'),
    ("日期_完整", r'(?<!\d)(\d{4}\s*[年\.\-/]\s*\d{1,2}\s*[月\.\-/]\s*\d{1,2}\s*日?)'),
    ("日期_年月", r'(?<!\d)(\d{4}\s*[年\.\-/]\s*\d{1,2}\s*月)'),
    ("日期_年", r'(?<!\d)(\d{4})(?=\s*年(?!\s*\d{1,2}\s*月))'),
    ("日期_天数", r'(?<!\d)(\d{1,2})(?=\s*[日天号])'),
    ("时间_月数", r'(?<!\d)(\d{1,2})(?=\s*个?\s*月)'),
    ("时间_年数", r'(?<!\d)(\d{1,3})(?=\s*个?\s*[周年])'),
    ("时间_小时", r'(?<!\d)(\d{1,4})(?=\s*个?\s*(?:小时|分钟|秒钟))'),
    ("时间_期限", r'(?<!\d)(\d{1,4})(?=\s*个?\s*(?:周|星期|季度|学期))'),
    ("数量_中文", r'(?<![一二三四五六七八九十百千万])[一二三四五六七八九十百千万两半]+(?=\s*[个只台套项件张本份支辆艘栋幢间日月年周天元角分秒时])'),
    ("范围", r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*[-~到至]\s*\d{1,3}(?:,\d{3})*(?:\.\d+)?'),
    ("复合日期", r'(?<!\d)(\d{1,2})(?=\s*个?\s*(?:工作日|自然日|日历日))'),
]

FLAGGED_PATTERNS = [
    ("括弧内容", r'[（(][^）)]{5,20}[）)]'),
    ("机构实体", r'[\u4e00-\u9fff]{2,10}(?:公司|学校|大学|学院|医院|单位|集团|中心|机构|部门|协会|商会|事务所|商行|分局|支行|营业部|代办处|办事处)'),
    ("品牌型号", r'[A-Z]{2,6}[- ]?\d{2,4}'),
]

def match_regex_sensitive(text):
    results = []
    seen = set()
    for category, pattern in REGEX_PATTERNS_FULL:
        for m in re.finditer(pattern, text):
            if m.lastindex and m.group(1):
                item = m.group(1).strip()
            else:
                item = m.group().strip()
            key = (item, m.start())
            if item and key not in seen:
                seen.add(key)
                results.append({"item": item, "category": category, "source": "regex"})
    for category, pattern in REGEX_PATTERNS_NUM:
        for m in re.finditer(pattern, text):
            if m.lastindex and m.group(1):
                item = m.group(1).strip()
                key = (item, m.start())
                if item and key not in seen:
                    seen.add(key)
                    results.append({"item": item, "category": category, "source": "regex"})
    results.sort(key=lambda x: len(x["item"]), reverse=True)
    return results

def flag_ambiguous(text):
    if not text:
        return text
    positions = []
    for category, pattern in FLAGGED_PATTERNS:
        for m in re.finditer(pattern, text):
            positions.append(m.end())
    if not positions:
        return text
    max_flags = max(5, len(text) // 100)
    positions = sorted(set(positions), reverse=True)
    if len(positions) > max_flags:
        cutoff = positions[max_flags - 1] if max_flags > 0 else positions[0]
        positions = [p for p in positions if p <= cutoff]
        positions = positions[:max_flags]
    result = text
    for pos in positions:
        if pos <= len(result):
            result = result[:pos] + "【⚠审】" + result[pos:]
    return result

def strip_ambiguity_markers(text):
    return text.replace("【⚠审】", "")

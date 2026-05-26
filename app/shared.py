import os
import json
import queue
import threading
import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from openpyxl.styles import Font, Border, Side, Alignment, PatternFill

class TaskStatus(Enum):
    WAITING = "waiting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class QueueMode(Enum):
    DESENSITIZE = "desensitize"
    EXTRACT = "extract"

class QueueState(Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    PAUSED = "paused"

@dataclass
class TaskState:
    task_id: str
    display_name: str
    original_name: str
    filepath: str
    mode: QueueMode
    status: TaskStatus = TaskStatus.WAITING

    is_chunk: bool = False
    parent_task_id: Optional[str] = None
    chunk_index: int = 0
    total_chunks: int = 1
    file_ext: str = ""

    checkpoint: str = ""
    checkpoint_data: Optional[dict] = None

    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    error_message: str = ""
    result: Optional[dict] = None

    def to_frontend(self):
        return {
            "task_id": self.task_id,
            "display_name": self.display_name,
            "original_name": self.original_name,
            "mode": self.mode.value,
            "status": self.status.value,
            "is_chunk": self.is_chunk,
            "parent_task_id": self.parent_task_id,
            "chunk_progress": f"{self.chunk_index}/{self.total_chunks}" if self.is_chunk else None,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "checkpoint": self.checkpoint,
        }

THIN_BORDER = Border(
    left=Side(style="thin", color="D1D5DB"),
    right=Side(style="thin", color="D1D5DB"),
    top=Side(style="thin", color="D1D5DB"),
    bottom=Side(style="thin", color="D1D5DB")
)

HEADER_FILL = PatternFill(start_color="059669", end_color="059669", fill_type="solid")
HEADER_FONT = Font(bold=True, size=11, color="FFFFFF")
CELL_ALIGNMENT = Alignment(horizontal="center", vertical="center")
HEADER_ALIGNMENT = Alignment(horizontal="center")

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)
OUTPUT_DIR = Path(config.get("desensitization", {}).get("output_dir", "output"))
if not OUTPUT_DIR.is_absolute():
    OUTPUT_DIR = BASE_DIR / OUTPUT_DIR
OUTPUT_DIR.mkdir(exist_ok=True)

CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

CONFIG_LOCK = threading.RLock()

def reload_config():
    global config
    with CONFIG_LOCK:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

def get_config_snapshot():
    with CONFIG_LOCK:
        return deepcopy(config)

def ensure_output_dir(cfg=None):
    global OUTPUT_DIR
    od = (cfg or config).get("desensitization", {}).get("output_dir", "output")
    p = Path(od)
    if not p.is_absolute():
        p = BASE_DIR / p
    p.mkdir(exist_ok=True)
    OUTPUT_DIR = p

def save_config(new_config):
    global config
    with CONFIG_LOCK:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(new_config, f, ensure_ascii=False, indent=2)
        config = new_config
        ensure_output_dir(new_config)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

TEXT_FORMATS = {".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".log", ".ini", ".cfg", ".conf", ".py", ".js", ".ts", ".html", ".css"}
DOCX_FORMATS = {".docx"}
IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".gif"}
PDF_FORMATS = {".pdf"}
ALL_SUPPORTED = TEXT_FORMATS | DOCX_FORMATS | IMAGE_FORMATS | PDF_FORMATS

task_queue = queue.Queue()
processing_event = threading.Event()
pause_event = threading.Event()
abort_event = threading.Event()
cancelled_task_ids = set()
CANCELLED_TASK_LOCK = threading.Lock()
sse_clients = []
sse_clients_lock = threading.Lock()
_interrupted_task = [None]
_INTERRUPTED_TASK_LOCK = threading.Lock()

def get_interrupted():
    with _INTERRUPTED_TASK_LOCK:
        return _interrupted_task[0]

def set_interrupted(task_id):
    with _INTERRUPTED_TASK_LOCK:
        _interrupted_task[0] = task_id

def clear_interrupted():
    with _INTERRUPTED_TASK_LOCK:
        _interrupted_task[0] = None


_file_row_map = {}
_FILE_ROW_LOCK = threading.RLock()

_file_item_count = {}

def send_sse(event, data):
    import json as _json
    msg = f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"
    with sse_clients_lock:
        dead = []
        for c in sse_clients:
            try:
                c.put_nowait(msg)
            except queue.Full:
                dead.append(c)
        for c in dead:
            sse_clients.remove(c)

_prompt_override = {}
_PROMPT_LOCK = threading.Lock()

PROMPT_FOOTER_FIRST = (
    "\n\n使用【内容开始】和【内容结束】标记包裹你的输出。\n"
    "严禁在标记之外输出任何文字（包括注意、注、建议、提示、校对等）。\n"
    "【⚠审】标记前20字符内若含公司名/品牌/人名/地址/产品名则纳入JSON。\n"
    "无标记的文本同样需地毯式搜索判断，不得遗漏任何敏感信息。\n"
    "输出中不要包含【⚠审】标记本身。\n"
    "格式：\n【内容开始】\n"
    '{"sensitive_info": ["敏感项1", "敏感项2"]}\n'
    "【内容结束】\n\n"
    "如果没有识别到任何敏感信息：\n"
    "【内容开始】\n{\"sensitive_info\": []}\n【内容结束】"
)

PROMPT_FOOTER_SECOND = (
    "\n\n只输出第一轮未识别到的敏感信息，不要重复。\n"
    "使用【内容开始】和【内容结束】标记包裹你的输出。\n"
    "严禁在标记之外输出任何文字。\n"
    "【⚠审】标记前20字符内若含敏感信息则纳入JSON。\n"
    "无标记文本同样需逐一审查，不得遗漏。\n"
    "输出中不要包含【⚠审】标记本身。\n"
    "格式：\n【内容开始】\n"
    '{"sensitive_info": ["漏掉的敏感项1"]}\n'
    "【内容结束】\n\n"
    "如果全部已覆盖没有遗漏：\n"
    "【内容开始】\n{\"sensitive_info\": []}\n【内容结束】"
)

_mode_override = None
_MODE_LOCK = threading.Lock()

def set_current_mode(mode):
    global _mode_override
    with _MODE_LOCK:
        _mode_override = mode

def get_current_mode():
    with _MODE_LOCK:
        if _mode_override:
            return _mode_override
    return get_config_snapshot().get("mode", "desensitize")

_excel_sheets = {}
_excel_active = None
_excel_labels = None
_EXCEL_LOCK = threading.RLock()

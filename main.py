from app.shared import (
    BASE_DIR, UPLOAD_DIR, CACHE_DIR,
    get_config_snapshot, logger,
    TEXT_FORMATS, DOCX_FORMATS, IMAGE_FORMATS, PDF_FORMATS
)
from app.llm_client import _get_llm_cfg
from app.routes import app
from app.queue_manager import start_worker, start_cleanup_scheduler
from app.task_store import init_db as init_task_store

if __name__ == "__main__":
    for f in CACHE_DIR.glob("*"):
        try:
            f.unlink()
        except OSError:
            pass
    logger.info(f"已清空缓存目录: {CACHE_DIR}")
    init_task_store()
    start_worker()
    start_cleanup_scheduler(interval=300, keep=20)
    cfg = get_config_snapshot()
    srv = cfg["server"]
    logger.info(f"文件脱敏服务启动中...")
    logger.info(f"支持的格式: 文本{TEXT_FORMATS} | Word{DOCX_FORMATS} | 图片{IMAGE_FORMATS} | PDF{PDF_FORMATS}")
    logger.info(f"文件大小限制: {app.config['MAX_CONTENT_LENGTH']//1024//1024}MB")
    llm_startup = _get_llm_cfg()
    logger.info(f"LLM Provider: {llm_startup.get('provider', 'lm_studio')} @ {llm_startup.get('base_url', '')} | Model: {llm_startup.get('model', '')} | Multimodal: {llm_startup.get('multimodal', True)}")
    logger.info(f"请打开浏览器访问 http://127.0.0.1:{srv['port']}")
    app.run(
        host=srv["host"],
        port=srv["port"],
        debug=srv["debug"],
        threaded=True
    )

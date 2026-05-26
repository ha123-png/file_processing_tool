import os

def split_pdf(filepath, original_name, upload_dir, task_id):
    try:
        import fitz
    except ImportError:
        return []
    doc = fitz.open(filepath)
    total_pages = len(doc)
    if total_pages < 5:
        doc.close()
        return []
    upload_dir = str(upload_dir)
    stem = _file_stem(original_name)
    chunks = []
    for page_idx in range(total_pages):
        page = doc[page_idx]
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        chunk_name = f"{stem}_p{page_idx+1:03d}（已脱敏待审查）.png"
        chunk_path = os.path.join(upload_dir, f"{task_id}_{chunk_name}")
        pix.save(str(chunk_path))
        chunks.append({
            "filepath": str(chunk_path),
            "display_name": f"{original_name} ({page_idx+1}/{total_pages})",
            "chunk_index": page_idx,
            "total_chunks": total_pages,
        })
    doc.close()
    return chunks

def split_text(filepath, original_name, upload_dir, task_id, chunk_size=2000):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return []
    if len(text) < 5000:
        return []
    upload_dir = str(upload_dir)
    lines = text.split("\n")
    chunks = []
    buf = ""
    for line in lines:
        buf += line + "\n"
        if len(buf) >= chunk_size:
            chunks.append(buf.strip())
            buf = ""
        if len(chunks) >= 100:
            break
    if buf.strip():
        chunks.append(buf.strip())
    total = len(chunks)
    if total < 2:
        return []
    stem = _file_stem(original_name)
    result = []
    for idx, chunk_text in enumerate(chunks):
        chunk_name = f"{stem}_p{idx+1:03d}（已脱敏待审查）.txt"
        chunk_path = os.path.join(upload_dir, f"{task_id}_{chunk_name}")
        with open(chunk_path, "w", encoding="utf-8") as f:
            f.write(chunk_text)
        result.append({
            "filepath": str(chunk_path),
            "display_name": f"{original_name} ({idx+1}/{total})",
            "chunk_index": idx,
            "total_chunks": total,
        })
    return result

def should_split(filepath, original_name):
    ext = os.path.splitext(original_name)[1].lower()
    if ext == '.pdf':
        try:
            import fitz
            doc = fitz.open(filepath)
            pages = len(doc)
            doc.close()
            return pages >= 5
        except Exception:
            return False
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return len(content) >= 5000
    except Exception:
        return False

def _file_stem(name):
    return os.path.splitext(os.path.basename(name))[0]

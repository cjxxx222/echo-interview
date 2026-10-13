import os
import uuid
from fastapi import UploadFile
from config import UPLOAD_DIR


def save_upload_file(file: UploadFile) -> tuple[str, str]:
    """保存上传文件，返回 (resume_id, file_path)"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    resume_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename or "")[1].lower()
    file_path = os.path.join(UPLOAD_DIR, f"{resume_id}{ext}")
    with open(file_path, "wb") as f:
        content = file.file.read()
        f.write(content)
    return resume_id, file_path


def extract_text(file_path: str) -> str:
    """根据文件后缀提取文本内容"""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    elif ext == ".docx":
        from docx import Document
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)

    elif ext in (".txt", ".md"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    else:
        raise ValueError(f"不支持的文件格式：{ext}")

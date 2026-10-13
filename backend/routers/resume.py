import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from services.file_service import save_upload_file, extract_text

router = APIRouter()

# 内存缓存：resume_id -> {resume_data, file_path, text}
_resume_cache: dict[str, dict] = {}


def _register_demo_resume() -> None:
    """把示例简历注册为固定 resume_id，setup 时传 "demo" 即可免上传体验全流程。"""
    from demo_data import DEMO_RESUME_TEXT
    _resume_cache["demo"] = {
        "resume_data": None,
        "file_path": "",
        "text": DEMO_RESUME_TEXT,
        "is_demo": True,
    }


_register_demo_resume()


@router.get("/demo")
async def demo_resume():
    """返回示例简历信息（虚构），供前端展示「用示例简历体验」入口。"""
    from demo_data import DEMO_RESUME_TEXT, DEMO_JD_TEXT
    return {"resume_id": "demo", "text_preview": DEMO_RESUME_TEXT[:200], "demo_jd": DEMO_JD_TEXT}


@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)):
    """上传简历文件，提取文本，立即返回（LLM解析在setup阶段进行）"""
    allowed_exts = {".pdf", ".docx", ".txt", ".md"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(400, f"不支持的文件格式，请上传：{', '.join(allowed_exts)}")

    # 保存文件
    resume_id, file_path = save_upload_file(file)

    # 提取文本（本地操作，很快）
    try:
        text = extract_text(file_path)
    except Exception as e:
        raise HTTPException(500, f"文本提取失败：{e}")

    # 缓存原始文本，LLM解析推迟到 /interview/setup 阶段
    _resume_cache[resume_id] = {
        "resume_data": None,
        "file_path": file_path,
        "text": text,
    }

    return {
        "resume_id": resume_id,
        "filename": file.filename,
        "text_preview": text[:200],
    }


@router.get("/{resume_id}")
async def get_resume(resume_id: str):
    if resume_id not in _resume_cache:
        raise HTTPException(404, "简历不存在")
    return _resume_cache[resume_id]["resume_data"].model_dump()


def get_resume_cache(resume_id: str) -> dict | None:
    return _resume_cache.get(resume_id)

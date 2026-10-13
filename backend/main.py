import os
from dotenv import load_dotenv
load_dotenv()  # 加载 .env 文件中的环境变量

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 确保上传和向量库目录存在
os.makedirs("./uploads", exist_ok=True)
os.makedirs("./vectorstore", exist_ok=True)

app = FastAPI(title="Echo Interview API", version="0.2.0")

# CORS配置：开发默认 localhost:5173，生产用 FRONTEND_ORIGIN 环境变量覆盖
_origins = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 面试会话状态（内存存储）+ 报告缓存（内存存储）
# 隐私策略：不落盘，30 天自动清理（见 data_retention.py）
interview_sessions: dict[str, dict] = {}

# 注册路由
from routers import resume, interview, report, calibration
app.include_router(resume.router, prefix="/api/resume", tags=["resume"])
app.include_router(interview.router, prefix="/api/interview", tags=["interview"])
app.include_router(report.router, prefix="/api/report", tags=["report"])
app.include_router(calibration.router, prefix="/api/calibration", tags=["calibration"])


@app.on_event("startup")
async def _start_retention_loop():
    """启动 30 天数据保留清理任务"""
    import asyncio
    from data_retention import retention_loop
    from routers.report import _report_cache

    def get_state():
        return interview_sessions, _report_cache

    asyncio.create_task(retention_loop(get_state))


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "message": "Echo Interview API is running"}


@app.get("/api/privacy")
async def privacy_policy():
    """隐私承诺：面试数据保留策略（前端报告页展示）"""
    from data_retention import RETENTION_DAYS
    return {
        "retention_days": RETENTION_DAYS,
        "statement": (
            f"面试对话与简历文本仅存于服务内存，不落盘；"
            f"超过 {RETENTION_DAYS} 天或服务重启后自动清除。"
            "示例简历为虚构内容，可用它完整体验而无需上传真实简历。"
        ),
    }


# ========== 同源前端服务（生产部署） ==========
# Docker 构建时 frontend/dist 由镜像内置；本地开发（未构建）时跳过。
# 所有 API 路由已注册在前，此处兜底其余路径 → SPA history 模式直接访问/刷新不 404
_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.isdir(_DIST):
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from fastapi import HTTPException

    _INDEX = os.path.join(_DIST, "index.html")
    if os.path.isdir(os.path.join(_DIST, "assets")):
        app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = os.path.join(_DIST, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_INDEX)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

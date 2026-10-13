# Echo Interview 单容器镜像：前端构建 → FastAPI 同源服务
# 为什么不用 Vercel/serverless：SSE 流式面试 + 内存会话状态，两者都被 serverless 模型克制
# 迁移路径：同一镜像可跑在 Railway / Render / 任意 VPS（docker run 即可）

# ---- stage 1: 构建前端 ----
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- stage 2: 运行时 ----
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV PORT=8000
EXPOSE 8000

# main.py 会把 ../frontend/dist 作为同源静态资源挂载（含 SPA fallback）
CMD ["sh", "-c", "cd backend && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]

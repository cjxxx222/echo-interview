import os

# ========== 大模型配置 ==========
# 模式：'ollama'（本地）或 'deepseek'（DeepSeek API）
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")

# Ollama 配置（本地模型）
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:7b"

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"  # DeepSeek-V3，速度快、质量高

# 当前使用的模型名称（各 Agent 统一读取）
LLM_MODEL = DEEPSEEK_MODEL if LLM_PROVIDER == "deepseek" else OLLAMA_MODEL

# ========== 其他配置 ==========
EMBEDDING_MODEL = "nomic-embed-text"
CHROMA_DIR = "./vectorstore"
UPLOAD_DIR = "./uploads"

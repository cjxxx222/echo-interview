# Echo Interview · 回响面试

> AI 模拟面试官：上传简历 → 多轮对话面试 → 结构化评分报告。**每条扣分都挂对话原文，评分体系经真人盲评校准。**

求职垂直场景的 C 端产品。差异不在功能——「多 Agent 拆分 + 评分报告」已是 2026 年主流架构；差异在两件事：

1. **可解释评分**：每个扣分点强制引用候选人回答的逐字原文（机器校验，模型编造引用会被重试/丢弃）
2. **可校准的评分**：评分维度经真人面试官背靠背盲评校准，人-人一致性作天花板，评测集与统计代码全部开源

**MVP 范围**：AI 产品经理方向的文字面试，无语音、无社区。隐私姿态：不提供真实简历也能用内置示例（虚构）体验全流程；面试数据仅存内存，30 天自动清除。

## 架构

```
简历/岗位 JD 输入
      ↓
setup_graph：简历解析 → JD 解析/生成 → 匹配分析 → 定制出题
      ↓
interview_graph：面试官 Agent（出题+追问，SSE 流式）
      ↓ 每轮回答
评估 Agent（四维度打分 + 扣分证据链）—— 盲评隔离：只看题目和回答，看不到面试官的任何信息
      ↓
报告 Agent（确定性聚合：维度加权 + 证据汇总 + 下一场练什么）
      ↓
结构化报告（维度分 + 每条扣分的原文引用 + 改进建议）
```

四维度与权重（`backend/dimensions.py` 单一来源）：结构 25% / 深度 30% / 岗位匹配 25% / 文字表达 20%。

## 本地运行

```bash
# 后端（Python 3.11+）
cd backend
pip install -r requirements.txt
cp .env.example .env   # 填入 DEEPSEEK_API_KEY
uvicorn main:app --port 8000 --reload

# 前端（Node 18+）
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173，点「用示例简历体验」可直接跑完整流程，无需上传真实简历。

## 测试

```bash
# 仓库根目录；31 个单测全部用 mock LLM，不需要 API key
python -m pytest tests/ -q
```

覆盖：证据链逐字校验（拒绝改写引用、禁止跨轮拼接/引用面试官、重试、丢弃）、统计函数正确性（Spearman 手算样例验证）、报告聚合、零方差场景、面试全流程集成（问答链进入最终评估）、数据保留清理。

## 校准实验（本项目核心资产）

真人盲评流程：导出盲评包（不含 AI 分）→ 评委用免登录表单页打分（`/api/calibration/form/{packet_id}`）→ 揭晓 AI 分 → 统计。

```bash
# 实验流程（以本地运行为例）
curl -X POST localhost:8000/api/calibration/export/<interview_id>   # 导盲评包
# 把 form_url 发给评委，收齐 5 人 × 8-10 场
curl -X POST localhost:8000/api/calibration/<packet_id>/reveal       # 逐包揭晓
curl localhost:8000/api/calibration/stats                            # 一致性报告
```

统计口径（`backend/calibration/stats.py`，纯 Python 无重依赖）：
- 人-人基线：全部真人评委两两 Spearman ρ 均值
- AI-人一致性：每维度 AI 分 vs 人类均分的 Spearman ρ + bootstrap 95% CI + 同向率
- 核心叙事口径：「AI 评分达到人类一致性的 XX%」（AI-人 ρ ÷ 人-人 ρ）
- badcase 矩阵：按人类均分分桶，看 AI 在哪段系统性偏严/偏松

设计纪律：小样本（n≈40）时一律报区间不裸报点估计；只使用可手工验证正确性的统计量。

## 部署

**架构决策：前后端打进同一个 Docker 镜像，由 FastAPI 同源服务。** 不上 Vercel/serverless，两条硬约束：① SSE 流式面试对话在 serverless 有执行时限与流式缓冲问题；② 会话状态在内存（隐私设计：不落盘），serverless 多实例会丢会话。同源部署同时做到零跨域配置、迁移零改动。

### 方案 A：Railway（0 成本起步，推荐）

1. 仓库推到 GitHub（`git remote add origin … && git push -u origin main`）
2. Railway → New Project → Deploy from GitHub repo → 自动识别 Dockerfile
3. 环境变量只配三个：

| 变量 | 值 |
|---|---|
| `DEEPSEEK_API_KEY` | 你的 DeepSeek key |
| `LLM_PROVIDER` | `deepseek` |
| `PORT` | `8000`（Railway 会自动注入，通常不用手动加） |

完成后 Railway 给一个域名，全部功能同源可用。

### 方案 B：任意 VPS（国内访问慢时迁这，约 ¥30-60/月）

```bash
docker build -t echo-interview .
docker run -d -p 80:8000 -e DEEPSEEK_API_KEY=sk-xxx echo-interview
```

推荐阿里云国际版/腾讯云**香港地域**轻量服务器：免 ICP 备案，国内访问快。镜像不变，只换运行环境——所谓的“迁移”就是这一条命令。

### 本地开发

本地前后端分离跑更高效：后端 `uvicorn main:app --port 8000`，前端 `npm run dev`（Vite 已配 `/api` 代理到 8000）。Docker 单容器只在部署时需要。

### 成本

一场完整面试（10 轮问答 + 评估 + 报告，双阶段评估约 12 次 LLM 调用）约 1~2 元（DeepSeek 计价）。Railway 免费额度跑 50 个种子用户足够；超出后约 $5/月。

## 目录

```
backend/
  agents/        各 Agent（evaluator 为差异化核心：维度打分+证据校验）
  calibration/   校准实验：rubric（行为锚定量表）/ export（盲评包）/ stats（统计）
  dimensions.py  四维度定义与权重（全项目单一来源）
  demo_data.py   虚构示例简历（隐私对策）
  data_retention.py 30 天清理任务
  graph/         面试编排（setup / interview）
  routers/       API 路由（interview / report / calibration / resume）
frontend/        Vue3 + Vite（报告页含证据链三段式卡片）
tests/           26 个单测（mock LLM，CI 无需 key）
```

## 致谢与许可证

基于 [tsgxiaode/interview-agent](https://github.com/tsgxiaode/interview-agent)（MIT）改造，保留了其多 Agent 编排与 SSE 面试流程；重写了评估/报告/评分体系并新增校准实验模块。MIT。

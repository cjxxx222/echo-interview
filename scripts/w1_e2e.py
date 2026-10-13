#!/usr/bin/env python
"""W1 验收：真调 LLM 端到端跑 N 场完整面试，产出评分质量基线数据。

前置条件：
  1) backend/.env 已填入真实 DEEPSEEK_API_KEY；
  2) 后端已在跑（uvicorn main:app --port 8000），且 key 生效。

用法：
  python scripts/w1_e2e.py --runs 3
  python scripts/w1_e2e.py --base-url http://localhost:8000 --runs 5 --out reports/w1_baseline.json

核心指标（本项目「把评分体系当产品验收」的落点）：
  - quote 合规率：报告里每条扣分证据的 quote 是否逐字落在候选人该题回答内（空白归一化后子串）
  - 维度分/综合分分布
  - 场次成本估算（按 LLM 调用次数粗估）
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from demo_data import DEMO_RESUME_TEXT  # noqa: E402

DEMO_RESUME_ID = "demo"

# 候选人模拟回答池：围绕示例简历（林晓雨 / AI 产品经理）构造的有信息量回答。
# 目的：给评估 Agent 真实可评的材料，测出「有细节 vs 空话」的区分度。
SELF_INTRO = (
    "面试官好，我是林晓雨，复旦信息管理与信息系统专业 2027 届。"
    "我在某互联网公司 AI 产品部做过 8 个月产品经理实习，主要做企业知识库问答产品。"
    "我负责过评测集建设，整理了 400 多条问答对，设计了 5 个维度评分标准，"
    "把问答准确率从 71% 推到 83%；另外每周跑一轮 badcase 归类，产出 20 多张 Prompt 迭代需求单。"
    "我比较擅长把模糊的产品问题拆成可量化的指标。"
)

ANSWER_POOL = [
    "这块我分三步做的。第一步先定口径，我把「准确率」拆成检索命中、答案忠实度、格式合规三个子指标，"
    "因为老板要的 83% 其实是综合值，不拆开根本不知道是哪一环拖后腿。第二步是建评测集，"
    "我拉了 400 多条真实用户问法，按业务场景分了 5 类，每类保证有覆盖长尾。"
    "第三步是回归机制，每周固定跑一遍，产出 badcase 归类表。这么做的取舍是前期慢，"
    "但后面每次 Prompt 改动都能立刻知道是涨是跌，不用靠感觉。",

    "我说个具体的 badcase。有次用户问「报销标准」，模型把差旅和日常费用混在一起答了，"
    "表面看是检索召回错了，但我归因后发现是 chunk 切分把一张费用表切断了。"
    "所以我提的需求不是改 Prompt，而是改文档切分策略，按表格结构切。"
    "这件事让我意识到，AI 产品的问题很多时候不在模型层，在数据层，得先定位再动手。",

    "竞品我重点看了三个。差异主要在两点：一是知识库的更新机制，有的产品要人工上传，"
    "有的支持自动同步，企业客户其实很在意这个；二是答案的可解释性，能不能给出引用出处。"
    "我判断我们的优势在垂直场景的评测深度，劣势在冷启动时知识库质量依赖客户自己填。"
    "所以我当时建议先做几个标杆行业的模板库，降低客户的启动成本。",

    "我做用户访谈的时候踩过坑。一开始我问「你觉得这个功能好不好用」，得到的全是客套话。"
    "后来改成让用户当着我的面完成一个真实任务，我只看他在哪一步卡住、停顿多久，"
    "这比问出来的靠谱得多。12 家企业访谈下来，我最大的收获是：用户说的需求和真实行为经常对不上，"
    "得看行为不能只听说法。",

    "二手书平台那个项目我主要负责需求分析和原型。最难的其实是撮合逻辑的需求定义，"
    "因为要平衡买家的匹配速度和卖家的成交率。我先用 Axure 出了 40 多页原型，"
    "跟两个开发同学对齐了四版才定稿。上线一学期促成 300 多单。"
    "这件事让我学会了怎么写一份开发真的能照着做的需求文档。",

    "我对 RAG 的理解是：它不是把文档丢给模型就完事。核心是三段——检索、增强、生成。"
    "检索决定了天花板，如果召回的 chunk 就是错的，后面 Prompt 写得再好也救不回来。"
    "我自己动手调过 embedding 和 top-k，发现 top-k 调大反而准确率下降，因为噪音进来了。"
    "所以我的判断是：RAG 产品的功夫一大半在检索侧的数据工程。",

    "数据分析我主要用 SQL 和 Excel。举个例，我做过一个留存分析，"
    "用 SQL 把用户按首周提问次数分层，发现提问 3 次以上的用户次周留存是提问 1 次的两倍多，"
    "所以推动产品加了一个新手引导，引导用户前三天多提问。"
    "我觉得数据分析的价值不在于出图，在于能推导出一个可执行的动作。",

    "如果让我重新做一次知识库问答项目，我会更早引入真人盲评。"
    "当时我们全靠自己的评测集，虽然指标在涨，但我心里没底——不知道这个分跟真人判断差多少。"
    "后来我意识到，自建评测集有自嗨风险，得有个外部标尺。"
    "这也是我为什么特别认同「评分体系本身也要被校准」这个思路。",

    "我理解这个岗位最核心的能力是「把不确定性变成可衡量」。"
    "AI 产品最大的特点是效果不稳定，传统产品那套需求文档不完全够用，"
    "你得先定义清楚「什么叫好」，再持续用数据逼近它。我实习时最花时间的不是写文档，"
    "是想清楚这个指标到底该怎么量。",

    "我觉得自己最大的短板是工程侧的深度不够，比如模型微调、分布式推理这些我只有概念。"
    "但我的优势是能跟算法同学对上话，知道 RAG 的瓶颈可能出在哪，"
    "所以提需求的时候不会提那种「让模型更聪明一点」的无效需求。",
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


# ---------- 候选人模拟（--simulate）：针对真实问题生成对口回答 ----------
def _load_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    env_path = Path(__file__).resolve().parent.parent / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


SIM_PROMPT = """你是求职者「林晓雨」，正在参加一场 AI 产品经理（校招）的文字面试。
下面你的简历与面试官的最新提问。请用第一人称、口语化地作答，长度 150~300 字。
要求：紧扣面试官的问题；结合简历里的具体经历给细节（数字、做法、取舍）；
可以适度暴露不足，不要写成完美范文；不要使用 Markdown 标记。

【你的简历】
{resume}

【面试官最新提问】
{question}

只输出你的回答正文。"""


def simulate_answer(question: str, api_key: str, model: str = "deepseek-chat") -> str:
    r = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": SIM_PROMPT.format(
                resume=DEMO_RESUME_TEXT, question=question)}],
            "temperature": 0.7,
        },
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _parse_sse(response) -> dict:
    """消费一条 SSE 流，返回 {'text': 面试官文本, 'status': 最后一次 status, 'done': bool}。"""
    text_parts: list[str] = []
    status = None
    done = False
    for raw in response.iter_lines(decode_unicode=True):
        if not raw:
            continue
        if not raw.startswith("data: "):
            continue
        payload = raw[len("data: "):]
        try:
            evt = json.loads(payload)
        except json.JSONDecodeError:
            continue
        t = evt.get("type")
        if t == "token":
            text_parts.append(evt.get("data", ""))
        elif t == "status":
            status = evt.get("data", {})
        elif t == "done":
            done = True
    return {"text": "".join(text_parts), "status": status, "done": done}


def _chat(base_url: str, interview_id: str, message: str) -> dict:
    r = requests.post(
        f"{base_url}/api/interview/chat",
        json={"interview_id": interview_id, "message": message},
        stream=True,
        timeout=300,
    )
    r.raise_for_status()
    return _parse_sse(r)


def run_one(base_url: str, idx: int, max_turns: int = 16, verbose: bool = True,
            simulate: bool = False, api_key: str = "") -> dict:
    t0 = time.time()
    # 1) setup
    setup = requests.post(
        f"{base_url}/api/interview/setup",
        json={
            "position_title": "AI 产品经理（校招）",
            "company": "示例科技",
            "jd_text": "",  # 留空 → 后端自动生成 JD
            "resume_id": DEMO_RESUME_ID,
        },
        timeout=300,
    )
    setup.raise_for_status()
    setup_data = setup.json()
    interview_id = setup_data["interview_id"]
    n_questions = setup_data["question_count"]
    if verbose:
        print(f"  [{idx}] setup ok: id={interview_id[:8]} 出题 {n_questions} 道")

    # 2) 开场
    opening = _chat(base_url, interview_id, "__START__")
    last_interviewer = opening.get("text") or ""

    # 3) 逐轮作答
    turns = 0
    answers = [SELF_INTRO] + ANSWER_POOL
    complete = False
    while turns < max_turns:
        if simulate and last_interviewer:
            try:
                answer = simulate_answer(last_interviewer, api_key)
            except Exception as e:
                print(f"      模拟作答失败，回退罐头回答：{e}")
                answer = answers[turns % len(answers)]
        else:
            answer = answers[turns % len(answers)]
        result = _chat(base_url, interview_id, answer)
        turns += 1
        last_interviewer = result.get("text") or last_interviewer
        status = result.get("status") or {}
        if verbose:
            print(f"      turn {turns:02d}: q_idx={status.get('question_index')}/{status.get('total')} "
                  f"complete={status.get('is_complete')}")
        if status.get("is_complete"):
            complete = True
            break

    # 4) 取报告（若面试未完，主动 /end 结算）
    report = None
    for _ in range(2):
        rr = requests.get(f"{base_url}/api/report/{interview_id}", timeout=300)
        if rr.status_code == 200:
            report = rr.json()
            break
        if rr.status_code == 400:  # 尚未结束
            requests.post(f"{base_url}/api/interview/{interview_id}/end", timeout=300)
            complete = True
            continue
        break

    duration = int(time.time() - t0)
    return {
        "run": idx,
        "interview_id": interview_id,
        "n_questions": n_questions,
        "turns": turns,
        "complete": complete,
        "duration_sec": duration,
        "report": report,
    }


def evaluate_run(run: dict) -> dict:
    """从单场结果里算指标：quote 合规率等。"""
    report = run.get("report")
    if not report:
        return {**{k: run[k] for k in ("run", "interview_id", "n_questions", "turns", "complete", "duration_sec")},
                "error": "无报告"}

    reviews = report.get("questionReviews", [])
    total_ev = 0
    valid_ev = 0
    invalid_samples = []
    for r in reviews:
        ans = _norm(r.get("userAnswer", ""))
        for e in r.get("evidence", []):
            total_ev += 1
            q = _norm(e.get("quote", ""))
            if q and q in ans:
                valid_ev += 1
            else:
                invalid_samples.append({"quote": e.get("quote"), "question": r.get("question", "")[:40]})

    return {
        "run": run["run"],
        "interview_id": run["interview_id"],
        "n_questions": run["n_questions"],
        "turns": run["turns"],
        "complete": run["complete"],
        "duration_sec": run["duration_sec"],
        "overall_score": report.get("overallScore"),
        "dimension_scores": report.get("dimensionScores"),
        "evidence_total": total_ev,
        "evidence_valid": valid_ev,
        "quote_compliance": round(valid_ev / total_ev, 4) if total_ev else None,
        "invalid_evidence_samples": invalid_samples[:5],
        "next_focus": report.get("nextFocus", []),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--max-turns", type=int, default=16)
    ap.add_argument("--simulate", action="store_true",
                    help="用 LLM 针对每道真实问题生成对口回答（默认用内置罐头回答池）")
    ap.add_argument("--model", default="deepseek-chat", help="模拟作答用的模型")
    ap.add_argument("--out", default="reports/w1_baseline.json")
    args = ap.parse_args()

    api_key = ""
    if args.simulate:
        api_key = _load_api_key()
        if not api_key or api_key.startswith("sk-在这里"):
            print("[simulate] 未找到有效 DEEPSEEK_API_KEY（环境变量或 backend/.env）")
            return 1
        print(f"[simulate] 已启用在线模拟作答（模型 {args.model}）")

    # 前置检查
    try:
        h = requests.get(f"{args.base_url}/api/health", timeout=10)
        print(f"[health] {h.status_code} {h.json()}")
    except Exception as e:
        print(f"[health] 后端不可达：{e}")
        return 1

    results = []
    for i in range(1, args.runs + 1):
        print(f"\n=== 第 {i}/{args.runs} 场 ===")
        try:
            run = run_one(args.base_url, i, max_turns=args.max_turns,
                          simulate=args.simulate, api_key=api_key)
            item = evaluate_run(run)
            item["report"] = run.get("report")  # 保留完整报告便于复盘
            results.append(item)
        except Exception as e:
            print(f"  场次 {i} 失败：{e}")
            results.append({"run": i, "error": str(e)})

    ok = [r for r in results if "error" not in r]
    comps = [r["quote_compliance"] for r in ok if r.get("quote_compliance") is not None]
    summary = {
        "base_url": args.base_url,
        "runs": args.runs,
        "runs_ok": len(ok),
        "quote_compliance_mean": round(statistics.mean(comps), 4) if comps else None,
        "quote_compliance_min": min(comps) if comps else None,
        "evidence_total": sum(r["evidence_total"] for r in ok),
        "evidence_invalid": sum(r["evidence_total"] - r["evidence_valid"] for r in ok),
        "overall_score_mean": round(statistics.mean([r["overall_score"] for r in ok]), 2)
        if all(r.get("overall_score") is not None for r in ok) and ok else None,
        "duration_mean_sec": round(statistics.mean([r["duration_sec"] for r in ok]), 1) if ok else None,
    }

    out = {"summary": summary, "runs": results}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n================ W1 基线汇总 ================")
    print(f"成功场次      : {summary['runs_ok']}/{summary['runs']}")
    print(f"quote 合规率  : 均值 {summary['quote_compliance_mean']} 最低 {summary['quote_compliance_min']}")
    print(f"证据总数/无效 : {summary['evidence_total']} / {summary['evidence_invalid']}")
    print(f"综合分均值    : {summary['overall_score_mean']}")
    print(f"单场耗时均值  : {summary['duration_mean_sec']}s")
    print(f"明细已写入    : {out_path}")
    for r in ok:
        print(f"  - run{r['run']}: 综合 {r['overall_score']} 维度 {r['dimension_scores']} "
              f"合规率 {r['quote_compliance']} ({r['evidence_valid']}/{r['evidence_total']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""评估 Agent —— 本项目的差异化核心。

设计原则：
1. 每个回答按四个维度独立打分（权重见 dimensions.py，全项目单一来源）。
2. 每条扣分必须附证据：evidence.quote 必须是候选人回答的逐字原文片段
   （从问答链中任意一轮候选人回答里原样复制，不许改写），由 validate_evidence
   机器校验，模型编造引用的会被重试或丢弃。这是「可解释评分」的硬约束。
3. 盲评隔离：本 Agent 的可见信息只有题目、考察意图、参考要点、JD 要求、问答链。
   看不到面试官的印象、provisional 评分或任何交互过程——防「流畅度污染」。
4. 问答链：一道题（含追问）聊完后，把完整问答链交给评估。深度维度的
   「被追问时能否给出细节」因此有了真正的观察对象——而不是只量第一轮回答。
"""
import re
from agents.llm_factory import get_llm
from dimensions import dimension_block_for_prompt
from models.schemas import Evidence, Question

MAX_EVIDENCE_RETRIES = 2

EVALUATE_PROMPT = """你是结构化面试评估员。请只依据给定信息，评估候选人对以下面试题（含面试官追问）的整体表现。
你不会看到面试官的任何主观印象——这是盲评，只凭问答内容本身判断。

题目：{question}
考察意图：{intent}
参考答案要点：{reference_points}
目标岗位要求：{jd_requirements}

面试问答记录（含追问，按时间顺序）：
{qa_chain}

评分维度（每个维度独立打 0-10 分）：
{dimension_block}

证据链规则（严格遵守）：
- 每一个扣分点都必须给证据：quote 字段必须从上面「面试问答记录」中候选人说的某一句话里
  逐字复制（原样复制，不许改写、不许翻译、不许拼接、不许跨轮拼句）
- 没有原文支撑的扣分不允许出现；只在心里想清但回答里没说的话，不能作为扣分证据
- 亮点可以写入 strengths，不强制配原文

只输出JSON，不要有其他文字，不要有markdown代码块标记：
{{
  "dimension_scores": {{"structure": 7, "depth": 5, "job_match": 6, "written_expression": 7}},
  "evidence": [
    {{"dimension": "depth", "quote": "候选人某一轮回答里的原文片段", "reason": "为什么这段原文导致扣分", "points_deducted": 2}}
  ],
  "strengths": ["亮点（可选，不强制配原文）"],
  "should_follow_up": false,
  "follow_up_direction": "若回答有明显遗漏或需要深挖的方向，写具体追问点；否则留空"
}}

打分口径：9-10 优秀（有细节有数据有取舍）；7-8 良好（覆盖主要要点）；5-6 有遗漏或较浅；
3-4 方向对但内容空或有错误；1-2 基本答不上来。没有证据支持的维度打高分要保守。"""

RETRY_HINT = """
上次输出中以下 quote 不是候选人回答的逐字原文子串，已被判无效：
{bad_quotes}
请重新输出 JSON，所有 quote 必须从「面试问答记录」中候选人说的某一句话里原样复制。"""


def _normalize(text: str) -> str:
    """证据校验用：去掉所有空白字符，避免纯排版差异误杀。"""
    return re.sub(r"\s+", "", text or "")


def to_qa_chain(answer_or_chain) -> list[dict]:
    """归一化输入：str → 单轮问答链；list → 原样返回。"""
    if isinstance(answer_or_chain, str):
        return [{"interviewer": "", "candidate": answer_or_chain}]
    return list(answer_or_chain or [])


def render_qa_chain(chain: list[dict]) -> str:
    """把问答链渲染进 Prompt。首轮提问记「面试官」，后续追问轮记「面试官（追问）」。"""
    lines = []
    for i, turn in enumerate(chain):
        role = "面试官" if i == 0 else "面试官（追问）"
        if turn.get("interviewer"):
            lines.append(f"{role}：{turn['interviewer']}")
        if turn.get("candidate"):
            lines.append(f"候选人：{turn['candidate']}")
    return "\n".join(lines) if lines else "（无记录）"


def validate_evidence(evidence: list[dict], chain) -> tuple[list[Evidence], list[str]]:
    """校验证据链：每条 quote 必须是问答链中某一轮候选人回答的逐字子串（空白归一化后）。

    不允许跨轮拼接：quote 必须完整落在单独的某一轮回答里。
    Returns: (valid_evidence, invalid_quotes)
    """
    from dimensions import DIMENSION_KEYS

    chain = to_qa_chain(chain)
    norm_turns = [_normalize(t.get("candidate", "")) for t in chain]
    valid: list[Evidence] = []
    invalid: list[str] = []

    for item in evidence:
        quote = (item.get("quote") or "").strip()
        nq = _normalize(quote)
        if not nq or not any(nq and nq in t for t in norm_turns):
            invalid.append(quote or "<空>")
            continue
        dim = item.get("dimension", "")
        if dim not in DIMENSION_KEYS:
            invalid.append(quote)
            continue
        valid.append(Evidence(
            dimension=dim,
            quote=quote,
            reason=item.get("reason", ""),
            points_deducted=int(item.get("points_deducted", 0) or 0),
        ))
    return valid, invalid


def _composite_score(dimension_scores: dict) -> int:
    """按维度权重计算综合分（0-10），权重来自 dimensions.py。"""
    from dimensions import DIMENSION_WEIGHTS

    total = 0.0
    for key, weight in DIMENSION_WEIGHTS.items():
        total += int(dimension_scores.get(key, 0)) * weight
    return int(round(total))


def _clamp_scores(scores) -> dict:
    return {
        k: max(0, min(10, int(v or 0)))
        for k, v in (scores or {}).items()
        if k in ("structure", "depth", "job_match", "written_expression")
    }


async def evaluate_answer(question: Question, answer_or_chain, jd_requirements: list[str] | None = None) -> dict:
    """评估一道题（含追问链）。返回原始 dict（由调用方构造 AnswerEvaluation）。

    证据链：最多重试 MAX_EVIDENCE_RETRIES 次让模型修正非法 quote；
    仍非法的证据项直接丢弃并打印日志——宁可少一条证据，不可留一条假引用。
    """
    from agents.utils import extract_json

    chain = to_qa_chain(answer_or_chain)

    llm = get_llm(temperature=0)
    base_prompt = EVALUATE_PROMPT.format(
        question=question.content,
        intent=question.intent,
        reference_points=", ".join(question.reference_points) or "无",
        jd_requirements=", ".join(jd_requirements) if jd_requirements else "未提供",
        qa_chain=render_qa_chain(chain),
        dimension_block=dimension_block_for_prompt(),
    )

    prompt = base_prompt
    last_data: dict | None = None
    bad_quotes: list[str] = []

    for attempt in range(MAX_EVIDENCE_RETRIES + 1):
        if attempt > 0 and bad_quotes:
            # 带修正提示重试：告诉模型上一轮哪些 quote 不是逐字原文
            prompt = base_prompt + RETRY_HINT.format(
                bad_quotes="\n".join(f"- {q}" for q in bad_quotes)
            )

        try:
            response = await llm.ainvoke(prompt)
            data = extract_json(response.content)
        except Exception as e:
            print(f"[evaluator] LLM 输出解析失败（第{attempt + 1}次）: {e}")
            continue

        last_data = data
        valid, bad_quotes = validate_evidence(data.get("evidence", []), chain)

        if not bad_quotes:
            data["evidence"] = [e.model_dump() for e in valid]
            data["dimension_scores"] = _clamp_scores(data.get("dimension_scores"))
            data["score"] = _composite_score(data["dimension_scores"])
            return data

        print(f"[evaluator] {len(bad_quotes)} 条证据引用非逐字原文，重试中: {bad_quotes}")

    if last_data is None:
        last_data = {"dimension_scores": {}, "evidence": [], "strengths": [],
                     "follow_up_direction": ""}

    # 重试耗尽：丢弃非法证据，保留合法部分与分数
    valid, _ = validate_evidence(last_data.get("evidence", []), chain)
    last_data["evidence"] = [e.model_dump() for e in valid]
    last_data["dimension_scores"] = _clamp_scores(last_data.get("dimension_scores"))
    last_data["score"] = _composite_score(last_data["dimension_scores"])
    return last_data

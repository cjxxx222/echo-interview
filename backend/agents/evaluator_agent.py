"""评估 Agent —— 本项目的差异化核心。

设计原则：
1. 每个回答按四个维度独立打分（权重见 dimensions.py，全项目单一来源）。
2. 每条扣分必须附证据：evidence.quote 必须是候选人回答的逐字原文子串，
   由 validate_evidence 机器校验，模型编造引用的会被重试或丢弃。
   这是「可解释评分」的硬约束，不依赖模型自觉。
3. 盲评隔离：本 Agent 的可见信息只有题目、考察意图、参考要点、JD 要求、候选人回答。
   看不到面试官的印象、评分或任何交互过程——防「流畅度污染」。
"""
import re
from agents.llm_factory import get_llm
from dimensions import dimension_block_for_prompt
from models.schemas import Evidence, Question

MAX_EVIDENCE_RETRIES = 2

EVALUATE_PROMPT = """你是结构化面试评估员。请只依据给定信息，评估候选人对以下面试题的回答。
你不会看到面试官的任何印象或互动过程——这是盲评，只凭回答内容本身判断。

题目：{question}
考察意图：{intent}
参考答案要点：{reference_points}
目标岗位要求：{jd_requirements}
候选人回答：{answer}

评分维度（每个维度独立打 0-10 分）：
{dimension_block}

证据链规则（严格遵守）：
- 每一个扣分点都必须给证据：quote 字段必须是「候选人回答」的逐字原文片段
  （从回答中原样复制，不许改写、不许翻译、不许拼接）
- 没有原文支撑的扣分不允许出现；只在心里想清楚但回答里没说的话，不能作为扣分证据
- 亮点可以写入 strengths，不强制配原文

只输出JSON，不要有其他文字，不要有markdown代码块标记：
{{
  "dimension_scores": {{"structure": 7, "depth": 5, "job_match": 6, "written_expression": 7}},
  "evidence": [
    {{"dimension": "depth", "quote": "回答中的原文片段", "reason": "为什么这段原文导致扣分", "points_deducted": 2}}
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
请重新输出 JSON，所有 quote 必须从「候选人回答」中原样复制。"""


def _normalize(text: str) -> str:
    """证据校验用：去掉所有空白字符，避免纯排版差异误杀。"""
    return re.sub(r"\s+", "", text or "")


def validate_evidence(evidence: list[dict], answer: str) -> tuple[list[Evidence], list[str]]:
    """校验证据链：每条 quote 必须是 answer 的逐字子串（空白归一化后）。

    Returns:
        (valid_evidence, invalid_quotes) —— 合法证据列表 + 被判无效的 quote 列表
    """
    from dimensions import DIMENSION_KEYS

    norm_answer = _normalize(answer)
    valid: list[Evidence] = []
    invalid: list[str] = []

    for item in evidence:
        quote = (item.get("quote") or "").strip()
        if not quote or not _normalize(quote) or _normalize(quote) not in norm_answer:
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


async def evaluate_answer(question: Question, answer: str, jd_requirements: list[str] | None = None) -> dict:
    """评估单个回答。返回原始 dict（由调用方构造 AnswerEvaluation）。

    证据链：最多重试 MAX_EVIDENCE_RETRIES 次让模型修正非法 quote；
    仍非法的证据项直接丢弃并打印日志——宁可少一条证据，不可留一条假引用。
    """
    from agents.utils import extract_json

    llm = get_llm(temperature=0)
    base_prompt = EVALUATE_PROMPT.format(
        question=question.content,
        intent=question.intent,
        reference_points=", ".join(question.reference_points) or "无",
        jd_requirements=", ".join(jd_requirements) if jd_requirements else "未提供",
        answer=answer,
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
        valid, bad_quotes = validate_evidence(data.get("evidence", []), answer)

        if not bad_quotes:
            data["evidence"] = [e.model_dump() for e in valid]
            data["dimension_scores"] = {
                k: max(0, min(10, int(v or 0)))
                for k, v in (data.get("dimension_scores") or {}).items()
            }
            data["score"] = _composite_score(data["dimension_scores"])
            return data

        print(f"[evaluator] {len(bad_quotes)} 条证据引用非逐字原文，重试中: {bad_quotes}")
        data["_dropped_evidence"] = bad_quotes

    if last_data is None:
        last_data = {"dimension_scores": {}, "evidence": [], "strengths": [],
                     "should_follow_up": False, "follow_up_direction": ""}

    # 重试耗尽：丢弃非法证据，保留合法部分与分数
    valid, _ = validate_evidence(last_data.get("evidence", []), answer)
    last_data["evidence"] = [e.model_dump() for e in valid]
    last_data["dimension_scores"] = {
        k: max(0, min(10, int(v or 0)))
        for k, v in (last_data.get("dimension_scores") or {}).items()
    }
    last_data["score"] = _composite_score(last_data["dimension_scores"])
    return last_data

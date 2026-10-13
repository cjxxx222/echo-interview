"""报告 Agent —— 结构化评分报告。

聚合逻辑（全部确定性计算，不靠 LLM 现编，保证可复现）：
1. 每题的维度分取该题评估结果；维度分 = 各题维度分的均值（0-10 → 0-100）
2. 总分 = 按 dimensions.py 权重加权
3. 证据链：所有题的 evidence 按维度汇总，报告里逐条展示 quote + 扣分理由
4. 「下一场练什么」：取最弱的两个维度，用 dimensions.focus_advice 生成建议
LLM 只负责：逐题的一句话点评与建议、总体建议（创意性内容）。
"""
import json
from datetime import datetime
from agents.llm_factory import get_llm
from dimensions import (
    DIMENSIONS, DIMENSION_KEYS, DIMENSION_LABELS, DIMENSION_WEIGHTS,
    dimension_block_for_prompt, focus_advice,
)
from models.schemas import InterviewReport, DimensionScores, QuestionReview
from agents.utils import extract_json

COMMENTARY_PROMPT = """你是面试评估专家。以下是结构化面试的逐题数据，请为每题写点评与改进建议，
并给出 3 条总体建议。只输出JSON，不要有其他文字，不要有markdown代码块标记：
{{
  "question_reviews": [
    {{"question_id": "q1", "suggestion": "针对这道题的具体改进建议"}}
  ],
  "overall_suggestions": ["总体建议1", "总体建议2", "总体建议3"]
}}

面试数据：
{data_json}"""


def _aggregate_dimension_scores(evaluations) -> DimensionScores:
    """各题维度分取均值，0-10 映射到 0-100。"""
    sums = {k: 0 for k in DIMENSION_KEYS}
    counts = {k: 0 for k in DIMENSION_KEYS}
    for ev in evaluations:
        for k, v in (ev.dimension_scores or {}).items():
            if k in sums:
                sums[k] += int(v)
                counts[k] += 1
    scores = {}
    for k in DIMENSION_KEYS:
        scores[k] = int(round(sums[k] * 10 / counts[k])) if counts[k] else 0
    return DimensionScores(**scores)


def _weighted_overall(dims: DimensionScores) -> int:
    total = sum(getattr(dims, k) * DIMENSION_WEIGHTS[k] for k in DIMENSION_KEYS)
    return int(round(total))


def _collect_evidence(evaluations) -> dict[str, list]:
    by_dim = {k: [] for k in DIMENSION_KEYS}
    for ev in evaluations:
        for e in ev.evidence:
            if e.dimension in by_dim:
                by_dim[e.dimension].append(e)
    return by_dim


def _next_focus(dims: DimensionScores) -> list[str]:
    ranked = sorted(DIMENSION_KEYS, key=lambda k: getattr(dims, k))
    return [focus_advice(k) for k in ranked[:2]]


async def generate_report(session: dict) -> InterviewReport:
    jd = session["jd"]
    evaluations = session.get("evaluations", [])
    start_time = session.get("start_time", 0)
    end_time = session.get("end_time", start_time)
    duration_sec = int(end_time - start_time)

    if not evaluations:
        return _minimal_report(session, duration_sec)

    dims = _aggregate_dimension_scores(evaluations)
    overall = _weighted_overall(dims)
    evidence_by_dim = _collect_evidence(evaluations)

    # ---- LLM 只负责创意性内容：逐题建议 + 总体建议 ----
    llm = get_llm(temperature=0.3)
    data = {}
    payload = [
        {
            "question_id": ev.question_id,
            "question": ev.question,
            "answer": ev.answer[:500],
            "dimension_scores": ev.dimension_scores,
            "evidence": [e.model_dump() for e in ev.evidence],
        }
        for ev in evaluations
    ]
    try:
        response = await llm.ainvoke(COMMENTARY_PROMPT.format(
            data_json=json.dumps(payload, ensure_ascii=False, indent=2)
        ))
        data = extract_json(response.content)
    except Exception as e:
        print(f"[report] LLM 点评生成失败，降级为模板建议: {e}")

    suggestions = {r.get("question_id"): r.get("suggestion", "")
                   for r in data.get("question_reviews", [])}
    overall_suggestions = data.get("overall_suggestions") or [
        f"{DIMENSION_LABELS[k]}维度相对薄弱，建议作为下一场练习重点" for k in
        sorted(DIMENSION_KEYS, key=lambda k: getattr(dims, k))[:2]
    ]

    # ---- 逐题回顾：原文截断 + 该题证据 ----
    reviews = []
    for ev in evaluations:
        reviews.append(QuestionReview(
            question_id=ev.question_id,
            question=ev.question,
            user_answer=ev.answer[:300] + ("…" if len(ev.answer) > 300 else ""),
            score=ev.score,
            strengths=ev.strengths,
            weaknesses=[f"{DIMENSION_LABELS.get(e.dimension, e.dimension)}：{e.reason}"
                        for e in ev.evidence] or ev.weaknesses,
            reference_answer="",  # 证据链取代了参考答案的展示位置
            suggestion=suggestions.get(ev.question_id, "结合证据链中的扣分点逐项改进"),
            evidence=list(ev.evidence),
        ))

    dim_text = "、".join(
        f"{DIMENSION_LABELS[d['key']]}{getattr(dims, d['key'])}" for d in DIMENSIONS
    )
    overall_suggestions = [f"维度得分：{dim_text}"] + overall_suggestions

    return InterviewReport(
        interview_id=session["id"],
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        duration=duration_sec,
        target_position=jd.title,
        overall_score=overall,
        dimension_scores=dims,
        question_reviews=reviews,
        overall_suggestions=overall_suggestions,
        study_plan=_next_focus(dims),
        next_focus=_next_focus(dims),
        evidence_by_dimension=evidence_by_dim,
    )


def _minimal_report(session: dict, duration_sec: int) -> InterviewReport:
    jd = session.get("jd")
    evaluations = session.get("evaluations", [])
    dims = _aggregate_dimension_scores(evaluations)
    reviews = [
        QuestionReview(
            question_id=e.question_id,
            question=e.question,
            user_answer=e.answer[:200],
            score=e.score,
            strengths=e.strengths,
            weaknesses=[],
            reference_answer="",
            suggestion="继续加强该方向的结构化表达",
            evidence=list(e.evidence),
        )
        for e in evaluations
    ]
    return InterviewReport(
        interview_id=session["id"],
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        duration=duration_sec,
        target_position=jd.title if jd else "未知岗位",
        overall_score=_weighted_overall(dims) if evaluations else 0,
        dimension_scores=dims,
        question_reviews=reviews,
        overall_suggestions=["评估数据不完整，建议重新完成一场面试"],
        study_plan=_next_focus(dims) if evaluations else [],
        next_focus=_next_focus(dims) if evaluations else [],
        evidence_by_dimension=_collect_evidence(evaluations),
    )

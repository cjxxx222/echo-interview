"""报告聚合逻辑测试（纯函数，不调 LLM）。"""
import json

import pytest

from models.schemas import AnswerEvaluation, Evidence, JDData
from agents.report_agent import _aggregate_dimension_scores, _weighted_overall, _next_focus
from dimensions import DIMENSION_WEIGHTS


def _ev(dim_scores: dict, evidence: list[Evidence] | None = None) -> AnswerEvaluation:
    return AnswerEvaluation(
        question_id="q1", question="题", answer="答", score=6,
        dimension_scores=dim_scores, evidence=evidence or [],
    )


class TestAggregation:
    def test_mean_and_scale(self):
        dims = _aggregate_dimension_scores([
            _ev({"structure": 8, "depth": 6, "job_match": 7, "written_expression": 5}),
            _ev({"structure": 6, "depth": 8, "job_match": 7, "written_expression": 7}),
        ])
        assert dims.structure == 70
        assert dims.depth == 70
        assert dims.job_match == 70
        assert dims.written_expression == 60

    def test_weighted_overall(self):
        # 手工验算：(70*0.25 + 70*0.30 + 70*0.25 + 60*0.20) = 68
        from models.schemas import DimensionScores
        dims = DimensionScores(structure=70, depth=70, job_match=70, written_expression=60)
        assert _weighted_overall(dims) == 68

    def test_next_focus_targets_weakest_two(self):
        from models.schemas import DimensionScores
        dims = DimensionScores(structure=90, depth=40, job_match=60, written_expression=70)
        focus = _next_focus(dims)
        assert len(focus) == 2
        assert "深挖" in focus[0]  # depth 最弱，advice 来自 dimensions.focus_advice


class _FakeCommentaryLLM:
    """报告 Agent 的 LLM 只产点评；返回空点评即可，重点验证聚合与原文保留。"""

    async def ainvoke(self, prompt: str):
        class _R:
            content = json.dumps(
                {"question_reviews": [], "overall_suggestions": ["保持练习"]},
                ensure_ascii=False,
            )
        return _R()


@pytest.mark.asyncio
async def test_report_preserves_full_answer_for_evidence(monkeypatch):
    """回归：报告不得截断 user_answer。

    证据链的 quote 是候选人回答的逐字原文；若报告把回答截断到 300 字，
    长回答里落在截断点之后的引文就无法在报告中找到核对，
    「每条扣分可对照原文」的核心承诺即被破坏。
    """
    monkeypatch.setattr("agents.report_agent.get_llm", lambda **kw: _FakeCommentaryLLM())

    tail_quote = "这是落在300字之后的原文片段"
    long_answer = "前" * 400 + tail_quote
    ev = AnswerEvaluation(
        question_id="q1", question="题", answer=long_answer, score=5,
        dimension_scores={"structure": 5, "depth": 5, "job_match": 5, "written_expression": 5},
        evidence=[Evidence(dimension="depth", quote=tail_quote, reason="r", points_deducted=2)],
    )
    session = {
        "id": "s1",
        "jd": JDData(title="AI 产品经理（校招）"),
        "evaluations": [ev],
        "start_time": 0,
        "end_time": 1,
    }

    from agents.report_agent import generate_report
    report = await generate_report(session)

    ua = report.question_reviews[0].user_answer
    assert ua == long_answer, "报告不应截断回答"
    assert tail_quote in ua, "证据引文必须能在报告展示的回答里找到"

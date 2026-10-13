"""报告聚合逻辑测试（纯函数，不调 LLM）。"""
from models.schemas import AnswerEvaluation, Evidence
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

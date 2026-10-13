"""证据链单元测试：quote 逐字校验 + 重试/丢弃逻辑。用 FakeLLM，不需要 API key。"""
import json
import pytest

from agents.evaluator_agent import validate_evidence, evaluate_answer, MAX_EVIDENCE_RETRIES
from models.schemas import Question


class FakeResponse:
    def __init__(self, content):
        self.content = content


class FakeLLM:
    """按脚本依次返回响应；超出脚本长度后重复最后一个。"""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls = 0

    async def ainvoke(self, prompt: str):
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return FakeResponse(self.responses[idx])


def _make_question():
    return Question(
        id="q1",
        phase="project",
        content="请介绍你做的评测集建设项目，具体怎么提升准确率的？",
        intent="考察数据驱动与细节深度",
        reference_points=["评测集规模", "维度设计", "准确率变化", "badcase 处理"],
    )


ANSWER = (
    "我负责评测集建设，整理了 400 多条问答对，设计了 5 个维度的评分标准。"
    "准确率从 71% 提升到 83%。"
    "另外我每周会做一轮 badcase 归类，推动 Prompt 迭代。"
)


def _good_eval_json():
    return json.dumps({
        "dimension_scores": {"structure": 7, "depth": 6, "job_match": 7, "written_expression": 7},
        "evidence": [
            {"dimension": "depth", "quote": "准确率从 71% 提升到 83%", "reason": "有量化结果但说不清78%到83%之间迭代了什么", "points_deducted": 2},
            {"dimension": "depth", "quote": "每周会做一轮 badcase 归类", "reason": "有动作但没讲归类标准和后续怎么改", "points_deducted": 1},
        ],
        "strengths": ["有量化数据"],
        "should_follow_up": False,
        "follow_up_direction": "",
    }, ensure_ascii=False)


class TestValidateEvidence:
    def test_verbatim_quote_accepted(self):
        valid, invalid = validate_evidence(
            [{"dimension": "depth", "quote": "整理了 400 多条问答对", "reason": "x", "points_deducted": 2}],
            ANSWER,
        )
        assert len(valid) == 1 and invalid == []
        assert valid[0].points_deducted == 2

    def test_whitespace_variant_accepted(self):
        """纯排版差异（换行/多空格）不应误杀——归一化后匹配。"""
        valid, invalid = validate_evidence(
            [{"dimension": "depth", "quote": "整理了  400 多条\n问答对", "reason": "x", "points_deducted": 1}],
            ANSWER,
        )
        assert len(valid) == 1 and invalid == []

    def test_paraphrase_rejected(self):
        """模型改写原文 = 编造引用，必须拒绝。"""
        valid, invalid = validate_evidence(
            [{"dimension": "depth", "quote": "我整理了数百条问答对", "reason": "x", "points_deducted": 1}],
            ANSWER,
        )
        assert valid == [] and len(invalid) == 1

    def test_quote_from_question_rejected(self):
        valid, invalid = validate_evidence(
            [{"dimension": "depth", "quote": "具体怎么提升准确率的", "reason": "x", "points_deducted": 1}],
            ANSWER,
        )
        assert valid == [] and len(invalid) == 1

    def test_unknown_dimension_rejected(self):
        valid, invalid = validate_evidence(
            [{"dimension": "communication", "quote": "整理了 400 多条问答对", "reason": "x", "points_deducted": 1}],
            ANSWER,
        )
        assert valid == []

    def test_empty_quote_rejected(self):
        valid, invalid = validate_evidence(
            [{"dimension": "depth", "quote": "", "reason": "x", "points_deducted": 1}],
            ANSWER,
        )
        assert valid == []


@pytest.mark.asyncio
class TestEvaluateAnswer:
    async def test_good_evidence_passes_first_try(self, monkeypatch):
        monkeypatch.setattr("agents.evaluator_agent.get_llm", lambda **kw: FakeLLM([_good_eval_json()]))
        result = await evaluate_answer(_make_question(), ANSWER, ["建设评测集"])
        assert len(result["evidence"]) == 2
        assert result["dimension_scores"]["structure"] == 7
        assert result["score"] == int(round(7 * .25 + 6 * .3 + 7 * .25 + 7 * .2))

    async def test_bad_quotes_trigger_retry_then_pass(self, monkeypatch):
        """第一轮编造引用 → 触发带修正提示的重试 → 第二轮合法。"""
        bad = json.dumps({
            "dimension_scores": {"structure": 7, "depth": 6, "job_match": 7, "written_expression": 7},
            "evidence": [{"dimension": "depth", "quote": "我做了很多数据优化", "reason": "编造的", "points_deducted": 3}],
        }, ensure_ascii=False)
        fake = FakeLLM([bad, _good_eval_json()])
        monkeypatch.setattr("agents.evaluator_agent.get_llm", lambda **kw: fake)
        result = await evaluate_answer(_make_question(), ANSWER, [])
        assert fake.calls == 2
        assert all("整理" not in e["quote"] or len(e["quote"]) > 3 for e in result["evidence"])
        assert len(result["evidence"]) == 2  # 伪造的被丢弃，第二轮的全保留

    async def test_persistent_bad_quotes_are_dropped(self, monkeypatch):
        """模型一直编造 → 重试耗尽后丢弃非法证据，保留合法部分，流程不崩。"""
        always_bad = json.dumps({
            "dimension_scores": {"structure": 8, "depth": 4, "job_match": 7, "written_expression": 6},
            "evidence": [
                {"dimension": "depth", "quote": "我做了很多数据优化", "reason": "编造", "points_deducted": 3},
                {"dimension": "structure", "quote": "设计了 5 个维度的评分标准", "reason": "合法引用", "points_deducted": 0},
            ],
        }, ensure_ascii=False)
        fake = FakeLLM([always_bad])
        monkeypatch.setattr("agents.evaluator_agent.get_llm", lambda **kw: fake)
        result = await evaluate_answer(_make_question(), ANSWER, [])
        assert fake.calls == MAX_EVIDENCE_RETRIES + 1
        assert len(result["evidence"]) == 1  # 只保留合法的
        assert result["evidence"][0]["quote"] == "设计了 5 个维度的评分标准"
        assert result["score"] > 0

    async def test_llm_failure_returns_safe_defaults(self, monkeypatch):
        class BrokenLLM:
            async def ainvoke(self, prompt):
                raise RuntimeError("API 挂了")

        monkeypatch.setattr("agents.evaluator_agent.get_llm", lambda **kw: BrokenLLM())
        result = await evaluate_answer(_make_question(), ANSWER, [])
        assert result["evidence"] == []
        assert result["dimension_scores"] == {}

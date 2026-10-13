"""题量上限测试：防止模型超额输出导致面试无法完成。"""
import json

import pytest

from models.schemas import ResumeData, JDData, MatchAnalysis


class _OverproducingLLM:
    """故意无视 6-8 道的要求，返回 n 道题。"""

    def __init__(self, n: int):
        self.n = n

    async def ainvoke(self, prompt: str):
        qs = [
            {"id": f"q{i}", "phase": "technical", "content": f"题{i}",
             "intent": "", "follow_ups": [], "reference_points": []}
            for i in range(1, self.n + 1)
        ]

        class _R:
            content = json.dumps({"questions": qs}, ensure_ascii=False)

        return _R()


@pytest.mark.asyncio
async def test_question_count_is_capped(monkeypatch):
    from agents import question_agent

    monkeypatch.setattr(question_agent, "get_llm", lambda **kw: _OverproducingLLM(14))
    questions = await question_agent.generate_questions(
        ResumeData(), JDData(title="AI 产品经理（校招）"), MatchAnalysis()
    )
    assert question_agent.MAX_QUESTIONS == 8
    assert len(questions) == 8, "模型超额输出时必须截断到硬上限"


@pytest.mark.asyncio
async def test_question_count_under_cap_untouched(monkeypatch):
    from agents import question_agent

    monkeypatch.setattr(question_agent, "get_llm", lambda **kw: _OverproducingLLM(6))
    questions = await question_agent.generate_questions(
        ResumeData(), JDData(title="AI 产品经理（校招）"), MatchAnalysis()
    )
    assert len(questions) == 6, "未超上限时不应截断"

"""面试流程集成测试：验证「完整问答链进入最终评估」的修复。

场景：一道题，第一轮回答 → 面试官追问 → 追问回答 → 面试官进入下一题。
断言：
1. 预备评估（驱动追问决策）发生了，但没有写入 evaluations
2. 定题评估发生在题目结束时，输入是完整问答链（prompt 里有两轮回答）
3. 最终入库的 evidence 可以引用追问轮回答的原文（修复前这是不可能的）
"""
import json
import pytest

from models.schemas import JDData, Question, InterviewPhase, ResumeData


class RoutingFakeLLM:
    """按 prompt 内容路由到不同角色的假响应。"""

    def __init__(self):
        self.prompts: list[str] = []

    async def ainvoke(self, prompt: str):
        self.prompts.append(prompt)
        if "结构化面试评估员" in prompt:
            # 区分预备评估（单轮）与定题评估（问答链）
            if "面试官（追问）" in prompt:
                return _resp(json.dumps({
                    "dimension_scores": {"structure": 7, "depth": 5, "job_match": 6, "written_expression": 7},
                    "evidence": [{"dimension": "depth", "quote": "每周做一轮 badcase 归类",
                                  "reason": "有动作但没讲归类标准", "points_deducted": 2}],
                    "strengths": ["有持续迭代动作"],
                    "follow_up_direction": "",
                }, ensure_ascii=False))
            return _resp(json.dumps({
                "dimension_scores": {"structure": 7, "depth": 6, "job_match": 6, "written_expression": 7},
                "evidence": [],
                "strengths": [],
                "should_follow_up": True,
                "follow_up_direction": "追问准确率提升的具体做法",
            }, ensure_ascii=False))
        if "以面试官的身份" in prompt:
            if "建议追问方向" in prompt:
                return _resp(json.dumps({"action": "follow_up", "response": "准确率具体是怎么提升的？能展开讲讲吗？", "evaluation_note": ""}, ensure_ascii=False))
            return _resp(json.dumps({"action": "next_question", "response": "好的，我们聊下一个话题。", "evaluation_note": ""}, ensure_ascii=False))
        if "请用友好、专业的语气开场" in prompt:
            return _resp("你好，欢迎参加面试。我们先从项目经历开始。")
        if "请为每题写点评" in prompt:
            return _resp(json.dumps({"question_reviews": [], "overall_suggestions": ["保持练习"]}, ensure_ascii=False))
        return _resp("{}")


def _resp(content):
    class R:
        pass
    r = R()
    r.content = content
    return r


def _make_session():
    q1 = Question(id="q1", phase=InterviewPhase.PROJECT, content="请介绍你的评测集建设项目",
                  intent="考察数据驱动", reference_points=["规模", "维度", "准确率"])
    return {
        "id": "s1",
        "resume": ResumeData(name="林晓雨", skills=["SQL", "Axure", "需求分析"],
                             projects=[{"name": "评测集建设", "role": "负责人",
                                        "tech_stack": ["Prompt"], "description": "评测集",
                                        "highlights": ["准确率71%→83%"]}]),
        "jd": JDData(title="AI 产品经理（校招）", requirements_must=["评测集建设"], responsibilities=["需求分析"]),
        "questions": [q1],
        "current_phase": InterviewPhase.OPENING,
        "current_question_index": 0,
        "conversation_history": [],
        "evaluations": [],
        "qa_chains": {},
        "evaluated_qids": [],
        "is_following_up": False,
        "is_complete": False,
        "start_time": 0,
    }


async def _drain(session, message):
    from graph.interview_graph import run_interview_turn
    chunks = []
    async for c in run_interview_turn(session, message):
        chunks.append(c)
    return chunks


@pytest.mark.asyncio
class TestInterviewFlow:
    async def test_full_chain_reaches_final_evaluation(self, monkeypatch):
        fake = RoutingFakeLLM()
        monkeypatch.setattr("agents.evaluator_agent.get_llm", lambda **kw: fake)
        monkeypatch.setattr("agents.interviewer_agent.get_llm", lambda **kw: fake)
        monkeypatch.setattr("agents.report_agent.get_llm", lambda **kw: fake)

        session = _make_session()

        await _drain(session, "__START__")

        # 第一轮回答：触发预备评估 → 面试官决定追问
        await _drain(session, "我整理了 400 多条问答对，设计了 5 个维度。")
        assert session["is_following_up"] is True
        # 预备评估没有入库
        assert len(session["evaluations"]) == 0

        # 追问回答 → 面试官进入下一题（本题结束）→ 定题评估
        await _drain(session, "每周做一轮 badcase 归类，推动 Prompt 迭代。")
        assert session["is_following_up"] is False
        assert len(session["evaluations"]) == 1

        ev = session["evaluations"][0]
        # 证据引用了追问轮的原文（修复前评估只看第一轮，这不可能发生）
        assert ev.evidence[0].quote == "每周做一轮 badcase 归类"
        # answer 字段含完整问答链的两轮回答
        assert "400 多条问答对" in ev.answer and "badcase" in ev.answer
        # 问答链记录了两轮
        assert len(session["qa_chains"]["q1"]) == 2
        assert session["evaluated_qids"] == ["q1"]
        # 面试结束 → 报告已生成
        assert session["is_complete"] is True

        # 定题评估的 prompt 里必须包含两轮回答
        eval_prompts = [p for p in fake.prompts if "结构化面试评估员" in p]
        chain_prompts = [p for p in eval_prompts if "面试官（追问）" in p]
        assert len(chain_prompts) == 1
        assert "400 多条问答对" in chain_prompts[0] and "badcase" in chain_prompts[0]

    async def test_finalize_is_idempotent(self, monkeypatch):
        fake = RoutingFakeLLM()
        monkeypatch.setattr("agents.evaluator_agent.get_llm", lambda **kw: fake)
        session = _make_session()
        session["qa_chains"]["q1"] = [{"interviewer": "请介绍项目", "candidate": "我整理了 400 多条问答对"}]
        from graph.interview_graph import finalize_question
        await finalize_question(session, session["questions"][0])
        await finalize_question(session, session["questions"][0])  # 第二次应跳过
        assert len(session["evaluations"]) == 1
        assert session["evaluated_qids"] == ["q1"]

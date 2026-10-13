"""面试对话图 —— SSE 流式输出。

评估时机设计（修复“深度维度没有观察对象”的问题）：
- 预备评估（provisional）：候选人回答一道题的第一轮回答时触发，仅用于面试官
  决定是否追问，**不写入 session["evaluations"]**（避免把半截回答当成最终分）。
- 定题评估（final）：一道题（含全部追问）结束后，把完整问答链交给评估 Agent，
  写入 evaluations——深度维度此时才有“被追问时的表现”可看。
"""
import json
import time
from models.schemas import InterviewPhase, ChatMessage, AnswerEvaluation, Evidence
from agents.evaluator_agent import evaluate_answer
from agents.interviewer_agent import get_opening_message, get_interviewer_response


def _ensure_session_state(session: dict) -> None:
    session.setdefault("qa_chains", {})        # question_id -> [{"interviewer","candidate"}]
    session.setdefault("evaluated_qids", [])   # 已入库评估的题目 id


def _last_interviewer_message(session: dict) -> str:
    for msg in reversed(session["conversation_history"]):
        if msg["role"] == "interviewer":
            return msg["content"]
    return ""


def _chain_answer_text(chain: list[dict]) -> str:
    return "\n".join(t.get("candidate", "") for t in chain if t.get("candidate"))


async def finalize_question(session: dict, question) -> None:
    """定题评估：完整问答链 → 评估 Agent → 入库。幂等（已评估过的题直接跳过）。"""
    _ensure_session_state(session)
    qid = question.id
    if qid in session["evaluated_qids"]:
        return
    chain = session["qa_chains"].get(qid) or []
    if not chain:
        return

    jd_reqs = session["jd"].requirements_must + session["jd"].responsibilities
    ev_data = await evaluate_answer(question, chain, jd_reqs)
    session["evaluations"].append(AnswerEvaluation(
        question_id=question.id,
        question=question.content,
        answer=_chain_answer_text(chain),
        score=ev_data.get("score", 5),
        strengths=ev_data.get("strengths", []),
        follow_up_direction=ev_data.get("follow_up_direction", ""),
        dimension_scores=ev_data.get("dimension_scores", {}),
        evidence=[Evidence(**e) for e in ev_data.get("evidence", [])],
    ))
    session["evaluated_qids"].append(qid)


async def finalize_pending_question(session: dict) -> None:
    """面试被提前结束时，结算当前进行中的题目（若有未入库的问答链）。"""
    _ensure_session_state(session)
    idx = session["current_question_index"]
    questions = session["questions"]
    if idx < len(questions):
        await finalize_question(session, questions[idx])


async def run_interview_turn(session: dict, candidate_message: str):
    """
    处理一轮对话，以 SSE 格式 yield 数据块。
    特殊消息 '__START__' 表示面试开始，生成开场白。
    """
    _ensure_session_state(session)
    questions = session["questions"]
    is_start = candidate_message == "__START__"

    # ---- 开场白 ----
    if is_start:
        # 幂等：页面刷新会再次发送 __START__。此时重放已有开场白，
        # 既不重复调用 LLM，也不往对话历史里重复插入（修复"刷新重复开场"）。
        existing_opening = next(
            (m["content"] for m in session["conversation_history"] if m["role"] == "interviewer"),
            "",
        )
        if existing_opening:
            opening_text = existing_opening
        else:
            try:
                opening_text = await get_opening_message(session)
            except Exception:
                opening_text = f"你好！欢迎参加本次面试。我们先从自我介绍开始，{questions[0].content if questions else '请做简单自我介绍'}。"

        # 流式输出开场白
        for char in opening_text:
            yield f"data: {json.dumps({'type': 'token', 'data': char}, ensure_ascii=False)}\n\n"

        # 仅首次开场才记录到会话历史
        if not existing_opening:
            session["conversation_history"].append({
                "role": "interviewer",
                "content": opening_text,
                "timestamp": time.time(),
            })

        # 发送状态：用会话的真实进度（刷新后能正确显示当前题号）
        yield f"data: {json.dumps({'type': 'status', 'data': {'phase': session['current_phase'].value, 'question_index': session['current_question_index'], 'total': len(questions), 'is_complete': session['is_complete']}})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # ---- 正常对话轮次 ----
    current_idx = session["current_question_index"]
    is_following_up = session["is_following_up"]

    # 记录候选人回答
    session["conversation_history"].append({
        "role": "candidate",
        "content": candidate_message,
        "timestamp": time.time(),
    })

    # 问答链缓冲：把本轮（面试官提问 → 候选人回答）挂到当前题目上
    current_q = questions[current_idx] if current_idx < len(questions) else None
    if current_q:
        session["qa_chains"].setdefault(current_q.id, []).append({
            "interviewer": _last_interviewer_message(session),
            "candidate": candidate_message,
        })

    # 预备评估：只在每道题的第一轮回答触发，仅用于面试官的追问决策，不写入 evaluations
    evaluation = None
    if current_q and not is_following_up:
        try:
            jd_reqs = session["jd"].requirements_must + session["jd"].responsibilities
            ev_data = await evaluate_answer(current_q, candidate_message, jd_reqs)
            evaluation = AnswerEvaluation(
                question_id=current_q.id,
                question=current_q.content,
                answer=candidate_message,
                score=ev_data.get("score", 5),
                strengths=ev_data.get("strengths", []),
                should_follow_up=ev_data.get("should_follow_up", False),
                follow_up_direction=ev_data.get("follow_up_direction", ""),
                dimension_scores=ev_data.get("dimension_scores", {}),
                evidence=[Evidence(**e) for e in ev_data.get("evidence", [])],
            )
        except Exception as e:
            print(f"预备评估异常: {e}")

    if evaluation is None:
        evaluation = AnswerEvaluation(
            question_id=current_q.id if current_q else "unknown",
            question=current_q.content if current_q else "",
            answer=candidate_message,
            score=6,
            should_follow_up=False,
        )

    # 获取面试官下一步回复
    try:
        action_data = await get_interviewer_response(session, candidate_message, evaluation)
    except Exception:
        action_data = {"action": "next_question", "response": "好的，我们继续下一个问题。", "evaluation_note": ""}

    action = action_data.get("action", "next_question")
    response_text = action_data.get("response", "")

    # 流式输出面试官回复
    for char in response_text:
        yield f"data: {json.dumps({'type': 'token', 'data': char}, ensure_ascii=False)}\n\n"

    # 记录面试官回复
    session["conversation_history"].append({
        "role": "interviewer",
        "content": response_text,
        "timestamp": time.time(),
    })

    # 更新会话状态
    if action == "follow_up":
        session["is_following_up"] = True
    elif action in ("next_question", "transition"):
        session["is_following_up"] = False
        # 定题评估：当前题（含追问）已结束，完整问答链入库
        if current_q:
            try:
                await finalize_question(session, current_q)
            except Exception as e:
                print(f"定题评估异常: {e}")
        next_idx = current_idx + 1
        if next_idx < len(questions):
            session["current_question_index"] = next_idx
            next_q = questions[next_idx]
            session["current_phase"] = next_q.phase
        else:
            session["is_complete"] = True
            session["end_time"] = time.time()
    elif action == "end":
        session["is_complete"] = True
        session["end_time"] = time.time()
        if current_q:
            try:
                await finalize_question(session, current_q)
            except Exception as e:
                print(f"定题评估异常: {e}")

    # 发送状态更新
    status_data = {
        "phase": session["current_phase"].value,
        "question_index": session["current_question_index"],
        "total": len(questions),
        "is_complete": session["is_complete"],
    }
    yield f"data: {json.dumps({'type': 'status', 'data': status_data})}\n\n"

    # 面试结束时自动生成报告
    if session["is_complete"]:
        try:
            from agents.report_agent import generate_report
            from routers.report import _report_cache
            report = await generate_report(session)
            _report_cache[session["id"]] = report
        except Exception as e:
            print(f"报告生成失败: {e}")

    yield f"data: {json.dumps({'type': 'done'})}\n\n"

"""面试对话 LangGraph — SSE流式输出"""
import json
import time
from models.schemas import InterviewPhase, ChatMessage, AnswerEvaluation, Evidence
from agents.evaluator_agent import evaluate_answer
from agents.interviewer_agent import get_opening_message, get_interviewer_response


async def run_interview_turn(session: dict, candidate_message: str):
    """
    处理一轮对话，以 SSE 格式 yield 数据块。
    特殊消息 '__START__' 表示面试开始，生成开场白。
    """
    questions = session["questions"]
    is_start = candidate_message == "__START__"

    # ---- 开场白 ----
    if is_start:
        try:
            opening_text = await get_opening_message(session)
        except Exception:
            opening_text = f"你好！欢迎参加本次面试。我们先从自我介绍开始，{questions[0].content if questions else '请做简单自我介绍'}。"

        # 流式输出开场白
        for char in opening_text:
            yield f"data: {json.dumps({'type': 'token', 'data': char}, ensure_ascii=False)}\n\n"

        # 记录到会话历史
        session["conversation_history"].append({
            "role": "interviewer",
            "content": opening_text,
            "timestamp": time.time(),
        })

        # 发送状态
        yield f"data: {json.dumps({'type': 'status', 'data': {'phase': session['current_phase'].value, 'question_index': 0, 'total': len(questions)}})}\n\n"
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

    # 评估当前回答（只在第一轮或不是追问时评估主题目）
    # 盲评隔离：评估只拿到题目+回答+JD要求，拿不到面试官的任何信息
    current_q = questions[current_idx] if current_idx < len(questions) else None
    evaluation = None
    if current_q and not is_following_up:
        try:
            from models.schemas import AnswerEvaluation
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
            session["evaluations"].append(evaluation)
        except Exception as e:
            print(f"评估异常: {e}")

    if evaluation is None:
        from models.schemas import AnswerEvaluation
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

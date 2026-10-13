import time
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from models.schemas import SetupRequest, SetupResponse, ChatRequest, InterviewStatus, InterviewPhase

router = APIRouter()

# 引用 main.py 中的全局会话字典（延迟导入避免循环）
def _get_sessions() -> dict:
    import main
    return main.interview_sessions


# =================== /setup ===================
@router.post("/setup", response_model=SetupResponse)
async def setup_interview(req: SetupRequest):
    from routers.resume import get_resume_cache
    from graph.setup_graph import run_setup

    cached = get_resume_cache(req.resume_id)
    if not cached:
        raise HTTPException(404, "简历不存在，请先上传简历")

    result = await run_setup(
        resume_text=cached["text"],
        position_title=req.position_title,
        company=req.company,
        jd_text=req.jd_text,
    )

    interview_id = result["interview_id"]
    sessions = _get_sessions()
    sessions[interview_id] = {
        "id": interview_id,
        "resume": result["resume"],
        "jd": result["jd"],
        "match_analysis": result["match_analysis"],
        "questions": result["questions"],
        "current_phase": InterviewPhase.OPENING,
        "current_question_index": 0,
        "conversation_history": [],
        "evaluations": [],
        "qa_chains": {},        # question_id -> 问答链（含追问）
        "evaluated_qids": [],   # 已入库评估的题目
        "is_following_up": False,
        "is_complete": False,
        "start_time": time.time(),
    }

    return SetupResponse(
        interview_id=interview_id,
        resume=result["resume"],
        jd=result["jd"],
        match_analysis=result["match_analysis"],
        question_count=len(result["questions"]),
    )


# =================== /chat (SSE) ===================
@router.post("/chat")
async def chat(req: ChatRequest):
    sessions = _get_sessions()
    session = sessions.get(req.interview_id)
    if not session:
        raise HTTPException(404, "面试会话不存在")

    from graph.interview_graph import run_interview_turn

    async def event_stream():
        async for chunk in run_interview_turn(session, req.message):
            yield chunk

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# =================== /status ===================
@router.get("/{interview_id}/status", response_model=InterviewStatus)
async def get_status(interview_id: str):
    sessions = _get_sessions()
    session = sessions.get(interview_id)
    if not session:
        raise HTTPException(404, "面试会话不存在")

    return InterviewStatus(
        interview_id=interview_id,
        current_phase=session["current_phase"],
        question_index=session["current_question_index"],
        total_questions=len(session["questions"]),
        is_complete=session["is_complete"],
    )


# =================== /end ===================
@router.post("/{interview_id}/end")
async def end_interview(interview_id: str):
    sessions = _get_sessions()
    session = sessions.get(interview_id)
    if not session:
        raise HTTPException(404, "面试会话不存在")

    session["is_complete"] = True
    session["end_time"] = time.time()

    # 结算当前进行中的题目（提前结束面试时，最后一道题的问答链还没入库）
    from graph.interview_graph import finalize_pending_question
    await finalize_pending_question(session)

    # 触发报告生成
    from agents.report_agent import generate_report
    report = await generate_report(session)

    from routers.report import _report_cache
    _report_cache[interview_id] = report

    return {"report_id": interview_id}

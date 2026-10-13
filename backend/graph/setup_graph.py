"""面试准备阶段工作流 — resume解析与JD处理并行执行，跳过LangGraph减少开销"""
import uuid
import asyncio
from agents.resume_agent import parse_resume
from agents.jd_agent import process_jd
from agents.match_agent import analyze_match
from agents.question_agent import generate_questions


async def run_setup(
    resume_text: str,
    position_title: str,
    company: str = "",
    jd_text: str = "",
) -> dict:
    print(f"[setup] 并行解析简历和JD: {position_title}")

    # Step 1: 并行执行（互不依赖，节省约50%时间）
    resume, jd = await asyncio.gather(
        parse_resume(resume_text),
        process_jd(position_title, company, jd_text),
    )
    print(f"[setup] 简历: {resume.name} | JD: {jd.title}")

    # Step 2: 匹配分析
    match_analysis = await analyze_match(resume, jd)
    print(f"[setup] 匹配完成，重点: {match_analysis.interview_focus[:2]}")

    # Step 3: 生成题库
    questions = await generate_questions(resume, jd, match_analysis)
    print(f"[setup] 题库就绪，共 {len(questions)} 道题")

    return {
        "interview_id": str(uuid.uuid4()),
        "resume": resume,
        "jd": jd,
        "match_analysis": match_analysis,
        "questions": questions,
    }

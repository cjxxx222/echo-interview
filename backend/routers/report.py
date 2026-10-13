from fastapi import APIRouter, HTTPException
from models.schemas import InterviewReport

router = APIRouter()

# 内存缓存：interview_id -> InterviewReport
_report_cache: dict[str, InterviewReport] = {}


@router.get("/{interview_id}")
async def get_report(interview_id: str):
    report = _report_cache.get(interview_id)
    if not report:
        # 尝试从会话生成
        import main
        session = main.interview_sessions.get(interview_id)
        if not session:
            raise HTTPException(404, "报告不存在")
        if not session.get("is_complete"):
            raise HTTPException(400, "面试尚未结束")
        from agents.report_agent import generate_report
        report = await generate_report(session)
        _report_cache[interview_id] = report

    # 转为前端期望的 camelCase
    return _to_camel(report)


@router.get("/")
async def list_reports():
    result = []
    for report in _report_cache.values():
        result.append({
            "id": report.interview_id,
            "targetPosition": report.target_position,
            "date": report.date,
            "overallScore": report.overall_score,
        })
    return result


def _evidence_to_camel(e) -> dict:
    return {
        "dimension": e.dimension,
        "quote": e.quote,
        "reason": e.reason,
        "pointsDeducted": e.points_deducted,
    }


def _to_camel(report: InterviewReport) -> dict:
    """将报告转换为 camelCase 格式返回给前端"""
    ds = report.dimension_scores
    return {
        "interviewId": report.interview_id,
        "date": report.date,
        "duration": report.duration,
        "targetPosition": report.target_position,
        "overallScore": report.overall_score,
        "dimensionScores": {
            "structure": ds.structure,
            "depth": ds.depth,
            "jobMatch": ds.job_match,
            "writtenExpression": ds.written_expression,
        },
        "questionReviews": [
            {
                "questionId": r.question_id,
                "question": r.question,
                "userAnswer": r.user_answer,
                "score": r.score,
                "strengths": r.strengths,
                "weaknesses": r.weaknesses,
                "referenceAnswer": r.reference_answer,
                "suggestion": r.suggestion,
                "evidence": [_evidence_to_camel(e) for e in r.evidence],
            }
            for r in report.question_reviews
        ],
        "overallSuggestions": report.overall_suggestions,
        "studyPlan": report.study_plan,
        "nextFocus": report.next_focus,
        "evidenceByDimension": {
            k: [_evidence_to_camel(e) for e in v]
            for k, v in report.evidence_by_dimension.items()
        },
    }

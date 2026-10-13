"""盲评包导出：把一个面试会话转为标准评测包。

两个版本：
- to_blind_packet：不含任何 AI 评分（真人盲评用，防锚定效应——真人一旦看到 AI 的分，打分会被带跑）
- reveal：盲评结束后才把 AI 维度分填进去，用于一致性计算
"""


def build_qa_pairs(session: dict) -> list[dict]:
    """从会话历史提取 (题目, 回答) 对。面试官的发言是问题，候选人的是回答。"""
    qa = []
    pending_q = None
    for msg in session.get("conversation_history", []):
        if msg["role"] == "interviewer":
            pending_q = {"question": msg["content"], "answer": ""}
        elif msg["role"] == "candidate" and pending_q is not None:
            pending_q["answer"] = msg["content"]
            qa.append(pending_q)
            pending_q = None
    return [q for q in qa if q["answer"].strip()]


def ai_dimension_scores(session: dict) -> dict[str, int]:
    """从会话的评估记录算 AI 的维度百分制得分（与报告口径一致）。"""
    from dimensions import DIMENSION_KEYS
    from agents.report_agent import _aggregate_dimension_scores

    return {k: getattr(_aggregate_dimension_scores(session.get("evaluations", [])), k)
            for k in DIMENSION_KEYS}


def to_blind_packet(session: dict, packet_id: str) -> dict:
    return {
        "packet_id": packet_id,
        "interview_id": session["id"],
        "created_at": session.get("end_time", 0),
        "target_position": session["jd"].title,
        "qa": build_qa_pairs(session),
        "ai_scores": {},
        "reviews": [],
        "revealed": False,
    }

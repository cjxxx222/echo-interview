import json
import re
from agents.llm_factory import get_llm
from models.schemas import ResumeData, Question, AnswerEvaluation, InterviewPhase

INTERVIEWER_SYSTEM_PROMPT = """你是一位资深的技术面试官，正在面试"{position_title}"岗位的候选人。

候选人背景：{resume_summary}

面试规则（严格遵守）：
1. 每次只说一段话，语气专业、友好、自然，像真人面试官一样交流
2. 根据回答质量决定下一步：
   - 回答优秀 → 简短肯定后进入下一题
   - 回答一般 → 追问一层深入细节
   - 回答较差 → 给予适当引导，不直接给答案
3. 追问最多1-2轮，不要过度纠缠一个问题
4. 适时做阶段过渡（如"好的，技术问题先到这里，我们聊聊你的项目经历"）
5. 不要在对话中暴露评分，不要说"这道题你得了X分"

当前状态：
- 面试阶段：{current_phase}
- 当前题目：{current_question}
- 已完成题数：{completed}/{total}
- 是否正在追问：{is_following_up}

对话历史：
{conversation_history}

候选人最新回答：
{candidate_answer}

请根据以上信息，以面试官的身份，决定下一步动作并输出回复。
只输出JSON，不要有其他文字，不要有markdown代码块标记：
{{
  "action": "follow_up 或 next_question 或 transition 或 end",
  "response": "面试官要说的话（自然语言，直接说出来的内容）",
  "evaluation_note": "内部简记"
}}"""

FIRST_QUESTION_PROMPT = """你是一位资深的技术面试官，正在开始面试"{position_title}"岗位的候选人。

请用友好、专业的语气开场，然后提出第一个问题：
{first_question}

只输出面试官要说的话，不要有其他内容。"""


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text)


def _build_resume_summary(resume: ResumeData) -> str:
    parts = []
    if resume.name:
        parts.append(f"姓名：{resume.name}")
    if resume.skills:
        parts.append(f"技能：{', '.join(resume.skills[:8])}")
    if resume.work_experience:
        exp = resume.work_experience[0]
        parts.append(f"最近工作：{exp.company} {exp.role}")
    if resume.projects:
        parts.append(f"项目：{resume.projects[0].name}")
    return "；".join(parts) if parts else resume.raw_text[:200]


def _build_history(history: list[dict]) -> str:
    lines = []
    for msg in history[-6:]:  # 只保留最近6条
        role = "面试官" if msg["role"] == "interviewer" else "候选人"
        lines.append(f"{role}：{msg['content'][:200]}")
    return "\n".join(lines) if lines else "（面试刚开始）"


async def get_opening_message(session: dict) -> str:
    """生成面试开场白和第一个问题"""
    llm = get_llm(temperature=0.7)
    questions = session["questions"]
    jd = session["jd"]
    first_q = questions[0].content if questions else "请做一个简短的自我介绍"

    prompt = FIRST_QUESTION_PROMPT.format(
        position_title=jd.title,
        first_question=first_q,
    )
    response = await llm.ainvoke(prompt)
    return response.content.strip()


async def get_interviewer_response(session: dict, candidate_answer: str, evaluation: AnswerEvaluation) -> dict:
    """根据回答和评估结果，生成面试官下一步回复"""
    llm = get_llm(temperature=0.7)

    questions: list[Question] = session["questions"]
    current_idx: int = session["current_question_index"]
    current_q = questions[current_idx] if current_idx < len(questions) else None
    is_following_up: bool = session["is_following_up"]
    jd = session["jd"]
    resume: ResumeData = session["resume"]

    # 决定下一题是什么
    next_idx = current_idx + 1
    next_q = questions[next_idx] if next_idx < len(questions) else None

    # 构建追问方向提示
    follow_up_hint = ""
    if evaluation.should_follow_up and not is_following_up and evaluation.follow_up_direction:
        follow_up_hint = f"（建议追问方向：{evaluation.follow_up_direction}）"
    elif is_following_up and next_q:
        follow_up_hint = f"（追问已完成，下一题：{next_q.content}）"

    prompt = INTERVIEWER_SYSTEM_PROMPT.format(
        position_title=jd.title,
        resume_summary=_build_resume_summary(resume),
        current_phase=session["current_phase"].value,
        current_question=current_q.content if current_q else "（所有题目已完成）",
        completed=current_idx,
        total=len(questions),
        is_following_up="是" if is_following_up else "否",
        conversation_history=_build_history(session["conversation_history"]),
        candidate_answer=candidate_answer + follow_up_hint,
    )

    for _ in range(2):
        try:
            response = await llm.ainvoke(prompt)
            data = extract_json(response.content)
            return data
        except Exception as e:
            print(f"面试官响应生成失败: {e}")
            continue

    # 兜底
    if next_q:
        return {"action": "next_question", "response": f"好的，我们继续。{next_q.content}", "evaluation_note": ""}
    else:
        return {"action": "end", "response": "非常感谢你今天的面试！整体表现不错，我们会尽快给你反馈。", "evaluation_note": ""}

import json
import re
from agents.llm_factory import get_llm
from models.schemas import ResumeData, JDData, MatchAnalysis, Question, InterviewPhase

QUESTION_GEN_PROMPT = """你是资深技术面试官。请根据以下信息，为候选人生成一套完整的面试题。

目标岗位：{position_title}
候选人技能：{skills}
匹配的技能：{matched_skills}
薄弱环节：{weak_points}
面试重点方向：{interview_focus}
候选人项目经历：{project_summary}

请生成10-15道面试题，覆盖5个阶段，只输出JSON，不要有其他文字，不要有markdown代码块标记：
{{
  "questions": [
    {{
      "id": "q1",
      "phase": "opening",
      "content": "请做一个简短的自我介绍",
      "intent": "了解候选人背景和表达能力",
      "follow_ups": ["你为什么选择这个方向？"],
      "reference_points": ["基本信息", "核心经历", "求职意向"]
    }}
  ]
}}

要求：
- opening阶段：1-2道（自我介绍类）
- technical阶段：3-5道（技术基础，结合岗位要求和候选人技能）
- project阶段：2-3道（针对候选人简历中的具体项目）
- scenario阶段：1-2道（场景设计题，贴近目标岗位实际工作）
- open阶段：1-2道（开放题）
- 每道题都要有考察意图和参考答案要点"""


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text)


async def generate_questions(
    resume: ResumeData,
    jd: JDData,
    match: MatchAnalysis,
) -> list[Question]:
    llm = get_llm(temperature=0.5)

    project_summary = ""
    if resume.projects:
        project_summary = "; ".join(
            f"{p.name}（{', '.join(p.tech_stack)}）" for p in resume.projects[:3]
        )

    prompt = QUESTION_GEN_PROMPT.format(
        position_title=jd.title,
        skills=", ".join(resume.skills[:10]),
        matched_skills=", ".join(match.matched_skills[:6]),
        weak_points=", ".join(match.weak_points[:4]),
        interview_focus=", ".join(match.interview_focus[:6]),
        project_summary=project_summary or "无项目经历",
    )

    for _ in range(2):
        try:
            response = await llm.ainvoke(prompt)
            data = extract_json(response.content)
            questions = []
            for q in data.get("questions", []):
                try:
                    questions.append(Question(
                        id=q["id"],
                        phase=InterviewPhase(q["phase"]),
                        content=q["content"],
                        intent=q.get("intent", ""),
                        follow_ups=q.get("follow_ups", []),
                        reference_points=q.get("reference_points", []),
                    ))
                except Exception:
                    continue
            if questions:
                return questions
        except Exception as e:
            print(f"题目生成失败: {e}")
            continue

    # 最小兜底题库
    return [
        Question(id="q1", phase=InterviewPhase.OPENING, content="请做一个简短的自我介绍", intent="了解候选人背景"),
        Question(id="q2", phase=InterviewPhase.TECHNICAL, content=f"请介绍一下你在{jd.title}方面最熟悉的技术栈", intent="了解技术深度"),
        Question(id="q3", phase=InterviewPhase.OPEN, content="你最近有在关注哪些新技术或行业动态？", intent="了解学习能力"),
    ]

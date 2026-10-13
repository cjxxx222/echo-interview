import json
import re
from agents.llm_factory import get_llm
from models.schemas import ResumeData, JDData, MatchAnalysis

MATCH_PROMPT = """你是面试策略分析师。请对比以下候选人简历和目标岗位要求，给出匹配分析。

候选人简历摘要：
{resume_summary}

目标岗位要求：
{jd_summary}

只输出JSON，不要有其他文字，不要有markdown代码块标记：
{{
  "matched_skills": ["简历中匹配岗位要求的技能"],
  "missing_skills": ["岗位要求但简历中缺少的技能"],
  "strong_points": ["候选人的突出优势，面试中应重点展现"],
  "weak_points": ["可能被面试官追问的薄弱环节"],
  "interview_focus": ["建议面试重点考察的5-8个方向"]
}}"""


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
        parts.append(f"技能：{', '.join(resume.skills)}")
    if resume.work_experience:
        exp = resume.work_experience[0]
        parts.append(f"最近工作：{exp.company} - {exp.role}")
    if resume.projects:
        names = [p.name for p in resume.projects]
        parts.append(f"项目经历：{', '.join(names)}")
    if resume.strengths:
        parts.append(f"优势：{', '.join(resume.strengths)}")
    # fallback to raw text snippet
    if not parts and resume.raw_text:
        parts.append(resume.raw_text[:500])
    return "\n".join(parts)


def _build_jd_summary(jd: JDData) -> str:
    parts = [f"岗位：{jd.title}"]
    if jd.requirements_must:
        parts.append(f"必须技能：{', '.join(jd.requirements_must)}")
    if jd.requirements_plus:
        parts.append(f"加分项：{', '.join(jd.requirements_plus)}")
    if jd.keywords:
        parts.append(f"关键词：{', '.join(jd.keywords)}")
    return "\n".join(parts)


async def analyze_match(resume: ResumeData, jd: JDData) -> MatchAnalysis:
    llm = get_llm(temperature=0)
    prompt = MATCH_PROMPT.format(
        resume_summary=_build_resume_summary(resume),
        jd_summary=_build_jd_summary(jd),
    )

    for _ in range(2):
        try:
            response = await llm.ainvoke(prompt)
            data = extract_json(response.content)
            return MatchAnalysis(**data)
        except Exception as e:
            print(f"匹配分析失败: {e}")
            continue

    return MatchAnalysis(
        matched_skills=resume.skills[:3],
        interview_focus=[jd.title + "核心技能"],
    )

import json
import re
from agents.llm_factory import get_llm
from models.schemas import JDData, JDSource

JD_GENERATE_PROMPT = """你是一个资深的技术招聘专家。用户想要面试的岗位是：{position_title}
{company_context}

请根据你对这个岗位的了解，生成一份详细的岗位要求。

只输出JSON，不要有其他文字，不要有markdown代码块标记：
{{
  "title": "岗位名称",
  "requirements_must": ["必须技能1", "必须技能2"],
  "requirements_plus": ["加分项1", "加分项2"],
  "responsibilities": ["职责1", "职责2"],
  "keywords": ["关键词1", "关键词2"]
}}

要求：
- 基于当前2025年的技术市场行情
- 必须技能列出6-8项核心要求
- 加分项列出3-5项
- 职责列出4-6项核心职责
- 关键词列出该岗位的8-10个核心技术关键词"""

JD_PARSE_PROMPT = """你是一个资深的技术招聘专家。请解析以下职位描述，提取结构化岗位要求。

职位描述：
{jd_text}

只输出JSON，不要有其他文字，不要有markdown代码块标记：
{{
  "title": "岗位名称",
  "requirements_must": ["必须技能1", "必须技能2"],
  "requirements_plus": ["加分项1", "加分项2"],
  "responsibilities": ["职责1", "职责2"],
  "keywords": ["关键词1", "关键词2"]
}}"""


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text)


async def process_jd(position_title: str, company: str = "", jd_text: str = "") -> JDData:
    if jd_text.strip():
        return await parse_jd_text(jd_text, position_title, company)
    else:
        return await generate_jd_from_title(position_title, company)


async def parse_jd_text(jd_text: str, position_title: str, company: str = "") -> JDData:
    llm = get_llm(temperature=0)
    prompt = JD_PARSE_PROMPT.format(jd_text=jd_text[:4000])

    for _ in range(2):
        try:
            response = await llm.ainvoke(prompt)
            data = extract_json(response.content)
            return JDData(
                source=JDSource.USER_INPUT,
                company=company,
                raw_text=jd_text,
                **data,
            )
        except Exception:
            continue

    return JDData(title=position_title, company=company, source=JDSource.USER_INPUT, raw_text=jd_text)


async def generate_jd_from_title(position_title: str, company: str = "") -> JDData:
    llm = get_llm(temperature=0.3)
    company_context = f"目标公司是：{company}。请结合该公司的业务特点调整要求。" if company else ""
    prompt = JD_GENERATE_PROMPT.format(position_title=position_title, company_context=company_context)

    for _ in range(2):
        try:
            response = await llm.ainvoke(prompt)
            data = extract_json(response.content)
            return JDData(
                source=JDSource.AUTO_GENERATED,
                company=company,
                **data,
            )
        except Exception as e:
            print(f"JD生成失败: {e}")
            continue

    return JDData(title=position_title, company=company, source=JDSource.AUTO_GENERATED)

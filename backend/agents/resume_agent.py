import json
import re
from agents.llm_factory import get_llm
from models.schemas import ResumeData

RESUME_PARSE_PROMPT = """你是一个专业的HR简历分析师。请解析以下简历内容，提取结构化信息。

简历内容：
{resume_text}

请严格按照以下JSON格式输出，只输出JSON，不要有其他文字，不要有markdown代码块标记：
{{
  "name": "姓名",
  "education": [{{"school": "学校", "degree": "学历", "major": "专业", "duration": "时间"}}],
  "skills": ["技能1", "技能2"],
  "work_experience": [{{"company": "公司", "role": "职位", "duration": "时间", "description": "工作描述"}}],
  "projects": [{{"name": "项目名", "role": "角色", "tech_stack": ["技术1"], "description": "描述", "highlights": ["亮点1"]}}],
  "strengths": ["个人优势1", "个人优势2"]
}}"""


def extract_json(text: str) -> dict:
    """从模型输出中提取JSON，兼容deepseek-r1的<think>块和markdown标记"""
    text = text.strip()
    # 去掉 deepseek-r1 的 <think>...</think> 思考块
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    # 去掉 ```json ... ``` 标记
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    # 提取第一个 { ... } 块
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        text = match.group()
    return json.loads(text)


async def parse_resume(resume_text: str) -> ResumeData:
    llm = get_llm(temperature=0)
    prompt = RESUME_PARSE_PROMPT.format(resume_text=resume_text[:3000])  # 限制长度

    last_error = None
    for attempt in range(2):
        try:
            response = await llm.ainvoke(prompt)
            data = extract_json(response.content)
            return ResumeData(raw_text=resume_text, **data)
        except Exception as e:
            last_error = e
            continue

    # 解析失败时返回最小结构
    print(f"简历解析失败: {last_error}")
    return ResumeData(raw_text=resume_text, name="未知", skills=[], strengths=[])

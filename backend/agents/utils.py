import re
import json


def extract_json(text: str) -> dict:
    """从LLM输出中提取JSON，兼容deepseek-r1的<think>块和markdown标记"""
    text = text.strip()
    # 去掉 deepseek-r1 的 <think>...</think> 思考块
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    # 去掉 ```json ... ``` 标记
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```\s*$', '', text)
    text = text.strip()
    # 提取第一个完整的 {...} 块
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        text = m.group()
    return json.loads(text)

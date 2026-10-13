"""维度定义与权重 —— 全项目单一来源。

任何模块（评估 Prompt、报告聚合、盲评 rubric、前端展示）都必须从这里读取，
不允许在别处硬编码维度名或权重。
"""

# 维度 key、中文展示名、权重、评分口径（会原样注入评估 Prompt）
DIMENSIONS: list[dict] = [
    {
        "key": "structure",
        "label": "结构",
        "weight": 0.25,
        "rubric_desc": (
            "结论先行、分层叙述、不跑题。高分特征：开头给结论，中段按逻辑展开"
            "（如背景-动作-结果），结尾收束；不堆砌、不漫谈、不偏离问题本身。"
        ),
    },
    {
        "key": "depth",
        "label": "深度",
        "weight": 0.30,
        "rubric_desc": (
            "被追问时能否给出细节、数据与取舍理由。高分特征：有量化数据、有具体场景、"
            "讲得出「为什么这么做」和「放弃了什么」；只会说教科书定义或喊口号则低分。"
        ),
    },
    {
        "key": "job_match",
        "label": "岗位匹配",
        "weight": 0.25,
        "rubric_desc": (
            "回答与目标岗位 JD 要求的相关度、术语使用的准确度。高分特征：主动把话题"
            "拉回岗位关心的能力上，术语使用准确；答非所问、关联牵强、术语误用则低分。"
        ),
    },
    {
        "key": "written_expression",
        "label": "文字表达",
        "weight": 0.20,
        "rubric_desc": (
            "文字面试场景下的表达质量：简洁、无冗余、无口语废词、段落清晰。"
            "注意：本产品 MVP 为文字面试，不考察口头禅、语速、时长。"
        ),
    },
]

DIMENSION_KEYS: list[str] = [d["key"] for d in DIMENSIONS]
DIMENSION_LABELS: dict[str, str] = {d["key"]: d["label"] for d in DIMENSIONS}
DIMENSION_WEIGHTS: dict[str, float] = {d["key"]: d["weight"] for d in DIMENSIONS}


def dimension_block_for_prompt() -> str:
    """生成评估 Prompt 里的维度说明段。"""
    lines = []
    for d in DIMENSIONS:
        lines.append(f"- {d['label']}（{d['key']}）：{d['rubric_desc']}")
    return "\n".join(lines)


def focus_advice(dimension_key: str) -> str:
    """按最弱维度给出「下一场练什么」的具体建议（用于报告，不依赖 LLM 现编）。"""
    return {
        "structure": "用「结论先行 + 背景/动作/结果三段」重写两道高频项目题的讲稿，限时 90 秒说清一件事",
        "depth": "准备 2 个项目的「深挖弹药」：量化数据、失败与取舍、复盘动作，练到被追问 3 层不空",
        "job_match": "把目标 JD 逐条拆成能力项，每个能力项配一个自己的经历证据，消灭「术语对不上」",
        "written_expression": "每天用 150 字回答一个专业问题并回删三分之一字数，消灭口语废词和重复",
    }.get(dimension_key, "针对该维度做专项练习")

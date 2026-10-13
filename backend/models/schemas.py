from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ========== 简历相关 ==========
class Education(BaseModel):
    school: str
    degree: str
    major: str
    duration: str = ""


class WorkExperience(BaseModel):
    company: str
    role: str
    duration: str
    description: str


class Project(BaseModel):
    name: str
    role: str
    tech_stack: list[str]
    description: str
    highlights: list[str]


class ResumeData(BaseModel):
    name: str = ""
    education: list[Education] = []
    skills: list[str] = []
    work_experience: list[WorkExperience] = []
    projects: list[Project] = []
    strengths: list[str] = []
    raw_text: str = ""


# ========== 岗位相关 ==========
class JDSource(str, Enum):
    USER_INPUT = "user_input"
    AUTO_GENERATED = "auto_generated"


class JDData(BaseModel):
    title: str
    company: str = ""
    source: JDSource = JDSource.AUTO_GENERATED
    raw_text: str = ""
    requirements_must: list[str] = []
    requirements_plus: list[str] = []
    responsibilities: list[str] = []
    keywords: list[str] = []


# ========== 匹配分析 ==========
class MatchAnalysis(BaseModel):
    matched_skills: list[str] = []
    missing_skills: list[str] = []
    strong_points: list[str] = []
    weak_points: list[str] = []
    interview_focus: list[str] = []


# ========== 面试题目 ==========
class InterviewPhase(str, Enum):
    OPENING = "opening"
    TECHNICAL = "technical"
    PROJECT = "project"
    SCENARIO = "scenario"
    OPEN = "open"


class Question(BaseModel):
    id: str
    phase: InterviewPhase
    content: str
    intent: str = ""
    follow_ups: list[str] = []
    reference_points: list[str] = []


# ========== 面试对话 ==========
class ChatMessage(BaseModel):
    role: str  # "interviewer" | "candidate"
    content: str
    phase: InterviewPhase = InterviewPhase.OPENING
    question_id: str = ""
    timestamp: float = 0


# ========== 评估 ==========
class Evidence(BaseModel):
    """一条扣分证据：扣分理由必须挂在对话原文的逐字引用上。"""
    dimension: str = ""           # 对应 dimensions.DIMENSION_KEYS 之一
    quote: str = ""               # 必须是候选人回答的逐字原文（校验见 evaluator_agent）
    reason: str = ""              # 为什么这段原文导致扣分
    points_deducted: int = 0      # 该证据对应的扣分幅度（0-10 分制）


class AnswerEvaluation(BaseModel):
    question_id: str
    question: str
    answer: str
    score: int = 0                # 四维度加权后的综合分（0-10）
    strengths: list[str] = []
    weaknesses: list[str] = []
    missing_points: list[str] = []
    should_follow_up: bool = False
    follow_up_direction: str = ""
    dimension_scores: dict[str, int] = {}   # {"structure": 7, "depth": 5, ...}
    evidence: list[Evidence] = []           # 每个扣分点必须有原文引用


# ========== 面试报告 ==========
class DimensionScores(BaseModel):
    """四维度百分制得分（加权口径见 dimensions.py）。"""
    structure: int = 0
    depth: int = 0
    job_match: int = 0
    written_expression: int = 0


class QuestionReview(BaseModel):
    question_id: str
    question: str
    user_answer: str
    score: int
    strengths: list[str]
    weaknesses: list[str]
    reference_answer: str
    suggestion: str
    evidence: list[Evidence] = []


class InterviewReport(BaseModel):
    interview_id: str
    date: str
    duration: int = 0
    target_position: str
    overall_score: int = 0
    dimension_scores: DimensionScores = DimensionScores()
    question_reviews: list[QuestionReview] = []
    overall_suggestions: list[str] = []
    study_plan: list[str] = []
    next_focus: list[str] = []          # 「下一场练什么」：按最弱维度生成
    evidence_by_dimension: dict[str, list[Evidence]] = {}   # 维度 -> 该维度全部证据


# ========== 校准实验（真人盲评） ==========
class ReviewerInfo(BaseModel):
    reviewer_id: str
    name: str = ""


class DimensionJudgment(BaseModel):
    dimension: str          # 对应 dimensions.DIMENSION_KEYS 之一
    score: int              # 1-5 分量表（见 calibration/rubric.py）
    note: str = ""


class BlindReviewSubmission(BaseModel):
    reviewer: ReviewerInfo
    judgments: list[DimensionJudgment]
    submitted_at: float = 0


class BlindPacket(BaseModel):
    """一场面试导出的盲评包。blind=True 时不含任何 AI 评分。"""
    packet_id: str
    interview_id: str
    created_at: float = 0
    target_position: str = ""
    qa: list[dict] = []                 # [{"question": ..., "answer": ...}, ...]
    ai_scores: dict[str, int] = {}      # 揭晓后才填充：维度 -> AI 百分制
    reviews: list[BlindReviewSubmission] = []
    revealed: bool = False


# ========== API请求/响应 ==========
class SetupRequest(BaseModel):
    position_title: str
    company: str = ""
    jd_text: str = ""
    resume_id: str


class SetupResponse(BaseModel):
    interview_id: str
    resume: ResumeData
    jd: JDData
    match_analysis: MatchAnalysis
    question_count: int


class ChatRequest(BaseModel):
    interview_id: str
    message: str


class InterviewStatus(BaseModel):
    interview_id: str
    current_phase: InterviewPhase
    question_index: int
    total_questions: int
    is_complete: bool

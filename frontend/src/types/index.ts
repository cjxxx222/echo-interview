// ========== 简历相关 ==========
export interface Education {
  school: string
  degree: string
  major: string
  duration: string
}

export interface WorkExperience {
  company: string
  role: string
  duration: string
  description: string
}

export interface Project {
  name: string
  role: string
  techStack: string[]
  description: string
  highlights: string[]
}

export interface ResumeData {
  name: string
  education: Education[]
  skills: string[]
  workExperience: WorkExperience[]
  projects: Project[]
  strengths: string[]
  rawText: string
}

// ========== 岗位相关 ==========
export type JDSource = 'user_input' | 'auto_generated'

export interface JDData {
  title: string
  company: string
  source: JDSource
  rawText: string
  requirementsMust: string[]
  requirementsPlus: string[]
  responsibilities: string[]
  keywords: string[]
}

// ========== 匹配分析 ==========
export interface MatchAnalysis {
  matchedSkills: string[]
  missingSkills: string[]
  strongPoints: string[]
  weakPoints: string[]
  interviewFocus: string[]
}

// ========== 面试题目 ==========
export type InterviewPhase = 'opening' | 'technical' | 'project' | 'scenario' | 'open'

export interface Question {
  id: string
  phase: InterviewPhase
  content: string
  intent: string
  followUps: string[]
  referencePoints: string[]
}

// ========== 面试对话 ==========
export interface ChatMessage {
  role: 'interviewer' | 'candidate'
  content: string
  phase: InterviewPhase
  questionId: string
  timestamp: number
}

// ========== 评估 ==========
export interface Evidence {
  dimension: string
  quote: string
  reason: string
  pointsDeducted: number
}

export interface AnswerEvaluation {
  questionId: string
  question: string
  answer: string
  score: number
  strengths: string[]
  weaknesses: string[]
  missingPoints: string[]
  shouldFollowUp: boolean
  followUpDirection: string
}

// ========== 面试报告 ==========
export interface DimensionScores {
  structure: number
  depth: number
  jobMatch: number
  writtenExpression: number
}

export interface QuestionReview {
  questionId: string
  question: string
  userAnswer: string
  score: number
  strengths: string[]
  weaknesses: string[]
  referenceAnswer: string
  suggestion: string
  evidence: Evidence[]
}

export interface InterviewReport {
  interviewId: string
  date: string
  duration: number
  targetPosition: string
  overallScore: number
  dimensionScores: DimensionScores
  questionReviews: QuestionReview[]
  overallSuggestions: string[]
  studyPlan: string[]
  nextFocus: string[]
  evidenceByDimension: Record<string, Evidence[]>
}

// ========== API请求/响应 ==========
export interface SetupRequest {
  positionTitle: string
  company?: string
  jdText?: string
  resumeId: string
}

export interface SetupResponse {
  interviewId: string
  resume: ResumeData
  jd: JDData
  matchAnalysis: MatchAnalysis
  questionCount: number
}

export interface ChatRequest {
  interviewId: string
  message: string
}

export interface InterviewStatus {
  interviewId: string
  currentPhase: InterviewPhase
  questionIndex: number
  totalQuestions: number
  isComplete: boolean
}

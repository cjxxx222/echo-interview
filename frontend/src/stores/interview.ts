import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ResumeData, JDData, MatchAnalysis, ChatMessage, InterviewPhase, InterviewReport } from '../types'

export const useInterviewStore = defineStore('interview', () => {
  const resumeId = ref<string>('')
  const interviewId = ref<string>('')
  const resume = ref<ResumeData | null>(null)
  const jd = ref<JDData | null>(null)
  const matchAnalysis = ref<MatchAnalysis | null>(null)
  const questionCount = ref<number>(0)
  const messages = ref<ChatMessage[]>([])
  const currentPhase = ref<InterviewPhase>('opening')
  const questionIndex = ref<number>(0)
  const totalQuestions = ref<number>(0)
  const isComplete = ref<boolean>(false)
  const report = ref<InterviewReport | null>(null)

  function reset() {
    resumeId.value = ''
    interviewId.value = ''
    resume.value = null
    jd.value = null
    matchAnalysis.value = null
    questionCount.value = 0
    messages.value = []
    currentPhase.value = 'opening'
    questionIndex.value = 0
    totalQuestions.value = 0
    isComplete.value = false
    report.value = null
  }

  return {
    resumeId, interviewId, resume, jd, matchAnalysis, questionCount,
    messages, currentPhase, questionIndex, totalQuestions, isComplete, report,
    reset
  }
})

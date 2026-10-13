<template>
  <div class="interview-layout">
    <!-- Left: chat area -->
    <div class="chat-area">
      <div class="messages" ref="messagesEl">
        <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role]">
          <div class="bubble" v-html="renderMarkdown(msg.content)"></div>
        </div>
        <div v-if="streaming" class="message interviewer">
          <div class="bubble streaming" v-html="renderMarkdown(streamingText + '▌')"></div>
        </div>
      </div>
      <div class="input-area">
        <textarea
          v-model="input"
          placeholder="输入你的回答... (Enter发送，Shift+Enter换行)"
          @keydown.enter.exact.prevent="sendMessage"
          :disabled="streaming || isComplete"
          rows="3"
        ></textarea>
        <button @click="sendMessage" :disabled="!input.trim() || streaming || isComplete" class="btn-primary">发送</button>
      </div>
    </div>

    <!-- Right: info panel -->
    <div class="info-panel">
      <div class="panel-section">
        <label>目标岗位</label>
        <p>{{ store.jd?.title || '—' }}</p>
      </div>
      <div class="panel-section">
        <label>面试阶段</label>
        <div class="phases">
          <span v-for="phase in phases" :key="phase.key"
            :class="['phase-badge', { active: currentPhase === phase.key }]">
            {{ phase.label }}
          </span>
        </div>
      </div>
      <div class="panel-section">
        <label>进度</label>
        <p>{{ questionIndex }} / {{ store.questionCount }} 题</p>
      </div>
      <div class="panel-section">
        <label>计时</label>
        <p class="timer">{{ timerFormatted }}</p>
      </div>
      <button class="btn-danger" @click="endInterview" :disabled="isComplete">结束面试</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { marked } from 'marked'
import { useInterviewStore } from '../stores/interview'
import { useSSE } from '../composables/useSSE'
import { useTimer } from '../composables/useTimer'
import type { ChatMessage, InterviewPhase } from '../types'

const route = useRoute()
const router = useRouter()
const store = useInterviewStore()
const { isStreaming: streaming, startStream } = useSSE()
const { formatted: timerFormatted, start: startTimer, stop: stopTimer } = useTimer()

const interviewId = route.params.id as string
const messages = ref<ChatMessage[]>([])
const streamingText = ref('')
const input = ref('')
const currentPhase = ref<InterviewPhase>('opening')
const questionIndex = ref(0)
const isComplete = ref(false)
const messagesEl = ref<HTMLElement | null>(null)

const phases = [
  { key: 'opening', label: '自我介绍' },
  { key: 'technical', label: '技术基础' },
  { key: 'project', label: '项目深挖' },
  { key: 'scenario', label: '场景设计' },
  { key: 'open', label: '开放题' },
]

function renderMarkdown(text: string) {
  return marked.parse(text) as string
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
}

onMounted(async () => {
  startTimer()
  // Load initial greeting from backend status
  const res = await fetch(`/api/interview/${interviewId}/status`)
  if (res.ok) {
    const status = await res.json()
    currentPhase.value = status.current_phase
    questionIndex.value = status.question_index
    isComplete.value = status.is_complete
  }
  // Request first question via a "start" message
  await sendFirstMessage()
})

async function sendFirstMessage() {
  streamingText.value = ''
  await startStream(
    '/api/interview/chat',
    { interview_id: interviewId, message: '__START__' },
    (token: string) => { streamingText.value += token; scrollToBottom() },
    (status: object) => {
      const s = status as { phase?: InterviewPhase; question_index?: number }
      if (s.phase) currentPhase.value = s.phase
      if (s.question_index !== undefined) questionIndex.value = s.question_index
    },
    () => {
      messages.value.push({ role: 'interviewer', content: streamingText.value, phase: currentPhase.value, questionId: '', timestamp: Date.now() })
      streamingText.value = ''
      scrollToBottom()
    }
  )
}

async function sendMessage() {
  const text = input.value.trim()
  if (!text || streaming.value || isComplete.value) return
  input.value = ''
  messages.value.push({ role: 'candidate', content: text, phase: currentPhase.value, questionId: '', timestamp: Date.now() })
  scrollToBottom()

  streamingText.value = ''
  await startStream(
    '/api/interview/chat',
    { interview_id: interviewId, message: text },
    (token: string) => { streamingText.value += token; scrollToBottom() },
    (status: object) => {
      const s = status as { phase?: InterviewPhase; question_index?: number; is_complete?: boolean }
      if (s.phase) currentPhase.value = s.phase
      if (s.question_index !== undefined) questionIndex.value = s.question_index
      if (s.is_complete) isComplete.value = true
    },
    () => {
      messages.value.push({ role: 'interviewer', content: streamingText.value, phase: currentPhase.value, questionId: '', timestamp: Date.now() })
      streamingText.value = ''
      scrollToBottom()
      if (isComplete.value) {
        stopTimer()
        setTimeout(() => router.push(`/report/${interviewId}`), 2000)
      }
    }
  )
}

async function endInterview() {
  if (!confirm('确定要结束面试吗？')) return
  stopTimer()
  const res = await fetch(`/api/interview/${interviewId}/end`, { method: 'POST' })
  if (res.ok) {
    router.push(`/report/${interviewId}`)
  }
}
</script>

<style scoped>
.interview-layout { display: flex; height: calc(100vh - 60px); gap: 0; }
.chat-area { flex: 7; display: flex; flex-direction: column; border-right: 1px solid #374151; }
.messages { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.message { display: flex; }
.message.interviewer { justify-content: flex-start; }
.message.candidate { justify-content: flex-end; }
.bubble { max-width: 75%; padding: 12px 16px; border-radius: 12px; line-height: 1.6; }
.message.interviewer .bubble { background: #1F2937; border: 1px solid #374151; color: #F9FAFB; }
.message.candidate .bubble { background: #3B82F6; color: white; }
.streaming { opacity: 0.9; }
.input-area { padding: 16px; border-top: 1px solid #374151; display: flex; gap: 12px; }
.input-area textarea { flex: 1; background: #1F2937; border: 1px solid #374151; border-radius: 8px; padding: 10px 12px; color: #F9FAFB; resize: none; font-size: 1rem; }
.info-panel { flex: 3; padding: 24px; display: flex; flex-direction: column; gap: 20px; }
.panel-section label { display: block; color: #6B7280; font-size: 0.8rem; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em; }
.panel-section p { color: #F9FAFB; font-weight: 500; }
.phases { display: flex; flex-direction: column; gap: 6px; }
.phase-badge { padding: 4px 12px; border-radius: 20px; font-size: 0.85rem; color: #6B7280; background: #1F2937; }
.phase-badge.active { background: #3B82F6; color: white; }
.timer { font-size: 1.5rem; font-weight: 700; font-variant-numeric: tabular-nums; color: #3B82F6; }
.btn-danger { background: #EF4444; color: white; border: none; border-radius: 8px; padding: 10px 20px; cursor: pointer; font-size: 1rem; }
.btn-danger:disabled { opacity: 0.5; cursor: not-allowed; }
</style>

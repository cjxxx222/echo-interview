<template>
  <div class="setup">
    <h2>面试准备</h2>
    <p class="subtitle">上传简历并填写目标岗位，AI将为你定制面试题</p>
    <!-- Step 1: Upload resume -->
    <div class="step" :class="{ active: step === 1 }">
      <h3>第一步：上传简历</h3>
      <div class="upload-area" @dragover.prevent @drop.prevent="onDrop">
        <input ref="fileInput" type="file" accept=".pdf,.docx,.txt,.md" @change="onFileChange" style="display:none" />
        <div v-if="!uploadedFile" @click="fileInput?.click()" class="upload-placeholder">
          <span>点击选择文件或拖拽到此处</span>
          <small>支持 PDF / DOCX / TXT / MD</small>
        </div>
        <div v-else class="upload-done">
          <span>✅ {{ uploadedFile.name }}</span>
          <button @click="uploadedFile = null; resumeId = ''">重新选择</button>
        </div>
      </div>
      <button class="btn-primary" :disabled="!uploadedFile || uploading" @click="uploadResume">
        {{ uploading ? '上传中...' : '上传简历' }}
      </button>
      <p class="demo-link">
        不想上传真实简历？
        <a href="javascript:void(0)" @click="useDemoResume">用示例简历（虚构的 AI 产品经理）体验完整流程</a>
      </p>
      <p v-if="errorMsg && step === 1" class="error">{{ errorMsg }}</p>
    </div>

    <!-- Step 2: Job info -->
    <div class="step" :class="{ active: step === 2 }">
      <h3>第二步：填写目标岗位</h3>
      <div class="form-group">
        <label>岗位名称 *</label>
        <input v-model="form.positionTitle" placeholder="如：AI应用工程师、前端开发工程师" />
      </div>
      <div class="form-group">
        <label>公司名称（选填）</label>
        <input v-model="form.company" placeholder="如：字节跳动、阿里巴巴" />
      </div>
      <div class="form-group">
        <label>职位描述 JD（选填）</label>
        <textarea v-model="form.jdText" rows="6" placeholder="粘贴职位描述，留空则自动生成岗位要求"></textarea>
      </div>
      <button class="btn-primary" :disabled="!form.positionTitle || preparing" @click="startInterview">
        {{ preparing ? '正在分析简历和准备面试题（约1-2分钟）...' : '开始面试' }}
      </button>
      <p v-if="errorMsg && step === 2" class="error">{{ errorMsg }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useInterviewStore } from '../stores/interview'

const router = useRouter()
const store = useInterviewStore()

const DEMO_JD_TEXT = `AI 产品经理（校招）

岗位职责：
1. 负责 AI 应用类产品（如智能问答、内容生成、AI 助理）的需求分析与产品设计
2. 建设与维护评测集，推动模型效果的系统性提升
3. 跨团队协作，跟进研发、算法与设计，保障交付质量

任职要求：
1. 2027 届本科及以上学历，专业不限，计算机相关优先
2. 对 AI 产品有真实使用体验与思考，能讲清至少一个 AI 产品的优劣势
3. 具备结构化表达与数据分析能力，熟练使用 SQL 者优先
4. 有 AI 相关实习或项目经历者优先`

const step = ref(1)
const fileInput = ref<HTMLInputElement | null>(null)
const uploadedFile = ref<File | null>(null)
const uploading = ref(false)
const preparing = ref(false)
const resumeId = ref('')
const errorMsg = ref('')

const form = ref({
  positionTitle: '',
  company: '',
  jdText: '',
})

function onFileChange(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (files?.length) uploadedFile.value = files[0]
}

function onDrop(e: DragEvent) {
  const files = e.dataTransfer?.files
  if (files?.length) uploadedFile.value = files[0]
}

async function useDemoResume() {
  resumeId.value = 'demo'
  store.resumeId = 'demo'
  form.value.positionTitle = 'AI 产品经理（校招）'
  form.value.jdText = DEMO_JD_TEXT
  step.value = 2
}

async function uploadResume() {
  if (!uploadedFile.value) return
  uploading.value = true
  errorMsg.value = ''
  try {
    const fd = new FormData()
    fd.append('file', uploadedFile.value)
    const res = await fetch('/api/resume/upload', { method: 'POST', body: fd })
    if (!res.ok) {
      const err = await res.text()
      throw new Error(err)
    }
    const data = await res.json()
    resumeId.value = data.resume_id
    store.resumeId = data.resume_id
    step.value = 2
  } catch (e) {
    errorMsg.value = '上传失败：' + (e as Error).message
  } finally {
    uploading.value = false
  }
}

async function startInterview() {
  if (!form.value.positionTitle || !resumeId.value) return
  preparing.value = true
  errorMsg.value = ''
  try {
    const res = await fetch('/api/interview/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        position_title: form.value.positionTitle,
        company: form.value.company,
        jd_text: form.value.jdText,
        resume_id: resumeId.value,
      }),
    })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    store.interviewId = data.interview_id
    store.resume = data.resume
    store.jd = data.jd
    store.matchAnalysis = data.match_analysis
    store.questionCount = data.question_count
    router.push(`/interview/${data.interview_id}`)
  } catch (e) {
    errorMsg.value = '准备失败：' + (e as Error).message
  } finally {
    preparing.value = false
  }
}
</script>

<style scoped>
.setup { max-width: 700px; margin: 0 auto; padding: 40px 24px; }
h2 { color: #F9FAFB; font-size: 1.8rem; margin-bottom: 8px; }
.subtitle { color: #9CA3AF; margin-bottom: 32px; }
.step { background: #1F2937; border: 1px solid #374151; border-radius: 12px; padding: 24px; margin-bottom: 24px; opacity: 0.5; pointer-events: none; }
.step.active { opacity: 1; pointer-events: all; }
.step h3 { color: #F9FAFB; margin-bottom: 16px; }
.upload-area { border: 2px dashed #374151; border-radius: 8px; padding: 32px; text-align: center; margin-bottom: 16px; cursor: pointer; }
.upload-placeholder { display: flex; flex-direction: column; gap: 8px; color: #9CA3AF; }
.upload-done { display: flex; align-items: center; gap: 16px; color: #10B981; }
.form-group { margin-bottom: 16px; }
.form-group label { display: block; color: #9CA3AF; margin-bottom: 6px; font-size: 0.9rem; }
.form-group input, .form-group textarea { width: 100%; background: #111827; border: 1px solid #374151; border-radius: 8px; padding: 10px 12px; color: #F9FAFB; font-size: 1rem; box-sizing: border-box; }
.form-group textarea { resize: vertical; }
.error { color: #EF4444; margin-top: 12px; font-size: 0.9rem; }
.demo-link { margin-top: 14px; font-size: 0.85rem; color: #6B7280; }
.demo-link a { color: #3B82F6; text-decoration: none; }
</style>

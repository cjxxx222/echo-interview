<template>
  <div class="report" v-if="report">
    <div class="report-header">
      <h2>面试报告</h2>
      <p>{{ report.targetPosition }} · {{ report.date }} · {{ Math.floor(report.duration / 60) }}分钟</p>
      <div class="overall-score">
        <span class="score-num">{{ report.overallScore }}</span>
        <span class="score-label">综合评分</span>
      </div>
    </div>

    <div class="dimensions">
      <h3>维度评分</h3>
      <div class="dim-list">
        <div v-for="(val, key) in report.dimensionScores" :key="key" class="dim-item">
          <span class="dim-label">{{ dimLabels[key as keyof typeof dimLabels] }}</span>
          <div class="dim-bar"><div class="dim-fill" :style="{ width: val + '%' }"></div></div>
          <span class="dim-val">{{ val }}</span>
        </div>
      </div>
    </div>

    <div class="evidence-chain" v-if="hasEvidence">
      <h3>扣分证据链</h3>
      <p class="chain-intro">每条扣分都挂着你回答里的原文——分数为什么被扣，逐条可回溯。</p>
      <div v-for="(items, dim) in report.evidenceByDimension" :key="dim" class="chain-group">
        <div class="chain-dim">{{ dimLabels[dim as keyof typeof dimLabels] || dim }}</div>
        <div v-for="(e, i) in items" :key="i" class="evidence-card">
          <div class="evidence-quote">「{{ e.quote }}」</div>
          <div class="evidence-reason">{{ e.reason }}<span class="deduct" v-if="e.pointsDeducted"> -{{ e.pointsDeducted }}分</span></div>
        </div>
      </div>
    </div>

    <div class="reviews">
      <h3>逐题点评</h3>
      <div v-for="review in report.questionReviews" :key="review.questionId" class="review-card">
        <div class="review-header" @click="toggleReview(review.questionId)">
          <span class="q-text">{{ review.question }}</span>
          <span class="q-score" :class="scoreClass(review.score)">{{ review.score }}/10</span>
        </div>
        <div v-if="expanded.has(review.questionId)" class="review-body">
          <div class="section"><label>你的回答</label><p>{{ review.userAnswer }}</p></div>
          <div class="section" v-if="review.strengths.length"><label>亮点</label>
            <ul><li v-for="s in review.strengths" :key="s">{{ s }}</li></ul></div>
          <div class="section" v-if="review.evidence.length"><label>本题扣分证据</label>
            <div v-for="(e, i) in review.evidence" :key="i" class="evidence-card">
              <div class="evidence-quote">「{{ e.quote }}」</div>
              <div class="evidence-reason">{{ e.reason }}</div>
            </div>
          </div>
          <div class="section"><label>改进建议</label><p>{{ review.suggestion }}</p></div>
        </div>
      </div>
    </div>

    <div class="suggestions">
      <h3>总体建议</h3>
      <ul><li v-for="s in report.overallSuggestions" :key="s">{{ s }}</li></ul>
    </div>

    <div class="next-focus" v-if="report.nextFocus.length">
      <h3>下一场练什么</h3>
      <p class="chain-intro">按本场最弱的两个维度生成——把一次面试变成下一次的练习清单。</p>
      <ul><li v-for="s in report.nextFocus" :key="s">{{ s }}</li></ul>
    </div>

    <div class="privacy">
      {{ privacyText }}
    </div>

    <div class="actions">
      <button class="btn-primary" @click="exportMarkdown">导出 Markdown</button>
      <button class="btn-secondary" @click="$router.push('/')">返回首页</button>
    </div>
  </div>
  <div v-else class="loading">加载报告中...</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import type { InterviewReport } from '../types'

const route = useRoute()
const report = ref<InterviewReport | null>(null)
const expanded = ref(new Set<string>())
const privacyText = ref('面试内容仅存于服务内存，不落盘，到期自动清除。')

const dimLabels = {
  structure: '结构',
  depth: '深度',
  jobMatch: '岗位匹配',
  writtenExpression: '文字表达',
}

const hasEvidence = computed(() =>
  Object.values(report.value?.evidenceByDimension || {}).some(v => v.length > 0)
)

function scoreClass(score: number) {
  if (score >= 8) return 'score-high'
  if (score >= 6) return 'score-mid'
  return 'score-low'
}

function toggleReview(id: string) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}

onMounted(async () => {
  const id = route.params.id
  const res = await fetch(`/api/report/${id}`)
  if (res.ok) report.value = await res.json()
  try {
    const p = await fetch('/api/privacy')
    if (p.ok) privacyText.value = (await p.json()).statement
  } catch { /* 隐私文案加载失败不影响报告展示 */ }
})

function exportMarkdown() {
  if (!report.value) return
  const r = report.value
  let md = `# 面试报告 - ${r.targetPosition}\n\n`
  md += `**综合评分**: ${r.overallScore}/100\n\n`
  md += `## 维度评分\n`
  for (const [k, v] of Object.entries(r.dimensionScores)) {
    md += `- ${dimLabels[k as keyof typeof dimLabels] || k}: ${v}\n`
  }
  md += `\n## 扣分证据链\n`
  for (const [dim, items] of Object.entries(r.evidenceByDimension)) {
    if (!items.length) continue
    md += `\n### ${dimLabels[dim as keyof typeof dimLabels] || dim}\n`
    for (const e of items) md += `- 「${e.quote}」——${e.reason}\n`
  }
  md += `\n## 逐题点评\n\n`
  for (const qr of r.questionReviews) {
    md += `### ${qr.question} (${qr.score}/10)\n${qr.suggestion}\n\n`
  }
  md += `## 下一场练什么\n${r.nextFocus.map(s => `- ${s}`).join('\n')}\n`
  const blob = new Blob([md], { type: 'text/markdown' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `interview-report-${r.interviewId}.md`
  a.click()
}
</script>

<style scoped>
.report { max-width: 800px; margin: 0 auto; padding: 40px 24px; }
.report-header { text-align: center; margin-bottom: 40px; }
.report-header h2 { color: #F9FAFB; font-size: 2rem; }
.report-header p { color: #9CA3AF; margin: 8px 0 20px; }
.overall-score { display: inline-flex; flex-direction: column; align-items: center; background: #1F2937; border: 2px solid #3B82F6; border-radius: 16px; padding: 20px 40px; }
.score-num { font-size: 3rem; font-weight: 700; color: #3B82F6; }
.score-label { color: #9CA3AF; font-size: 0.9rem; }
.dimensions, .reviews, .suggestions, .study-plan, .evidence-chain, .next-focus { background: #1F2937; border: 1px solid #374151; border-radius: 12px; padding: 24px; margin-bottom: 24px; }
h3 { color: #F9FAFB; margin-bottom: 16px; }
.chain-intro { color: #9CA3AF; font-size: 0.85rem; margin: -8px 0 16px; }
.dim-item { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.dim-label { width: 100px; color: #9CA3AF; font-size: 0.9rem; }
.dim-bar { flex: 1; background: #374151; border-radius: 4px; height: 8px; }
.dim-fill { height: 100%; background: #3B82F6; border-radius: 4px; transition: width 0.5s; }
.dim-val { width: 30px; color: #F9FAFB; text-align: right; }
.chain-dim { color: #3B82F6; font-size: 0.9rem; font-weight: 600; margin: 16px 0 8px; }
.chain-group:first-of-type .chain-dim { margin-top: 0; }
.evidence-card { border-left: 3px solid #F59E0B; background: #111827; border-radius: 0 8px 8px 0; padding: 12px 16px; margin-bottom: 8px; }
.evidence-quote { color: #FBBF24; font-size: 0.9rem; line-height: 1.6; }
.evidence-reason { color: #D1D5DB; font-size: 0.85rem; margin-top: 6px; }
.deduct { color: #F87171; margin-left: 6px; }
.review-card { border: 1px solid #374151; border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
.review-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; cursor: pointer; background: #111827; }
.q-text { color: #F9FAFB; flex: 1; }
.q-score { font-weight: 700; padding: 2px 8px; border-radius: 4px; }
.score-high { color: #10B981; }
.score-mid { color: #F59E0B; }
.score-low { color: #EF4444; }
.review-body { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.section label { display: block; color: #6B7280; font-size: 0.8rem; margin-bottom: 4px; text-transform: uppercase; }
.section p { color: #D1D5DB; }
.section ul { color: #D1D5DB; padding-left: 20px; }
.privacy { color: #6B7280; font-size: 0.8rem; line-height: 1.6; margin-bottom: 16px; }
.actions { display: flex; gap: 12px; margin-top: 24px; }
.loading { text-align: center; color: #9CA3AF; padding: 60px; }
</style>

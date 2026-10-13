<template>
  <div class="history">
    <h2>历史记录</h2>
    <p v-if="!reports.length" class="empty">暂无历史记录</p>
    <div v-for="r in reports" :key="r.id" class="history-item" @click="$router.push(`/report/${r.id}`)">
      <div>
        <p class="position">{{ r.targetPosition }}</p>
        <p class="date">{{ r.date }}</p>
      </div>
      <span class="score">{{ r.overallScore }}</span>
    </div>
    <button class="btn-secondary" @click="$router.push('/')">返回首页</button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
const reports = ref<{ id: string; targetPosition: string; date: string; overallScore: number }[]>([])

onMounted(async () => {
  const res = await fetch('/api/report/')
  if (res.ok) reports.value = await res.json()
})
</script>

<style scoped>
.history { max-width: 700px; margin: 0 auto; padding: 40px 24px; }
h2 { color: #F9FAFB; margin-bottom: 24px; }
.empty { color: #9CA3AF; }
.history-item { display: flex; justify-content: space-between; align-items: center; background: #1F2937; border: 1px solid #374151; border-radius: 8px; padding: 16px; margin-bottom: 12px; cursor: pointer; }
.history-item:hover { border-color: #3B82F6; }
.position { color: #F9FAFB; font-weight: 500; }
.date { color: #9CA3AF; font-size: 0.85rem; margin-top: 4px; }
.score { font-size: 1.5rem; font-weight: 700; color: #3B82F6; }
</style>

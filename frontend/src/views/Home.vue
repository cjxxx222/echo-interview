<template>
  <div class="home">
    <div class="hero">
      <h1>回响面试</h1>
      <p>AI 模拟面试官——每条扣分都挂着你回答里的原文，评分体系经真人校准</p>
      <div class="actions">
        <button class="btn-primary" @click="$router.push('/setup')">开始模拟面试</button>
        <button class="btn-secondary" @click="$router.push('/history')">历史记录</button>
      </div>
    </div>
    <div class="features">
      <div class="feature">
        <span class="icon">📄</span>
        <h3>简历定制问题</h3>
        <p>上传简历，AI 围绕你的项目经历出题并动态追问</p>
      </div>
      <div class="feature">
        <span class="icon">🔍</span>
        <h3>扣分证据链</h3>
        <p>每个扣分点都引用你回答的逐字原文——分数为什么被扣，可回溯</p>
      </div>
      <div class="feature">
        <span class="icon">🎯</span>
        <h3>真人校准评分</h3>
        <p>四维度评分经真人面试官盲评校准，一致性数据公开</p>
      </div>
      <div class="feature">
        <span class="icon">📊</span>
        <h3>下一场练什么</h3>
        <p>按最弱维度生成练习清单，把面试变成进步路径</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home {
  max-width: 900px;
  margin: 0 auto;
  padding: 60px 24px;
}
.hero {
  text-align: center;
  margin-bottom: 60px;
}
.hero h1 {
  font-size: 3rem;
  font-weight: 700;
  color: #3B82F6;
  margin-bottom: 12px;
}
.hero p {
  font-size: 1.2rem;
  color: #9CA3AF;
  margin-bottom: 32px;
}
.actions {
  display: flex;
  gap: 16px;
  justify-content: center;
}
.features {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
}
.feature {
  background: #1F2937;
  border: 1px solid #374151;
  border-radius: 12px;
  padding: 24px;
  text-align: center;
}
.feature .icon { font-size: 2rem; }
.feature h3 { color: #F9FAFB; margin: 12px 0 8px; }
.feature p { color: #9CA3AF; font-size: 0.9rem; }
</style>

<template>
  <view class="dashboard-page">
    <!-- Hero -->
    <view class="hero">
      <view class="hero-bg"></view>
      <view class="hero-decor-circle c1"></view>
      <view class="hero-decor-circle c2"></view>
      <view class="hero-content">
        <text class="hero-greeting">{{ greeting }}，{{ userName }}</text>
        <text class="hero-subtitle">数据结构 AI 智练中心</text>
        <view class="hero-stats" v-if="profile">
          <view class="hero-stat">
            <text class="hs-num">{{ todayCount }}</text>
            <text class="hs-label">今日答题</text>
          </view>
          <view class="hero-stat">
            <text class="hs-num accent">{{ accuracy }}%</text>
            <text class="hs-label">正确率</text>
          </view>
          <view class="hero-stat">
            <text class="hs-num">{{ profile.practice_streak || 0 }}</text>
            <text class="hs-label">连续天数</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 快捷操作 -->
    <view class="quick-section">
      <SmCard v-for="action in quickActions" :key="action.label" :clickable="true" @click="action.handler">
        <view class="quick-card">
          <text class="quick-icon">{{ action.icon }}</text>
          <text class="quick-title">{{ action.label }}</text>
          <text class="quick-desc">{{ action.desc }}</text>
        </view>
      </SmCard>
    </view>

    <!-- 学习画像 -->
    <view class="section" v-if="profile">
      <text class="section-title">学习画像</text>
      <view class="profile-grid">
        <view class="profile-stat">
          <text class="ps-num">{{ profile.total_attempts || 0 }}</text>
          <text class="ps-label">总练习</text>
        </view>
        <view class="profile-stat">
          <text class="ps-num accent">{{ accuracy }}%</text>
          <text class="ps-label">正确率</text>
        </view>
        <view class="profile-stat">
          <text class="ps-num">{{ profile.total_correct || 0 }}</text>
          <text class="ps-label">答对</text>
        </view>
        <view class="profile-stat">
          <text class="ps-num">{{ profile.practice_streak || 0 }}</text>
          <text class="ps-label">连续天</text>
        </view>
      </view>

      <!-- 题型雷达图 -->
      <SmCard title="题型掌握度" style="margin-top:12px">
        <view class="radar-wrap">
          <view class="radar-bars">
            <view class="radar-bar-row" v-for="(val, i) in typeAccuracyList" :key="i">
              <text class="radar-bar-label">{{ val.label }}</text>
              <view class="radar-bar-track">
                <view class="radar-bar-fill" :style="{ width: val.value + '%', background: val.value >= 70 ? '#16a34a' : val.value >= 40 ? '#e89c35' : '#dc2626' }"></view>
              </view>
              <text class="radar-bar-val">{{ val.value }}%</text>
            </view>
          </view>
        </view>
      </SmCard>

      <!-- 弱项 / 强项 -->
      <view class="concept-row">
        <view class="weak-section" v-if="profile.weak_concepts && profile.weak_concepts.length">
          <text class="concept-title">需要加强</text>
          <view class="concept-tags">
            <text class="concept-tag weak" v-for="w in profile.weak_concepts" :key="w">{{ w }}</text>
          </view>
        </view>
        <view class="strong-section" v-if="strongConcepts.length">
          <text class="concept-title">已掌握</text>
          <view class="concept-tags">
            <text class="concept-tag strong" v-for="s in strongConcepts" :key="s">{{ s }}</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 章节统计 -->
    <view class="section" v-if="chapterStats.length">
      <text class="section-title">章节题目分布</text>
      <view class="chapter-list">
        <view class="chapter-item" v-for="ch in chapterStats" :key="ch.name">
          <view class="chapter-info">
            <text class="chapter-name">{{ ch.name }}</text>
            <text class="chapter-count">{{ ch.count }} 题</text>
          </view>
          <view class="chapter-bar-track">
            <view class="chapter-bar-fill" :style="{ width: ch.pct + '%' }"></view>
          </view>
        </view>
      </view>
    </view>

    <!-- 学习热力图 -->
    <view class="section" v-if="heatmapData.length">
      <SmCard>
        <view class="heatmap-header">
          <text class="section-title" style="margin-bottom:0">学习热力图</text>
          <text class="heatmap-subtitle">最近30天答题热度</text>
        </view>
        <view class="heatmap-legend">
          <text class="legend-label">少</text>
          <view class="legend-cell" v-for="lvl in heatLevels" :key="lvl" :class="'level-' + lvl"></view>
          <text class="legend-label">多</text>
        </view>
        <view class="heatmap">
          <view
            v-for="day in heatmapData"
            :key="day.date"
            :class="['heatmap-cell', getHeatLevel(day.count)]"
          >
            <text class="heatmap-tooltip" v-if="day.count">{{ day.count }}</text>
          </view>
        </view>
      </SmCard>
    </view>

    <!-- 最近错题 -->
    <view class="section" v-if="recentWrong.length">
      <text class="section-title">最近错题</text>
      <view class="wrong-mini-list">
        <view class="wrong-mini" v-for="w in recentWrong" :key="w.id" @click="goPractice">
          <text class="wrong-mini-chapter">{{ w.chapter }}</text>
          <text class="wrong-mini-stem">{{ truncate(w.stem, 30) }}</text>
          <text class="wrong-mini-arrow">查看</text>
        </view>
      </view>
    </view>

    <!-- 快速入口 -->
    <view class="section">
      <view class="action-row">
        <SmButton variant="primary" block @click="goPractice">开始练习</SmButton>
        <SmButton variant="soft" block @click="goAI">AI 导师答疑</SmButton>
        <SmButton variant="ghost" block @click="goWrong">错题本</SmButton>
      </view>
    </view>

    <!-- 未登录 -->
    <view class="login-cta" v-if="!isLoggedIn">
      <SmCard glass>
        <view class="cta-content">
          <image src="/static/logo.svg" class="cta-logo" mode="aspectFit"/>
          <text class="cta-title">登录解锁全部功能</text>
          <text class="cta-desc">个性化学习推荐、AI导师答疑、学习画像追踪</text>
          <SmButton variant="primary" block @click="goLogin">立即登录</SmButton>
        </view>
      </SmCard>
    </view>
  </view>
</template>

<script>
import SmCard from '@/components/SmCard.vue'
import SmButton from '@/components/SmButton.vue'
import { callCloud, normalizeCloudProfile, normalizeCloudQuestion } from '@/utils/cloud.js'
// getApp() 是 uni-app 全局函数，无需导入

export default {
  components: { SmCard, SmButton },
  data() {
    return {
      profile: Object.create(null),
      heatmapData: Array(),
      chapterStats: Array(),
      recentWrong: Array(),
      todayCount: 0,
      heatLevels: [0, 1, 2, 3, 4],
      quickActions: [
        { icon: '', label: '题库练习', desc: '客观题随时练', handler: () => uni.switchTab({ url: '/pages/practice/practice' }) },
        { icon: '', label: 'AI 导师', desc: '苏格拉底式答疑', handler: () => uni.switchTab({ url: '/pages/ai/ai' }) },
        { icon: '', label: '错题本', desc: '回顾薄弱点', handler: () => uni.navigateTo({ url: '/pages/wrong/wrong' }) },
        { icon: '', label: '智能推荐', desc: '弱项精准练习', handler: this.startRecommend },
      ],
    }
  },
  computed: {
    greeting() {
      const h = new Date().getHours()
      return h < 6 ? '夜深了' : h < 12 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好'
    },
    userName() {
      const app = getApp()
      return app.globalData?.user?.name || '同学'
    },
    isLoggedIn() {
      const app = getApp()
      return !!app.globalData?.token
    },
    accuracy() {
      if (!this.profile?.total_attempts) return 0
      return Math.round((this.profile.total_correct / this.profile.total_attempts) * 100)
    },
    typeAccuracyList() {
      const ta = this.profile?.type_accuracy || {}
      const order = ['单选题', '多选题', '填空题', '判断题']
      return order.map(t => ({ label: t, value: Math.round((ta[t] || 0) * 100) }))
    },
    strongConcepts() {
      return (this.profile?.strong_concepts || []).slice(0, 4)
    },
  },
  async mounted() {
    await this.loadData()
  },
  onShow() {
    this.loadData()
  },
  methods: {
    async loadData() {
      const app = getApp()
      if (!app.globalData?.token) return
      try {
        const token = app.globalData.token
        const [profileData, wrongData] = await Promise.all([
          callCloud('structmind-stats', 'userProfile', { token }),
          callCloud('structmind-practice', 'getWrongQuestions', { token, page_size: 20 }),
        ])
        this.profile = profileData.profile ? normalizeCloudProfile(profileData.profile) : null
        const stats = { chapter_stats: Object.entries(this.profile?.chapter_stats || {}).map(
          ([chapter, item]) => {
            const rawItem = JSON.parse(JSON.stringify(item || {})) || { attempted: 0 }
            return { chapter, attempted: Number(rawItem.attempted) || 0 }
          },
        ) }
        const wrongItems = (wrongData.questions || []).map(question => ({
          question: normalizeCloudQuestion(question),
        }))

        // 章节统计
        const maxCount = (stats.chapter_stats || []).reduce(
          (max, item) => Math.max(max, Number(item.attempted) || 0), 1,
        )
        this.chapterStats = (stats.chapter_stats || []).map(item => ({
          name: item.chapter,
          count: Number(item.attempted) || 0,
          pct: Math.round(((Number(item.attempted) || 0) / maxCount) * 100),
        }))

        // 最近错题
        this.recentWrong = wrongItems.slice(0, 3).map(it => ({
          id: it.question?.id,
          chapter: it.question?.chapter || '未知',
          stem: (it.question?.stem || '').replace(/\[IMAGE:.*?\]/g, ''),
        }))

        // 生成最近30天热力图数据
        this.heatmapData = this.generateHeatmap(stats)
        this.todayCount = 0
      } catch (e) {
        console.log('Dashboard load failed', e)
      }
    },
    generateHeatmap(stats) {
      const days = Array()
      const now = new Date()
      const dailyActivity = stats.daily_activity || {}
      for (let i = 29; i >= 0; i--) {
        const d = new Date(now)
        d.setDate(d.getDate() - i)
        const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
        days.push({ date: key, count: dailyActivity[key] || 0 })
      }
      return days
    },
    getHeatLevel(count) {
      if (!count) return 'level-0'
      if (count <= 5) return 'level-1'
      if (count <= 15) return 'level-2'
      if (count <= 30) return 'level-3'
      return 'level-4'
    },
    startRecommend() { uni.switchTab({ url: '/pages/practice/practice' }) },
    goLogin() { uni.navigateTo({ url: '/pages/login/login' }) },
    goPractice() { uni.switchTab({ url: '/pages/practice/practice' }) },
    goAI() { uni.switchTab({ url: '/pages/ai/ai' }) },
    goWrong() { uni.navigateTo({ url: '/pages/wrong/wrong' }) },
    truncate(text, max) { return (text || '').slice(0, max) + ((text || '').length > max ? '...' : '') },
  },
}
</script>

<style scoped>
.dashboard-page { min-height: 100vh; background: #f5f8f7; padding-bottom: 40px; }

/* Hero */
.hero {
  position: relative; background: linear-gradient(135deg, #2d8a7b 0%, #47b5a3 50%, #5ec9b8 100%);
  padding: 32px 20px 40px; overflow: hidden;
}
.hero-bg { position: absolute; top: -40px; right: -40px; width: 200px; height: 200px; border-radius: 50%; background: rgba(255,255,255,0.06); }
.hero-decor-circle { position: absolute; border-radius: 50%; border: 2px solid rgba(255,255,255,0.15); }
.hero-decor-circle.c1 { width: 80px; height: 80px; right: 30px; top: 10px; }
.hero-decor-circle.c2 { width: 50px; height: 50px; right: 70px; top: 50px; }
.hero-content { position: relative; z-index: 1; }
.hero-greeting { color: rgba(255,255,255,0.85); font-size: 15px; display: block; }
.hero-subtitle { color: rgba(255,255,255,0.6); font-size: 13px; margin-top: 2px; display: block; }

.hero-stats { display: flex; gap: 16px; margin-top: 18px; }
.hero-stat { flex: 1; }
.hs-num { color: #fff; font-size: 28px; font-weight: 700; display: block; }
.hs-num.accent { color: #a8f0e0; }
.hs-label { color: rgba(255,255,255,0.65); font-size: 12px; }

/* Quick Actions */
.quick-section { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 16px; margin-top: -20px; position: relative; z-index: 2; }
.quick-card { display: flex; flex-direction: column; gap: 2px; }
.quick-icon { font-size: 28px; }
.quick-title { font-size: 15px; font-weight: 600; color: #1a2b28; }
.quick-desc { font-size: 12px; color: #6b8280; }

/* Sections */
.section { padding: 0 16px; margin-top: 12px; }
.section-title { font-size: 18px; font-weight: 700; color: #1a2b28; display: block; margin-bottom: 10px; }

/* Profile Grid */
.profile-grid { display: flex; gap: 8px; }
.profile-stat {
  flex: 1; background: #fff; border-radius: 14px; padding: 14px 8px;
  text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}
.ps-num { font-size: 24px; font-weight: 700; color: #1a2b28; }
.ps-num.accent { color: #2d8a7b; }
.ps-label { font-size: 11px; color: #6b8280; }

/* Radar Bars */
.radar-wrap { padding: 4px 0; }
.radar-bars { display: flex; flex-direction: column; gap: 10px; }
.radar-bar-row { display: flex; align-items: center; gap: 10px; }
.radar-bar-label { width: 56px; font-size: 12px; color: #4a5c58; text-align: right; flex-shrink: 0; }
.radar-bar-track { flex: 1; height: 10px; border-radius: 5px; background: #edf2f0; overflow: hidden; }
.radar-bar-fill { height: 100%; border-radius: 5px; transition: width 0.6s ease; min-width: 2px; }
.radar-bar-val { width: 36px; font-size: 11px; font-weight: 600; color: #6b8280; text-align: left; flex-shrink: 0; }

/* Concept Tags */
.concept-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
.concept-title { font-size: 13px; font-weight: 600; color: #1a2b28; margin-bottom: 6px; display: block; }
.concept-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.concept-tag { font-size: 11px; padding: 3px 10px; border-radius: 20px; }
.concept-tag.weak { background: #fef3c7; color: #a16207; }
.concept-tag.strong { background: #f0fdf4; color: #16a34a; }

/* Chapter Stats */
.chapter-list { background: #fff; border-radius: 16px; padding: 14px 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.03); display: flex; flex-direction: column; gap: 10px; }
.chapter-item { display: flex; flex-direction: column; gap: 4px; }
.chapter-info { display: flex; justify-content: space-between; }
.chapter-name { font-size: 13px; color: #4a5c58; }
.chapter-count { font-size: 13px; font-weight: 600; color: #2d8a7b; }
.chapter-bar-track { height: 6px; border-radius: 3px; background: #edf2f0; overflow: hidden; }
.chapter-bar-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, #2d8a7b, #47b5a3); transition: width 0.5s ease; }

/* Heatmap */
.heatmap-header { margin-bottom: 8px; }
.heatmap-subtitle { font-size: 12px; color: #6b8280; }
.heatmap-legend { display: flex; align-items: center; gap: 2px; justify-content: flex-end; margin-bottom: 8px; }
.legend-label { font-size: 10px; color: #a0b0ac; }
.legend-cell { width: 12px; height: 12px; border-radius: 2px; }
.legend-cell.level-0 { background: #edf2f0; }
.legend-cell.level-1 { background: #b8ddd4; }
.legend-cell.level-2 { background: #6fc0b0; }
.legend-cell.level-3 { background: #3ba895; }
.legend-cell.level-4 { background: #1a5c52; }

.heatmap { display: flex; flex-wrap: wrap; gap: 3px; }
.heatmap-cell {
  width: 16px; height: 16px; border-radius: 3px; position: relative;
  display: flex; align-items: center; justify-content: center;
}
.heatmap-cell.level-0 { background: #edf2f0; }
.heatmap-cell.level-1 { background: #b8ddd4; }
.heatmap-cell.level-2 { background: #6fc0b0; }
.heatmap-cell.level-3 { background: #3ba895; }
.heatmap-cell.level-4 { background: #1a5c52; }
.heatmap-tooltip { font-size: 8px; color: #fff; font-weight: 600; }

/* Wrong Mini */
.wrong-mini-list { display: flex; flex-direction: column; gap: 8px; }
.wrong-mini {
  background: #fff; border-radius: 12px; padding: 10px 14px;
  display: flex; align-items: center; gap: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.03);
}
.wrong-mini-chapter { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #e8f5f2; color: #2d8a7b; flex-shrink: 0; }
.wrong-mini-stem { flex: 1; font-size: 13px; color: #4a5c58; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wrong-mini-arrow { font-size: 12px; color: #a0b0ac; }

/* Action Row */
.action-row { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }

/* Login CTA */
.login-cta { padding: 16px; }
.cta-content { display: flex; flex-direction: column; align-items: center; gap: 10px; text-align: center; }
.cta-logo {
  width: 56px; height: 56px; border-radius: 16px;
  background: linear-gradient(135deg, #2d8a7b, #47b5a3); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 800; letter-spacing: 2px;
  box-shadow: 0 4px 16px rgba(45,138,123,0.3);
}
.cta-title { font-size: 18px; font-weight: 700; }
.cta-desc { font-size: 13px; color: #6b8280; }
</style>

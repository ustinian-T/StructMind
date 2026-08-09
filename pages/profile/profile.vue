<template>
  <view class="profile-page">
    <!-- 头部 -->
    <view class="profile-header">
      <view class="avatar-lg">{{ userName[0] || '?' }}</view>
      <text class="profile-name">{{ userName }}</text>
      <text class="profile-account">@{{ userAccount }}</text>
      <text class="profile-role" v-if="isAdmin">管理员</text>
    </view>

    <!-- 统计卡片 -->
    <view class="stats-grid" v-if="profile">
      <view class="stat-item">
        <text class="stat-num">{{ profile.total_attempts || 0 }}</text>
        <text class="stat-label">总练习</text>
      </view>
      <view class="stat-item">
        <text class="stat-num accent">{{ accuracy }}%</text>
        <text class="stat-label">正确率</text>
      </view>
      <view class="stat-item">
        <text class="stat-num">{{ profile.practice_streak || 0 }}</text>
        <text class="stat-label">连续天数</text>
      </view>
    </view>

    <!-- 题型掌握度 -->
    <view class="section" v-if="profile">
      <text class="section-title">题型掌握度</text>
      <SmCard>
        <view class="type-bars">
          <view class="type-row" v-for="item in typeAccuracyList" :key="item.label">
            <text class="type-label">{{ item.label }}</text>
            <view class="type-track">
              <view
                class="type-fill"
                :style="{ width: item.value + '%', background: item.value >= 70 ? '#16a34a' : item.value >= 40 ? '#e89c35' : '#dc2626' }"
              ></view>
            </view>
            <text class="type-val">{{ item.value }}%</text>
          </view>
        </view>
      </SmCard>
    </view>

    <!-- 章节掌握度 -->
    <view class="section" v-if="chapterAccuracy.length">
      <text class="section-title">章节正确率</text>
      <SmCard>
        <view class="chapter-stats">
          <view class="ch-row" v-for="ch in chapterAccuracy" :key="ch.name">
            <view class="ch-info">
              <text class="ch-name">{{ ch.name }}</text>
              <text class="ch-score">{{ ch.accuracy }}%</text>
            </view>
            <view class="ch-track">
              <view class="ch-fill" :style="{ width: ch.accuracy + '%' }"></view>
            </view>
          </view>
        </view>
      </SmCard>
    </view>

    <!-- 强弱项 -->
    <view class="section" v-if="profile">
      <view class="concept-grid">
        <view class="concept-box" v-if="profile.weak_concepts && profile.weak_concepts.length">
          <text class="concept-box-title weak-title">需要加强</text>
          <view class="concept-tags">
            <text class="concept-tag weak" v-for="w in profile.weak_concepts" :key="w">{{ w }}</text>
          </view>
        </view>
        <view class="concept-box" v-if="strongConcepts.length">
          <text class="concept-box-title strong-title">已掌握</text>
          <view class="concept-tags">
            <text class="concept-tag strong" v-for="s in strongConcepts" :key="s">{{ s }}</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 练习趋势图 -->
    <view class="section" v-if="practiceTrend.length">
      <text class="section-title">最近练习趋势</text>
      <SmCard>
        <view class="trend-chart">
          <view class="trend-bar" v-for="(day, i) in practiceTrend" :key="i">
            <view class="trend-bar-inner" :style="{ height: day.pct + '%' }"></view>
            <text class="trend-date">{{ day.label }}</text>
          </view>
        </view>
        <view class="trend-summary">
          <text>过去7天共练习 {{ trendTotal }} 题</text>
        </view>
      </SmCard>
    </view>

    <!-- 菜单 -->
    <view class="menu-section">
      <view class="menu-item" @tap="goAdmin" v-if="isAdmin">
        <text class="menu-icon"></text>
        <text class="menu-text">管理审批</text>
        <text class="menu-arrow">></text>
      </view>
      <view class="menu-item" @tap="goWrong">
        <text class="menu-icon"></text>
        <text class="menu-text">错题本</text>
        <text class="menu-arrow">></text>
      </view>
      <view class="menu-item" @tap="goDashboard">
        <text class="menu-icon"></text>
        <text class="menu-text">学习仪表盘</text>
        <text class="menu-arrow">></text>
      </view>
    </view>

    <!-- 退出登录 -->
    <view class="logout-section">
      <SmButton variant="danger" block @click="handleLogout">退出登录</SmButton>
    </view>

    <SmToast :visible="toastVisible" :message="toastMsg" :type="toastType" @close="toastVisible = false" />
  </view>
</template>

<script>
import SmCard from '@/components/SmCard.vue'
import SmButton from '@/components/SmButton.vue'
import SmToast from '@/components/SmToast.vue'
// getApp() 是 uni-app 全局函数，无需导入

export default {
  components: { SmCard, SmButton, SmToast },
  data() {
    return {
      userName: '同学',
      userAccount: '',
      isAdmin: false,
      profile: null,
      chapterAccuracy: [],
      practiceTrend: [],
      trendTotal: 0,
      toastVisible: false,
      toastMsg: '',
      toastType: 'info',
    }
  },
  computed: {
    accuracy() {
      if (!this.profile?.total_attempts) return 0
      return Math.round((this.profile.total_correct / this.profile.total_attempts) * 100)
    },
    typeAccuracyList() {
      const ta = this.profile?.type_accuracy || {}
      return ['单选题', '多选题', '填空题', '判断题'].map(label => ({
        label,
        value: Math.round((ta[label] || 0) * 100),
      }))
    },
    strongConcepts() {
      return (this.profile?.strong_concepts || []).slice(0, 6)
    },
  },
  async mounted() {
    const app = getApp()
    const auth = app.globalData
    if (!auth.token) {
      uni.reLaunch({ url: '/pages/login/login' })
      return
    }
    this.userName = auth.user?.name || '同学'
    this.userAccount = auth.user?.account || ''
    this.isAdmin = auth.user?.role === 'admin'
    await this.loadProfile()
  },
  onShow() {
    if (this.profile) this.loadProfile()
  },
  methods: {
    async loadProfile() {
      const app = getApp()
      const token = app.globalData?.token
      if (!token) return
      try {
        const apiBase = app.globalData.apiBase || 'https://datastytest.tshai.top'
        const [profileRes, statsRes] = await Promise.all([
          uni.request({ url: `${apiBase}/api/profile`, header: { Authorization: `Bearer ${token}` } }),
          uni.request({ url: `${apiBase}/api/stats` }),
        ])
        this.profile = profileRes.data?.profile || null
        const stats = statsRes.data || {}

        // 章节正确率
        const chAcc = stats.chapter_accuracy || {}
        this.chapterAccuracy = Object.entries(chAcc)
          .map(([name, acc]) => ({ name, accuracy: Math.round(acc * 100) }))
          .sort((a, b) => a.accuracy - b.accuracy)

        // 最近7天练习趋势
        this.practiceTrend = this.generateTrend(stats.daily_activity || {})
      } catch (e) {
        console.log('Profile load failed')
      }
    },
    generateTrend(dailyActivity) {
      const now = new Date()
      const days = []
      let total = 0
      for (let i = 6; i >= 0; i--) {
        const d = new Date(now)
        d.setDate(d.getDate() - i)
        const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
        const val = dailyActivity[key] || 0
        total += val
        days.push({
          label: `${d.getMonth()+1}/${d.getDate()}`,
          count: val,
          pct: Math.min(100, val * 10), // scale: 10 questions = 100%
        })
      }
      this.trendTotal = total
      return days
    },
    goAdmin() { uni.navigateTo({ url: '/pages/admin/admin' }) },
    goWrong() { uni.navigateTo({ url: '/pages/wrong/wrong' }) },
    goDashboard() { uni.switchTab({ url: '/pages/index/index' }) },
    handleLogout() {
      const app = getApp()
      const g = app.globalData; g.token = null; g.user = null; uni.removeStorageSync('auth')
      uni.reLaunch({ url: '/pages/login/login' })
    },
  },
}
</script>

<style scoped>
.profile-page { min-height: 100vh; background: #f5f8f7; padding-bottom: 40px; }

/* Header */
.profile-header {
  background: linear-gradient(135deg, #2d8a7b, #47b5a3);
  padding: 56px 24px 32px;
  display: flex; flex-direction: column; align-items: center; gap: 6px;
}
.avatar-lg {
  width: 80px; height: 80px; border-radius: 28px;
  background: rgba(255,255,255,0.25); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 36px; font-weight: 700; border: 3px solid rgba(255,255,255,0.3);
}
.profile-name { color: #fff; font-size: 24px; font-weight: 700; }
.profile-account { color: rgba(255,255,255,0.7); font-size: 14px; }
.profile-role {
  margin-top: 2px; padding: 2px 12px; border-radius: 20px;
  background: rgba(255,255,255,0.2); color: #fff; font-size: 11px;
}

/* Stats Grid */
.stats-grid {
  display: flex; margin: -20px 16px 0; position: relative; z-index: 2; gap: 8px;
}
.stat-item {
  flex: 1; background: #fff; border-radius: 16px; padding: 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.06); display: flex;
  flex-direction: column; align-items: center;
}
.stat-num { font-size: 24px; font-weight: 700; color: #1a2b28; }
.stat-num.accent { color: #2d8a7b; }
.stat-label { font-size: 12px; color: #6b8280; margin-top: 2px; }

/* Sections */
.section { padding: 0 16px; margin-top: 16px; }
.section-title { font-size: 17px; font-weight: 700; color: #1a2b28; display: block; margin-bottom: 8px; }

/* Type Bars */
.type-bars { display: flex; flex-direction: column; gap: 10px; }
.type-row { display: flex; align-items: center; gap: 10px; }
.type-label { width: 56px; font-size: 12px; color: #4a5c58; text-align: right; flex-shrink: 0; }
.type-track { flex: 1; height: 10px; border-radius: 5px; background: #edf2f0; overflow: hidden; }
.type-fill { height: 100%; border-radius: 5px; transition: width 0.6s ease; min-width: 2px; }
.type-val { width: 36px; font-size: 11px; font-weight: 600; color: #6b8280; text-align: left; flex-shrink: 0; }

/* Chapter Stats */
.chapter-stats { display: flex; flex-direction: column; gap: 10px; }
.ch-row { display: flex; flex-direction: column; gap: 3px; }
.ch-info { display: flex; justify-content: space-between; }
.ch-name { font-size: 13px; color: #4a5c58; }
.ch-score { font-size: 13px; font-weight: 600; color: #2d8a7b; }
.ch-track { height: 6px; border-radius: 3px; background: #edf2f0; overflow: hidden; }
.ch-fill { height: 100%; border-radius: 3px; background: #2d8a7b; transition: width 0.5s ease; }

/* Concept Grid */
.concept-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.concept-box { background: #fff; border-radius: 14px; padding: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.03); }
.concept-box-title { font-size: 13px; font-weight: 600; display: block; margin-bottom: 8px; }
.weak-title { color: #e89c35; }
.strong-title { color: #16a34a; }
.concept-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.concept-tag { font-size: 11px; padding: 3px 10px; border-radius: 20px; }
.concept-tag.weak { background: #fef3c7; color: #a16207; }
.concept-tag.strong { background: #f0fdf4; color: #16a34a; }

/* Trend Chart */
.trend-chart { display: flex; align-items: flex-end; gap: 8px; height: 120px; padding: 8px 0; justify-content: center; }
.trend-bar {
  flex: 1; max-width: 36px; display: flex; flex-direction: column; align-items: center;
  justify-content: flex-end; height: 100%; gap: 4px;
}
.trend-bar-inner {
  width: 100%; min-height: 4px; border-radius: 6px 6px 0 0;
  background: linear-gradient(180deg, #47b5a3, #2d8a7b); transition: height 0.4s ease;
}
.trend-date { font-size: 10px; color: #a0b0ac; }
.trend-summary { margin-top: 8px; text-align: center; }
.trend-summary text { font-size: 12px; color: #6b8280; }

/* Menu */
.menu-section {
  margin: 24px 16px 0; background: #fff; border-radius: 16px;
  overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.04);
}
.menu-item {
  display: flex; align-items: center; gap: 12px;
  padding: 16px 18px; border-bottom: 1px solid #f5f5f5;
}
.menu-item:last-child { border-bottom: none; }
.menu-icon { font-size: 20px; }
.menu-text { flex: 1; font-size: 15px; color: #1a2b28; font-weight: 500; }
.menu-arrow { font-size: 18px; color: #c0c8c5; }

.logout-section { padding: 24px 16px; }
</style>

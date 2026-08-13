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
      <view class="stat-item" v-if="fsrsReviewCount > 0">
        <text class="stat-num review">{{ fsrsReviewCount }}</text>
        <text class="stat-label">待复习</text>
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

    <!-- 概念掌握度 -->
    <view class="section" v-if="conceptMastery.length">
      <text class="section-title">概念掌握度</text>
      <SmCard>
        <view class="type-bars">
          <view class="type-row" v-for="item in conceptMastery" :key="item.name">
            <text class="type-label">{{ item.name }}</text>
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

    <view class="section learning-archive">
      <text class="section-title">考试学习计划</text>
      <SmCard>
        <view class="archive-form">
          <text class="field-label">考试日期</text>
          <input class="archive-input" type="date" v-model="examDate" />
          <text class="field-label">每日学习时长（分钟）</text>
          <input class="archive-input" type="number" v-model="dailyMinutes" />
          <SmButton variant="primary" block @click="saveLearningPlan">保存并生成计划</SmButton>
          <view v-if="learningPlan" class="plan-proof">
            <text>计划版本 {{ learningPlan.version }} · {{ learningPlan.status }}</text>
            <text v-for="(task, index) in (learningPlan.plan_data?.tasks || [])" :key="index">{{ task.title || task.concept }} · {{ task.estimated_minutes || 0 }}分钟</text>
          </view>
        </view>
      </SmCard>
    </view>

    <view class="section" v-if="dueReviews.length">
      <text class="section-title">今日间隔复习</text>
      <SmCard>
        <view class="review-item" v-for="review in dueReviews" :key="review.concept">
          <text class="review-concept">{{ review.concept }}</text>
          <text class="review-time">到期：{{ formatTime(review.next_review_at) }}</text>
          <view class="feedback-row">
            <view @tap="sendReviewFeedback(review, 'too_hard')">太难</view>
            <view @tap="sendReviewFeedback(review, 'just_right')">正好</view>
            <view @tap="sendReviewFeedback(review, 'too_easy')">太简单</view>
          </view>
        </view>
      </SmCard>
    </view>

    <view class="section">
      <text class="section-title">学习笔记</text>
      <SmCard>
        <view class="archive-form">
          <input class="archive-input" v-model="noteTitle" placeholder="笔记标题" />
          <textarea class="note-input" v-model="noteContent" placeholder="记录今天的理解与疑问" />
          <SmButton variant="primary" block @click="createLearningNote">新增笔记</SmButton>
          <view class="note-item" v-for="note in notes" :key="note._id">
            <input class="archive-input" v-model="note.title" @blur="updateLearningNote(note)" />
            <textarea class="note-input" v-model="note.user_content" @blur="updateLearningNote(note)" />
            <text class="archive-note" @tap="archiveLearningNote(note)">归档笔记</text>
          </view>
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
      <view class="menu-item spaced-item" @tap="spacedPractice">
        <text class="menu-icon"></text>
        <text class="menu-text">间隔练习{{ fsrsReviewCount > 0 ? ' · ' + fsrsReviewCount + '个概念待复习' : '' }}</text>
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
import { callCloud, normalizeCloudProfile } from '@/utils/cloud.js'
// getApp() 是 uni-app 全局函数，无需导入

export default {
  components: { SmCard, SmButton, SmToast },
  data() {
    return {
      userName: '同学',
      userAccount: '',
      isAdmin: false,
      profile: Object.create(null),
      chapterAccuracy: Array(),
      conceptMastery: Array(),
      fsrsReviewCount: 0,
      practiceTrend: Array(),
      trendTotal: 0,
      learningPlan: null,
      examDate: '',
      dailyMinutes: 30,
      dueReviews: Array(),
      notes: Array(),
      noteTitle: '',
      noteContent: '',
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
    await Promise.all([this.loadProfile(), this.loadLearningArchive()])
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
        const profileData = await callCloud('structmind-stats', 'userProfile', { token })
        this.profile = profileData.profile ? normalizeCloudProfile(profileData.profile) : null
        const stats = {
          chapter_accuracy: this.profile?.chapter_accuracy || {},
          daily_activity: this.profile?.daily_activity || {},
          fsrs_review_count: this.profile?.fsrs_review_count || 0,
        }

        // FSRS review count
        this.fsrsReviewCount = this.profile?.fsrs_review_count
          || this.profile?.pending_review_count
          || (stats.fsrs_review_count)
          || 0

        // Concept mastery may be present in the cloud profile response.
        this.conceptMastery = this.extractConceptMastery(this.profile, stats)

        // 章节正确率
        const chAcc = stats.chapter_accuracy || {}
        this.chapterAccuracy = Object.entries(chAcc)
          .map(([name, acc]) => ({ name, accuracy: Math.round((Number(acc) || 0) * 100) }))
          .sort((a, b) => a.accuracy - b.accuracy)

        // 最近7天练习趋势
        this.practiceTrend = this.generateTrend(stats.daily_activity || {})
      } catch (e) {
        console.log('Profile load failed')
      }
    },
    async loadLearningArchive() {
      const token = getApp().globalData?.token
      if (!token) return
      try {
        const [planData, reviewData, noteData] = await Promise.all([
          callCloud('structmind-learning', 'getPlan', { token }),
          callCloud('structmind-learning', 'getReviews', { token }),
          callCloud('structmind-learning', 'listNotes', { token, archived: false }),
        ])
        this.learningPlan = planData.plan || null
        this.examDate = this.learningPlan?.exam_date || this.examDate
        this.dailyMinutes = this.learningPlan?.daily_minutes || this.dailyMinutes
        this.dueReviews = reviewData.reviews || []
        this.notes = noteData.notes || []
        this.fsrsReviewCount = this.dueReviews.length || this.fsrsReviewCount
      } catch (e) { this.showToast('学习档案暂时无法加载', 'error') }
    },
    async saveLearningPlan() {
      if (!this.examDate || Number(this.dailyMinutes) < 10) {
        this.showToast('请选择考试日期，每日时长至少10分钟', 'error'); return
      }
      try {
        const data = await callCloud('structmind-learning', 'savePlan', {
          token: getApp().globalData?.token, exam_date: this.examDate,
          daily_minutes: Number(this.dailyMinutes), timezone: 'Asia/Shanghai',
        })
        this.learningPlan = data.plan
        this.showToast('学习计划已更新', 'success')
      } catch (e) { this.showToast('学习计划保存失败', 'error') }
    },
    async sendReviewFeedback(review, feedback) {
      try {
        await callCloud('structmind-learning', 'reviewFeedback', {
          token: getApp().globalData?.token, concept: review.concept, feedback,
          learning_event_id: review.learning_event_id,
        })
        await this.loadLearningArchive()
        this.showToast('复习反馈已记录', 'success')
      } catch (e) { this.showToast('反馈保存失败', 'error') }
    },
    async createLearningNote() {
      if (!this.noteTitle.trim()) { this.showToast('请输入笔记标题', 'error'); return }
      await callCloud('structmind-learning', 'createNote', {
        token: getApp().globalData?.token, title: this.noteTitle, user_content: this.noteContent,
      })
      this.noteTitle = ''; this.noteContent = ''; await this.loadLearningArchive()
    },
    async updateLearningNote(note) {
      await callCloud('structmind-learning', 'updateNote', {
        token: getApp().globalData?.token, note_id: note._id,
        title: note.title, user_content: note.user_content, is_archived: false,
      })
    },
    async archiveLearningNote(note) {
      await callCloud('structmind-learning', 'updateNote', {
        token: getApp().globalData?.token, note_id: note._id, is_archived: true,
      })
      await this.loadLearningArchive()
    },
    formatTime(value) { return value ? new Date(value).toLocaleString() : '现在' },
    generateTrend(dailyActivity) {
      const now = new Date()
      const days = Array()
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
    extractConceptMastery(profile, stats) {
      // Try profile.concept_mastery first, then stats, then fallback
      const mastery = profile?.concept_mastery || stats?.concept_mastery || {}
      if (!mastery || typeof mastery !== 'object') return []
      return Object.entries(mastery)
        .filter(([, v]) => !isNaN(Number(v)))
        .map(([name, val]) => ({ name, value: Math.round((Number(val) || 0) * 100) }))
        .sort((a, b) => a.value - b.value)
    },
    async spacedPractice() {
      const app = getApp()
      const token = app.globalData?.token
      if (!token) {
        uni.showToast({ title: '请先登录', icon: 'none' })
        return
      }
      try {
        const data = await callCloud('structmind-practice', 'createSession', {
          token,
          mode: 'random',
          limit: 15,
          include_wrong: true,
        })
        if (data.questions?.length) {
          const qCount = data.questions.length
          this.showToast(`已生成${qCount}题间隔复习`, 'success')
        } else {
          this.showToast('暂无可复习内容，继续加油！', 'info')
        }
      } catch (e) {
        this.showToast('间隔复习请求失败，请稍后重试', 'error')
      }
    },
    async handleLogout() {
      const app = getApp()
      const g = app.globalData
      try {
        if (g.token) await callCloud('structmind-auth', 'logout', { token: g.token })
      } catch (e) {}
      g.token = null; g.user = null; uni.removeStorageSync('auth')
      uni.reLaunch({ url: '/pages/login/login' })
    },
    showToast(msg, type = 'info') {
      this.toastMsg = msg
      this.toastType = type
      this.toastVisible = true
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
.stat-num.review { color: #e89c35; }
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
.menu-item.spaced-item { background: rgba(45,138,123,0.04); }
.menu-item.spaced-item .menu-text { color: #2d8a7b; }
.menu-icon { font-size: 20px; }
.menu-text { flex: 1; font-size: 15px; color: #1a2b28; font-weight: 500; }
.menu-arrow { font-size: 18px; color: #c0c8c5; }

.logout-section { padding: 24px 16px; }
.learning-archive { margin-top: 24px; }
.archive-form { display: flex; flex-direction: column; gap: 10px; }
.field-label { font-size: 12px; color: #6b8280; }
.archive-input, .note-input { box-sizing: border-box; width: 100%; padding: 10px 12px; border: 1px solid #dce5e3; border-radius: 10px; background: #fff; font-size: 14px; }
.note-input { min-height: 72px; }
.plan-proof { display: flex; flex-direction: column; gap: 5px; padding: 10px; border-radius: 10px; background: #e8f5f2; font-size: 12px; color: #2d8a7b; }
.review-item, .note-item { padding: 12px 0; border-bottom: 1px solid #edf2f0; display: flex; flex-direction: column; gap: 8px; }
.review-item:last-child, .note-item:last-child { border-bottom: 0; }
.review-concept { font-size: 14px; font-weight: 700; color: #1a2b28; }
.review-time { font-size: 11px; color: #6b8280; }
.feedback-row { display: flex; gap: 8px; }
.feedback-row view, .archive-note { flex: 1; padding: 8px; border-radius: 10px; background: #e8f5f2; color: #2d8a7b; font-size: 12px; text-align: center; }
</style>

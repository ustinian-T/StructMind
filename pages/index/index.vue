<template>
  <view class="index-page">
    <!-- 顶部横幅 -->
    <view class="hero-banner">
      <view class="hero-gradient"></view>
      <view class="hero-content">
        <text class="hero-greeting">{{ greeting }}</text>
        <text class="hero-name">{{ userName }}</text>
        <text class="hero-stats" v-if="profile">
          已练习 {{ profile.total_attempts || 0 }} 题 · 正确率 {{ accuracy }}%
        </text>
      </view>
      <view class="hero-decor">
        <view class="decor-circle c1"></view>
        <view class="decor-circle c2"></view>
        <view class="decor-circle c3"></view>
      </view>
    </view>

    <!-- 快捷操作 -->
    <view class="quick-actions">
      <view class="action-card" @tap="goPractice">
        <text class="action-icon">📝</text>
        <text class="action-title">题库练习</text>
        <text class="action-desc">323道客观题随时练</text>
      </view>
      <view class="action-card" @tap="goAI">
        <text class="action-icon">🤖</text>
        <text class="action-title">AI 导师</text>
        <text class="action-desc">苏格拉底式答疑</text>
      </view>
      <view class="action-card" @tap="goRecommend">
        <text class="action-icon">🎯</text>
        <text class="action-title">智能推荐</text>
        <text class="action-desc">针对弱项精准练习</text>
      </view>
      <view class="action-card" @tap="goWrong">
        <text class="action-icon">📖</text>
        <text class="action-title">错题本</text>
        <text class="action-desc">回顾薄弱知识点</text>
      </view>
    </view>

    <!-- 学习画像 -->
    <view class="section" v-if="profile">
      <view class="section-header">
        <text class="section-title">📊 学习画像</text>
      </view>
      <view class="profile-cards">
        <view class="profile-card">
          <text class="profile-label">总练习</text>
          <text class="profile-value">{{ profile.total_attempts || 0 }}</text>
          <text class="profile-unit">题</text>
        </view>
        <view class="profile-card">
          <text class="profile-label">正确率</text>
          <text class="profile-value accent">{{ accuracy }}</text>
          <text class="profile-unit">%</text>
        </view>
        <view class="profile-card">
          <text class="profile-label">连续天数</text>
          <text class="profile-value">{{ profile.practice_streak || 0 }}</text>
          <text class="profile-unit">天</text>
        </view>
      </view>
      <view class="weak-section" v-if="profile.weak_concepts && profile.weak_concepts.length">
        <text class="weak-title">🔍 建议加强：</text>
        <view class="weak-tags">
          <text class="weak-tag" v-for="w in profile.weak_concepts" :key="w">{{ w }}</text>
        </view>
      </view>
    </view>

    <!-- 未登录提示 -->
    <view class="login-prompt" v-if="!isLoggedIn">
      <text class="prompt-text">登录后解锁个性化学习功能</text>
      <button class="prompt-btn" @tap="goLogin">立即登录</button>
    </view>
  </view>
</template>

<script>
import { callCloud, normalizeCloudProfile } from '@/utils/cloud.js'
// getApp() 是 uni-app 全局函数，无需导入

export default {
  data() {
    return {
      isLoggedIn: false,
      userName: '同学',
      profile: Object.create(null),
    }
  },
  computed: {
    greeting() {
      const h = new Date().getHours()
      return h < 12 ? '早上好' : h < 18 ? '下午好' : '晚上好'
    },
    accuracy() {
      if (!this.profile || !this.profile.total_attempts) return 0
      return Math.round((this.profile.total_correct / this.profile.total_attempts) * 100)
    },
  },
  async mounted() {
    const app = getApp()
    const auth = app.globalData
    this.isLoggedIn = !!auth.token
    this.userName = auth.user?.name || '同学'

    if (auth.token) {
      try {
        const data = await callCloud('structmind-stats', 'userProfile', { token: auth.token })
        this.profile = data.profile ? normalizeCloudProfile(data.profile) : null
      } catch (err) {
        console.log('Failed to load profile')
      }
    }
  },
  methods: {
    goPractice() { uni.switchTab({ url: '/pages/practice/practice' }) },
    goAI() { uni.switchTab({ url: '/pages/ai/ai' }) },
    goWrong() { uni.navigateTo({ url: '/pages/wrong/wrong' }) },
    goRecommend() {
      uni.switchTab({ url: '/pages/practice/practice' })
    },
    goLogin() { uni.navigateTo({ url: '/pages/login/login' }) },
  },
}
</script>

<style scoped>
.index-page {
  min-height: 100vh;
  background: #f5f8f7;
  padding-bottom: 40px;
}

.hero-banner {
  position: relative;
  background: linear-gradient(135deg, #2d8a7b 0%, #47b5a3 50%, #5ec9b8 100%);
  padding: 32px 20px 40px;
  overflow: hidden;
}

.hero-gradient {
  position: absolute;
  top: -40px;
  right: -40px;
  width: 200px;
  height: 200px;
  border-radius: 50%;
  background: rgba(255,255,255,0.08);
}

.hero-content { position: relative; z-index: 1; }

.hero-greeting {
  color: rgba(255,255,255,0.8);
  font-size: 15px;
  display: block;
}

.hero-name {
  color: white;
  font-size: 28px;
  font-weight: 700;
  display: block;
  margin-top: 4px;
}

.hero-stats {
  color: rgba(255,255,255,0.75);
  font-size: 13px;
  display: block;
  margin-top: 8px;
}

.hero-decor { position: absolute; right: 20px; top: 10px; }
.decor-circle {
  position: absolute;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.2);
}
.c1 { width: 80px; height: 80px; right: 0; top: 0; }
.c2 { width: 50px; height: 50px; right: 50px; top: 40px; }
.c3 { width: 30px; height: 30px; right: 20px; top: 70px; }

.quick-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding: 20px 16px;
  margin-top: -24px;
  position: relative;
  z-index: 2;
}

.action-card {
  background: white;
  border-radius: 16px;
  padding: 18px 16px;
  box-shadow: 0 4px 20px rgba(45, 138, 123, 0.08);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.action-icon { font-size: 28px; }
.action-title { font-size: 15px; font-weight: 600; color: #1a2b28; }
.action-desc { font-size: 12px; color: #6b8280; }

.section { padding: 0 16px; margin-top: 8px; }
.section-header { margin-bottom: 12px; }
.section-title { font-size: 18px; font-weight: 700; color: #1a2b28; }

.profile-cards {
  display: flex;
  gap: 10px;
}

.profile-card {
  flex: 1;
  background: white;
  border-radius: 14px;
  padding: 16px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.profile-label { font-size: 12px; color: #6b8280; }
.profile-value { font-size: 28px; font-weight: 700; color: #1a2b28; margin-top: 4px; }
.profile-value.accent { color: #2d8a7b; }
.profile-unit { font-size: 11px; color: #a0b0ac; }

.weak-section { margin-top: 12px; background: white; border-radius: 14px; padding: 16px; }
.weak-title { font-size: 14px; font-weight: 600; color: #1a2b28; display: block; margin-bottom: 8px; }
.weak-tags { display: flex; flex-wrap: wrap; gap: 8px; }
.weak-tag {
  background: #fef3c7;
  color: #a16207;
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 20px;
}

.login-prompt {
  margin: 40px 16px;
  padding: 32px;
  background: white;
  border-radius: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.04);
}

.prompt-text { color: #6b8280; font-size: 15px; }
.prompt-btn {
  background: linear-gradient(135deg, #2d8a7b, #47b5a3);
  color: white;
  padding: 12px 40px;
  border-radius: 12px;
  font-weight: 600;
  border: none;
}
</style>

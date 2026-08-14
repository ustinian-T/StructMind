<template>
  <view class="login-page">
    <view class="login-header">
      <view class="logo-area">
        <image src="/static/logo.svg" class="logo-icon" mode="aspectFit"/>
        <text class="app-name">StructMind</text>
        <text class="app-subtitle">数据结构 AI 智练中心</text>
      </view>
    </view>

    <form class="login-card" @submit="handleLogin">
      <text class="card-title">欢迎回来</text>
      <text class="card-desc">登录你的学习账号继续练习</text>

      <view class="form-group">
        <text class="form-label">账号</text>
        <input
          class="form-input"
          v-model="account"
          placeholder="请输入账号"
          :disabled="loading"
        />
      </view>

      <view class="form-group">
        <text class="form-label">密码</text>
        <input
          class="form-input"
          v-model="password"
          type="password"
          placeholder="请输入密码"
          :disabled="loading"
        />
      </view>

      <view class="error-msg" v-if="errorMsg">
        <text>{{ errorMsg }}</text>
      </view>

      <button class="login-btn" form-type="submit" :disabled="loading || !account || !password">
        <text v-if="!loading">登 录</text>
        <text v-else>登录中...</text>
      </button>

      <view class="login-footer">
        <text class="footer-link" @tap="goRegister">还没有账号？立即注册</text>
      </view>
    </form>

    <view class="login-bottom">
      <text class="bottom-text">© 2026 StructMind · 谭书宏</text>
      <text class="bottom-text icp" @tap="openICP">湘ICP备2026021754号-2</text>
    </view>
  </view>
</template>

<script>
import { callCloud, getErrorMessage } from '@/utils/cloud.js'
// getApp() 是 uni-app 全局函数，无需导入

export default {
  data() {
    return {
      account: '',
      password: '',
      loading: false,
      errorMsg: '',
    }
  },
  methods: {
    async handleLogin() {
      if (!this.account.trim() || !this.password.trim()) {
        this.errorMsg = '请输入账号和密码'
        return
      }
      this.loading = true
      this.errorMsg = ''
      try {
        const app = getApp()
        const data = await callCloud('structmind-auth', 'login', {
          account: this.account.trim(),
          password: this.password,
        })
        if (data.token && data.user) {
          const g = app.globalData || {}
          g.token = data.token
          g.user = data.user
          uni.setStorageSync('auth', JSON.stringify({ token: data.token, user: data.user }))
          uni.reLaunch({ url: '/pages/index/index' })
        } else {
          this.errorMsg = '登录失败，请重试'
        }
      } catch (err) {
        this.errorMsg = getErrorMessage(err, '登录失败，请检查网络连接')
      } finally {
        this.loading = false
      }
    },
    goRegister() {
      uni.navigateTo({ url: '/pages/register/register' })
    },
    openICP() {
      // #ifdef H5
      window.open('https://beian.miit.gov.cn', '_blank')
      // #endif
    },
  },
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  background: #f3f7f0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 60px 24px 40px;
}

.login-header {
  margin-bottom: 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.logo-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.logo-icon {
  width: 80px;
  height: 80px;
  border-radius: 22px;
  box-shadow: 0 10px 28px rgba(47, 95, 61, 0.16);
  margin-bottom: 12px;
}

.app-name {
  font-size: 28px;
  font-weight: 700;
  color: #1a2b28;
  letter-spacing: 2px;
}

.app-subtitle {
  font-size: 14px;
  color: #6b8280;
  letter-spacing: 2px;
}

.login-card {
  width: 100%;
  max-width: 380px;
  background: #fffefb;
  border-radius: 18px;
  padding: 32px 28px;
  box-shadow: 0 18px 48px rgba(47, 95, 61, 0.1);
  border: 1px solid #dfe9da;
}

.card-title {
  font-size: 24px;
  font-weight: 700;
  color: #1a2b28;
  display: block;
  margin-bottom: 4px;
}

.card-desc {
  font-size: 14px;
  color: #6b8280;
  display: block;
  margin-bottom: 28px;
}

.form-group {
  margin-bottom: 20px;
}

.form-label {
  font-size: 14px;
  font-weight: 600;
  color: #4a5c58;
  display: block;
  margin-bottom: 8px;
}

.form-input {
  width: 100%;
  height: 48px;
  background: #fff;
  border: 1px solid #d8e4d3;
  border-radius: 12px;
  padding: 0 16px;
  font-size: 16px;
  color: #1a2b28;
  box-sizing: border-box;
}

.form-input:focus {
  border-color: #6f9a73;
  background: #ffffff;
}

.error-msg {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 16px;
}

.error-msg text {
  color: #dc2626;
  font-size: 13px;
}

.login-btn {
  width: 100%;
  height: 50px;
  background: #477a50;
  border-radius: 14px;
  border: none;
  color: white;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 7px 18px rgba(47, 95, 61, 0.18);
  margin-top: 8px;
}

.login-btn:active {
  opacity: 0.85;
  transform: scale(0.98);
}

.login-btn[disabled] {
  opacity: 0.5;
}

.login-footer {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}

.footer-link {
  color: #477a50;
  font-size: 14px;
  font-weight: 500;
}

.login-bottom {
  margin-top: auto;
  padding-top: 32px;
}

.bottom-text {
  color: #a0b0ac;
  font-size: 12px;
  display: block;
}
.bottom-text.icp {
  margin-top: 4px;
  color: #8a9b96;
}
</style>

<template>
  <view class="register-page">
    <view class="register-header">
      <view class="back-btn" @tap="goBack">
        <text class="back-icon">←</text>
      </view>
      <text class="header-title">创建账号</text>
      <view class="spacer"></view>
    </view>

    <view class="register-card">
      <text class="card-title">注册 StructMind</text>
      <text class="card-desc">填写信息创建你的专属学习账号</text>

      <view class="form-group">
        <text class="form-label">账号</text>
        <input class="form-input" v-model="account" placeholder="设置登录账号" :disabled="loading" />
      </view>

      <view class="form-group">
        <text class="form-label">密码</text>
        <input class="form-input" v-model="password" type="password" placeholder="设置密码（至少6位）" :disabled="loading" />
      </view>

      <view class="form-group">
        <text class="form-label">姓名</text>
        <input class="form-input" v-model="name" placeholder="请输入真实姓名" :disabled="loading" />
      </view>

      <view class="form-group">
        <text class="form-label">手机号</text>
        <input class="form-input" v-model="phone" type="number" placeholder="请输入手机号码" :disabled="loading" maxlength="11" />
      </view>

      <view class="error-msg" v-if="errorMsg">
        <text>{{ errorMsg }}</text>
      </view>

      <view class="success-msg" v-if="successMsg">
        <text>{{ successMsg }}</text>
      </view>

      <button class="register-btn" @tap="handleRegister" :disabled="loading || !account || !password || !name || !phone">
        <text v-if="!loading">注 册</text>
        <text v-else>注册中...</text>
      </button>

      <view class="notice-box">
        <text class="notice-text">📋 注册后需等待管理员审批通过方可登录使用</text>
      </view>
    </view>
  </view>
</template>

<script>
// getApp() 是 uni-app 全局函数，无需导入
export default {
  data() {
    return {
      account: '',
      password: '',
      name: '',
      phone: '',
      loading: false,
      errorMsg: '',
      successMsg: '',
    }
  },
  methods: {
    goBack() {
      uni.navigateBack()
    },
    async handleRegister() {
      if (this.password.length < 6) {
        this.errorMsg = '密码长度不能少于6位'
        return
      }
      if (this.phone.length !== 11) {
        this.errorMsg = '请输入正确的11位手机号码'
        return
      }
      this.loading = true
      this.errorMsg = ''
      this.successMsg = ''
      try {
        const app = getApp()
        const apiBase = app.globalData.apiBase || 'https://datastytest.tshai.top'
        const res = await uni.request({
          url: apiBase + '/api/auth/register',
          method: 'POST',
          data: {
            account: this.account.trim(),
            password: this.password,
            name: this.name.trim(),
            phone: this.phone.trim(),
          },
        })
        const data = res.data
        if (data.id) {
          this.successMsg = '注册成功！请等待管理员审批后登录。'
          this.account = ''
          this.password = ''
          this.name = ''
          this.phone = ''
          setTimeout(() => {
            uni.navigateBack()
          }, 2000)
        }
      } catch (err) {
        const msg = err.data?.error || err.message || '注册失败，请重试'
        this.errorMsg = msg
      } finally {
        this.loading = false
      }
    },
  },
}
</script>

<style scoped>
.register-page {
  min-height: 100vh;
  background: linear-gradient(160deg, #e8f5f2 0%, #f5f8f7 40%, #ffffff 100%);
  display: flex;
  flex-direction: column;
  padding: 0 24px 40px;
}

.register-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 44px 0 24px;
}

.back-btn {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: rgba(255,255,255,0.8);
  display: flex;
  align-items: center;
  justify-content: center;
}

.back-icon {
  font-size: 20px;
  color: #2d8a7b;
  font-weight: 700;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  color: #1a2b28;
}

.spacer { width: 40px; }

.register-card {
  width: 100%;
  max-width: 380px;
  align-self: center;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  border-radius: 24px;
  padding: 28px 24px;
  box-shadow: 0 8px 40px rgba(45, 138, 123, 0.1);
  border: 1px solid rgba(45, 138, 123, 0.08);
}

.card-title { font-size: 22px; font-weight: 700; color: #1a2b28; display: block; margin-bottom: 4px; }
.card-desc { font-size: 14px; color: #6b8280; display: block; margin-bottom: 24px; }

.form-group { margin-bottom: 16px; }
.form-label { font-size: 14px; font-weight: 600; color: #4a5c58; display: block; margin-bottom: 6px; }
.form-input {
  width: 100%; height: 46px; background: #f5f8f7; border: 1.5px solid #dce5e3;
  border-radius: 12px; padding: 0 14px; font-size: 16px; color: #1a2b28; box-sizing: border-box;
}
.form-input:focus { border-color: #2d8a7b; background: #ffffff; }

.error-msg { background: #fef2f2; border: 1px solid #fecaca; border-radius: 10px; padding: 10px 14px; margin-bottom: 12px; }
.error-msg text { color: #dc2626; font-size: 13px; }

.success-msg { background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 10px; padding: 10px 14px; margin-bottom: 12px; }
.success-msg text { color: #16a34a; font-size: 13px; }

.register-btn {
  width: 100%; height: 50px; background: linear-gradient(135deg, #2d8a7b, #47b5a3);
  border-radius: 14px; border: none; color: white; font-size: 17px; font-weight: 600;
  letter-spacing: 4px; display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4px 20px rgba(45, 138, 123, 0.3); margin-top: 4px;
}
.register-btn:active { opacity: 0.85; transform: scale(0.98); }
.register-btn[disabled] { opacity: 0.5; }

.notice-box { margin-top: 20px; padding: 14px; background: #f0f9f6; border-radius: 12px; border: 1px solid #d0ebe4; }
.notice-text { font-size: 13px; color: #4a7c6e; line-height: 1.6; }
</style>

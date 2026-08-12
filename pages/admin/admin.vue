<template>
  <view class="admin-page">
    <view class="admin-header">
      <text class="header-title">🔐 管理审批</text>
      <text class="header-desc">审批新用户注册申请</text>
    </view>

    <view class="stats-row">
      <view class="stat-card">
        <text class="stat-num">{{ pendingUsers.length }}</text>
        <text class="stat-label">待审批</text>
      </view>
      <view class="stat-card">
        <text class="stat-num">{{ approvedCount }}</text>
        <text class="stat-label">已通过</text>
      </view>
    </view>

    <view class="empty-state" v-if="pendingUsers.length === 0 && !loading">
      <text class="empty-icon">✅</text>
      <text class="empty-text">没有待审批的申请</text>
    </view>

    <view class="user-list" v-else>
      <view class="user-card" v-for="user in pendingUsers" :key="user.id">
        <view class="user-info">
          <view class="user-avatar">{{ user.name[0] }}</view>
          <view class="user-detail">
            <text class="user-name">{{ user.name }}</text>
            <text class="user-meta">@{{ user.account }} · {{ user.phone }}</text>
            <text class="user-time">{{ formatTime(user.created_at) }}</text>
          </view>
        </view>
        <view class="user-actions">
          <button class="btn-approve" @tap="approveUser(user.id, true)">通过</button>
          <button class="btn-reject" @tap="approveUser(user.id, false)">拒绝</button>
        </view>
      </view>
    </view>

    <view class="section-divider">
      <text class="divider-text">全部用户</text>
    </view>

    <view class="user-list">
      <view class="user-card" v-for="user in allUsers" :key="user.id">
        <view class="user-info">
          <view class="user-avatar" :class="user.status === 'approved' ? 'approved' : user.status === 'rejected' ? 'rejected' : ''">
            {{ user.name[0] }}
          </view>
          <view class="user-detail">
            <text class="user-name">
              {{ user.name }}
              <text class="role-badge" :class="user.role">{{ user.role === 'admin' ? '管理员' : '学生' }}</text>
            </text>
            <text class="user-meta">@{{ user.account }} · {{ user.phone }}</text>
          </view>
        </view>
        <view class="status-tag" :class="user.status">
          {{ user.status === 'approved' ? '已通过' : user.status === 'rejected' ? '已拒绝' : '待审批' }}
        </view>
      </view>
    </view>

    <view class="error-msg" v-if="errorMsg">
      <text>{{ errorMsg }}</text>
    </view>
  </view>
</template>

<script>
import { callCloud, getErrorMessage } from '@/utils/cloud.js'
// getApp() 是 uni-app 全局函数，无需导入

export default {
  data() {
    return {
      pendingUsers: Array(),
      allUsers: Array(),
      approvedCount: 0,
      loading: true,
      errorMsg: '',
    }
  },
  async mounted() {
    await this.loadUsers()
  },
  methods: {
    async loadUsers() {
      this.loading = true
      try {
        const app = getApp()
        const auth = app.globalData
        const [pendingData, allData] = await Promise.all([
          callCloud('structmind-admin', 'pending', { token: auth.token }),
          callCloud('structmind-admin', 'users', { token: auth.token }),
        ])

        const normalizeUser = user => ({ ...user, id: user.id || user._id })
        this.pendingUsers = (pendingData.users || []).map(normalizeUser)
        this.allUsers = (allData.users || []).map(normalizeUser)
        this.approvedCount = this.allUsers.filter(u => u.status === 'approved').length
      } catch (err) {
        this.errorMsg = getErrorMessage(err, '加载失败')
      } finally {
        this.loading = false
      }
    },

    async approveUser(userId, approved) {
      try {
        const app = getApp()
        const auth = app.globalData
        await callCloud('structmind-admin', 'approve', {
          token: auth.token,
          user_id: userId,
          approved,
        })

        await this.loadUsers()
        uni.showToast({ title: approved ? '已通过' : '已拒绝', icon: 'success' })
      } catch (err) {
        uni.showToast({ title: getErrorMessage(err, '操作失败'), icon: 'none' })
      }
    },

    formatTime(ts) {
      const value = Number(ts || 0)
      const d = new Date(value > 100000000000 ? value : value * 1000)
      return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
    },
  },
}
</script>

<style scoped>
.admin-page {
  min-height: 100vh;
  background: #f5f8f7;
  padding: 20px 16px 40px;
}

.admin-header {
  padding: 16px 0 20px;
}

.header-title {
  font-size: 24px;
  font-weight: 700;
  color: #1a2b28;
  display: block;
}

.header-desc {
  font-size: 14px;
  color: #6b8280;
  margin-top: 4px;
  display: block;
}

.stats-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.stat-card {
  flex: 1;
  background: white;
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-num {
  font-size: 32px;
  font-weight: 700;
  color: #2d8a7b;
}

.stat-label {
  font-size: 13px;
  color: #6b8280;
  margin-top: 4px;
}

.empty-state {
  padding: 48px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.empty-icon { font-size: 48px; }
.empty-text { color: #6b8280; font-size: 15px; }

.user-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.user-card {
  background: white;
  border-radius: 16px;
  padding: 16px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.user-avatar {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: linear-gradient(135deg, #e0f0ec, #c8e4dd);
  color: #2d8a7b;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 700;
}

.user-avatar.approved { background: #d4f5e4; color: #16a34a; }
.user-avatar.rejected { background: #fde8e8; color: #dc2626; }

.user-detail {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-name {
  font-size: 16px;
  font-weight: 600;
  color: #1a2b28;
}

.role-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 20px;
  margin-left: 6px;
  background: #e0f0ec;
  color: #2d8a7b;
}

.role-badge.admin { background: #fef3c7; color: #b45309; }

.user-meta {
  font-size: 13px;
  color: #6b8280;
}

.user-time {
  font-size: 12px;
  color: #a0b0ac;
}

.user-actions {
  display: flex;
  gap: 8px;
}

.btn-approve {
  padding: 8px 16px;
  border-radius: 10px;
  background: #2d8a7b;
  color: white;
  font-size: 14px;
  font-weight: 600;
  border: none;
}

.btn-reject {
  padding: 8px 16px;
  border-radius: 10px;
  background: #f5f5f5;
  color: #666;
  font-size: 14px;
  font-weight: 500;
  border: none;
}

.status-tag {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 20px;
  font-weight: 500;
}

.status-tag.approved { background: #f0fdf4; color: #16a34a; }
.status-tag.rejected { background: #fef2f2; color: #dc2626; }
.status-tag.pending { background: #fef9c3; color: #a16207; }

.section-divider {
  padding: 24px 0 12px;
}

.divider-text {
  font-size: 15px;
  font-weight: 600;
  color: #4a5c58;
}

.error-msg {
  background: #fef2f2;
  border-radius: 10px;
  padding: 12px;
  margin-top: 16px;
}

.error-msg text { color: #dc2626; font-size: 13px; }
</style>

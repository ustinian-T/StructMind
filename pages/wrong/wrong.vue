<template>
  <view class="wrong-page">
    <view class="page-header">
      <text class="page-title">📖 错题本</text>
      <text class="page-desc">回顾答错的题目，针对性提升</text>
    </view>

    <view class="empty" v-if="wrongItems.length === 0">
      <text class="empty-icon">🎉</text>
      <text class="empty-text">还没有错题记录</text>
      <text class="empty-desc">继续练习，答错的题目会自动收集到这里</text>
    </view>

    <view class="wrong-list" v-else>
      <view class="w-card" v-for="item in wrongItems" :key="item.attempt_id">
        <view class="w-meta">
          <text class="w-tag">{{ item.question.chapter }}</text>
          <text class="w-tag type">{{ item.question.qtype }}</text>
          <text class="w-tag bad">答错</text>
        </view>
        <text class="w-stem">{{ truncate(item.question.stem, 100) }}</text>
        <view class="w-answer">
          <text class="w-label">你的答案：</text>
          <text class="w-value wrong">{{ formatAnswer(item.user_answer) }}</text>
        </view>
        <view class="w-answer">
          <text class="w-label">正确答案：</text>
          <text class="w-value correct">{{ item.question.answer }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { callCloud, normalizeCloudQuestion } from '@/utils/cloud.js'
// getApp() 是 uni-app 全局函数，无需导入

export default {
  data() {
    return {
      wrongItems: [],
    }
  },
  async mounted() {
    try {
      const app = getApp()
      const auth = app.globalData
      const data = await callCloud('structmind-practice', 'getWrongQuestions', {
        token: auth.token,
        page_size: 100,
      })
      this.wrongItems = (data.questions || []).map(raw => {
        const question = normalizeCloudQuestion(raw)
        question.answer = '请重新作答后查看'
        return { attempt_id: question.id, question, user_answer: '—' }
      })
    } catch (err) {
      console.log('Failed to load wrong items')
    }
  },
  methods: {
    truncate(text, max) {
      return (text || '').replace(/\[IMAGE:.*?\]/g, '').slice(0, max) + ((text || '').length > max ? '...' : '')
    },
    formatAnswer(ans) {
      if (Array.isArray(ans)) return ans.join(', ')
      return String(ans || '')
    },
  },
}
</script>

<style scoped>
.wrong-page {
  min-height: 100vh;
  background: #f5f8f7;
  padding-bottom: 40px;
}

.page-header { padding: 16px; }
.page-title { font-size: 20px; font-weight: 700; color: #1a2b28; display: block; }
.page-desc { font-size: 13px; color: #6b8280; margin-top: 2px; display: block; }

.empty {
  padding: 60px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.empty-icon { font-size: 56px; }
.empty-text { font-size: 16px; color: #4a5c58; font-weight: 600; }
.empty-desc { font-size: 14px; color: #6b8280; }

.wrong-list { padding: 0 16px; display: flex; flex-direction: column; gap: 10px; }

.w-card {
  background: white;
  border-radius: 14px;
  padding: 14px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.w-meta { display: flex; gap: 6px; }
.w-tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #e8f5f2; color: #2d8a7b; }
.w-tag.type { background: #e8f0f5; color: #3b6f9e; }
.w-tag.bad { background: #fde8e8; color: #dc2626; }
.w-stem { font-size: 14px; color: #1a2b28; line-height: 1.5; }
.w-answer { display: flex; gap: 8px; align-items: baseline; }
.w-label { font-size: 12px; color: #a0b0ac; flex-shrink: 0; }
.w-value { font-size: 14px; font-weight: 600; }
.w-value.wrong { color: #dc2626; }
.w-value.correct { color: #16a34a; }
</style>

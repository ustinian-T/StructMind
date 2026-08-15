<template>
  <view class="ai-page">
    <view class="page-header">
      <view>
        <text class="page-title">AI 导师</text>
        <text class="page-desc">{{ tutorMode === 'multi-agent' ? '多智能体协作答疑' : '苏格拉底式引导答疑' }}</text>
      </view>
      <view class="model-status" @tap="goAISettings">
        <text class="model-status-label">当前模型</text>
        <text class="model-status-value">{{ aiConfig.default_model || '点击配置' }}</text>
      </view>
    </view>

    <!-- 导师模式切换 -->
    <view class="mode-switch-bar">
      <view
        class="mode-switch-item"
        :class="{ active: tutorMode === 'standard' }"
        @tap="switchMode('standard')"
      >
        <text>标准导师</text>
      </view>
      <view
        class="mode-switch-item"
        :class="{ active: tutorMode === 'multi-agent' }"
        @tap="switchMode('multi-agent')"
      >
        <text>多智能体</text>
      </view>
    </view>

    <!-- 对话区域使用 SmChat 组件 -->
    <SmChat
      :messages="messages"
      :streaming="streaming"
      :streamContent="streamContent"
      :inputValue="userInput"
      inputPlaceholder="输入你的问题或思考..."
      :examples="exampleQuestions"
      emptyIcon=""
      emptyTitle="我是你的数据结构AI导师"
      emptyDesc="我不会直接给你答案，而是通过提问和引导，帮助你真正理解数据结构的核心概念。"
      assistantAvatar=""
      :richContent="true"
      @send="sendMessage"
      @stop="stopStreaming"
      @ask-example="askExample"
      @update:inputValue="userInput = $event"
    >
      <template #input-prefix>
        <view class="new-chat-btn" @tap="startNewChat">
          <text>新对话</text>
        </view>
      </template>
    </SmChat>

    <!-- 对话状态 -->
    <view class="conv-status" v-if="conversationId">
      <text>对话 #{{ conversationId }}{{ tutorMode === 'multi-agent' ? '  · 多智能体模式' : '' }}</text>
    </view>
    <view class="summary-card" v-if="conversationSummary">
      <text class="summary-title">规则摘要</text>
      <text class="summary-status">由确定性规则生成，每条结论可追溯到原消息</text>
      <view class="summary-fact" v-for="fact in summaryFacts" :key="fact.message_id">
        <text>{{ fact.text }}</text>
        <text class="summary-ref">依据：{{ fact.message_id }}</text>
      </view>
    </view>

    <SmToast :visible="toastVisible" :message="toastMsg" :type="toastType" @close="toastVisible = false" />
  </view>
</template>

<script>
import SmChat from '@/components/SmChat.vue'
import SmToast from '@/components/SmToast.vue'
import { callCloud } from '@/utils/cloud.js'

export default {
  components: { SmChat, SmToast },
  data() {
    return {
      messages: Array(),
      userInput: '',
      streaming: false,
      streamContent: '',
      streamConvId: null,
      conversationId: null,
      conversationSummary: null,
      tutorMode: 'standard',   // 'standard' | 'multi-agent'
      toastVisible: false,
      toastMsg: '',
      toastType: 'info',
      aiConfig: { default_model: '', ai_configured: false },
      exampleQuestions: [
        '二叉树的三种遍历有什么区别？什么场景用哪种？',
        '哈希表冲突解决有哪些方法？各自的优缺点？',
        '快速排序和归并排序的时间复杂度分析怎么做？',
        '如何判断一个图是否有环？',
      ],
    }
  },
  onShow() { this.loadAIConfig() },
  methods: {
    async loadAIConfig() {
      const token = getApp().globalData?.token
      if (!token) return
      try {
        this.aiConfig = await callCloud('structmind-ai', 'getAIConfig', { token })
      } catch (e) {
        this.aiConfig = { default_model: '', ai_configured: false }
      }
    },
    goAISettings() { uni.navigateTo({ url: '/pages/ai-settings/ai-settings' }) },
    switchMode(mode) {
      if (mode === this.tutorMode) return
      this.tutorMode = mode
      // Reset conversation when switching modes
      this.messages = []
      this.conversationId = null
      this.streamContent = ''
      this.streaming = false
      this.conversationSummary = null
    },
    askExample(question) {
      this.userInput = question
      this.sendMessage()
    },
    startNewChat() {
      this.messages = []
      this.conversationId = null
      this.streamContent = ''
      this.streaming = false
    },
    stopStreaming() {
      // 当前云函数返回一次性 events 数组（非真正的 SSE/WebSocket），无法
      // 在中途真正中断。这里只把本地状态收回，提示用户已停止；后端请求
      // 完成后会被丢弃。
      if (!this.streaming) return
      this.streaming = false
      this.streamContent = ''
      this.messages.push({ role: 'assistant', content: '（用户已停止本次生成）' })
    },
    async sendMessage() {
      const msg = this.userInput.trim()
      if (!msg || this.streaming) return
      if (!this.aiConfig.default_model) {
        this.showToast('请先配置并选择一个 AI 模型', 'error')
        this.goAISettings()
        return
      }
      this.messages.push({ role: 'user', content: msg })
      this.userInput = ''
      this.streaming = true
      this.streamContent = ''

      const app = getApp()
      const auth = app.globalData

      try {
        const data = await callCloud('structmind-ai', 'tutor', {
          token: auth.token,
          message: msg,
          conversation_id: this.conversationId,
          mode: this.tutorMode,
        })
        const events = Array.isArray(data.events) ? data.events : []
        let reply = ''
        events.forEach((event) => {
          if (event.protocol !== 'structmind.agent.v1') return
          if (event.type === 'delta' && event.content) {
            reply += event.content
            this.streamContent = reply
          }
          if (event.type === 'done' && event.conversation_id) {
            this.streamConvId = event.conversation_id
          }
          if (event.type === 'error') {
            throw new Error(event.message || 'Agent执行失败')
          }
        })
        this.messages.push({ role: 'assistant', content: reply || data.message || '暂未获得回复' })
        this.conversationId = data.conversation_id || this.streamConvId
        await this.refreshConversationSummary()
      } catch (err) {
        const needsConfig = ['AI_CONFIG_REQUIRED', 'AI_PROVIDER_NOT_CONFIGURED', 'AI_CREDENTIAL_INVALID'].includes(err.code)
        this.messages.push({ role: 'assistant', content: needsConfig ? '当前模型尚未正确配置，请检查 API Key 或重新选择模型。' : '抱歉，AI服务暂时不可用，请稍后重试。' })
        this.showToast(needsConfig ? '请检查我的 AI 模型' : 'AI服务暂不可用', 'error')
      } finally {
        this.streaming = false
        this.streamContent = ''
        this.streamConvId = null
      }
    },
    async refreshConversationSummary() {
      if (!this.conversationId) return
      try {
        const data = await callCloud('structmind-learning', 'summarizeConversation', {
          token: getApp().globalData?.token,
          conversation_id: this.conversationId,
        })
        this.conversationSummary = data.summary?.summary_final || data.summary?.summary_rule || null
      } catch (e) { this.conversationSummary = null }
    },

    showToast(msg, type = 'info') {
      this.toastMsg = msg
      this.toastType = type
      this.toastVisible = true
    },
  },
  computed: {
    summaryFacts() {
      if (!this.conversationSummary) return []
      return [
        ...(this.conversationSummary.student_understanding || []),
        ...(this.conversationSummary.misconceptions || []),
        ...(this.conversationSummary.next_steps || []),
      ].filter(item => item && item.message_id)
    },
  },
}
</script>

<style scoped>
.ai-page {
  min-height: 100vh;
  background: #f3f7f0;
  display: flex;
  flex-direction: column;
}
.page-header {
  padding: 12px 16px 8px;
  background: #fff;
  border-bottom: 1px solid #edf2f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.page-title { font-size: 20px; font-weight: 700; color: #1a2b28; display: block; }
.page-desc { font-size: 13px; color: #6b8280; margin-top: 2px; display: block; }
.model-status { max-width: 48%; padding: 8px 12px; border-radius: 12px; border: 1px solid #dce8d9; background: linear-gradient(135deg, #f4faf1, #edf7ec); }
.model-status-label, .model-status-value { display: block; text-align: right; }
.model-status-label { color: #83968a; font-size: 10px; }
.model-status-value { margin-top: 2px; color: #3e744b; font-size: 12px; font-weight: 650; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Mode Switch Bar */
.mode-switch-bar {
  display: flex; margin: 10px 16px 0; background: #fff;
  border-radius: 14px; border: 1px solid #edf2f0; overflow: hidden;
}
.mode-switch-item {
  flex: 1; padding: 10px 0; text-align: center; font-size: 14px;
  font-weight: 500; color: #6b8280; transition: all 0.2s;
}
.mode-switch-item.active {
  background: #477a50; color: #fff;
  font-weight: 600;
}

.new-chat-btn {
  padding: 6px 12px; border-radius: 12px; background: #fffefb;
  border: 1px solid #d8e4d3; margin-right: 8px;
}
.new-chat-btn text { font-size: 12px; color: #6b8280; }
.conv-status { padding: 6px 16px 12px; }
.conv-status text { font-size: 11px; color: #a0b0ac; }
.summary-card { margin: 0 16px 12px; padding: 14px; border-radius: 14px; background: #fff; border: 1px solid #dce5e3; display: flex; flex-direction: column; gap: 8px; }
.summary-title { font-size: 15px; font-weight: 700; color: #1a2b28; }
.summary-status, .summary-ref { font-size: 11px; color: #6b8280; }
.summary-fact { display: flex; flex-direction: column; gap: 3px; padding-top: 8px; border-top: 1px solid #edf2f0; font-size: 13px; color: #4a5c58; }
</style>

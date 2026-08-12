<template>
  <view class="ai-page">
    <view class="page-header">
      <text class="page-title">AI 导师</text>
      <text class="page-desc">{{ tutorMode === 'multi-agent' ? '多智能体协作答疑' : '苏格拉底式引导答疑' }}</text>
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
      tutorMode: 'standard',   // 'standard' | 'multi-agent'
      toastVisible: false,
      toastMsg: '',
      toastType: 'info',
      exampleQuestions: [
        '二叉树的三种遍历有什么区别？什么场景用哪种？',
        '哈希表冲突解决有哪些方法？各自的优缺点？',
        '快速排序和归并排序的时间复杂度分析怎么做？',
        '如何判断一个图是否有环？',
      ],
    }
  },
  methods: {
    switchMode(mode) {
      if (mode === this.tutorMode) return
      this.tutorMode = mode
      // Reset conversation when switching modes
      this.messages = []
      this.conversationId = null
      this.streamContent = ''
      this.streaming = false
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
    async sendMessage() {
      const msg = this.userInput.trim()
      if (!msg || this.streaming) return
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
      } catch (err) {
        this.messages.push({ role: 'assistant', content: '抱歉，AI服务暂时不可用。请检查API配置或网络连接。' })
        this.showToast('AI服务暂不可用', 'error')
      } finally {
        this.streaming = false
        this.streamContent = ''
        this.streamConvId = null
      }
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
.ai-page {
  min-height: 100vh;
  background: #f5f8f7;
  display: flex;
  flex-direction: column;
}
.page-header {
  padding: 12px 16px 8px;
  background: #fff;
  border-bottom: 1px solid #edf2f0;
}
.page-title { font-size: 20px; font-weight: 700; color: #1a2b28; display: block; }
.page-desc { font-size: 13px; color: #6b8280; margin-top: 2px; display: block; }

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
  background: linear-gradient(135deg, #2d8a7b, #47b5a3); color: #fff;
  font-weight: 600;
}

.new-chat-btn {
  padding: 6px 12px; border-radius: 16px; background: #f5f8f7;
  border: 1px solid #dce5e3; margin-right: 8px;
}
.new-chat-btn text { font-size: 12px; color: #6b8280; }
.conv-status { padding: 6px 16px 12px; }
.conv-status text { font-size: 11px; color: #a0b0ac; }
</style>

<template>
  <view class="ai-page">
    <view class="page-header">
      <text class="page-title">AI 导师</text>
      <text class="page-desc">苏格拉底式引导答疑</text>
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
      <text>对话 #{{ conversationId }}</text>
    </view>

    <SmToast :visible="toastVisible" :message="toastMsg" :type="toastType" @close="toastVisible = false" />
  </view>
</template>

<script>
import SmChat from '@/components/SmChat.vue'
import SmToast from '@/components/SmToast.vue'
// getApp() 是 uni-app 全局函数，无需导入

export default {
  components: { SmChat, SmToast },
  data() {
    return {
      messages: [],
      userInput: '',
      streaming: false,
      streamContent: '',
      conversationId: null,
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
      const apiBase = app.globalData.apiBase || 'https://datastytest.tshai.top'

      try {
        const res = await uni.request({
          url: `${apiBase}/api/ai/tutor`,
          method: 'POST',
          header: auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
          data: {
            message: msg,
            conversation_id: this.conversationId,
          },
        })
        const data = res.data
        this.messages.push({ role: 'assistant', content: data.reply })
        this.conversationId = data.conversation_id
      } catch (err) {
        this.messages.push({ role: 'assistant', content: '抱歉，AI服务暂时不可用。请检查API配置或网络连接。' })
        this.showToast('AI服务暂不可用', 'error')
      } finally {
        this.streaming = false
        this.streamContent = ''
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
.new-chat-btn {
  padding: 6px 12px; border-radius: 16px; background: #f5f8f7;
  border: 1px solid #dce5e3; margin-right: 8px;
}
.new-chat-btn text { font-size: 12px; color: #6b8280; }
.conv-status { padding: 6px 16px 12px; }
.conv-status text { font-size: 11px; color: #a0b0ac; }
</style>

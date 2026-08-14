<template>
  <view class="sm-chat">
    <scroll-view class="sm-chat-messages" scroll-y :scroll-top="scrollTop" ref="chatArea">
      <!-- 空状态 -->
      <view class="sm-chat-empty" v-if="messages.length === 0">
        <text class="sm-chat-empty-icon">{{ emptyIcon }}</text>
        <text class="sm-chat-empty-title">{{ emptyTitle }}</text>
        <text class="sm-chat-empty-desc">{{ emptyDesc }}</text>
        <view class="sm-chat-examples" v-if="examples.length">
          <text class="sm-chat-examples-label">试试这些问题：</text>
          <view
            class="sm-chat-example"
            v-for="(ex, i) in examples"
            :key="i"
            @click="$emit('ask-example', ex)"
          >
            <text>{{ ex }}</text>
          </view>
        </view>
      </view>

      <!-- 消息列表 -->
      <view
        class="sm-chat-msg"
        :class="msg.role"
        v-for="(msg, idx) in messages"
        :key="idx"
        :animation="msg._animating ? fadeInAnimation : ''"
      >
        <view class="sm-chat-avatar">
          <text>{{ msg.role === 'user' ? userAvatar : assistantAvatar }}</text>
        </view>
        <view class="sm-chat-bubble">
          <rich-text v-if="richContent" :nodes="formatContent(msg.content)"></rich-text>
          <text v-else>{{ msg.content }}</text>
        </view>
      </view>

      <!-- 打字指示器 -->
      <view class="sm-chat-msg assistant" v-if="streaming">
        <view class="sm-chat-avatar">
          <text>{{ assistantAvatar }}</text>
        </view>
        <view class="sm-chat-bubble sm-chat-typing">
          <view class="sm-typing-dots">
            <view class="sm-typing-dot"></view>
            <view class="sm-typing-dot"></view>
            <view class="sm-typing-dot"></view>
          </view>
        </view>
      </view>

      <!-- 流式内容 -->
      <view class="sm-chat-msg assistant" v-if="streaming && streamContent">
        <view class="sm-chat-avatar">
          <text>{{ assistantAvatar }}</text>
        </view>
        <view class="sm-chat-bubble">
          <text>{{ streamContent }}</text>
          <text class="sm-stream-cursor">|</text>
        </view>
      </view>
    </scroll-view>

    <!-- 输入区域 -->
    <view class="sm-chat-input-area">
      <slot name="input-prefix"></slot>
      <input
        class="sm-chat-input"
        :value="inputValue"
        @input="onInput"
        :placeholder="inputPlaceholder"
        :disabled="streaming"
        :confirm-type="confirmType"
        @confirm="$emit('send')"
      />
      <button
        class="sm-chat-send"
        :disabled="streaming || !inputValue"
        @click="$emit('send')"
      >
        <text>发送</text>
      </button>
    </view>
  </view>
</template>

<script>
export default {
  props: {
    messages: { type: Array, default: () => [] },
    streaming: { type: Boolean, default: false },
    streamContent: { type: String, default: '' },
    inputValue: { type: String, default: '' },
    inputPlaceholder: { type: String, default: '输入消息...' },
    confirmType: { type: String, default: 'send' },
    richContent: { type: Boolean, default: false },
    emptyIcon: { type: String, default: '💬' },
    emptyTitle: { type: String, default: '开始对话' },
    emptyDesc: { type: String, default: '发送消息开始与AI导师对话' },
    examples: { type: Array, default: () => [] },
    userAvatar: { type: String, default: '👤' },
    assistantAvatar: { type: String, default: '🦉' },
    scrollTop: { type: Number, default: 0 },
  },
  emits: ['ask-example', 'send', 'update:inputValue', 'update:scrollTop'],
  data() {
    return { fadeInAnimation: '' }
  },
  methods: {
    onInput(e) {
      this.$emit('update:inputValue', e.detail.value)
    },
    formatContent(text) {
      return (text || '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/`(.+?)`/g, '<code style="background:rgba(45,138,123,0.06);border:1px solid rgba(45,138,123,0.12);border-radius:4px;padding:1px 6px;font-family:monospace">$1</code>')
        .replace(/\n/g, '<br/>')
    },
    scrollToBottom() {
      this.$emit('update:scrollTop', 99999)
    },
  },
}
</script>

<style scoped>
.sm-chat { display: flex; flex-direction: column; height: 100%; }
.sm-chat-messages { flex: 1; overflow-y: auto; padding: 16px; }

/* 空状态 */
.sm-chat-empty { display: flex; flex-direction: column; align-items: center; padding: 40px 20px; gap: 10px; }
.sm-chat-empty-icon { font-size: 56px; }
.sm-chat-empty-title { font-size: 17px; font-weight: 600; color: #1a2b28; }
.sm-chat-empty-desc { font-size: 14px; color: #6b8280; text-align: center; line-height: 1.5; max-width: 280px; }
.sm-chat-examples { margin-top: 12px; width: 100%; display: flex; flex-direction: column; gap: 8px; }
.sm-chat-examples-label { font-size: 13px; color: #a0b0ac; }
.sm-chat-example {
  background: #fff; border-radius: 12px; padding: 12px 14px;
  border: 1px solid #edf2f0; cursor: pointer;
}
.sm-chat-example text { font-size: 14px; color: #477a50; }

/* 消息 */
.sm-chat-msg { display: flex; gap: 10px; margin-bottom: 16px; }
.sm-chat-msg.user { flex-direction: row-reverse; }
.sm-chat-avatar {
  width: 36px; height: 36px; border-radius: 12px; flex-shrink: 0;
  background: #edf5e9; display: flex; align-items: center; justify-content: center;
}
.sm-chat-bubble {
  max-width: 75%; padding: 10px 14px; border-radius: 16px;
  font-size: 15px; line-height: 1.6;
}
.sm-chat-msg.user .sm-chat-bubble {
  background: #477a50; color: #fff;
  border-bottom-right-radius: 4px;
}
.sm-chat-msg.assistant .sm-chat-bubble {
  background: #fff; color: #1a2b28; border: 1px solid #edf2f0;
  border-bottom-left-radius: 4px;
}

/* 打字指示器 */
.sm-chat-typing { padding: 14px 18px; }
.sm-typing-dots { display: flex; gap: 4px; }
.sm-typing-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #a0b0ac;
  animation: sm-dot-bounce 1.4s ease-in-out infinite;
}
.sm-typing-dot:nth-child(2) { animation-delay: 0.2s; }
.sm-typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes sm-dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

.sm-stream-cursor { animation: sm-blink 1s infinite; color: #477a50; }
@keyframes sm-blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }

/* 输入区 */
.sm-chat-input-area {
  display: flex; gap: 10px; padding: 12px 16px;
  background: #fffefb; border-top: 1px solid #dfe9da; align-items: center;
}
.sm-chat-input {
  flex: 1; height: 44px; background: #fff; border: 1px solid #d8e4d3;
  border-radius: 22px; padding: 0 18px; font-size: 15px;
}
.sm-chat-send {
  width: 64px; height: 44px; border-radius: 22px; border: none;
  background: #477a50; color: #fff;
  font-weight: 600; display: flex; align-items: center; justify-content: center;
  cursor: pointer;
}
.sm-chat-send[disabled] { opacity: 0.5; }
</style>

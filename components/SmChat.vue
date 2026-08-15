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

      <!-- 思考中（首 token 到达前的占位 + 中断按钮） -->
      <view class="sm-chat-msg assistant" v-if="streaming && !streamContent">
        <view class="sm-chat-avatar">
          <text>{{ assistantAvatar }}</text>
        </view>
        <view class="sm-chat-bubble sm-chat-thinking">
          <view class="sm-thinking-pulse" aria-hidden="true"></view>
          <text class="sm-thinking-label">思考中…</text>
          <button class="sm-thinking-stop" @click="$emit('stop')">停止</button>
        </view>
      </view>

      <!-- 流式内容：打字机光标（高亮底色 + 渐变尾） -->
      <view class="sm-chat-msg assistant" v-if="streaming && streamContent">
        <view class="sm-chat-avatar">
          <text>{{ assistantAvatar }}</text>
        </view>
        <view class="sm-chat-bubble">
          <text>{{ streamContent }}</text>
          <text class="sm-stream-caret" aria-hidden="true">▍</text>
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
        v-if="!streaming"
        class="sm-chat-send"
        :disabled="!inputValue"
        @click="$emit('send')"
      >
        <text>发送</text>
      </button>
      <button
        v-else
        class="sm-chat-stop"
        @click="$emit('stop')"
      >
        <text>停止</text>
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
  emits: ['ask-example', 'send', 'stop', 'update:inputValue', 'update:scrollTop'],
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

/* 思考中（首 token 到达前 + 中断按钮） */
.sm-chat-thinking {
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 180px;
}
.sm-thinking-pulse {
  width: 10px; height: 10px; border-radius: 50%;
  background: linear-gradient(135deg, #477a50, #6caa72);
  animation: sm-pulse 1.2s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes sm-pulse {
  0%, 100% { transform: scale(.7); opacity: .55; }
  50% { transform: scale(1.15); opacity: 1; }
}
.sm-thinking-label {
  font-size: 13px;
  color: #6b8280;
  letter-spacing: .02em;
  flex: 1;
}
.sm-thinking-stop {
  background: transparent;
  border: 1px solid #d8e4d3;
  color: #b84b42;
  border-radius: 999px;
  padding: 3px 12px;
  font-size: 12px;
  line-height: 1.4;
  cursor: pointer;
}
.sm-thinking-stop:active { background: #fff0ee; }

/* 流式光标（打字机）—— 高亮底色 + 渐变尾 */
.sm-stream-caret {
  display: inline-block;
  margin-left: 2px;
  font-size: 18px;
  line-height: 1;
  color: #477a50;
  background: linear-gradient(180deg, transparent 0%, transparent 40%, rgba(71, 122, 80, .18) 40%, rgba(71, 122, 80, .18) 80%, transparent 80%);
  animation: sm-caret-blink 1s steps(2, jump-none) infinite;
}
@keyframes sm-caret-blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: .15; }
}

/* 输入区 */
.sm-chat-input-area {
  display: flex; gap: 10px; padding: 12px 16px;
  background: #fffefb; border-top: 1px solid #dfe9da; align-items: center;
}
.sm-chat-input {
  flex: 1; height: 44px; background: #fff; border: 1px solid #d8e4d3;
  border-radius: 22px; padding: 0 18px; font-size: 15px;
}
.sm-chat-send, .sm-chat-stop {
  width: 64px; height: 44px; border-radius: 22px; border: none;
  background: #477a50; color: #fff;
  font-weight: 600; display: flex; align-items: center; justify-content: center;
  cursor: pointer;
}
.sm-chat-send[disabled] { opacity: 0.5; }
.sm-chat-stop { background: #b84b42; }
</style>

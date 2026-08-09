<template>
  <view class="sm-question" :class="{ 'sm-question-correct': result === 'correct', 'sm-question-wrong': result === 'wrong' }">
    <!-- 题目头部 -->
    <view class="q-header">
      <view class="q-tags">
        <text class="q-tag" v-if="chapter">{{ chapter }}</text>
        <text class="q-tag q-tag-type">{{ qtype }}</text>
        <text class="q-tag q-tag-info" v-if="aiCompleted">AI补全</text>
        <text class="q-tag q-tag-warn" v-if="repaired">已校验</text>
      </view>
      <view class="q-number">#{{ sourceOrder || id }}</view>
    </view>

    <!-- AI补全提示 -->
    <view class="q-notice" v-if="aiCompleted">
      <text>{{ completionNote || '本题显示文本已由AI补全表修复，标准答案不变' }}</text>
    </view>

    <!-- 题干 -->
    <view class="q-stem">
      <rich-text :nodes="renderedStem"></rich-text>
    </view>

    <!-- 配图 -->
    <image v-for="(img, i) in images" :key="i" :src="img" class="q-image" mode="widthFix" />

    <!-- 选项 -->
    <view class="q-options" v-if="hasOptions">
      <view
        v-for="opt in displayOptions"
        :key="opt.key"
        :class="['q-option', { selected: isSelected(opt.key) }]"
        @click="toggleOption(opt.key)"
      >
        <view class="q-option-radio" :class="{ checked: isSelected(opt.key) }">
          <text v-if="isSelected(opt.key)">●</text>
        </view>
        <view class="q-option-content">
          <text class="q-option-key">{{ opt.key }}.</text>
          <text>{{ opt.text }}</text>
          <text class="q-option-note" v-if="opt.aiSupplemented">AI补全</text>
        </view>
      </view>
    </view>

    <!-- 填空/简答输入 -->
    <view class="q-input-area" v-else>
      <textarea
        v-if="qtype === '简答题'"
        class="q-textarea"
        :value="textAnswer"
        @input="textAnswer = $event.detail.value"
        placeholder="写出你的解题过程或关键结论..."
      />
      <input
        v-else
        class="q-input"
        :value="textAnswer"
        @input="textAnswer = $event.detail.value"
        placeholder="输入答案"
      />
    </view>

    <!-- AI解析按钮 -->
    <view class="q-ai-btn" v-if="showAiButton" @click="$emit('ai-analyze')">
      <text>🤖 AI 解析</text>
    </view>

    <!-- 结果展示 -->
    <view class="q-result" v-if="showResult">
      <view class="q-result-head">
        <text class="q-result-icon">{{ result === 'correct' ? '✅' : '❌' }}</text>
        <text class="q-result-text">{{ result === 'correct' ? '回答正确！' : '回答错误' }}</text>
      </view>
      <view class="q-answer-line" v-if="correctAnswer">
        <text class="q-answer-label">正确答案</text>
        <text class="q-answer-value">{{ correctAnswer }}</text>
      </view>
      <view class="q-answer-line" v-if="analysis">
        <text class="q-answer-label">解析</text>
        <rich-text :nodes="analysis"></rich-text>
      </view>
    </view>
  </view>
</template>

<script>
export default {
  props: {
    id: { type: [Number, String], default: 0 },
    sourceOrder: { type: Number, default: 0 },
    qtype: { type: String, default: '单选题' },
    chapter: { type: String, default: '' },
    stem: { type: String, default: '' },
    options: { type: Array, default: () => [] },
    images: { type: Array, default: () => [] },
    aiCompleted: { type: Boolean, default: false },
    repaired: { type: Boolean, default: false },
    completionNote: { type: String, default: '' },
    answer: { type: String, default: '' },        // 正确答案
    analysis: { type: String, default: '' },
    result: { type: String, default: '' },         // '' | 'correct' | 'wrong'
    showResult: { type: Boolean, default: false },
    showAiButton: { type: Boolean, default: true },
  },
  emits: ['update:answer', 'ai-analyze'],
  data() {
    return {
      selectedKeys: [],
      textAnswer: '',
    }
  },
  computed: {
    hasOptions() {
      return this.qtype === '单选题' || this.qtype === '多选题' || this.qtype === '判断题'
    },
    displayOptions() {
      if (this.options.length > 0) return this.options
      return [{ key: 'A', text: '对' }, { key: 'B', text: '错' }]
    },
    correctAnswer() {
      return this.answer
    },
    renderedStem() {
      return (this.stem || '').replace(/\[IMAGE:.*?\]/g, '')
    },
  },
  methods: {
    isSelected(key) {
      return this.selectedKeys.includes(key)
    },
    toggleOption(key) {
      if (this.qtype === '多选题') {
        const idx = this.selectedKeys.indexOf(key)
        if (idx >= 0) this.selectedKeys.splice(idx, 1)
        else this.selectedKeys.push(key)
      } else {
        this.selectedKeys = [key]
      }
      this.$emit('update:answer', this.qtype === '多选题' ? [...this.selectedKeys] : this.selectedKeys[0] || '')
    },
    getAnswer() {
      return this.hasOptions
        ? (this.qtype === '多选题' ? this.selectedKeys : this.selectedKeys[0] || '')
        : this.textAnswer.trim()
    },
  },
}
</script>

<style scoped>
.sm-question { padding: 16px; border-radius: 16px; background: #fff; border: 1.5px solid #edf2f0; transition: border-color 0.2s; }
.sm-question-correct { border-color: #bbf7d0; background: #fafdfb; }
.sm-question-wrong { border-color: #fecaca; background: #fefafa; }

.q-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 6px; }
.q-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.q-tag { font-size: 11px; padding: 3px 10px; border-radius: 20px; background: #e8f5f2; color: #2d8a7b; }
.q-tag-type { background: #e8f0f5; color: #3b6f9e; }
.q-tag-info { background: #dbeafe; color: #2563eb; }
.q-tag-warn { background: #fef3c7; color: #a16207; }
.q-number { font-size: 12px; color: #a0b0ac; }

.q-notice { margin-bottom: 8px; padding: 8px 12px; border-radius: 8px; background: #e8f5f2; }
.q-notice text { font-size: 12px; color: #2d8a7b; }

.q-stem { font-size: 17px; line-height: 1.7; color: #1a2b28; margin: 10px 0; }
.q-image { max-width: 100%; border-radius: 12px; margin: 8px 0; }

.q-options { display: flex; flex-direction: column; gap: 8px; margin: 14px 0; }
.q-option {
  display: flex; align-items: flex-start; gap: 12px; padding: 14px 16px;
  border: 1.5px solid #dce5e3; border-radius: 14px; background: #f9fbfa;
  transition: all 0.15s ease;
}
.q-option:active { transform: scale(0.99); }
.q-option.selected { border-color: #2d8a7b; background: rgba(45,138,123,0.04); }
.q-option-radio {
  width: 22px; height: 22px; border-radius: 50%; border: 2px solid #c0c8c5;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 2px;
}
.q-option-radio.checked { border-color: #2d8a7b; background: #2d8a7b; }
.q-option-radio text { color: #fff; font-size: 12px; }
.q-option-content { flex: 1; }
.q-option-key { font-weight: 700; color: #2d8a7b; margin-right: 4px; }
.q-option-note { font-size: 10px; padding: 1px 6px; border-radius: 10px; background: #dbeafe; color: #2563eb; margin-left: 6px; }

.q-input-area { margin: 14px 0; }
.q-input, .q-textarea {
  width: 100%; padding: 12px 16px; border: 1.5px solid #dce5e3; border-radius: 12px;
  font-size: 16px; background: #f9fbfa;
}
.q-textarea { min-height: 100px; }
.q-input:focus, .q-textarea:focus { border-color: #2d8a7b; outline: none; }

.q-ai-btn { text-align: center; padding: 10px; color: #2d8a7b; font-size: 14px; }

.q-result { margin-top: 14px; padding: 14px; border-radius: 12px; background: #f9fbfa; }
.q-result-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.q-result-icon { font-size: 20px; }
.q-result-text { font-weight: 700; color: #1a2b28; }
.q-answer-line { margin-top: 8px; }
.q-answer-label { font-size: 12px; color: #6b8280; display: block; }
.q-answer-value { font-weight: 600; color: #1a2b28; }
</style>

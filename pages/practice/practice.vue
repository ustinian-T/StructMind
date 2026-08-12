<template>
  <view class="practice-page">
    <view class="page-header">
      <text class="page-title">题库练习</text>
      <text class="page-desc">数据结构期末 · 323道客观题</text>
    </view>

    <!-- 题型筛选 -->
    <scroll-view class="filter-scroll" scroll-x>
      <view class="filter-bar">
        <view
          class="filter-item"
          :class="{ active: activeType === '' }"
          @tap="setType('')"
        >
          <text>全部</text>
        </view>
        <view
          class="filter-item"
          v-for="t in types"
          :key="t"
          :class="{ active: activeType === t }"
          @tap="setType(t)"
        >
          <text>{{ t }}</text>
        </view>
      </view>
    </scroll-view>

    <!-- 章节筛选 -->
    <scroll-view class="filter-scroll" scroll-x style="margin-top:0;padding-top:0">
      <view class="filter-bar">
        <view
          class="filter-item chapter-filter"
          :class="{ active: activeChapter === '' }"
          @tap="setChapter('')"
        >
          <text>全部章节</text>
        </view>
        <view
          class="filter-item chapter-filter"
          v-for="ch in chapters"
          :key="ch"
          :class="{ active: activeChapter === ch }"
          @tap="setChapter(ch)"
        >
          <text>{{ ch }}</text>
        </view>
      </view>
    </scroll-view>

    <!-- ═══ Answer Mode ═══ -->
    <view v-if="answerMode && currentQ" class="answer-view">
      <!-- Question display -->
      <view class="answer-card">
        <view class="q-meta">
          <text class="q-tag">{{ currentQ.chapter }}</text>
          <text class="q-tag type">{{ currentQ.qtype }}</text>
          <text class="q-tag difficulty" v-if="currentQ.difficulty">{{ currentQ.difficulty }}</text>
          <text class="q-tag source">#{{ currentQ.source_order || currentQ.id }}</text>
        </view>
        <text class="answer-stem">{{ currentQ.stem }}</text>
      </view>

      <!-- Answer controls: radio/checkbox for choice questions -->
      <view v-if="isChoiceQ" class="answer-options">
        <label
          class="answer-option"
          :class="{ selected: isOptionSelected(opt.key) }"
          v-for="opt in displayOptions"
          :key="opt.key"
          @tap="toggleOption(opt.key)"
        >
          <view class="option-radio" :class="{ checked: isOptionSelected(opt.key), multi: isMultiQ }">
            <text v-if="isOptionSelected(opt.key)">✓</text>
          </view>
          <text class="option-text"><text class="option-key">{{ opt.key }}.</text> {{ opt.text || '选项缺失' }}</text>
        </label>
      </view>

      <!-- Answer controls: text input for fill-in-blank / short answer -->
      <view v-if="isTextQ" class="answer-input-area">
        <textarea
          v-if="currentQ.qtype === '简答题'"
          class="answer-textarea"
          v-model="userAnswer"
          placeholder="写出解题过程或结论"
          :disabled="submitting || answerResult !== null"
        />
        <input
          v-else
          class="answer-input"
          v-model="userAnswer"
          placeholder="输入填空答案"
          :disabled="submitting || answerResult !== null"
        />
      </view>

      <!-- Submit button -->
      <view class="answer-submit-area" v-if="!answerResult">
        <SmButton variant="primary" block @click="submitAnswer" :disabled="submitting || !hasAnswer">
          {{ submitting ? '提交中...' : '提交答案' }}
        </SmButton>
      </view>

      <!-- Grading result -->
      <view v-if="answerResult" class="answer-result" :class="answerResult.is_correct ? 'correct' : 'wrong'">
        <view class="result-head">
          <text class="result-icon">{{ answerResult.is_correct ? '✅' : '❌' }}</text>
          <text class="result-title">{{ answerResult.is_correct ? '回答正确！' : '回答错误' }}</text>
        </view>
        <view class="result-line" v-if="answerResult.correct_answer">
          <text class="result-label">标准答案</text>
          <text class="result-value">{{ answerResult.correct_answer }}</text>
        </view>
        <view class="result-line" v-if="answerResult.analysis">
          <text class="result-label">解析</text>
          <text class="result-value">{{ answerResult.analysis }}</text>
        </view>
      </view>

      <!-- Navigation (bottom of answer panel) -->
      <view class="answer-nav">
        <view class="nav-btn prev" @tap="prevAnswerQ" v-if="answerQIndex > 0">
          <text>上一题</text>
        </view>
        <view class="nav-btn exit" @tap="exitAnswer">
          <text>退出答题</text>
        </view>
        <view class="nav-btn next" @tap="nextAnswerQ" v-if="answerQIndex < filteredQuestions.length - 1">
          <text>下一题</text>
        </view>
      </view>
    </view>

    <!-- ═══ Browse Mode (list + swipe) ═══ -->
    <view v-else>
      <!-- 模式切换 -->
      <view class="mode-toggle" v-if="practiceMode === 'list'">
        <view class="mode-toggle-row">
          <text class="mode-result">{{ filteredQuestions.length }} 题</text>
          <view class="mode-btn" @tap="practiceMode = 'swipe'">
            <text>滑动模式</text>
          </view>
        </view>
      </view>

      <!-- 列表模式 -->
      <scroll-view class="question-list" scroll-y v-if="practiceMode === 'list'" @scrolltolower="loadMore">
        <view
          class="q-card"
          v-for="(q, i) in paginatedQuestions"
          :key="q.id"
          @tap="enterAnswer(i)"
        >
          <view class="q-meta">
            <text class="q-tag">{{ q.chapter }}</text>
            <text class="q-tag type">{{ q.qtype }}</text>
            <text class="q-tag difficulty" v-if="q.difficulty">{{ q.difficulty }}</text>
          </view>
          <text class="q-stem">{{ truncate(q.stem, 100) }}</text>
          <view class="q-footer">
            <text class="q-source">#{{ q.source_order || q.id }}</text>
            <text class="q-start-btn">开始答题</text>
          </view>
        </view>
        <view class="empty" v-if="filteredQuestions.length === 0">
          <text class="empty-icon">📚</text>
          <text class="empty-text">暂无该类型的题目</text>
        </view>
      </scroll-view>

      <!-- 滑动模式 -->
      <view class="swipe-container" v-if="practiceMode === 'swipe' && filteredQuestions.length > 0">
        <view class="swipe-header">
          <text class="swipe-counter">{{ currentIndex + 1 }} / {{ filteredQuestions.length }}</text>
          <view class="swipe-actions">
            <view class="mode-btn" @tap="practiceMode = 'list'">
              <text>列表模式</text>
            </view>
            <view class="mode-btn danger" @tap="practiceMode = 'list'; currentIndex = 0">
              <text>退出</text>
            </view>
          </view>
        </view>

        <!-- 滑动卡片 -->
        <view
          class="swipe-card"
          :style="cardStyle"
          @touchstart="onTouchStart"
          @touchmove="onTouchMove"
          @touchend="onTouchEnd"
        >
          <view class="swipe-card-inner">
            <view class="q-meta">
              <text class="q-tag">{{ currentQ.chapter }}</text>
              <text class="q-tag type">{{ currentQ.qtype }}</text>
            </view>
            <text class="q-stem full">{{ truncate(currentQ.stem, 300) }}</text>
            <view class="swipe-hint-left">上一题</view>
            <view class="swipe-hint-right">下一题</view>
          </view>
        </view>

        <!-- 卡片底部操作 -->
        <view class="swipe-quick-actions">
          <view class="swipe-btn prev" @tap="prevCard">
            <text>上一题</text>
          </view>
          <view class="swipe-btn start" @tap="enterAnswer(currentIndex)">
            <text>开始作答</text>
          </view>
          <view class="swipe-btn next" @tap="nextCard">
            <text>下一题</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 底部快捷按钮（浏览模式下显示） -->
    <view class="bottom-actions" v-if="!answerMode">
      <SmButton variant="primary" block icon="" @click="startRandom10">随机10题</SmButton>
      <SmButton variant="gradient" block @click="startRecommend">智能推荐</SmButton>
    </view>

    <!-- Toast -->
    <SmToast :visible="toastVisible" :message="toastMsg" :type="toastType" @close="toastVisible = false" />
  </view>
</template>

<script>
import SmButton from '@/components/SmButton.vue'
import SmToast from '@/components/SmToast.vue'
import { callCloud, normalizeCloudQuestion } from '@/utils/cloud.js'

export default {
  components: { SmButton, SmToast },
  data() {
    return {
      questions: Array(),
      sessionId: null,
      types: ['单选题', '多选题', '填空题', '判断题'],
      activeType: '',
      activeChapter: '',
      chapters: Array(),
      practiceMode: 'list',
      currentIndex: 0,
      pageSize: 20,
      currentPage: 1,
      cardStyle: '',
      touchStartX: 0,
      touchStartY: 0,
      touchMoved: false,
      // Answer mode
      answerMode: false,
      answerQIndex: 0,
      userAnswer: '',
      userAnswerArr: Array(),
      answerResult: null,
      submitting: false,
      toastVisible: false,
      toastMsg: '',
      toastType: 'info',
    }
  },
  computed: {
    filteredQuestions() {
      let qs = this.questions
      if (this.activeType) qs = qs.filter(q => q.qtype === this.activeType)
      if (this.activeChapter) qs = qs.filter(q => q.chapter === this.activeChapter)
      return qs
    },
    paginatedQuestions() {
      return this.filteredQuestions.slice(0, this.currentPage * this.pageSize)
    },
    currentQuestion() {
      return this.filteredQuestions[this.currentIndex] || { chapter: '', qtype: '', stem: '', id: 0 }
    },
    currentQ() {
      // The question currently being answered, or the swipe card question
      if (this.answerMode) {
        return this.filteredQuestions[this.answerQIndex] || null
      }
      return this.currentQuestion
    },
    isChoiceQ() {
      const qt = this.currentQ?.qtype || ''
      return qt === '单选题' || qt === '多选题' || qt === '判断题'
    },
    isMultiQ() {
      return this.currentQ?.qtype === '多选题'
    },
    isTextQ() {
      const qt = this.currentQ?.qtype || ''
      return qt === '填空题' || qt === '简答题'
    },
    displayOptions() {
      return this.currentQ?.options?.length
        ? this.currentQ.options
        : [{ key: 'A', text: '对' }, { key: 'B', text: '错' }]
    },
    hasAnswer() {
      if (this.isMultiQ) return this.userAnswerArr.length > 0
      return !!this.userAnswer.trim()
    },
  },
  async mounted() {
    await this.loadQuestions()
  },
  methods: {
    async loadQuestions(mode = 'sequence', limit = 200, includeWrong = false) {
      try {
        const app = getApp()
        const token = app.globalData?.token
        if (!token) {
          uni.navigateTo({ url: '/pages/login/login' })
          return
        }
        const data = await callCloud('structmind-practice', 'createSession', {
          token,
          mode,
          limit,
          include_wrong: includeWrong,
        })
        this.sessionId = data.session_id
        this.questions = (data.questions || []).map(normalizeCloudQuestion)
        const chSet = new Set(this.questions.map(q => q.chapter).filter(Boolean))
        this.chapters = [...chSet].sort()
      } catch (err) {
        console.log('Failed to load questions')
      }
    },
    setType(type) {
      this.activeType = this.activeType === type ? '' : type
      this.currentPage = 1
      this.currentIndex = 0
    },
    setChapter(ch) {
      this.activeChapter = this.activeChapter === ch ? '' : ch
      this.currentPage = 1
      this.currentIndex = 0
    },
    loadMore() {
      if (this.currentPage * this.pageSize < this.filteredQuestions.length) {
        this.currentPage++
      }
    },
    truncate(text, max) {
      const t = (text || '').replace(/\[IMAGE:.*?\]/g, '').trim()
      return t.length > max ? t.slice(0, max) + '...' : t
    },

    // ── Answer mode ──
    enterAnswer(index) {
      this.answerMode = true
      this.answerQIndex = index
      this.userAnswer = ''
      this.userAnswerArr = []
      this.answerResult = null
      this.submitting = false
    },
    exitAnswer() {
      // Sync the currentIndex for swipe mode
      if (this.practiceMode === 'swipe') {
        this.currentIndex = this.answerQIndex
      }
      this.answerMode = false
      this.answerResult = null
      this.userAnswer = ''
      this.userAnswerArr = []
    },
    prevAnswerQ() {
      if (this.answerQIndex > 0) {
        this.answerQIndex--
        this.userAnswer = ''
        this.userAnswerArr = []
        this.answerResult = null
      }
    },
    nextAnswerQ() {
      if (this.answerQIndex < this.filteredQuestions.length - 1) {
        this.answerQIndex++
        this.userAnswer = ''
        this.userAnswerArr = []
        this.answerResult = null
      }
    },
    isOptionSelected(key) {
      if (this.isMultiQ) return this.userAnswerArr.includes(key)
      return this.userAnswer === key
    },
    toggleOption(key) {
      if (this.submitting || this.answerResult) return
      if (this.isMultiQ) {
        const idx = this.userAnswerArr.indexOf(key)
        if (idx >= 0) {
          this.userAnswerArr.splice(idx, 1)
        } else {
          this.userAnswerArr.push(key)
        }
      } else {
        this.userAnswer = this.userAnswer === key ? '' : key
      }
    },
    async submitAnswer() {
      if (this.submitting || !this.hasAnswer) return
      const q = this.currentQ
      if (!q || !q.id) {
        this.showToast('题目数据异常', 'error')
        return
      }

      this.submitting = true

      // Build answer payload
      let answer
      if (this.isMultiQ) {
        answer = this.userAnswerArr.sort()
      } else {
        answer = this.userAnswer.trim()
      }

      const app = getApp()
      const auth = app.globalData

      try {
        const data = await callCloud('structmind-practice', 'submitAnswer', {
          token: auth.token,
          session_id: this.sessionId,
          question_id: q.id,
          user_answer: answer,
        })
        this.answerResult = data

      } catch (err) {
        this.showToast('提交失败，请检查网络连接', 'error')
      } finally {
        this.submitting = false
      }
    },
    // ── Quick actions ──
    startSwipePractice(qId) {
      const idx = this.filteredQuestions.findIndex(q => q.id === qId)
      if (idx >= 0) {
        this.enterAnswer(idx)
      }
    },
    async startRandom10() {
      await this.loadQuestions('random', 10)
      this.currentIndex = 0
      this.currentPage = 1
      this.showToast('已生成10道随机练习', 'success')
    },
    async startRecommend() {
      await this.loadQuestions('random', 15, true)
      this.currentIndex = 0
      this.currentPage = 1
      this.showToast('已生成错题优先练习', 'success')
    },

    // ── Swipe handlers ──
    onTouchStart(e) {
      this.touchStartX = e.touches[0].clientX
      this.touchStartY = e.touches[0].clientY
      this.touchMoved = false
    },
    onTouchMove(e) {
      if (!this.touchMoved) {
        this.touchMoved = true
      }
      const dx = e.touches[0].clientX - this.touchStartX
      const dy = e.touches[0].clientY - this.touchStartY
      if (Math.abs(dx) > Math.abs(dy)) {
        this.cardStyle = `transform: translateX(${dx}px) rotate(${dx * 0.02}deg); opacity: 1; transition: none;`
      }
    },
    onTouchEnd(e) {
      if (!this.touchMoved) return
      const dx = e.changedTouches[0].clientX - this.touchStartX
      const threshold = 80

      if (dx < -threshold) {
        this.cardStyle = 'transform: translateX(-400px); opacity: 0; transition: all 200ms ease;'
        setTimeout(() => this.nextCard(), 200)
      } else if (dx > threshold) {
        this.cardStyle = 'transform: translateX(400px); opacity: 0; transition: all 200ms ease;'
        setTimeout(() => this.prevCard(), 200)
      } else {
        this.resetCard()
      }
    },
    nextCard() {
      if (this.currentIndex < this.filteredQuestions.length - 1) {
        this.currentIndex++
        this.resetCard()
      }
    },
    prevCard() {
      if (this.currentIndex > 0) {
        this.currentIndex--
        this.resetCard()
      }
    },
    resetCard() {
      this.cardStyle = 'transform: translateX(0) rotate(0deg); opacity: 1; transition: all 200ms ease;'
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
.practice-page { min-height: 100vh; background: #f5f8f7; padding-bottom: 120px; }

.page-header { padding: 16px 16px 4px; }
.page-title { font-size: 20px; font-weight: 700; color: #1a2b28; display: block; }
.page-desc { font-size: 13px; color: #6b8280; margin-top: 2px; display: block; }

/* Filters */
.filter-scroll { white-space: nowrap; padding: 8px 0; }
.filter-bar { display: flex; gap: 8px; padding: 0 16px; }
.filter-item {
  display: inline-flex; padding: 8px 16px; border-radius: 20px;
  background: #fff; border: 1px solid #dce5e3; font-size: 13px;
  color: #6b8280; white-space: nowrap; transition: all 0.2s;
}
.filter-item.active { background: #2d8a7b; border-color: #2d8a7b; color: #fff; }
.chapter-filter { font-size: 12px; padding: 6px 12px; }

/* Mode Toggle */
.mode-toggle { padding: 8px 16px; }
.mode-toggle-row { display: flex; justify-content: space-between; align-items: center; }
.mode-result { font-size: 13px; color: #6b8280; }
.mode-btn {
  padding: 6px 14px; border-radius: 20px; background: #e8f5f2; color: #2d8a7b;
  font-size: 13px; font-weight: 500;
}
.mode-btn.danger { background: #fef2f2; color: #dc2626; }

/* Question List */
.question-list { padding: 0 16px; height: calc(100vh - 340px); }
.q-card {
  background: #fff; border-radius: 14px; padding: 14px;
  margin-bottom: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.03);
  transition: transform 0.2s, opacity 0.2s;
}
.q-card:active { transform: scale(0.98); }
.q-meta { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.q-tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #e8f5f2; color: #2d8a7b; }
.q-tag.type { background: #e8f0f5; color: #3b6f9e; }
.q-tag.difficulty { background: #fef3c7; color: #a16207; }
.q-tag.source { background: #f5f5f5; color: #a0b0ac; }
.q-stem { font-size: 14px; color: #1a2b28; line-height: 1.5; display: block; }
.q-stem.full { font-size: 16px; line-height: 1.7; }
.q-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.q-source { font-size: 11px; color: #a0b0ac; }
.q-start-btn { font-size: 12px; color: #2d8a7b; font-weight: 600; }

/* Empty */
.empty { padding: 40px 20px; text-align: center; }
.empty-icon { font-size: 48px; display: block; margin-bottom: 8px; }
.empty-text { font-size: 15px; color: #6b8280; }

/* Swipe Mode */
.swipe-container { padding: 8px 16px; display: flex; flex-direction: column; gap: 12px; }
.swipe-header { display: flex; justify-content: space-between; align-items: center; }
.swipe-counter { font-size: 14px; font-weight: 600; color: #4a5c58; }
.swipe-actions { display: flex; gap: 8px; }

.swipe-card {
  background: #fff; border-radius: 20px; box-shadow: 0 4px 24px rgba(0,0,0,0.06);
  min-height: 260px; position: relative; overflow: hidden;
  touch-action: pan-y; user-select: none;
}
.swipe-card-inner { padding: 20px; }
.swipe-hint-left, .swipe-hint-right {
  position: absolute; top: 50%; transform: translateY(-50%);
  font-size: 12px; color: #a0b0ac; pointer-events: none;
}
.swipe-hint-left { left: 12px; }
.swipe-hint-right { right: 12px; }

.swipe-quick-actions { display: flex; gap: 10px; }
.swipe-btn {
  flex: 1; padding: 12px; border-radius: 14px; text-align: center;
  background: #f5f8f7; border: 1px solid #dce5e3; font-size: 14px;
  font-weight: 600; color: #4a5c58;
}
.swipe-btn.start { background: linear-gradient(135deg, #2d8a7b, #47b5a3); color: #fff; border: none; }

/* ═══ Answer Mode ═══ */
.answer-view {
  padding: 0 16px 120px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.answer-card {
  background: #fff; border-radius: 14px; padding: 16px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
}
.answer-stem {
  font-size: 16px; line-height: 1.75; color: #1a2b28;
  display: block; margin-top: 8px; white-space: pre-wrap;
}

/* Answer options (reuse from design system) */
.answer-options { display: grid; gap: 10px; }
.answer-option {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 14px 16px; border: 1.5px solid #dce5e3; border-radius: 12px;
  background: #f5f8f7; transition: all 0.15s ease;
}
.answer-option:active { transform: scale(0.98); }
.answer-option.selected {
  border-color: #2d8a7b; background: rgba(45,138,123,0.04);
}
.option-radio {
  width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  border: 2px solid #dce5e3; background: #fff; margin-top: 1px;
}
.option-radio.checked { background: #2d8a7b; border-color: #2d8a7b; color: #fff; }
.option-radio.multi { border-radius: 6px; }
.option-radio text { font-size: 12px; font-weight: 700; }
.option-text { font-size: 15px; color: #1a2b28; line-height: 1.5; }
.option-key { font-weight: 700; color: #2d8a7b; }

/* Answer text input */
.answer-input-area { padding: 4px 0; }
.answer-input {
  width: 100%; height: 48px; padding: 0 14px;
  border: 1.5px solid #dce5e3; border-radius: 12px;
  background: #fff; font-size: 16px; color: #1a2b28;
}
.answer-textarea {
  width: 100%; min-height: 120px; padding: 14px;
  border: 1.5px solid #dce5e3; border-radius: 12px;
  background: #fff; font-size: 15px; color: #1a2b28;
  line-height: 1.6;
}

/* Submit area */
.answer-submit-area { padding: 4px 0; }

/* Grading result */
.answer-result {
  padding: 16px; border-radius: 14px; border: 1.5px solid;
}
.answer-result.correct { background: #f0fdf4; border-color: #bbf7d0; }
.answer-result.wrong { background: #fef2f2; border-color: #fecaca; }
.result-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.result-icon { font-size: 24px; }
.result-title { font-size: 16px; font-weight: 700; color: #1a2b28; }
.result-line { margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(0,0,0,0.06); }
.result-label { font-size: 12px; color: #6b8280; display: block; margin-bottom: 2px; }
.result-value { font-size: 15px; color: #1a2b28; line-height: 1.6; display: block; }

/* Answer navigation */
.answer-nav {
  display: flex; gap: 10px; justify-content: center; padding: 12px 0;
}
.nav-btn {
  flex: 1; max-width: 140px; padding: 12px 0; border-radius: 14px;
  text-align: center; font-size: 14px; font-weight: 600;
  background: #f5f8f7; border: 1px solid #dce5e3; color: #4a5c58;
}
.nav-btn.exit { background: #fef2f2; border-color: #fecaca; color: #dc2626; }

/* Bottom Actions */
.bottom-actions {
  position: fixed; bottom: 0; left: 0; right: 0;
  padding: 12px 16px; padding-bottom: calc(12px + env(safe-area-inset-bottom, 0));
  background: rgba(255,255,255,0.92); backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-top: 1px solid #edf2f0; display: flex; gap: 10px;
}
</style>

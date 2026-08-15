<template>
  <view class="practice-page">
    <view class="page-header">
      <view class="page-title-row">
        <text class="page-title">题库练习</text>
      </view>
      <text class="page-desc">{{ sourceDescription }}</text>
      <view class="source-switch" role="tablist" aria-label="练习来源">
        <view
          class="source-tab"
          :class="{ active: practiceSource === 'local' }"
          role="tab"
          tabindex="0"
          @tap="activateSource('local')"
          @keyup.enter="activateSource('local')"
        >
          <text class="source-tab-title">本地练习</text>
          <text class="source-tab-meta">323 题 · 即开即练</text>
        </view>
        <view
          class="source-tab"
          :class="{ active: practiceSource === 'ai' }"
          role="tab"
          tabindex="0"
          @tap="openAIGenerate"
          @keyup.enter="openAIGenerate"
        >
          <text class="source-tab-title">AI 出题</text>
          <text class="source-tab-meta">按章节定制</text>
        </view>
      </view>
      <view v-if="practiceSource === 'local'" class="sync-status" :class="syncState">
        <text class="sync-dot"></text>
        <text>{{ syncMessage }}</text>
        <text v-if="syncState === 'offline'" class="sync-retry" @tap="syncCloudSession">重试同步</text>
      </view>
    </view>

    <!-- AI 出题工作区 -->
    <view v-if="practiceSource === 'ai' && !answerMode" class="ai-gen-workspace">
      <view class="ai-gen-head">
        <view>
          <text class="ai-gen-title">生成一组专属练习</text>
          <text class="ai-gen-subtitle">选择范围后，AI 题目会作为独立练习集展示。</text>
        </view>
        <text v-if="aiQuestions.length" class="ai-result-count">{{ aiQuestions.length }} 道</text>
      </view>
      <view class="ai-gen-body">
        <text class="ai-gen-label">章节</text>
        <input class="ai-gen-input" v-model="aiGenParams.chapter" placeholder="例如：栈和队列" />
        <text class="ai-gen-label">题型</text>
        <view class="ai-gen-chips">
          <view
            v-for="t in aiGenTypes"
            :key="t.value"
            class="ai-gen-chip"
            :class="{ active: aiGenParams.type === t.value }"
            @tap="aiGenParams.type = t.value"
          >
            <text>{{ t.label }}</text>
          </view>
        </view>
        <view class="ai-gen-grid">
          <view class="ai-gen-field">
            <text class="ai-gen-label">难度</text>
            <view class="ai-gen-chips">
              <view
                v-for="d in [1,2,3,4,5]"
                :key="d"
                class="ai-gen-chip compact"
                :class="{ active: aiGenParams.difficulty === d }"
                @tap="aiGenParams.difficulty = d"
              ><text>{{ d }}</text></view>
            </view>
          </view>
          <view class="ai-gen-field">
            <text class="ai-gen-label">数量</text>
            <view class="ai-gen-chips">
              <view
                v-for="n in [1,3,5]"
                :key="n"
                class="ai-gen-chip compact"
                :class="{ active: aiGenParams.count === n }"
                @tap="aiGenParams.count = n"
              ><text>{{ n }} 道</text></view>
            </view>
          </view>
        </view>
        <text v-if="aiGenError" class="ai-gen-error">{{ aiGenError }}</text>
        <view v-if="aiGenNeedsConfig" class="ai-config-link" @tap="openAISettings">
          <text>前往“我的 AI 模型”配置</text>
        </view>
        <text v-if="aiGenSuccess" class="ai-gen-success">{{ aiGenSuccess }}</text>
      </view>
      <view class="ai-gen-actions">
        <button class="ai-gen-btn ghost" @tap="closeAIGenerate">返回本地题库</button>
        <button class="ai-gen-btn primary" :disabled="aiGenSubmitting" @tap="submitAIGenerate">
          <text>{{ aiGenSubmitting ? '生成中…' : (aiQuestions.length ? '重新生成' : '生成题目') }}</text>
        </button>
      </view>
    </view>

    <!-- 题型筛选 -->
    <scroll-view v-if="practiceSource === 'local' || aiQuestions.length" class="filter-scroll" scroll-x>
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
    <scroll-view v-if="practiceSource === 'local' || aiQuestions.length" class="filter-scroll" scroll-x style="margin-top:0;padding-top:0">
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
          <text class="result-icon">{{ answerResult.is_correct ? '✓' : '×' }}</text>
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
        <view class="learning-proof" v-if="answerResult.learning_event_id">
          <text class="proof-title">本题学习轨迹</text>
          <view class="mastery-row" v-for="change in (answerResult.mastery_changes || [])" :key="change.concept">
            <text>{{ change.concept }}</text>
            <text>{{ percent(change.before_score) }} → {{ percent(change.after_score) }}（{{ signedPercent(change.delta) }}）</text>
          </view>
          <text class="proof-line" v-if="answerResult.error_reason">错因：{{ errorReasonText(answerResult.error_reason) }}</text>
          <text class="proof-line" v-if="answerResult.review_updates && answerResult.review_updates[0]">下次复习：{{ formatTime(answerResult.review_updates[0].next_review_at) }}</text>
        </view>

        <!-- AI 详细解析：答完题后可调用 structmind-ai/questionAI -->
        <view v-if="canAskAIExplain" class="ai-explain-row">
          <button class="ai-explain-btn" :disabled="aiExplainLoading" @tap="askAIExplain">
            <text>{{ aiExplainLoading ? 'AI 解析中…' : 'AI 详细解析' }}</text>
          </button>
        </view>
        <view v-if="aiExplainReply" class="ai-explain-reply">
          <text class="ai-explain-content">{{ aiExplainReply }}</text>
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
    <view v-else-if="practiceSource === 'local' || aiQuestions.length">
      <!-- 模式切换 -->
      <view class="mode-toggle" v-if="practiceMode === 'list'">
        <view class="mode-toggle-row">
          <text class="mode-result">{{ filteredQuestions.length }} 题</text>
          <view class="mode-actions">
            <view v-if="practiceSource === 'local'" class="mode-btn" @tap="startRandom10">
              <text>随机 10 题</text>
            </view>
            <view v-if="practiceSource === 'local'" class="mode-btn" @tap="resetLocalPractice">
              <text>全部题目</text>
            </view>
            <view class="mode-btn emphasized" @tap="practiceMode = 'swipe'">
              <text>滑动模式</text>
            </view>
          </view>
        </view>
      </view>

      <!-- 列表模式 -->
      <view class="question-list" v-if="practiceMode === 'list'">
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
        <view class="empty" v-if="loadingQuestions">
          <view class="empty-pulse"></view>
          <text class="empty-title">正在准备题库</text>
          <text class="empty-text">正在同步章节与练习题，请稍候</text>
        </view>
        <view class="empty empty-error" v-else-if="loadError">
          <text class="empty-kicker">连接未完成</text>
          <text class="empty-title">题库暂时没有加载成功</text>
          <text class="empty-text">{{ loadError }}</text>
          <view class="empty-actions">
            <view class="empty-retry" @tap="loadQuestions()"><text>重新加载</text></view>
            <view class="empty-retry secondary" @tap="openAIGenerate">
              <text>试试 AI 出题</text>
            </view>
          </view>
          <text class="empty-tip">
            没有题目时，可以先用"AI 出题"生成 1~5 道题练手；正式题目需要在管理后台导入
            （运行 scripts/export_question_bank.py → scripts/post_to_unicloud.py 一键灌库）。
          </text>
        </view>
        <view class="empty" v-else-if="filteredQuestions.length === 0">
          <text class="empty-kicker">当前筛选</text>
          <text class="empty-title">没有匹配的题目</text>
          <text class="empty-text">换一个题型或章节再试试</text>
        </view>
        <view
          v-if="paginatedQuestions.length < filteredQuestions.length"
          class="load-more"
          @tap="loadMore"
        ><text>继续加载 {{ Math.min(pageSize, filteredQuestions.length - paginatedQuestions.length) }} 题</text></view>
      </view>

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

    <!-- Toast -->
    <SmToast :visible="toastVisible" :message="toastMsg" :type="toastType" @close="toastVisible = false" />
  </view>
</template>

<script>
import SmButton from '@/components/SmButton.vue'
import SmToast from '@/components/SmToast.vue'
import { callCloud, getErrorMessage } from '@/utils/cloud.js'
import localExamQuestions from '@/static/data/exam_questions.json'
import {
  extractGeneratedQuestions,
  getPracticeErrorCode,
  gradePracticeAnswer,
  normalizeQuestionList,
  pickRandomQuestions,
  selectPracticeQuestions,
  toQuestionTypeValue,
} from '@/utils/practice-core.mjs'

export default {
  components: { SmButton, SmToast },
  data() {
    return {
      questions: Array(),
      localQuestions: Array(),
      aiQuestions: Array(),
      practiceSource: 'local',
      sessionId: null,
      loadingQuestions: true,
      loadError: '',
      syncState: 'idle',
      syncMessage: '本地题库已就绪',
      cloudQuestionMap: Object.create(null),
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
      attemptTokens: Object.create(null),
      questionStartedAt: Date.now(),
      submitting: false,
      toastVisible: false,
      toastMsg: '',
      toastType: 'info',
      // AI 出题弹窗
      aiGenSubmitting: false,
      aiGenError: '',
      aiGenSuccess: '',
      aiGenNeedsConfig: false,
      aiGenTypes: [
        { label: '单选题', value: 'single_choice' },
        { label: '多选题', value: 'multi_choice' },
        { label: '判断题', value: 'true_false' },
        { label: '填空题', value: 'fill_blank' },
      ],
      aiGenParams: {
        chapter: '',
        type: 'single_choice',
        difficulty: 3,
        count: 1,
      },
      // AI 详细解析（每题答完后）
      aiExplainLoading: false,
      aiExplainReply: '',
    }
  },
  computed: {
    sourceDescription() {
      if (this.practiceSource === 'ai') {
        return this.aiQuestions.length
          ? `AI 已生成 · ${this.aiQuestions.length} 道练习题`
          : '按章节、题型与难度生成专属练习'
      }
      return `数据结构期末 · ${this.localQuestions.length} 道本地客观题`
    },
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
    canAskAIExplain() {
      const q = this.currentQ
      if (!q) return false
      return Boolean(q.cloud_id || this.cloudQuestionMap[String(q.source_id || q.id)])
    },
  },
  mounted() {
    this.loadLocalQuestions()
    this.syncCloudSession()
  },
  methods: {
    loadLocalQuestions() {
      this.loadingQuestions = true
      this.loadError = ''
      try {
        this.localQuestions = normalizeQuestionList(localExamQuestions, 'local')
        this.questions = this.localQuestions
        const chSet = new Set(this.localQuestions.map(q => q.chapter).filter(Boolean))
        this.chapters = [...chSet]
        this.syncMessage = `本地题库已就绪 · ${this.localQuestions.length} 题`
      } catch (err) {
        this.loadError = getErrorMessage(err, '本地题库资源读取失败')
      } finally {
        this.loadingQuestions = false
      }
    },
    loadQuestions() {
      this.loadLocalQuestions()
      this.syncCloudSession()
    },
    activateSource(source) {
      this.practiceSource = source === 'ai' ? 'ai' : 'local'
      this.questions = selectPracticeQuestions(this.practiceSource, this.localQuestions, this.aiQuestions)
      const chSet = new Set(this.questions.map(q => q.chapter).filter(Boolean))
      this.chapters = [...chSet]
      this.activeType = ''
      this.activeChapter = ''
      this.currentIndex = 0
      this.currentPage = 1
      this.answerMode = false
      this.answerResult = null
    },
    async syncCloudSession() {
      const app = getApp()
      const token = app.globalData?.token
      if (!token) {
        this.syncState = 'offline'
        this.syncMessage = '本地练习可用 · 登录后同步答题记录'
        return
      }
      this.syncState = 'syncing'
      this.syncMessage = '正在连接学习记录'
      try {
        const data = await callCloud('structmind-practice', 'createSession', {
          token,
          mode: 'sequence',
          limit: 200,
        })
        this.sessionId = data.session_id
        const mapping = Object.create(null)
        for (const item of (data.questions || [])) {
          const sourceId = item.question_id || item.source_id
          if (sourceId) mapping[String(sourceId)] = item._id || item.id
        }
        this.cloudQuestionMap = mapping
        this.syncState = 'synced'
        this.syncMessage = '答题记录将自动同步'
      } catch (err) {
        this.syncState = 'offline'
        this.syncMessage = '云端暂不可用 · 本地练习不受影响'
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
      this.questionStartedAt = Date.now()
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
        this.questionStartedAt = Date.now()
      }
    },
    nextAnswerQ() {
      if (this.answerQIndex < this.filteredQuestions.length - 1) {
        this.answerQIndex++
        this.userAnswer = ''
        this.userAnswerArr = []
        this.answerResult = null
        this.questionStartedAt = Date.now()
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

      const attemptKey = `${this.sessionId || 'local'}:${q.id}`
      if (!this.attemptTokens[attemptKey]) {
        this.attemptTokens[attemptKey] = `mobile-${Date.now()}-${Math.random().toString(36).slice(2)}`
      }
      const localResult = gradePracticeAnswer(q, answer)
      this.answerResult = localResult
      this.submitting = false
      this.syncAttemptInBackground(q, answer, localResult, this.attemptTokens[attemptKey])
    },
    async syncAttemptInBackground(q, answer, localResult, attemptToken) {
      const app = getApp()
      const token = app.globalData?.token
      const cloudQuestionId = this.cloudQuestionMap[String(q.source_id || q.id)] || q.cloud_id
      if (!token || !this.sessionId || !cloudQuestionId || q.practice_source === 'ai') return
      try {
        const data = await callCloud('structmind-practice', 'submitAnswer', {
          token,
          session_id: this.sessionId,
          question_id: cloudQuestionId,
          user_answer: answer,
          attempt_token: attemptToken,
          time_spent: Math.max(1, Math.round((Date.now() - this.questionStartedAt) / 1000)),
        })
        if (this.currentQ && String(this.currentQ.id) === String(q.id) && this.answerResult) {
          this.answerResult = {
            ...data,
            is_correct: localResult.is_correct,
            correct_answer: localResult.correct_answer,
            analysis: data.analysis || data.explanation || localResult.analysis,
            sync_status: 'synced',
          }
        }
      } catch (_err) {
        this.syncState = 'offline'
        this.syncMessage = '本题已本地保存 · 云端记录稍后重试'
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
      this.practiceSource = 'local'
      this.questions = pickRandomQuestions(this.localQuestions, 10)
      this.activeType = ''
      this.activeChapter = ''
      this.currentIndex = 0
      this.currentPage = 1
      this.showToast('已抽取 10 道本地练习', 'success')
    },
    resetLocalPractice() {
      this.activateSource('local')
      this.showToast('已恢复全部本地题目', 'success')
    },
    percent(value) { return `${Math.round(Number(value || 0) * 100)}%` },
    signedPercent(value) {
      const amount = Math.round(Number(value || 0) * 100)
      return `${amount >= 0 ? '+' : ''}${amount}%`
    },
    formatTime(value) { return value ? new Date(value).toLocaleString() : '待安排' },
    errorReasonText(reason) {
      const labels = { concept_gap: '知识点缺口', careless: '粗心失误', misconception: '概念误解', procedure_error: '步骤错误' }
      return labels[reason.code || reason.category] || reason.label || '规则自动分类'
    },

    // ── AI 详细解析（每题答完后） ──
    async askAIExplain() {
      if (this.aiExplainLoading) return
      const q = this.currentQ
      const cloudQuestionId = q && (q.cloud_id || this.cloudQuestionMap[String(q.source_id || q.id)])
      if (!q || !cloudQuestionId) {
        this.showToast('本题尚未同步到云端，可先查看标准答案', 'info')
        return
      }
      this.aiExplainLoading = true
      this.aiExplainReply = ''
      try {
        const app = getApp()
        const data = await callCloud('structmind-ai', 'questionAI', {
          token: app.globalData?.token,
          question_id: cloudQuestionId,
          bank_id: q.bank_id || 'exam',
          mode: 'explain',
          model: '',
        })
        this.aiExplainReply = (data && data.reply) || 'AI 暂未返回内容'
      } catch (err) {
        const code = getPracticeErrorCode(err)
        if (code === 'AI_CONFIG_REQUIRED' || code === 'AI_CREDENTIAL_INVALID') {
          this.showToast('请先在"我的 AI 模型"配置可用 API Key', 'error')
        } else if (code === 404) {
          this.showToast('AI 题库未找到该题目（可能尚未导入）', 'error')
        } else {
          this.showToast(getErrorMessage(err, 'AI 解析失败'), 'error')
        }
      } finally {
        this.aiExplainLoading = false
      }
    },

    // ── AI 出题 ──
    openAIGenerate() {
      this.aiGenError = ''
      this.aiGenSuccess = ''
      this.aiGenNeedsConfig = false
      this.aiGenParams.chapter = this.activeChapter || ''
      // 根据当前筛选的题型智能预选
      const selectedType = toQuestionTypeValue(this.activeType)
      if (selectedType) {
        this.aiGenParams.type = selectedType
      }
      this.activateSource('ai')
    },
    closeAIGenerate() {
      if (this.aiGenSubmitting) return
      this.aiGenError = ''
      this.activateSource('local')
    },
    async submitAIGenerate() {
      const params = this.aiGenParams
      if (!params.chapter || !params.chapter.trim()) {
        this.aiGenError = '请填写章节，例如"栈和队列"'
        return
      }
      this.aiGenSubmitting = true
      this.aiGenError = ''
      this.aiGenNeedsConfig = false
      try {
        const app = getApp()
        const data = await callCloud('structmind-ai', 'generateQuestion', {
          token: app.globalData?.token,
          chapter: params.chapter.trim(),
          type: params.type,
          difficulty: params.difficulty,
          count: params.count,
          auto_import: true,   // 自动入库，下一轮就能直接练
        })
        const items = extractGeneratedQuestions(data)
        if (!items.length) throw new Error(data.message || '生成结果为空')
        this.aiQuestions = normalizeQuestionList(items.map((item) => ({
          ...item,
          type: item.type || params.type,
          chapter: item.chapter || params.chapter,
          analysis: item.analysis || item.explanation || '',
        })), 'ai')
        this.questions = this.aiQuestions
        const chSet = new Set(this.aiQuestions.map(q => q.chapter).filter(Boolean))
        this.chapters = [...chSet]
        this.currentIndex = 0
        this.currentPage = 1
        this.aiGenSuccess = `已生成 ${this.aiQuestions.length} 道题，可以直接开始练习`
        if (data.publish_denied) this.aiGenSuccess += '（仅保留在本次练习中）'
        this.showToast(`已生成 ${this.aiQuestions.length} 道题`, 'success')
      } catch (err) {
        const code = getPracticeErrorCode(err)
        if (code === 'AI_CONFIG_REQUIRED' || code === 'AI_CREDENTIAL_INVALID') {
          this.aiGenError = '请先到"我的 AI 模型"配置可用 API Key。'
          this.aiGenNeedsConfig = true
        } else if (code === 'AI_QUOTA_EXCEEDED') {
          this.aiGenError = 'AI 额度不足，请稍后再试。'
        } else {
          this.aiGenError = getErrorMessage(err, '生成失败，请检查 AI 配置或网络')
        }
      } finally {
        this.aiGenSubmitting = false
      }
    },
    openAISettings() {
      uni.navigateTo({ url: '/pages/ai-settings/ai-settings' })
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
.practice-page {
  min-height: 100vh; background: #f3f7f0; padding: 20px 16px 112px;
  box-sizing: border-box; color: #183229;
}

.page-header { padding: 0 0 16px; }
.page-title { font-size: 26px; line-height: 1.2; font-weight: 760; color: #183229; display: block; }
.page-desc { font-size: 14px; color: #6b8280; margin-top: 6px; display: block; }
.source-switch {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px; max-width: 620px; margin-top: 20px;
}
.source-tab {
  min-height: 72px; padding: 12px 16px; box-sizing: border-box;
  display: flex; flex-direction: column; justify-content: center; gap: 3px;
  border: 1px solid #d8e4d3; border-radius: 14px; background: #fffefb;
  color: #4a5c58; cursor: pointer; transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
}
.source-tab:active { transform: translateY(1px); }
.source-tab:focus-visible,
.ai-gen-btn:focus-visible,
.ai-gen-input:focus-visible { outline: 3px solid rgba(71, 122, 80, 0.24); outline-offset: 2px; }
.source-tab.active { border-color: #477a50; background: #edf5e9; box-shadow: 0 8px 24px rgba(47, 95, 61, 0.08); }
.source-tab-title { font-size: 15px; font-weight: 700; color: #244333; }
.source-tab-meta { font-size: 12px; color: #708076; }
.sync-status {
  display: flex; align-items: center; gap: 8px; min-height: 32px;
  flex-direction: row; flex-wrap: wrap;
  margin-top: 12px; font-size: 12px; color: #61736a;
}
.sync-dot { width: 7px; height: 7px; border-radius: 50%; background: #a0aea5; }
.sync-status.syncing .sync-dot { background: #a86e27; animation: emptyPulse 1.25s ease-in-out infinite; }
.sync-status.synced .sync-dot { background: #3f7d4d; }
.sync-status.offline .sync-dot { background: #a86e27; }
.sync-retry { margin-left: 4px; color: #2f5f3d; font-weight: 700; cursor: pointer; }

/* Filters */
.filter-scroll { white-space: nowrap; padding: 6px 0; }
.filter-bar { display: flex; flex-direction: row; gap: 8px; padding: 0; }
.filter-item {
  display: inline-flex; min-height: 40px; box-sizing: border-box; align-items: center;
  flex: 0 0 auto;
  padding: 8px 16px; border-radius: 12px;
  background: #fff; border: 1px solid #dce5e3; font-size: 13px;
  color: #6b8280; white-space: nowrap; transition: all 0.2s;
}
.filter-item.active { background: #477a50; border-color: #477a50; color: #fff; }
.chapter-filter { font-size: 12px; padding: 6px 12px; }

/* Mode Toggle */
.mode-toggle { padding: 14px 0 10px; }
.mode-toggle-row {
  display: flex; flex-direction: row; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 10px;
}
.mode-result { font-size: 13px; color: #6b8280; }
.mode-actions { display: flex; flex-direction: row; align-items: center; flex-wrap: wrap; gap: 8px; }
.mode-btn {
  min-height: 44px; box-sizing: border-box; display: flex; align-items: center;
  padding: 8px 14px; border-radius: 11px; background: #fffefb; color: #477a50;
  border: 1px solid #d8e4d3; font-size: 13px; font-weight: 600;
}
.mode-btn.emphasized { background: #edf5e9; border-color: transparent; }
.mode-btn.danger { background: #fef2f2; color: #dc2626; }

/* Question List */
.question-list { display: grid; grid-template-columns: 1fr; gap: 12px; padding: 0; }
.q-card {
  min-height: 146px; box-sizing: border-box; display: flex; flex-direction: column;
  background: #fffefb; border: 1px solid #dfe9da; border-radius: 16px; padding: 18px;
  box-shadow: 0 8px 24px rgba(47,95,61,0.055);
  transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
}
.q-card:hover { border-color: #b8ceb3; box-shadow: 0 12px 30px rgba(47,95,61,0.09); }
.q-card:active { transform: scale(0.99); }
.q-meta { display: flex; flex-direction: row; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.q-tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #edf5e9; color: #477a50; }
.q-tag.type { background: #e8f0f5; color: #3b6f9e; }
.q-tag.difficulty { background: #fef3c7; color: #a16207; }
.q-tag.source { background: #f5f5f5; color: #a0b0ac; }
.q-stem { font-size: 15px; color: #1a2b28; line-height: 1.65; display: block; flex: 1; }
.q-stem.full { font-size: 16px; line-height: 1.7; }
.q-footer { display: flex; flex-direction: row; justify-content: space-between; align-items: center; margin-top: 14px; }
.q-source { font-size: 11px; color: #a0b0ac; }
.q-start-btn { font-size: 12px; color: #477a50; font-weight: 600; }
.load-more {
  grid-column: 1 / -1; min-height: 46px; display: flex; align-items: center; justify-content: center;
  border: 1px solid #d8e4d3; border-radius: 12px; background: #fffefb;
  color: #2f5f3d; font-size: 13px; font-weight: 700; cursor: pointer;
}

/* Empty */
.empty {
  max-width: 520px; margin: 28px auto; padding: 34px 28px; text-align: center;
  background: #fff; border: 1px solid #e0e8dc; border-radius: 18px;
  box-shadow: 0 14px 40px rgba(50, 82, 58, 0.08);
}
.empty-kicker { display: block; color: #477a50; font-size: 12px; font-weight: 700; letter-spacing: 1px; }
.empty-title { display: block; margin-top: 8px; color: #1a2b28; font-size: 20px; font-weight: 700; }
.empty-text { display: block; margin-top: 8px; font-size: 14px; line-height: 1.7; color: #6b8280; }
.empty-actions {
  display: flex; gap: 10px; margin-top: 4px; flex-wrap: wrap;
}
.empty-retry.secondary {
  background: transparent; color: #2f5f3d;
  border: 1px solid #d8e4d3;
}
.empty-tip {
  display: block; margin-top: 14px; font-size: 12px; line-height: 1.6;
  color: #94a097; max-width: 320px;
}
.empty-retry {
  display: inline-flex; margin-top: 18px; padding: 10px 22px; border-radius: 12px;
  background: #477a50; color: #fff; font-size: 14px; font-weight: 700;
}
.empty-pulse {
  width: 28px; height: 28px; margin: 0 auto 6px; border-radius: 50%;
  background: #b7d5ad; animation: emptyPulse 1.25s ease-in-out infinite;
}
@keyframes emptyPulse { 50% { transform: scale(0.72); opacity: 0.45; } }

/* Swipe Mode */
.swipe-container { max-width: 760px; margin: 0 auto; padding: 14px 0; display: flex; flex-direction: column; gap: 12px; }
.swipe-header { display: flex; flex-direction: row; justify-content: space-between; align-items: center; }
.swipe-counter { font-size: 14px; font-weight: 600; color: #4a5c58; }
.swipe-actions { display: flex; flex-direction: row; gap: 8px; }

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

.swipe-quick-actions { display: flex; flex-direction: row; gap: 10px; }
.swipe-btn {
  flex: 1; padding: 12px; border-radius: 14px; text-align: center;
  background: #f3f7f0; border: 1px solid #d8e4d3; font-size: 14px;
  font-weight: 600; color: #4a5c58;
}
.swipe-btn.start { background: #477a50; color: #fff; border: none; }

/* ═══ Answer Mode ═══ */
.answer-view {
  width: 100%; max-width: 760px; margin: 12px auto 0; padding: 0 0 96px;
  box-sizing: border-box;
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
  min-height: 54px;
  display: flex; flex-direction: row; align-items: flex-start; gap: 12px;
  padding: 14px 16px; border: 1.5px solid #dce5e3; border-radius: 12px;
  background: #fffefb; transition: all 0.15s ease;
}
.answer-option:active { transform: scale(0.98); }
.answer-option.selected {
  border-color: #6f9a73; background: #f3f8f0;
}
.option-radio {
  width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  border: 2px solid #dce5e3; background: #fff; margin-top: 1px;
}
.option-radio.checked { background: #477a50; border-color: #477a50; color: #fff; }
.option-radio.multi { border-radius: 6px; }
.option-radio text { font-size: 12px; font-weight: 700; }
.option-text { font-size: 15px; color: #1a2b28; line-height: 1.5; }
.option-key { font-weight: 700; color: #477a50; }

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
.result-head { display: flex; flex-direction: row; align-items: center; gap: 8px; margin-bottom: 10px; }
.result-icon { font-size: 24px; }
.result-title { font-size: 16px; font-weight: 700; color: #1a2b28; }
.result-line { margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(0,0,0,0.06); }
.result-label { font-size: 12px; color: #6b8280; display: block; margin-bottom: 2px; }
.result-value { font-size: 15px; color: #1a2b28; line-height: 1.6; display: block; }

/* Answer navigation */
.answer-nav {
  display: flex; flex-direction: row; gap: 10px; justify-content: center; padding: 12px 0;
}
.nav-btn {
  flex: 1; max-width: 180px; min-height: 44px; padding: 12px 0; border-radius: 12px;
  text-align: center; font-size: 14px; font-weight: 600;
  background: #f3f7f0; border: 1px solid #d8e4d3; color: #3d574c;
}
.nav-btn.exit { background: #fef2f2; border-color: #fecaca; color: #dc2626; }

/* Bottom Actions */
.bottom-actions {
  position: sticky; bottom: 12px; width: calc(100% - 8px); max-width: 520px;
  margin: 20px auto 0; padding: 10px;
  background: rgba(255,255,255,0.92); backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid #d8e4d3; border-radius: 14px;
  box-shadow: 0 14px 34px rgba(47, 95, 61, 0.12);
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px;
  z-index: 20; box-sizing: border-box;
}
.learning-proof { margin-top: 14px; padding-top: 14px; border-top: 1px solid #dce5e3; display: flex; flex-direction: column; gap: 8px; }
.proof-title { font-size: 14px; font-weight: 700; color: #1a2b28; }
.proof-line { font-size: 12px; line-height: 1.6; color: #4a5c58; }
.mastery-row { display: flex; flex-direction: row; justify-content: space-between; gap: 12px; font-size: 12px; color: #477a50; }
.recommend-proof { padding: 12px; border-radius: 12px; background: #edf5e9; display: flex; flex-direction: column; gap: 8px; }

.page-title-row {
  display: flex; flex-direction: row; align-items: center; gap: 10px; flex-wrap: wrap;
}
.ai-gen-workspace {
  padding: 22px; margin: 0 0 16px; border: 1px solid #d8e4d3; border-radius: 18px;
  background: #fffefb; box-shadow: 0 14px 38px rgba(47, 95, 61, 0.08);
}
.ai-gen-head {
  display: flex; flex-direction: row; align-items: center; justify-content: space-between;
}
.ai-gen-title { display: block; font-size: 19px; font-weight: 750; color: #183229; }
.ai-gen-subtitle { display: block; margin-top: 5px; font-size: 13px; line-height: 1.55; color: #708076; }
.ai-result-count {
  flex-shrink: 0; padding: 6px 10px; border-radius: 10px;
  background: #edf5e9; color: #2f5f3d; font-size: 12px; font-weight: 700;
}
.ai-gen-body { display: flex; flex-direction: column; gap: 10px; margin-top: 20px; }
.ai-gen-label {
  font-size: 13px; color: #4a5c58; font-weight: 600;
}
.ai-gen-input {
  width: 100%; height: 46px; padding: 0 13px; box-sizing: border-box;
  border: 1px solid #d8e4d3; border-radius: 10px;
  background: #fff; font-size: 14px; color: #183229;
}
.ai-gen-input:focus { border-color: #477a50; outline: none; }
.ai-gen-chips { display: flex; flex-direction: row; flex-wrap: wrap; gap: 8px; }
.ai-gen-chip {
  min-height: 40px; box-sizing: border-box; display: flex; align-items: center;
  padding: 7px 14px; border-radius: 10px;
  border: 1px solid #d8e4d3; background: #fffefb;
  font-size: 13px; color: #4a5c58;
  transition: all 0.15s ease;
}
.ai-gen-chip.compact { min-width: 42px; justify-content: center; }
.ai-gen-chip.active {
  background: #477a50; color: #fff; border-color: #477a50;
}
.ai-gen-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 4px; }
.ai-gen-field { display: flex; flex-direction: column; gap: 9px; }
.ai-gen-error {
  font-size: 12px; color: #b84b42; padding: 8px 12px;
  background: #fff0ee; border-radius: 8px;
}
.ai-config-link {
  min-height: 40px; display: flex; align-items: center; justify-content: center;
  border: 1px solid #d8e4d3; border-radius: 10px; color: #2f5f3d;
  font-size: 13px; font-weight: 700; cursor: pointer;
}
.ai-gen-success {
  font-size: 12px; color: #2f5f3d; padding: 9px 12px;
  background: #edf5e9; border-radius: 8px;
}
.ai-gen-actions {
  display: flex; flex-direction: row; gap: 10px; justify-content: flex-end;
  border-top: 1px solid #eef3ec; margin-top: 18px; padding-top: 16px;
}
.ai-gen-btn {
  min-width: 120px; min-height: 44px; padding: 0 18px;
  border-radius: 10px; font-size: 13px; font-weight: 600;
  border: 1px solid #d8e4d3; background: #fffefb; color: #4a5c58;
}
.ai-gen-btn.primary {
  background: #477a50; color: #fff; border-color: #477a50;
}
.ai-gen-btn[disabled] { opacity: 0.5; }
.ai-gen-btn:active:not([disabled]) { transform: scale(0.97); }

/* AI 详细解析（答完题后展示） */
.ai-explain-row { margin-top: 14px; }
.ai-explain-btn {
  width: 100%; min-height: 40px;
  border-radius: 10px;
  background: #f4f8f3; color: #2f5f3d;
  border: 1px solid #d8e4d3; font-size: 13px; font-weight: 600;
  transition: all 0.15s ease;
}
.ai-explain-btn:active:not([disabled]) { transform: scale(0.97); background: #eaf5e7; }
.ai-explain-btn[disabled] { opacity: 0.55; }
.ai-explain-reply {
  margin-top: 12px; padding: 14px;
  border-radius: 10px;
  background: #f5f8f3;
  border-left: 3px solid #477a50;
}
.ai-explain-content {
  font-size: 14px; line-height: 1.7; color: #244333;
  white-space: pre-wrap;
}

.empty { grid-column: 1 / -1; }

@media (min-width: 980px) {
  .question-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .practice-page { padding-bottom: 56px; }
}

@media (max-width: 640px) {
  .practice-page { padding: 16px 14px 104px; }
  .page-title { font-size: 23px; }
  .source-switch { gap: 8px; margin-top: 16px; }
  .source-tab { min-height: 68px; padding: 10px 12px; }
  .source-tab-title { font-size: 14px; }
  .filter-item { min-height: 38px; padding: 7px 13px; }
  .ai-gen-workspace { padding: 18px 14px; border-radius: 16px; }
  .ai-gen-head { align-items: flex-start; gap: 10px; }
  .ai-gen-grid { grid-template-columns: 1fr; gap: 12px; }
  .ai-gen-actions { display: grid; grid-template-columns: 1fr 1fr; }
  .ai-gen-btn { width: 100%; min-width: 0; padding: 0 10px; }
  .q-card { min-height: 0; padding: 16px; }
  .answer-view { padding-bottom: 88px; }
  .answer-card { padding: 15px; }
  .answer-option { padding: 13px 14px; }
  .bottom-actions { width: 100%; bottom: 8px; margin-top: 16px; }
}

@media (prefers-reduced-motion: reduce) {
  .source-tab,
  .q-card,
  .answer-option,
  .ai-gen-chip,
  .ai-gen-btn,
  .ai-explain-btn { transition: none !important; }
  .source-tab:active,
  .q-card:active,
  .answer-option:active,
  .ai-gen-btn:active:not([disabled]) { transform: none !important; }
  .empty-pulse,
  .sync-status.syncing .sync-dot { animation: none !important; }
}
</style>

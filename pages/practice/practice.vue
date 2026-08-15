<template>
  <view class="practice-page">
    <view class="page-header">
      <view class="page-title-row">
        <text class="page-title">题库练习</text>
        <view v-if="fromCache" class="cache-badge" @tap="refreshOnline">
          <text class="cache-badge-dot"></text>
          <text>本地缓存 · {{ cacheAgeLabel }}</text>
        </view>
      </view>
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
          <view class="recommend-proof" v-if="answerResult.next_recommendation">
            <text class="proof-title">为什么推荐下一题</text>
            <text class="proof-line">{{ answerResult.next_recommendation.explanation }}</text>
            <text class="proof-line">规则基础结果 · 事件 {{ answerResult.learning_event_id }}</text>
            <SmButton variant="primary" block @click="startNextRecommendation">开始推荐题</SmButton>
          </view>
        </view>

        <!-- AI 详细解析：答完题后可调用 structmind-ai/questionAI -->
        <view class="ai-explain-row">
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
    <view class="bottom-actions" v-if="!answerMode && !loadingQuestions && !loadError">
      <SmButton variant="primary" block icon="" @click="startRandom10">随机10题</SmButton>
      <SmButton variant="gradient" block @click="startRecommend">智能推荐</SmButton>
      <SmButton variant="soft" block @click="openAIGenerate">AI 出题</SmButton>
    </view>

    <!-- AI 出题弹窗 -->
    <view v-if="showAIGenerateModal" class="ai-gen-modal-mask" @tap.self="closeAIGenerate">
      <view class="ai-gen-modal">
        <view class="ai-gen-head">
          <text class="ai-gen-title">AI 智能出题</text>
          <text class="ai-gen-close" @tap="closeAIGenerate">×</text>
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
          <text class="ai-gen-label">难度（1-5）</text>
          <view class="ai-gen-chips">
            <view
              v-for="d in [1,2,3,4,5]"
              :key="d"
              class="ai-gen-chip"
              :class="{ active: aiGenParams.difficulty === d }"
              @tap="aiGenParams.difficulty = d"
            >
              <text>{{ d }}</text>
            </view>
          </view>
          <text class="ai-gen-label">生成数量</text>
          <view class="ai-gen-chips">
            <view
              v-for="n in [1,3,5]"
              :key="n"
              class="ai-gen-chip"
              :class="{ active: aiGenParams.count === n }"
              @tap="aiGenParams.count = n"
            >
              <text>{{ n }} 道</text>
            </view>
          </view>
          <text v-if="aiGenError" class="ai-gen-error">{{ aiGenError }}</text>
        </view>
        <view class="ai-gen-actions">
          <button class="ai-gen-btn ghost" @tap="closeAIGenerate">取消</button>
          <button class="ai-gen-btn primary" :disabled="aiGenSubmitting" @tap="submitAIGenerate">
            <text>{{ aiGenSubmitting ? '生成中…' : '生成题目' }}</text>
          </button>
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
import { callCloud, normalizeCloudQuestion } from '@/utils/cloud.js'

export default {
  components: { SmButton, SmToast },
  data() {
    return {
      questions: Array(),
      sessionId: null,
      loadingQuestions: true,
      loadError: '',
      // 离线缓存：显示已缓存的题目时为 true
      fromCache: false,
      cacheAgeLabel: '',
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
      showAIGenerateModal: false,
      aiGenSubmitting: false,
      aiGenError: '',
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
    // 1) 先尝试从本地缓存秒开（离线 / 弱网下也能浏览）
    this.hydrateFromCache()
    // 2) 再去云端拉新数据；失败则保留缓存 + 显示小提示
    await this.loadQuestions()
  },
  methods: {
    _cacheKey() {
      const app = getApp()
      const token = app.globalData?.token || 'anon'
      return `sm_practice_${token.slice(0, 8)}_${this.activeType || 'all'}_${this.activeChapter || 'all'}`
    },
    _serializeQuestions() {
      // uni.setStorageSync 的 key 上限 ~1MB，需要剥掉大字段
      return this.questions.map(q => ({
        ...q,
        // 移除前端不需要的大字段，缩减存储
        images: Array.isArray(q.images) ? q.images.slice(0, 3) : [],
        recommendation_explanation: '',
        answer: '',
        raw_correct: '',
      }))
    },
    hydrateFromCache() {
      try {
        const raw = uni.getStorageSync(this._cacheKey())
        if (!raw) return
        const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
        if (!parsed || !parsed.questions || !Array.isArray(parsed.questions)) return
        // 缓存有效期 12 小时
        if (Date.now() - (parsed.cached_at || 0) > 12 * 60 * 60 * 1000) return

        this.questions = parsed.questions.map(normalizeCloudQuestion)
        const chSet = new Set(this.questions.map(q => q.chapter).filter(Boolean))
        this.chapters = [...chSet].sort()
        this.sessionId = parsed.session_id || null
        this.fromCache = true
        const ageMs = Date.now() - (parsed.cached_at || 0)
        this.cacheAgeLabel = ageMs < 60_000 ? '刚刚' :
          ageMs < 3600_000 ? `${Math.round(ageMs / 60_000)} 分钟前` :
          `${Math.round(ageMs / 3600_000)} 小时前`
        this.loadingQuestions = false
      } catch (_e) { /* 静默吞：缓存损坏不应阻塞 UI */ }
    },
    persistCache() {
      try {
        uni.setStorageSync(this._cacheKey(), {
          questions: this._serializeQuestions(),
          session_id: this.sessionId,
          cached_at: Date.now(),
        })
      } catch (_e) { /* 配额满或序列化失败，吞掉即可 */ }
    },
    refreshOnline() {
      this.fromCache = false
      return this.loadQuestions()
    },
    async loadQuestions(mode = 'sequence', limit = 200, includeWrong = false) {
      this.loadingQuestions = true
      this.loadError = ''
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
        // 写入本地缓存（云端拉取成功后覆盖旧缓存）
        this.persistCache()
        this.fromCache = false
      } catch (err) {
        // 云端失败：若已有缓存则保留缓存 + 提示
        const msg = (err && (err.message || err.errMsg)) || ''
        const code = err && err.code
        if (this.questions.length > 0) {
          this.loadError = `云端同步失败：${msg || '请检查网络'}（当前显示的是缓存）`
        } else {
          if (code === 401) this.loadError = '登录已失效，请重新登录后重试。'
          else if (code === 403) this.loadError = '账号未通过审批，无法加载题库。'
          else if (code === 404) this.loadError = `题库为空：${msg}。请在管理后台导入题目数据。`
          else this.loadError = msg
            ? `${msg}（请检查网络或确认题库云函数已部署）`
            : '请检查网络或重新登录后再试。若持续失败，请确认题库云函数已部署。'
        }
      } finally {
        this.loadingQuestions = false
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

      const app = getApp()
      const auth = app.globalData
      const attemptKey = `${this.sessionId}:${q.id}`
      if (!this.attemptTokens[attemptKey]) {
        this.attemptTokens[attemptKey] = `mobile-${Date.now()}-${Math.random().toString(36).slice(2)}`
      }

      try {
        const data = await callCloud('structmind-practice', 'submitAnswer', {
          token: auth.token,
          session_id: this.sessionId,
          question_id: q.id,
          user_answer: answer,
          attempt_token: this.attemptTokens[attemptKey],
          time_spent: Math.max(1, Math.round((Date.now() - this.questionStartedAt) / 1000)),
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
      const app = getApp()
      try {
        const recommendations = await callCloud('structmind-learning', 'recommend', { token: app.globalData?.token, count: 15 })
        const ids = (recommendations.recommendations || []).map(item => item.question_id)
        if (!ids.length) throw new Error('暂无推荐题')
        const session = await callCloud('structmind-practice', 'createSession', {
          token: app.globalData?.token, question_ids: ids, limit: ids.length, mode: 'sequence',
        })
        const explanationById = Object.fromEntries((recommendations.recommendations || [])
          .map(item => [String(item.question_id), item.explanation]))
        this.questions = (session.questions || []).map(item => ({
          ...normalizeCloudQuestion(item), recommendation_explanation: explanationById[String(item._id || item.id)] || '',
        }))
        this.sessionId = session.session_id
      } catch (e) {
        await this.loadQuestions('random', 15, true)
      }
      this.currentIndex = 0
      this.currentPage = 1
      this.showToast('已生成错题优先练习', 'success')
    },
    async startNextRecommendation() {
      const recommendation = this.answerResult?.next_recommendation
      if (!recommendation?.question_id) return
      let index = this.filteredQuestions.findIndex(q => String(q.id) === String(recommendation.question_id))
      if (index < 0) {
        await this.startRecommend()
        index = this.filteredQuestions.findIndex(q => String(q.id) === String(recommendation.question_id))
      }
      if (index >= 0) this.enterAnswer(index)
      else this.showToast('推荐依据已保存，题目将在下一轮出现', 'info')
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
      if (!q || !q.id) {
        this.showToast('题目数据缺失', 'error')
        return
      }
      this.aiExplainLoading = true
      this.aiExplainReply = ''
      try {
        const app = getApp()
        const data = await callCloud('structmind-ai', 'questionAI', {
          token: app.globalData?.token,
          question_id: q.id,
          bank_id: q.bank_id || 'exam',
          mode: 'explain',
          model: '',
        })
        this.aiExplainReply = (data && data.reply) || 'AI 暂未返回内容'
      } catch (err) {
        const code = err && err.code
        if (code === 'AI_CONFIG_REQUIRED' || code === 'AI_CREDENTIAL_INVALID') {
          this.showToast('请先在"我的 AI 模型"配置可用 API Key', 'error')
        } else if (code === 404) {
          this.showToast('AI 题库未找到该题目（可能尚未导入）', 'error')
        } else {
          this.showToast((err && (err.message || err.errMsg)) || 'AI 解析失败', 'error')
        }
      } finally {
        this.aiExplainLoading = false
      }
    },

    // ── AI 出题 ──
    openAIGenerate() {
      this.aiGenError = ''
      this.aiGenParams.chapter = this.activeChapter || ''
      // 根据当前筛选的题型智能预选
      const map = { '单选题': 'single_choice', '多选题': 'multi_choice', '判断题': 'true_false', '填空题': 'fill_blank' }
      if (this.activeType && map[this.activeType]) {
        this.aiGenParams.type = map[this.activeType]
      }
      this.showAIGenerateModal = true
    },
    closeAIGenerate() {
      if (this.aiGenSubmitting) return
      this.showAIGenerateModal = false
      this.aiGenError = ''
    },
    async submitAIGenerate() {
      const params = this.aiGenParams
      if (!params.chapter || !params.chapter.trim()) {
        this.aiGenError = '请填写章节，例如"栈和队列"'
        return
      }
      this.aiGenSubmitting = true
      this.aiGenError = ''
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
        const items = Array.isArray(data.questions) ? data.questions : []
        if (!items.length) throw new Error(data.message || '生成结果为空')
        // 把 AI 题注入当前 session（不重置 sessionId，便于继续练）
        const qItems = items.map(it => normalizeCloudQuestion({
          id: it.question_id || it._id,
          _id: it._id,
          type: it.type || params.type,
          qtype: ({ single_choice: '单选题', multi_choice: '多选题', true_false: '判断题', fill_blank: '填空题' })[it.type] || params.type,
          chapter: it.chapter || params.chapter,
          content: it.content || it.stem,
          stem: it.content || it.stem,
          options: it.options || [],
          answer: it.answer || '',
          analysis: it.analysis || '',
        }))
        this.questions = [...this.questions, ...qItems]
        const chSet = new Set(this.questions.map(q => q.chapter).filter(Boolean))
        this.chapters = [...chSet].sort()
        this.persistCache()
        this.showAIGenerateModal = false
        this.showToast(`已生成 ${items.length} 道题，可直接练习`, 'success')
      } catch (err) {
        const code = err && err.code
        if (code === 'AI_CONFIG_REQUIRED' || code === 'AI_CREDENTIAL_INVALID') {
          this.aiGenError = '请先到"我的 AI 模型"配置可用 API Key。'
        } else if (code === 'AI_QUOTA_EXCEEDED') {
          this.aiGenError = 'AI 额度不足，请稍后再试。'
        } else {
          this.aiGenError = (err && (err.message || err.errMsg)) || '生成失败，请检查 AI 配置或网络'
        }
      } finally {
        this.aiGenSubmitting = false
      }
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
.practice-page { min-height: 100vh; background: #f3f7f0; padding-bottom: 120px; }

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
.filter-item.active { background: #477a50; border-color: #477a50; color: #fff; }
.chapter-filter { font-size: 12px; padding: 6px 12px; }

/* Mode Toggle */
.mode-toggle { padding: 8px 16px; }
.mode-toggle-row { display: flex; justify-content: space-between; align-items: center; }
.mode-result { font-size: 13px; color: #6b8280; }
.mode-btn {
  padding: 6px 14px; border-radius: 20px; background: #edf5e9; color: #477a50;
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
.q-tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #edf5e9; color: #477a50; }
.q-tag.type { background: #e8f0f5; color: #3b6f9e; }
.q-tag.difficulty { background: #fef3c7; color: #a16207; }
.q-tag.source { background: #f5f5f5; color: #a0b0ac; }
.q-stem { font-size: 14px; color: #1a2b28; line-height: 1.5; display: block; }
.q-stem.full { font-size: 16px; line-height: 1.7; }
.q-footer { display: flex; justify-content: space-between; align-items: center; margin-top: 8px; }
.q-source { font-size: 11px; color: #a0b0ac; }
.q-start-btn { font-size: 12px; color: #477a50; font-weight: 600; }

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
  background: #f3f7f0; border: 1px solid #d8e4d3; font-size: 14px;
  font-weight: 600; color: #4a5c58;
}
.swipe-btn.start { background: #477a50; color: #fff; border: none; }

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
  background: #f3f7f0; border: 1px solid #d8e4d3; color: #3d574c;
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
.learning-proof { margin-top: 14px; padding-top: 14px; border-top: 1px solid #dce5e3; display: flex; flex-direction: column; gap: 8px; }
.proof-title { font-size: 14px; font-weight: 700; color: #1a2b28; }
.proof-line { font-size: 12px; line-height: 1.6; color: #4a5c58; }
.mastery-row { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; color: #477a50; }
.recommend-proof { padding: 12px; border-radius: 12px; background: #edf5e9; display: flex; flex-direction: column; gap: 8px; }

/* 缓存状态徽章（点击触发云端同步） */
.page-title-row {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.cache-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 10px; border-radius: 999px;
  background: rgba(71, 122, 80, 0.08);
  border: 1px solid rgba(71, 122, 80, 0.18);
  color: #2f5f3d; font-size: 11px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.cache-badge:active { background: rgba(71, 122, 80, 0.18); }
.cache-badge-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #477a50;
  animation: cache-pulse 1.6s ease-in-out infinite;
}
@keyframes cache-pulse {
  0%, 100% { opacity: 0.45; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.15); }
}

/* AI 出题弹窗 */
.ai-gen-modal-mask {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(15, 32, 25, 0.45);
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
.ai-gen-modal {
  width: 100%; max-width: 420px; background: #fffefb;
  border-radius: 18px; padding: 22px;
  box-shadow: 0 24px 60px rgba(15, 32, 25, 0.22);
  display: flex; flex-direction: column; gap: 14px;
}
.ai-gen-head {
  display: flex; align-items: center; justify-content: space-between;
}
.ai-gen-title { font-size: 17px; font-weight: 700; color: #183229; }
.ai-gen-close {
  width: 28px; height: 28px; line-height: 26px; text-align: center;
  font-size: 22px; color: #94a097; border-radius: 50%;
  background: transparent; border: 0;
}
.ai-gen-close:active { background: rgba(0,0,0,0.05); }
.ai-gen-body { display: flex; flex-direction: column; gap: 12px; }
.ai-gen-label {
  font-size: 13px; color: #4a5c58; font-weight: 600;
}
.ai-gen-input {
  height: 40px; padding: 0 12px;
  border: 1px solid #d8e4d3; border-radius: 10px;
  background: #fff; font-size: 14px; color: #183229;
}
.ai-gen-input:focus { border-color: #477a50; outline: none; }
.ai-gen-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.ai-gen-chip {
  padding: 6px 14px; border-radius: 999px;
  border: 1px solid #d8e4d3; background: #fffefb;
  font-size: 13px; color: #4a5c58;
  transition: all 0.15s ease;
}
.ai-gen-chip.active {
  background: #477a50; color: #fff; border-color: #477a50;
}
.ai-gen-error {
  font-size: 12px; color: #b84b42; padding: 8px 12px;
  background: #fff0ee; border-radius: 8px;
}
.ai-gen-actions {
  display: flex; gap: 8px; justify-content: flex-end;
  border-top: 1px solid #eef3ec; padding-top: 14px;
}
.ai-gen-btn {
  min-width: 92px; min-height: 38px; padding: 0 16px;
  border-radius: 10px; font-size: 13px; font-weight: 600;
  border: 1px solid #d8e4d3; background: #fffefb; color: #4a5c58;
}
.ai-gen-btn.primary {
  background: #477a50; color: #fff; border-color: #477a50;
}
.ai-gen-btn[disabled] { opacity: 0.5; }
.ai-gen-btn:active:not([disabled]) { transform: scale(0.97); }

/* 底部按钮：原本只有 2 个，现在加 AI 出题 → 3 列网格 */
.bottom-actions {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
}
@media (max-width: 480px) {
  .bottom-actions { grid-template-columns: 1fr; }
}

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
</style>

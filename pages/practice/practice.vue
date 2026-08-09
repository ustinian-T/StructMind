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

    <!-- 题目列表 / 滑动模式 -->
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
        v-for="q in paginatedQuestions"
        :key="q.id"
        @tap="startSwipePractice(q.id)"
        :animation="q._anim"
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
        :animation="cardAnimation"
        @touchstart="onTouchStart"
        @touchmove="onTouchMove"
        @touchend="onTouchEnd"
      >
        <view class="swipe-card-inner">
          <view class="q-meta">
            <text class="q-tag">{{ currentQuestion.chapter }}</text>
            <text class="q-tag type">{{ currentQuestion.qtype }}</text>
          </view>
          <text class="q-stem full">{{ truncate(currentQuestion.stem, 300) }}</text>
          <view class="swipe-hint-left">上一题</view>
          <view class="swipe-hint-right">下一题</view>
        </view>
      </view>

      <!-- 卡片底部操作 -->
      <view class="swipe-quick-actions">
        <view class="swipe-btn prev" @tap="prevCard">
          <text>上一题</text>
        </view>
        <view class="swipe-btn start" @tap="startSwipePractice(currentQuestion.id)">
          <text>开始作答</text>
        </view>
        <view class="swipe-btn next" @tap="nextCard">
          <text>下一题</text>
        </view>
      </view>
    </view>

    <!-- 底部快捷按钮 -->
    <view class="bottom-actions">
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
// getApp() 是 uni-app 全局函数，无需导入

export default {
  components: { SmButton, SmToast },
  data() {
    return {
      questions: [],
      types: ['单选题', '多选题', '填空题', '判断题'],
      activeType: '',
      activeChapter: '',
      chapters: [],
      practiceMode: 'list',      // 'list' | 'swipe'
      currentIndex: 0,
      pageSize: 20,
      currentPage: 1,
      cardAnimation: null,
      touchStartX: 0,
      touchStartY: 0,
      touchMoved: false,
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
  },
  async mounted() {
    await this.loadQuestions()
  },
  methods: {
    async loadQuestions() {
      try {
        const app = getApp()
        const apiBase = app.globalData.apiBase || 'https://datastytest.tshai.top'
        const res = await uni.request({ url: `${apiBase}/api/questions` })
        this.questions = res.data?.questions || []
        // 提取章节列表
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
    startSwipePractice(qId) {
      uni.showToast({ title: '请使用Web端进行完整练习', icon: 'none' })
    },
    startRandom10() {
      uni.showToast({ title: '请登录Web端使用随机练习', icon: 'none' })
    },
    startRecommend() {
      uni.showToast({ title: '请登录Web端使用智能推荐', icon: 'none' })
    },
    // Swipe card handlers
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
      // Only apply horizontal swipe (ignore vertical scroll)
      if (Math.abs(dx) > Math.abs(dy)) {
        const anim = uni.createAnimation({ duration: 0 })
        anim.translateX(dx).rotate(dx * 0.02 + 'deg').step()
        this.cardAnimation = anim.export()
      }
    },
    onTouchEnd(e) {
      if (!this.touchMoved) return
      const dx = e.changedTouches[0].clientX - this.touchStartX
      const threshold = 80
      const anim = uni.createAnimation({ duration: 250 })

      if (dx < -threshold) {
        // Swipe left -> next
        anim.translateX(-400).opacity(0).step({ duration: 200 })
        this.cardAnimation = anim.export()
        setTimeout(() => this.nextCard(), 200)
      } else if (dx > threshold) {
        // Swipe right -> prev
        anim.translateX(400).opacity(0).step({ duration: 200 })
        this.cardAnimation = anim.export()
        setTimeout(() => this.prevCard(), 200)
      } else {
        // Snap back
        anim.translateX(0).rotate('0deg').step()
        this.cardAnimation = anim.export()
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
      const anim = uni.createAnimation({ duration: 200 })
      anim.translateX(0).opacity(1).rotate('0deg').step()
      this.cardAnimation = anim.export()
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

/* Bottom Actions */
.bottom-actions {
  position: fixed; bottom: 0; left: 0; right: 0;
  padding: 12px 16px; padding-bottom: calc(12px + env(safe-area-inset-bottom, 0));
  background: rgba(255,255,255,0.92); backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-top: 1px solid #edf2f0; display: flex; gap: 10px;
}
</style>

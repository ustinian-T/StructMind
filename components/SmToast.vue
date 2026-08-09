<template>
  <view v-if="visible" :class="['sm-toast', `sm-toast-${type}`, `sm-toast-${position}`]" :style="customStyle">
    <text class="sm-toast-icon">{{ iconMap[type] || 'ℹ️' }}</text>
    <text class="sm-toast-text">{{ message }}</text>
  </view>
</template>

<script>
export default {
  props: {
    message: { type: String, default: '' },
    type: { type: String, default: 'info' },       // info | success | error | warning
    duration: { type: Number, default: 3000 },
    visible: { type: Boolean, default: false },
    position: { type: String, default: 'top' },     // top | center | bottom
    customStyle: { type: String, default: '' },
  },
  emits: ['close'],
  data() {
    return {
      iconMap: { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️' },
      timer: null,
    }
  },
  watch: {
    visible(val) {
      if (this.timer) { clearTimeout(this.timer); this.timer = null; }
      if (val && this.duration > 0) {
        this.timer = setTimeout(() => {
          this.$emit('close')
          this.timer = null
        }, this.duration)
      }
    },
  },
  beforeUnmount() {
    if (this.timer) clearTimeout(this.timer)
  },
}
</script>

<style scoped>
.sm-toast {
  position: fixed; left: 50%; transform: translateX(-50%); z-index: 999;
  display: flex; align-items: center; gap: 8px;
  padding: 12px 24px; border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.15);
  animation: sm-toast-in 0.3s cubic-bezier(0.34,1.56,0.64,1);
  max-width: 90vw;
}
.sm-toast-top { top: 60px; }
.sm-toast-center { top: 50%; transform: translate(-50%, -50%); }
.sm-toast-bottom { bottom: 60px; }
.sm-toast-info { background: #1a2b28; color: #fff; }
.sm-toast-success { background: #16a34a; color: #fff; }
.sm-toast-error { background: #dc2626; color: #fff; }
.sm-toast-warning { background: #e89c35; color: #fff; }
.sm-toast-icon { font-size: 18px; }
.sm-toast-text { font-size: 14px; line-height: 1.4; }
@keyframes sm-toast-in {
  from { opacity: 0; transform: translateX(-50%) translateY(-12px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}
.sm-toast-center { animation-name: sm-toast-center-in; }
@keyframes sm-toast-center-in {
  from { opacity: 0; transform: translate(-50%, -50%) scale(0.9); }
  to { opacity: 1; transform: translate(-50%, -50%) scale(1); }
}
</style>

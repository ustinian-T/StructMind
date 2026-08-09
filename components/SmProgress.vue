<template>
  <view :class="['sm-progress-wrapper', { 'sm-progress-indeterminate': indeterminate }]">
    <view class="sm-progress-header" v-if="showLabel">
      <text class="sm-progress-label">{{ label }}</text>
      <text class="sm-progress-value">{{ displayValue }}%</text>
    </view>
    <view :class="['sm-progress-track', `sm-progress-${size}`]">
      <view
        :class="['sm-progress-bar', `sm-progress-${variant}`]"
        :style="{ width: indeterminate ? '40%' : `${clampedValue}%` }"
      ></view>
    </view>
  </view>
</template>

<script>
export default {
  props: {
    value: { type: Number, default: 0 },
    label: { type: String, default: '' },
    showLabel: { type: Boolean, default: false },
    variant: { type: String, default: 'primary' }, // primary | success | warning | danger
    size: { type: String, default: 'md' },          // sm | md | lg
    indeterminate: { type: Boolean, default: false },
  },
  computed: {
    clampedValue() { return Math.min(100, Math.max(0, this.value)) },
    displayValue() { return this.indeterminate ? '...' : Math.round(this.clampedValue) },
  },
}
</script>

<style scoped>
.sm-progress-wrapper { display: flex; flex-direction: column; gap: 4px; width: 100%; }
.sm-progress-header { display: flex; justify-content: space-between; align-items: center; }
.sm-progress-label { font-size: 13px; color: #4a5c58; font-weight: 500; }
.sm-progress-value { font-size: 13px; color: #6b8280; font-weight: 600; }
.sm-progress-track { width: 100%; border-radius: 999px; background: #edf2f0; overflow: hidden; }
.sm-progress-sm .sm-progress-track { height: 4px; }
.sm-progress-md .sm-progress-track { height: 8px; }
.sm-progress-lg .sm-progress-track { height: 12px; }
.sm-progress-bar {
  height: 100%; border-radius: inherit;
  transition: width 0.5s cubic-bezier(0.22,1,0.36,1);
}
.sm-progress-primary .sm-progress-bar { background: linear-gradient(90deg, #2d8a7b, #47b5a3); }
.sm-progress-success .sm-progress-bar { background: linear-gradient(90deg, #16a34a, #4ade80); }
.sm-progress-warning .sm-progress-bar { background: linear-gradient(90deg, #e89c35, #fbbf24); }
.sm-progress-danger .sm-progress-bar { background: linear-gradient(90deg, #dc2626, #f87171); }

.sm-progress-indeterminate .sm-progress-bar {
  animation: sm-progress-indeterminate 1.5s ease-in-out infinite;
}
@keyframes sm-progress-indeterminate {
  0% { transform: translateX(-100%); }
  50% { transform: translateX(80%); }
  100% { transform: translateX(200%); }
}
</style>

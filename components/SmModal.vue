<template>
  <view v-if="visible" class="sm-modal-overlay" @click="closeOnOverlay && $emit('close')">
    <view :class="['sm-modal', `sm-modal-${size}`]" @click.stop>
      <view class="sm-modal-header" v-if="title || $slots.header || showClose">
        <slot name="header">
          <view class="sm-modal-header-content">
            <text class="sm-modal-title">{{ title }}</text>
            <text class="sm-modal-subtitle" v-if="subtitle">{{ subtitle }}</text>
          </view>
        </slot>
        <view class="sm-modal-close" v-if="showClose" @click="$emit('close')">
          <text>×</text>
        </view>
      </view>
      <scroll-view class="sm-modal-body" scroll-y :style="{ maxHeight: maxHeight }">
        <slot />
      </scroll-view>
      <view class="sm-modal-footer" v-if="$slots.footer">
        <slot name="footer" />
      </view>
    </view>
  </view>
</template>

<script>
export default {
  props: {
    visible: { type: Boolean, default: false },
    title: { type: String, default: '' },
    subtitle: { type: String, default: '' },
    size: { type: String, default: 'md' },       // sm | md | lg | full
    showClose: { type: Boolean, default: true },
    closeOnOverlay: { type: Boolean, default: true },
    maxHeight: { type: String, default: '70vh' },
  },
  emits: ['close'],
}
</script>

<style scoped>
.sm-modal-overlay {
  position: fixed; inset: 0; z-index: 100;
  background: rgba(26,43,40,0.4); backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  padding: 16px;
  animation: sm-modal-fade 0.2s ease;
}
.sm-modal {
  width: 100%;
  background: rgba(255,255,255,0.92);
  backdrop-filter: blur(32px);
  -webkit-backdrop-filter: blur(32px);
  border-radius: 24px;
  border: 1px solid rgba(255,255,255,0.6);
  box-shadow: 0 24px 80px rgba(0,0,0,0.1);
  display: flex; flex-direction: column;
  animation: sm-modal-in 0.3s cubic-bezier(0.34,1.56,0.64,1);
}
.sm-modal-sm { max-width: 360px; }
.sm-modal-md { max-width: 480px; }
.sm-modal-lg { max-width: 640px; }
.sm-modal-full {
  max-width: 100vw; max-height: 100vh;
  margin: 0; border-radius: 0; border: none;
}

.sm-modal-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 20px 20px 0;
}
.sm-modal-header-content { flex: 1; }
.sm-modal-title { font-size: 18px; font-weight: 700; color: #1a2b28; display: block; }
.sm-modal-subtitle { font-size: 13px; color: #6b8280; margin-top: 2px; display: block; }
.sm-modal-close {
  width: 40px; height: 40px; border-radius: 12px;
  background: rgba(0,0,0,0.04); display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; cursor: pointer; margin-left: 12px;
}
.sm-modal-close text { font-size: 22px; color: #6b8280; line-height: 1; }
.sm-modal-body { padding: 16px 20px 20px; flex: 1; min-height: 0; }
.sm-modal-footer { padding: 0 20px 20px; display: flex; gap: 10px; }

@keyframes sm-modal-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes sm-modal-in {
  from { opacity: 0; transform: scale(0.94) translateY(10px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
</style>

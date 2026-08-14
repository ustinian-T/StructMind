<template>
  <view
    :class="['sm-card', { 'sm-card-glass': glass, 'sm-card-clickable': clickable, 'sm-card-flat': flat }]"
    :style="customStyle"
    @click="handleClick"
  >
    <view v-if="title || $slots.header" class="sm-card-header">
      <slot name="header">
        <text class="sm-card-title">{{ title }}</text>
        <text v-if="subtitle" class="sm-card-subtitle">{{ subtitle }}</text>
      </slot>
    </view>
    <view class="sm-card-body"><slot /></view>
    <view v-if="$slots.footer" class="sm-card-footer"><slot name="footer" /></view>
  </view>
</template>

<script>
export default {
  props: {
    title: { type: String, default: '' },
    subtitle: { type: String, default: '' },
    glass: { type: Boolean, default: false },
    flat: { type: Boolean, default: false },
    clickable: { type: Boolean, default: false },
    customStyle: { type: String, default: '' },
  },
  emits: ['click'],
  methods: {
    handleClick(e) { if (this.clickable) this.$emit('click', e) },
  },
}
</script>

<style scoped>
.sm-card {
  background: #fffefb; border-radius: 14px; padding: 20px;
  border: 1px solid #dfe9da; box-shadow: 0 12px 32px rgba(47,95,61,0.07);
  transition: all 0.25s ease;
}
.sm-card-glass {
  background: #fffefb;
  border: 1px solid #dfe9da;
}
.sm-card-flat { box-shadow: none; border: 1px solid #edf2f0; }
.sm-card-clickable:active { transform: scale(0.98); opacity: 0.9; }
.sm-card-clickable { cursor: pointer; }
.sm-card-header { margin-bottom: 12px; }
.sm-card-title { font-size: 18px; font-weight: 700; color: #1a2b28; display: block; }
.sm-card-subtitle { font-size: 13px; color: #6b8280; margin-top: 2px; display: block; }
.sm-card-footer { margin-top: 12px; padding-top: 12px; border-top: 1px solid #edf2f0; }
</style>

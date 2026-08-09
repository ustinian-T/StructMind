<template>
  <text :class="['sm-tag', `sm-tag-${variant}`, { 'sm-tag-sm': size === 'sm', 'sm-tag-dot': dot }]">
    <text class="sm-tag-dot-mark" v-if="dot">● </text>
    <slot />
  </text>
</template>

<script>
export default {
  props: {
    variant: { type: String, default: 'default' }, // default | primary | success | warning | danger | info | outline
    size: { type: String, default: 'md' },          // sm | md
    dot: { type: Boolean, default: false },
  },
}
</script>

<style scoped>
.sm-tag {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 12px; border-radius: 999px;
  font-size: 13px; font-weight: 500; white-space: nowrap;
  border: 1px solid transparent;
}
.sm-tag-sm { padding: 2px 8px; font-size: 11px; }
.sm-tag-dot-mark { font-size: 8px; }

.sm-tag-default { background: #f5f8f7; color: #6b8280; border-color: #dce5e3; }
.sm-tag-primary { background: #e8f5f2; color: #2d8a7b; border-color: #b8ddd4; }
.sm-tag-success { background: #f0fdf4; color: #16a34a; border-color: #bbf7d0; }
.sm-tag-warning { background: #fef9c3; color: #a16207; border-color: #fde68a; }
.sm-tag-danger { background: #fef2f2; color: #dc2626; border-color: #fecaca; }
.sm-tag-info { background: #dbeafe; color: #2563eb; border-color: #bfdbfe; }
.sm-tag-outline { background: transparent; color: #2d8a7b; border-color: #2d8a7b; }
</style>

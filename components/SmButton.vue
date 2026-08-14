<template>
  <button
    :class="['sm-btn', `sm-btn-${variant}`, sizeClass, { 'sm-btn-block': block, 'sm-btn-round': round }]"
    :disabled="disabled || loading"
    :style="customStyle"
    @click="handleClick"
  >
    <view v-if="loading" class="sm-btn-spinner"></view>
    <text v-if="icon && !loading" class="sm-btn-icon">{{ icon }}</text>
    <text class="sm-btn-text"><slot /></text>
  </button>
</template>

<script>
export default {
  props: {
    variant: { type: String, default: 'primary' }, // primary | soft | ghost | danger | outline | gradient
    size: { type: String, default: 'md' },          // xs | sm | md | lg
    block: { type: Boolean, default: false },
    round: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
    icon: { type: String, default: '' },
    customStyle: { type: String, default: '' },
  },
  emits: ['click'],
  computed: {
    sizeClass() {
      return { xs: 'sm-btn-xs', sm: 'sm-btn-sm', md: '', lg: 'sm-btn-lg' }[this.size] || ''
    },
  },
  methods: {
    handleClick(e) {
      if (!this.disabled && !this.loading) this.$emit('click', e)
    },
  },
}
</script>

<style scoped>
.sm-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  min-height: 44px; padding: 12px 24px; border-radius: 14px;
  font-size: 16px; font-weight: 600; border: none; cursor: pointer;
  transition: all 0.2s cubic-bezier(0.22,1,0.36,1); white-space: nowrap;
  position: relative; overflow: hidden;
}
.sm-btn::after {
  content: ''; position: absolute; inset: 0; border-radius: inherit;
  background: transparent; transition: background 0.2s;
}
.sm-btn:active::after { background: rgba(0,0,0,0.06); }
.sm-btn:active { transform: scale(0.97); }

/* Sizes */
.sm-btn-xs { min-height: 30px; padding: 5px 12px; font-size: 12px; border-radius: 8px; }
.sm-btn-sm { min-height: 36px; padding: 8px 16px; font-size: 14px; border-radius: 10px; }
.sm-btn-lg { min-height: 52px; padding: 16px 32px; font-size: 18px; border-radius: 16px; }
.sm-btn-block { width: 100%; display: flex; }
.sm-btn-round { border-radius: 9999px; }

/* Variants */
.sm-btn-primary {
  background: #477a50;
  color: #fff;
  box-shadow: 0 6px 18px rgba(47,95,61,0.18);
}
.sm-btn-primary:hover { background: #3d6d47; box-shadow: 0 8px 22px rgba(47,95,61,0.22); transform: translateY(-1px); }
.sm-btn-primary:active { box-shadow: 0 2px 10px rgba(47,95,61,0.16); }

.sm-btn-gradient {
  background: #477a50;
  color: #fff;
  box-shadow: 0 6px 18px rgba(47,95,61,0.18);
}
.sm-btn-gradient:hover { background: #3d6d47; box-shadow: 0 8px 22px rgba(47,95,61,0.22); transform: translateY(-1px); }

.sm-btn-soft { background: #edf5e9; color: #477a50; }
.sm-btn-soft:hover { background: #dfeeda; }

.sm-btn-ghost { background: transparent; color: #3d574c; border: 1px solid #d8e4d3; }
.sm-btn-ghost:hover { border-color: #7da882; color: #477a50; }

.sm-btn-outline { background: transparent; color: #477a50; border: 1px solid #7da882; }
.sm-btn-outline:hover { background: #edf5e9; }

.sm-btn-danger { background: #fef2f2; color: #dc2626; }
.sm-btn-danger:hover { background: #fde8e8; }

.sm-btn[disabled] { opacity: 0.45; cursor: not-allowed; transform: none !important; box-shadow: none !important; }

.sm-btn-spinner {
  width: 16px; height: 16px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.4); border-top-color: #fff;
  animation: sm-spin 0.7s linear infinite;
}
.sm-btn-soft .sm-btn-spinner,
.sm-btn-ghost .sm-btn-spinner {
  border-color: rgba(71,122,80,0.2); border-top-color: #477a50;
}
@keyframes sm-spin { to { transform: rotate(360deg); } }
</style>

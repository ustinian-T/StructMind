<template>
  <view :class="['sm-input-wrapper', { 'sm-input-error': invalid, 'sm-input-success': valid, 'sm-input-disabled': disabled }]">
    <view class="sm-input-label-row" v-if="label">
      <text class="sm-input-label">{{ label }}</text>
      <text class="sm-input-hint" v-if="hint">{{ hint }}</text>
    </view>
    <view class="sm-input-inner">
      <text class="sm-input-prefix" v-if="prefix">{{ prefix }}</text>
      <input
        v-if="type !== 'textarea'"
        :class="['sm-input-field', inputClass]"
        :type="type"
        :value="modelValue"
        @input="onInput"
        :placeholder="placeholder"
        :disabled="disabled"
        :maxlength="maxlength"
        :password="type === 'password'"
        :confirm-type="confirmType"
        @confirm="$emit('confirm', $event)"
        @focus="$emit('focus', $event)"
        @blur="$emit('blur', $event)"
      />
      <textarea
        v-else
        :class="['sm-input-field', 'sm-textarea-field', inputClass]"
        :value="modelValue"
        @input="onInput"
        :placeholder="placeholder"
        :disabled="disabled"
        :maxlength="maxlength"
        @focus="$emit('focus', $event)"
        @blur="$emit('blur', $event)"
      />
      <text class="sm-input-suffix" v-if="suffix">{{ suffix }}</text>
      <view class="sm-input-clear" v-if="clearable && modelValue" @click.stop="onClear">
        <text>×</text>
      </view>
    </view>
    <text class="sm-input-error-text" v-if="errorMsg">{{ errorMsg }}</text>
  </view>
</template>

<script>
export default {
  props: {
    modelValue: { type: String, default: '' },
    type: { type: String, default: 'text' }, // text | password | number | textarea | tel | email
    label: { type: String, default: '' },
    hint: { type: String, default: '' },
    placeholder: { type: String, default: '' },
    disabled: { type: Boolean, default: false },
    invalid: { type: Boolean, default: false },
    valid: { type: Boolean, default: false },
    errorMsg: { type: String, default: '' },
    maxlength: { type: Number, default: 140 },
    clearable: { type: Boolean, default: false },
    prefix: { type: String, default: '' },
    suffix: { type: String, default: '' },
    confirmType: { type: String, default: 'done' },
    inputClass: { type: String, default: '' },
  },
  emits: ['update:modelValue', 'focus', 'blur', 'confirm', 'clear'],
  methods: {
    onInput(e) {
      this.$emit('update:modelValue', e.detail.value)
    },
    onClear() {
      this.$emit('update:modelValue', '')
      this.$emit('clear')
    },
  },
}
</script>

<style scoped>
.sm-input-wrapper { display: flex; flex-direction: column; gap: 6px; }
.sm-input-label-row { display: flex; align-items: center; justify-content: space-between; }
.sm-input-label { font-size: 14px; font-weight: 600; color: #4a5c58; }
.sm-input-hint { font-size: 12px; color: #a0b0ac; }
.sm-input-inner {
  display: flex; align-items: center; gap: 8px;
  border: 1.5px solid #dce5e3; border-radius: 12px;
  background: #f9fbfa; padding: 0 14px;
  transition: all 0.2s ease;
}
.sm-input-inner:focus-within { border-color: #2d8a7b; background: #fff; box-shadow: 0 0 0 3px rgba(45,138,123,0.1); }
.sm-input-error .sm-input-inner { border-color: #dc2626; background: #fff; }
.sm-input-error .sm-input-inner:focus-within { box-shadow: 0 0 0 3px rgba(220,38,38,0.1); }
.sm-input-success .sm-input-inner { border-color: #16a34a; }
.sm-input-disabled .sm-input-inner { opacity: 0.5; background: #f5f5f5; }
.sm-input-field {
  flex: 1; height: 44px; font-size: 16px; border: none; background: transparent;
  color: #1a2b28; outline: none; padding: 0;
}
.sm-textarea-field { height: auto; min-height: 100px; padding: 12px 0; resize: vertical; line-height: 1.6; }
.sm-input-field::placeholder { color: #a0b0ac; }
.sm-input-prefix, .sm-input-suffix { font-size: 14px; color: #6b8280; flex-shrink: 0; }
.sm-input-clear {
  width: 22px; height: 22px; border-radius: 50%; background: #dce5e3;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0; cursor: pointer;
}
.sm-input-clear text { font-size: 14px; color: #6b8280; line-height: 1; }
.sm-input-error-text { font-size: 12px; color: #dc2626; }
</style>

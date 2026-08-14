<template>
  <view class="settings-page">
    <view class="ambient ambient-one"></view>
    <view class="ambient ambient-two"></view>
    <view class="settings-shell">
      <view class="settings-head">
        <view>
          <text class="eyebrow">个人模型空间</text>
          <text class="page-title">我的 AI 模型</text>
          <text class="page-desc">每个平台的密钥仅用于当前账号发起请求，页面不会回填或缓存密钥明文。</text>
        </view>
        <view class="current-model">
          <text class="current-label">当前模型</text>
          <text class="current-value">{{ config.default_model || '尚未选择' }}</text>
        </view>
      </view>

      <view v-if="loading" class="state-card"><text>正在读取你的模型配置…</text></view>

      <view v-else class="provider-grid">
        <view class="provider-card" v-for="provider in providers" :key="provider.id">
          <view class="provider-top">
            <view>
              <text class="provider-name">{{ provider.label }}</text>
              <text class="provider-status" :class="{ ready: provider.configured }">
                {{ provider.configured ? '已配置 ' + provider.key_preview : '等待填写 API Key' }}
              </text>
            </view>
            <view class="status-dot" :class="{ ready: provider.configured }"></view>
          </view>

          <view class="model-list">
            <button
              v-for="model in provider.models"
              :key="model"
              class="model-chip"
              :class="{ selected: config.default_model === model }"
              :disabled="!provider.configured || busyProvider === provider.id"
              @tap="selectModel(provider, model)"
            >
              <text>{{ model }}</text>
              <text v-if="config.default_model === model" class="selected-mark">使用中</text>
            </button>
          </view>

          <view class="key-field">
            <input
              v-if="visible[provider.id]"
              class="key-input"
              type="text"
              v-model="keys[provider.id]"
              :placeholder="provider.configured ? '输入新 Key 可替换现有配置' : '填写该平台 API Key'"
              autocomplete="off"
            />
            <input
              v-else
              class="key-input"
              type="password"
              v-model="keys[provider.id]"
              :placeholder="provider.configured ? '输入新 Key 可替换现有配置' : '填写该平台 API Key'"
              autocomplete="new-password"
            />
            <button class="reveal-button" @tap="toggleVisible(provider.id)">
              {{ visible[provider.id] ? '隐藏' : '显示' }}
            </button>
          </view>

          <view class="action-row">
            <button class="action primary" :disabled="busyProvider === provider.id" @tap="saveProvider(provider)">
              {{ busyProvider === provider.id ? '处理中…' : '保存密钥' }}
            </button>
            <button class="action" :disabled="!provider.configured || busyProvider === provider.id" @tap="testProvider(provider)">测试连接</button>
            <button class="action danger" :disabled="!provider.configured || busyProvider === provider.id" @tap="deleteProvider(provider)">删除</button>
          </view>

          <view v-if="provider.last_test" class="test-result" :class="{ ok: provider.last_test.ok }">
            <text>{{ provider.last_test.ok ? '最近连接成功' : errorText(provider.last_test.code) }}</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
import { callCloud, getErrorMessage } from '@/utils/cloud.js'

const PROVIDER_HINTS = [
  { id: 'minimax', label: 'MiniMax', models: ['MiniMax-M3[1M]'] },
  { id: 'deepseek', label: 'DeepSeek', models: ['deepseek-v4-flash', 'deepseek-v4-pro[1m]'] },
  { id: 'volcengine', label: '火山方舟', models: ['ark-code-latest'] },
  { id: 'stepfun', label: '阶跃星辰', models: ['step-router-v1'] },
]

export default {
  data() {
    return {
      loading: true,
      busyProvider: '',
      config: { default_model: '', providers: [] },
      providers: PROVIDER_HINTS.map(item => ({ ...item, configured: false, key_preview: '', last_test: null })),
      keys: { minimax: '', deepseek: '', volcengine: '', stepfun: '' },
      visible: { minimax: false, deepseek: false, volcengine: false, stepfun: false },
    }
  },
  onShow() { this.loadConfig() },
  methods: {
    token() { return getApp().globalData?.token || '' },
    applyConfig(data = {}) {
      this.config = data
      const remote = new Map((data.providers || []).map(item => [item.id, item]))
      this.providers = PROVIDER_HINTS.map(item => ({ ...item, ...(remote.get(item.id) || {}) }))
    },
    async loadConfig() {
      this.loading = true
      try {
        this.applyConfig(await callCloud('structmind-ai', 'getAIConfig', { token: this.token() }))
      } catch (error) {
        uni.showToast({ title: getErrorMessage(error, '读取模型配置失败'), icon: 'none' })
      } finally { this.loading = false }
    },
    toggleVisible(providerId) { this.visible[providerId] = !this.visible[providerId] },
    async saveProvider(provider) {
      const apiKey = String(this.keys[provider.id] || '').trim()
      if (!apiKey) {
        uni.showToast({ title: '请先填写 API Key', icon: 'none' })
        return
      }
      this.busyProvider = provider.id
      try {
        const selected = provider.models.includes(this.config.default_model)
          ? this.config.default_model : provider.models[0]
        const data = await callCloud('structmind-ai', 'saveAIConfig', {
          token: this.token(), provider_id: provider.id, api_key: apiKey, model_id: selected,
        })
        this.keys[provider.id] = ''
        this.visible[provider.id] = false
        this.applyConfig(data)
        uni.showToast({ title: '密钥已安全保存', icon: 'success' })
      } catch (error) {
        uni.showToast({ title: getErrorMessage(error, '保存失败'), icon: 'none' })
      } finally { this.busyProvider = '' }
    },
    async selectModel(provider, model) {
      if (!provider.configured) return
      this.busyProvider = provider.id
      try {
        this.applyConfig(await callCloud('structmind-ai', 'selectAIModel', {
          token: this.token(), model_id: model,
        }))
        uni.showToast({ title: '已切换模型', icon: 'success' })
      } catch (error) {
        uni.showToast({ title: getErrorMessage(error, '切换失败'), icon: 'none' })
      } finally { this.busyProvider = '' }
    },
    async testProvider(provider) {
      this.busyProvider = provider.id
      const model = provider.models.includes(this.config.default_model)
        ? this.config.default_model : provider.models[0]
      try {
        await callCloud('structmind-ai', 'testAIConnection', {
          token: this.token(), provider_id: provider.id, model_id: model,
        })
        await this.loadConfig()
        uni.showToast({ title: '连接正常', icon: 'success' })
      } catch (error) {
        await this.loadConfig()
        uni.showToast({ title: this.errorText(error.code) || getErrorMessage(error), icon: 'none' })
      } finally { this.busyProvider = '' }
    },
    deleteProvider(provider) {
      uni.showModal({
        title: `删除 ${provider.label} 配置`,
        content: '删除后，该平台模型将立即停止使用。',
        confirmColor: '#b64b4b',
        success: async result => {
          if (!result.confirm) return
          this.busyProvider = provider.id
          try {
            this.applyConfig(await callCloud('structmind-ai', 'deleteAIConfig', {
              token: this.token(), provider_id: provider.id,
            }))
            uni.showToast({ title: '配置已删除', icon: 'success' })
          } catch (error) {
            uni.showToast({ title: getErrorMessage(error, '删除失败'), icon: 'none' })
          } finally { this.busyProvider = '' }
        },
      })
    },
    errorText(code) {
      return ({
        AI_CREDENTIAL_INVALID: 'API Key 无效或没有模型权限',
        AI_QUOTA_EXCEEDED: '额度不足或请求过于频繁',
        AI_PROVIDER_TIMEOUT: '连接超时，请稍后重试',
        AI_PROVIDER_UNAVAILABLE: '模型服务暂时不可用',
      })[code] || '最近连接失败'
    },
  },
}
</script>

<style scoped>
.settings-page { min-height: 100vh; background: linear-gradient(145deg, #f7fbf4 0%, #eef7ed 48%, #f8fbf6 100%); color: #183229; position: relative; overflow: hidden; }
.ambient { position: fixed; border-radius: 50%; filter: blur(8px); pointer-events: none; opacity: .5; }
.ambient-one { width: 380px; height: 380px; right: -120px; top: -150px; background: radial-gradient(circle, rgba(154, 222, 170, .38), transparent 68%); }
.ambient-two { width: 320px; height: 320px; left: -150px; bottom: -100px; background: radial-gradient(circle, rgba(195, 234, 181, .3), transparent 70%); }
.settings-shell { width: min(1180px, calc(100% - 48px)); margin: 0 auto; padding: 42px 0 72px; position: relative; z-index: 1; }
.settings-head { display: flex; justify-content: space-between; gap: 28px; align-items: flex-end; margin-bottom: 28px; }
.eyebrow { display: block; color: #5c8f69; font-size: 13px; letter-spacing: .12em; margin-bottom: 8px; }
.page-title { display: block; font-size: 32px; font-weight: 750; letter-spacing: -.03em; }
.page-desc { display: block; max-width: 650px; margin-top: 10px; color: #678075; font-size: 14px; line-height: 1.7; }
.current-model { min-width: 240px; padding: 16px 18px; border: 1px solid rgba(124, 169, 132, .28); border-radius: 18px; background: rgba(255, 255, 255, .64); backdrop-filter: blur(18px); box-shadow: 0 14px 35px rgba(63, 104, 70, .08); }
.current-label, .current-value { display: block; }
.current-label { color: #789084; font-size: 12px; }
.current-value { margin-top: 5px; font-size: 16px; font-weight: 650; color: #315f3d; }
.provider-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.provider-card, .state-card { background: rgba(255, 255, 255, .78); border: 1px solid rgba(130, 171, 137, .24); border-radius: 24px; padding: 24px; box-shadow: 0 20px 50px rgba(59, 96, 64, .08); backdrop-filter: blur(20px); }
.provider-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.provider-name, .provider-status { display: block; }
.provider-name { font-size: 19px; font-weight: 700; }
.provider-status { margin-top: 6px; color: #8b9d94; font-size: 12px; }
.provider-status.ready { color: #548760; }
.status-dot { width: 10px; height: 10px; margin-top: 6px; border-radius: 50%; background: #c6d1cb; box-shadow: 0 0 0 6px rgba(198, 209, 203, .2); }
.status-dot.ready { background: #79bd84; box-shadow: 0 0 0 6px rgba(121, 189, 132, .16), 0 0 18px rgba(91, 177, 108, .36); }
.model-list { display: flex; flex-wrap: wrap; gap: 8px; margin: 20px 0; }
.model-chip { margin: 0; min-height: 38px; padding: 0 13px; border: 1px solid #dce9dd; border-radius: 12px; background: #f8fbf7; color: #4c6858; font-size: 12px; display: flex; align-items: center; gap: 8px; }
.model-chip::after, .action::after, .reveal-button::after { border: 0; }
.model-chip.selected { border-color: #83bc8a; background: linear-gradient(135deg, #eaf6e8, #f5fbf2); color: #2f683d; box-shadow: inset 0 1px rgba(255,255,255,.9), 0 6px 18px rgba(80, 137, 89, .1); }
.selected-mark { padding: 2px 6px; border-radius: 999px; background: rgba(82, 151, 95, .12); font-size: 10px; }
.key-field { display: flex; align-items: center; border: 1px solid #dce7dc; border-radius: 14px; background: rgba(249, 252, 248, .9); overflow: hidden; }
.key-input { flex: 1; height: 46px; padding: 0 14px; font-size: 13px; color: #244333; }
.reveal-button { margin: 0; width: 64px; height: 46px; line-height: 46px; padding: 0; border-radius: 0; background: transparent; color: #5d8167; font-size: 12px; }
.action-row { display: flex; gap: 8px; margin-top: 14px; }
.action { margin: 0; min-height: 40px; padding: 0 14px; border-radius: 12px; border: 1px solid #d8e5d8; background: rgba(255,255,255,.72); color: #4f6a58; font-size: 12px; }
.action.primary { color: #fff; border-color: #78ad80; background: linear-gradient(135deg, rgba(91, 160, 105, .92), rgba(116, 184, 124, .88)); box-shadow: inset 0 1px rgba(255,255,255,.25), 0 8px 20px rgba(71, 127, 82, .18); }
.action.danger { color: #a05555; }
.test-result { margin-top: 12px; color: #a45b5b; font-size: 12px; }
.test-result.ok { color: #4d8759; }
@media (max-width: 820px) { .settings-shell { width: min(100% - 28px, 680px); padding-top: 26px; } .settings-head { align-items: stretch; flex-direction: column; } .provider-grid { grid-template-columns: 1fr; } .current-model { min-width: 0; } }
</style>

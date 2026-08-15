<template>
  <!-- 用 scroll-view 包裹确保 H5 端一定能上下滚动，绕过 uni-app x 在某些 H5 外壳下不响应 body overflow 的问题。 -->
  <scroll-view scroll-y class="settings-scroll">
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
  </scroll-view>
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
/* 滚动容器：template 根用 scroll-view，确保 H5 / 各端都能滚 */
.settings-scroll {
  width: 100%;
  height: 100vh;
  background: #f5f8f3;
}
/* 滚动：之前 overflow:hidden 把内容切掉无法下滑；改为 min-height + 自然滚动 */
.settings-page {
  min-height: 100vh;
  background: #f5f8f3;
  color: #183229;
  position: relative;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
}
/* 装饰光晕降权：之前 blur(8px) 在大屏上非常喧宾夺主，改为更柔和的薄雾 */
.ambient { position: fixed; border-radius: 50%; filter: blur(40px); pointer-events: none; opacity: .35; z-index: 0; }
.ambient-one { width: 320px; height: 320px; right: -100px; top: -120px; background: radial-gradient(circle, rgba(154, 222, 170, .42), transparent 70%); }
.ambient-two { width: 280px; height: 280px; left: -120px; bottom: -100px; background: radial-gradient(circle, rgba(195, 234, 181, .35), transparent 70%); }
.settings-shell { width: min(1180px, calc(100% - 48px)); margin: 0 auto; padding: 32px 0 80px; position: relative; z-index: 1; }
.settings-head { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; margin-bottom: 24px; }
.eyebrow { display: block; color: #5c8f69; font-size: 12px; letter-spacing: .14em; margin-bottom: 8px; text-transform: uppercase; font-weight: 600; }
.page-title { display: block; font-size: 28px; font-weight: 700; letter-spacing: -.02em; color: #183229; }
.page-desc { display: block; max-width: 620px; margin-top: 8px; color: #6b7d72; font-size: 14px; line-height: 1.65; }
.current-model {
  min-width: 220px;
  padding: 14px 18px;
  border: 1px solid #d8e4d3;
  border-radius: 14px;
  background: #fffefb;
  box-shadow: 0 1px 2px rgba(47, 95, 61, .04);
}
.current-label, .current-value { display: block; }
.current-label { color: #708076; font-size: 11px; letter-spacing: .04em; }
.current-value { margin-top: 4px; font-size: 15px; font-weight: 600; color: #2f5f3d; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
/* 卡片：去掉 blur 玻璃效果，改为纯白卡片 + 细描边，信息层级更清晰 */
.provider-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.provider-card, .state-card {
  background: #ffffff;
  border: 1px solid #e2ebde;
  border-radius: 16px;
  padding: 22px;
  box-shadow: 0 1px 2px rgba(47, 95, 61, .04), 0 6px 18px rgba(47, 95, 61, .03);
}
.provider-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding-bottom: 16px; border-bottom: 1px solid #eef3ec; margin-bottom: 16px; }
.provider-name, .provider-status { display: block; }
.provider-name { font-size: 17px; font-weight: 700; color: #183229; letter-spacing: -.01em; }
.provider-status { margin-top: 4px; color: #8b9d94; font-size: 12px; }
.provider-status.ready { color: #397548; }
.status-dot { width: 8px; height: 8px; margin-top: 8px; border-radius: 50%; background: #c6d1cb; flex-shrink: 0; }
.status-dot.ready { background: #56a867; box-shadow: 0 0 0 3px rgba(86, 168, 103, .15); }
.model-list { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 16px; }
.model-chip {
  margin: 0;
  min-height: 32px;
  padding: 0 12px;
  border: 1px solid #d8e4d3;
  border-radius: 999px;
  background: #fffefb;
  color: #4c6858;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all .15s ease;
}
.model-chip::after, .action::after, .reveal-button::after { border: 0; }
.model-chip:active { transform: scale(.97); }
.model-chip.selected {
  border-color: #477a50;
  background: #477a50;
  color: #fff;
  font-weight: 600;
}
.model-chip.selected .selected-mark { background: rgba(255, 255, 255, .22); color: #fff; }
.selected-mark { padding: 2px 6px; border-radius: 999px; background: rgba(82, 151, 95, .12); color: #2f5f3d; font-size: 10px; font-weight: 500; }
.key-field {
  display: flex;
  align-items: center;
  border: 1px solid #d8e4d3;
  border-radius: 10px;
  background: #f8fbf5;
  margin-bottom: 14px;
  transition: border-color .15s ease;
}
.key-field:focus-within { border-color: #477a50; background: #fff; }
.key-input { flex: 1; height: 42px; padding: 0 14px; font-size: 13px; color: #244333; background: transparent; }
.reveal-button { margin: 0; width: 60px; height: 42px; line-height: 42px; padding: 0; border-radius: 0; background: transparent; color: #5d8167; font-size: 12px; }
.action-row { display: flex; gap: 8px; }
.action {
  margin: 0;
  flex: 1;
  min-height: 38px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid #d8e5d8;
  background: #fffefb;
  color: #4f6a58;
  font-size: 13px;
  font-weight: 500;
  transition: all .15s ease;
}
.action:active:not([disabled]) { transform: scale(.97); }
.action[disabled] { opacity: .45; }
.action.primary {
  color: #fff;
  border-color: #477a50;
  background: #477a50;
  font-weight: 600;
}
.action.primary:active:not([disabled]) { background: #2f5f3d; }
.action.danger { color: #b84b42; border-color: #ebd6d2; }
.action.danger:active:not([disabled]) { background: #fff0ee; }
.test-result { margin-top: 12px; color: #b84b42; font-size: 12px; padding: 8px 12px; background: #fff5f4; border-radius: 8px; }
.test-result.ok { color: #397548; background: #eaf5e7; }
@media (max-width: 820px) {
  .settings-shell { width: min(100% - 24px, 680px); padding-top: 24px; padding-bottom: 60px; }
  .settings-head { align-items: stretch; flex-direction: column; gap: 16px; }
  .provider-grid { grid-template-columns: 1fr; gap: 14px; }
  .current-model { min-width: 0; }
}
</style>

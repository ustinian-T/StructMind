<template>
  <view class="sm-radar">
    <canvas
      :canvas-id="canvasId"
      :id="canvasId"
      :style="{ width: canvasWidth + 'px', height: canvasHeight + 'px' }"
      class="sm-radar-canvas"
    ></canvas>
    <view class="sm-radar-labels" v-if="labels.length">
      <view class="sm-radar-label" v-for="(label, i) in labels" :key="i">
        <view class="sm-radar-dot" :style="{ background: color }"></view>
        <text class="sm-radar-label-text">{{ label }}</text>
        <text class="sm-radar-label-value">{{ values[i] }}%</text>
      </view>
    </view>
  </view>
</template>

<script>
export default {
  props: {
    canvasId: { type: String, default: 'sm-radar-canvas' },
    values: { type: Array, default: () => [0, 0, 0, 0] },
    labels: { type: Array, default: () => [] },
    maxValue: { type: Number, default: 100 },
    color: { type: String, default: '#2d8a7b' },
    fillColor: { type: String, default: 'rgba(45,138,123,0.12)' },
    gridColor: { type: String, default: '#edf2f0' },
    size: { type: Number, default: 280 },
  },
  computed: {
    canvasWidth() { return this.size },
    canvasHeight() { return this.size },
  },
  watch: {
    values: { handler: 'draw', immediate: false },
    labels: { handler: 'draw', immediate: false },
  },
  mounted() {
    this.$nextTick(() => { setTimeout(() => this.draw(), 150) })
  },
  methods: {
    draw() {
      // uni-app canvas radar - draws a radar chart using SVG-like approach via canvas
      // For uni-app compatibility, we draw using 2D canvas API
      const ctx = uni.createCanvasContext(this.canvasId, this)
      if (!ctx) return

      const cx = this.size / 2
      const cy = this.size / 2
      const maxR = this.size * 0.38
      const count = Math.max(this.labels.length, this.values.length)
      if (count < 2) {
        ctx.clearRect(0, 0, this.size, this.size)
        ctx.draw()
        return
      }

      ctx.clearRect(0, 0, this.size, this.size)

      // Grid circles
      for (let p = 0.25; p <= 1; p += 0.25) {
        ctx.setStrokeStyle(this.gridColor)
        ctx.setLineWidth(0.5)
        ctx.beginPath()
        for (let i = 0; i <= count; i++) {
          const angle = (Math.PI * 2 / count) * i - Math.PI / 2
          const r = maxR * p
          const x = cx + r * Math.cos(angle)
          const y = cy + r * Math.sin(angle)
          if (i === 0) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        ctx.closePath()
        ctx.stroke()

        // Percentage label on top axis
        if (p > 0) {
          ctx.setFillStyle('#a0b0ac')
          ctx.setFontSize(10)
          ctx.setTextAlign('center')
          ctx.fillText(Math.round(p * 100) + '%', cx, cy - maxR * p - 4)
        }
      }

      // Axis lines
      for (let i = 0; i < count; i++) {
        const angle = (Math.PI * 2 / count) * i - Math.PI / 2 + 0.0001
        ctx.setStrokeStyle(this.gridColor)
        ctx.setLineWidth(0.5)
        ctx.beginPath()
        ctx.moveTo(cx, cy)
        ctx.lineTo(cx + maxR * Math.cos(angle), cy + maxR * Math.sin(angle))
        ctx.stroke()

        // Labels at ends of axes
        const lx = cx + (maxR + 20) * Math.cos(angle)
        const ly = cy + (maxR + 20) * Math.sin(angle)
        ctx.setFillStyle('#4a5c58')
        ctx.setFontSize(12)
        ctx.setTextAlign(Math.abs(lx - cx) < 10 ? 'center' : lx > cx ? 'left' : 'right')
        ctx.setTextBaseline(Math.abs(ly - cy) < 10 ? 'center' : ly < cy ? 'bottom' : 'top')
        const l = this.labels[i] || ''
        ctx.fillText(l, lx, ly)
      }

      // Data polygon
      const pts = []
      for (let i = 0; i < count; i++) {
        const angle = (Math.PI * 2 / count) * i - Math.PI / 2
        const v = (this.values[i] || 0) / this.maxValue
        const r = maxR * Math.max(0, Math.min(1, v))
        pts.push({ x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) })
      }

      // Fill
      ctx.setFillStyle(this.fillColor)
      ctx.beginPath()
      pts.forEach((p, i) => {
        if (i === 0) ctx.moveTo(p.x, p.y)
        else ctx.lineTo(p.x, p.y)
      })
      ctx.closePath()
      ctx.fill()

      // Stroke
      ctx.setStrokeStyle(this.color)
      ctx.setLineWidth(2)
      ctx.beginPath()
      pts.forEach((p, i) => {
        if (i === 0) ctx.moveTo(p.x, p.y)
        else ctx.lineTo(p.x, p.y)
      })
      ctx.closePath()
      ctx.stroke()

      // Data points
      pts.forEach(p => {
        ctx.setFillStyle('#fff')
        ctx.setStrokeStyle(this.color)
        ctx.setLineWidth(2)
        ctx.beginPath()
        ctx.arc(p.x, p.y, 4, 0, Math.PI * 2)
        ctx.fill()
        ctx.stroke()
      })

      ctx.draw()
    },

    // Re-draw helper
    refresh() {
      this.$nextTick(() => { setTimeout(() => this.draw(), 100) })
    },
  },
}
</script>

<style scoped>
.sm-radar {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
}
.sm-radar-canvas {
  border-radius: 16px;
}
.sm-radar-labels {
  display: flex; flex-wrap: wrap; gap: 12px; justify-content: center;
  padding: 8px 0;
}
.sm-radar-label {
  display: flex; align-items: center; gap: 4px;
}
.sm-radar-dot {
  width: 8px; height: 8px; border-radius: 50%;
}
.sm-radar-label-text {
  font-size: 12px; color: #6b8280;
}
.sm-radar-label-value {
  font-size: 12px; font-weight: 600; color: #1a2b28;
}
</style>

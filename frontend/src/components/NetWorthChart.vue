<script setup lang="ts">
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
} from 'chart.js'
import type { Plugin } from 'chart.js'
import { formatCurrency } from '../composables/useApi'
import type { NetWorthPoint } from '../types'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip)

const props = defineProps<{
  points: NetWorthPoint[]
  todayIndex: number
}>()

function formatMonth(month: string): string {
  const [year, mon] = month.split('-')
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[parseInt(mon) - 1]} '${year.slice(2)}`
}

const chartData = computed(() => {
  if (!props.points.length) return null

  const labels = props.points.map(p => formatMonth(p.month))

  // Historical data (up to and including today)
  const historical = props.points.map((p, i) =>
    i <= props.todayIndex ? p.balance / 100 : null
  )

  // Projected data (from today onward)
  const projected = props.points.map((p, i) =>
    i >= props.todayIndex ? p.balance / 100 : null
  )

  return {
    labels,
    datasets: [
      {
        label: 'Historical',
        data: historical,
        borderColor: '#0d9488',
        backgroundColor: 'rgba(13, 148, 136, 0.08)',
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        pointHoverRadius: 4,
        borderWidth: 2,
      },
      {
        label: 'Projected',
        data: projected,
        borderColor: '#0d9488',
        backgroundColor: 'rgba(13, 148, 136, 0.04)',
        borderDash: [6, 4],
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        pointHoverRadius: 4,
        borderWidth: 2,
      },
    ],
  }
})

// Custom plugin to draw "Today" vertical line
const todayLinePlugin: Plugin = {
  id: 'todayLine',
  afterDraw(chart) {
    const todayIdx = props.todayIndex
    const meta = chart.getDatasetMeta(0)
    if (!meta.data[todayIdx]) return

    const x = meta.data[todayIdx].x
    const { top, bottom } = chart.chartArea
    const ctx = chart.ctx

    ctx.save()
    ctx.beginPath()
    ctx.setLineDash([4, 4])
    ctx.strokeStyle = '#64748b'
    ctx.lineWidth = 1
    ctx.moveTo(x, top)
    ctx.lineTo(x, bottom)
    ctx.stroke()

    ctx.setLineDash([])
    ctx.font = '10px "DM Mono", monospace'
    ctx.fillStyle = '#64748b'
    ctx.textAlign = 'center'
    ctx.fillText('Today', x, top - 6)
    ctx.restore()
  },
}

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  interaction: {
    mode: 'index' as const,
    intersect: false,
  },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: '#1e293b',
      titleFont: { family: 'DM Mono', size: 11 },
      bodyFont: { family: 'DM Mono', size: 11 },
      padding: 10,
      cornerRadius: 8,
      filter: (item: any) => item.raw !== null,
      callbacks: {
        label: (ctx: any) => {
          if (ctx.raw === null) return ''
          return `${ctx.dataset.label}: ${formatCurrency(Math.round(ctx.raw * 100))}`
        },
      },
    },
  },
  scales: {
    x: {
      grid: { display: false },
      border: { display: false },
      ticks: {
        font: { family: 'DM Mono', size: 10 },
        color: '#64748b',
        maxTicksLimit: 12,
      },
    },
    y: {
      grid: { color: 'rgba(0,0,0,0.04)' },
      border: { display: false },
      ticks: {
        font: { family: 'DM Mono', size: 10 },
        color: '#64748b',
        callback: (val: any) => {
          const n = val as number
          if (Math.abs(n) >= 1000000) return `$${(n / 1000000).toFixed(1)}M`
          if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(0)}K`
          return `$${n}`
        },
      },
    },
  },
}

const chartPlugins = [todayLinePlugin]
</script>

<template>
  <div class="w-full">
    <div v-if="chartData && chartData.labels.length > 0" class="h-80">
      <Line :data="chartData" :options="chartOptions" :plugins="chartPlugins" />
    </div>
    <div v-else class="h-80 flex items-center justify-center">
      <p class="text-sm text-surface-400">No data available</p>
    </div>
  </div>
</template>

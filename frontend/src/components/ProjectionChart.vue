<script setup lang="ts">
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
} from 'chart.js'
import { formatCurrency } from '../composables/useApi'
import type { ProjectionBand } from '../types'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Filler)

const props = defineProps<{
  bands: ProjectionBand[]
  monthlyContribution: number
  timeHorizonYears: number
}>()

const chartData = computed(() => {
  if (!props.bands.length) return null

  const years = Array.from({ length: props.timeHorizonYears + 1 }, (_, i) => `Year ${i}`)

  // Find bands by return rate (lowest, middle, highest)
  const sorted = [...props.bands].sort((a, b) => a.annual_return - b.annual_return)
  const low = sorted[0]
  const avg = sorted.length > 1 ? sorted[Math.floor(sorted.length / 2)] : sorted[0]
  const high = sorted[sorted.length - 1]

  return {
    labels: years,
    datasets: [
      {
        label: high.label,
        data: high.points.map(p => p.balance / 100),
        borderColor: 'rgba(200, 255, 0, 0.4)',
        backgroundColor: 'rgba(200, 255, 0, 0.05)',
        borderWidth: 1.5,
        borderDash: [4, 4],
        fill: '+2',
        pointRadius: 0,
        pointHitRadius: 8,
        tension: 0.3,
      },
      {
        label: avg.label,
        data: avg.points.map(p => p.balance / 100),
        borderColor: '#c8ff00',
        backgroundColor: 'transparent',
        borderWidth: 2.5,
        fill: false,
        pointRadius: 0,
        pointHitRadius: 8,
        tension: 0.3,
      },
      {
        label: low.label,
        data: low.points.map(p => p.balance / 100),
        borderColor: 'rgba(200, 255, 0, 0.4)',
        backgroundColor: 'transparent',
        borderWidth: 1.5,
        borderDash: [4, 4],
        fill: false,
        pointRadius: 0,
        pointHitRadius: 8,
        tension: 0.3,
      },
      {
        label: 'Contributions Only',
        data: avg.points.map(p => p.contributions / 100),
        borderColor: 'rgba(119, 119, 119, 0.4)',
        backgroundColor: 'transparent',
        borderWidth: 1,
        borderDash: [2, 4],
        fill: false,
        pointRadius: 0,
        pointHitRadius: 8,
        tension: 0,
      },
    ],
  }
})

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
      backgroundColor: '#0a0a0a',
      titleFont: { family: 'DM Mono', size: 11 },
      bodyFont: { family: 'DM Mono', size: 11 },
      padding: 10,
      cornerRadius: 8,
      callbacks: {
        label: (ctx: any) => `${ctx.dataset.label}: ${formatCurrency(Math.round(ctx.raw * 100))}`,
      },
    },
  },
  scales: {
    x: {
      grid: { display: false },
      border: { display: false },
      ticks: {
        font: { family: 'DM Mono', size: 10 },
        color: '#777777',
        maxTicksLimit: 7,
      },
    },
    y: {
      grid: { color: 'rgba(0,0,0,0.04)' },
      border: { display: false },
      ticks: {
        font: { family: 'DM Mono', size: 10 },
        color: '#777777',
        callback: (val: any) => {
          const v = val as number
          if (v >= 1000000) return `$${(v / 1000000).toFixed(1)}M`
          if (v >= 1000) return `$${(v / 1000).toFixed(0)}K`
          return `$${v}`
        },
      },
    },
  },
}
</script>

<template>
  <div class="w-full">
    <!-- Legend -->
    <div class="flex items-center gap-4 mb-4 flex-wrap">
      <div class="flex items-center gap-1.5">
        <div class="w-5 h-0.5 bg-accent"></div>
        <span class="text-[10px] font-mono text-surface-400 uppercase tracking-wider">Average (10%)</span>
      </div>
      <div class="flex items-center gap-1.5">
        <div class="w-5 h-0.5 bg-accent/40 border-t border-dashed border-accent/40"></div>
        <span class="text-[10px] font-mono text-surface-400 uppercase tracking-wider">Low / High</span>
      </div>
      <div class="flex items-center gap-1.5">
        <div class="w-5 h-0.5 bg-surface-300/40 border-t border-dashed border-surface-300"></div>
        <span class="text-[10px] font-mono text-surface-400 uppercase tracking-wider">Contributions Only</span>
      </div>
    </div>

    <div v-if="chartData" class="h-80">
      <Line :data="chartData" :options="chartOptions" />
    </div>
    <div v-else class="h-80 flex items-center justify-center">
      <p class="text-sm text-surface-400">No projection data</p>
    </div>
  </div>
</template>

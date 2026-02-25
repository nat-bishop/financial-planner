<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { Bar } from 'vue-chartjs'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
} from 'chart.js'
import { useApi, formatCurrency } from '../composables/useApi'
import type { MonthlyTrendResponse } from '../types'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)

const api = useApi()
const data = ref<MonthlyTrendResponse | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    data.value = await api.get<MonthlyTrendResponse>('/analytics/monthly-trend')
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
})

function formatMonth(month: string): string {
  const [year, mon] = month.split('-')
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${months[parseInt(mon) - 1]} ${year.slice(2)}`
}

const chartData = computed(() => {
  if (!data.value || data.value.months.length === 0) return null

  return {
    labels: data.value.months.map(m => formatMonth(m.month)),
    datasets: [
      {
        label: 'Income',
        data: data.value.months.map(m => m.income / 100),
        backgroundColor: '#10b981',
        borderRadius: 4,
        borderSkipped: false,
        barPercentage: 0.8,
        categoryPercentage: 0.7,
      },
      {
        label: 'Expenses',
        data: data.value.months.map(m => m.expenses / 100),
        backgroundColor: '#ef4444',
        borderRadius: 4,
        borderSkipped: false,
        barPercentage: 0.8,
        categoryPercentage: 0.7,
      },
    ],
  }
})

const chartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: '#1e293b',
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
        color: '#64748b',
      },
    },
    y: {
      grid: { color: 'rgba(0,0,0,0.04)' },
      border: { display: false },
      ticks: {
        font: { family: 'DM Mono', size: 10 },
        color: '#64748b',
        callback: (val: any) => `$${(val as number).toLocaleString()}`,
      },
    },
  },
}
</script>

<template>
  <div class="w-full">
    <!-- Legend -->
    <div class="flex items-center gap-4 mb-4">
      <div class="flex items-center gap-1.5">
        <div class="w-2.5 h-2.5 rounded-sm bg-income"></div>
        <span class="text-[10px] font-mono text-surface-400 uppercase tracking-wider">Income</span>
      </div>
      <div class="flex items-center gap-1.5">
        <div class="w-2.5 h-2.5 rounded-sm bg-expense"></div>
        <span class="text-[10px] font-mono text-surface-400 uppercase tracking-wider">Expenses</span>
      </div>
    </div>

    <div v-if="loading" class="h-64 flex items-center justify-center">
      <div class="w-5 h-5 border-2 border-surface-300 border-t-accent rounded-full animate-spin"></div>
    </div>
    <div v-else-if="chartData && chartData.labels.length > 0" class="h-64">
      <Bar :data="chartData" :options="chartOptions" />
    </div>
    <div v-else class="h-64 flex items-center justify-center">
      <p class="text-sm text-surface-400">No transaction data yet</p>
    </div>
  </div>
</template>

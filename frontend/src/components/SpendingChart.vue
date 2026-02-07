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
import type { SpendingByCategoryResponse } from '../types'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)

const api = useApi()
const spending = ref<SpendingByCategoryResponse | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    spending.value = await api.get<SpendingByCategoryResponse>('/analytics/spending-by-category')
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
})

const chartData = computed(() => {
  if (!spending.value) return null

  const cats = spending.value.categories.slice(0, 8)

  return {
    labels: cats.map(c => c.category || 'Uncategorized'),
    datasets: [{
      data: cats.map(c => c.total / 100),
      backgroundColor: [
        '#c8ff00',
        '#ff4d4d',
        '#4da6ff',
        '#ffb84d',
        '#00d68f',
        '#b084ff',
        '#ff84b0',
        '#84d9ff',
      ],
      borderRadius: 6,
      borderSkipped: false,
      barThickness: 28,
    }],
  }
})

const chartOptions = {
  indexAxis: 'y' as const,
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: '#0a0a0a',
      titleFont: { family: 'DM Mono', size: 11 },
      bodyFont: { family: 'DM Mono', size: 11 },
      padding: 10,
      cornerRadius: 8,
      callbacks: {
        label: (ctx: any) => formatCurrency(Math.round(ctx.raw * 100)),
      },
    },
  },
  scales: {
    x: {
      display: false,
      grid: { display: false },
    },
    y: {
      grid: { display: false },
      border: { display: false },
      ticks: {
        font: { family: 'DM Sans', size: 12 },
        color: '#777777',
        padding: 8,
      },
    },
  },
}
</script>

<template>
  <div class="w-full">
    <div v-if="loading" class="h-64 flex items-center justify-center">
      <div class="w-5 h-5 border-2 border-surface-300 border-t-accent rounded-full animate-spin"></div>
    </div>
    <div v-else-if="chartData && chartData.labels.length > 0" class="h-64">
      <Bar :data="chartData" :options="chartOptions" />
    </div>
    <div v-else class="h-64 flex items-center justify-center">
      <p class="text-sm text-surface-400">No spending data yet</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useProjectionStore } from '../stores/projection'
import NetWorthChart from '../components/NetWorthChart.vue'
import { formatCurrency } from '../composables/useApi'

const store = useProjectionStore()

onMounted(async () => {
  await store.fetch()
})
</script>

<template>
  <div class="p-8 max-w-6xl animate-fade-up">
    <!-- Header -->
    <div class="mb-10">
      <h1 class="font-display text-4xl text-surface-100 tracking-tight mb-1">Stats</h1>
      <p class="text-sm text-surface-400">Net worth history and financial summary</p>
    </div>

    <!-- Loading -->
    <div v-if="store.loading" class="flex items-center justify-center py-20">
      <div class="w-6 h-6 border-2 border-surface-300 border-t-accent rounded-full animate-spin"></div>
    </div>

    <template v-else-if="store.data">
      <!-- Summary cards -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div class="bg-white border border-surface-900/8 rounded-2xl p-6">
          <p class="text-xs font-mono uppercase tracking-widest text-surface-400 mb-2">Total Balance</p>
          <p class="font-display text-2xl text-surface-100 tracking-tight">
            {{ formatCurrency(store.data.points[store.data.today_index]?.balance ?? 0) }}
          </p>
        </div>
        <div class="bg-white border border-surface-900/8 rounded-2xl p-6">
          <p class="text-xs font-mono uppercase tracking-widest text-surface-400 mb-2">Monthly Income</p>
          <p class="font-display text-2xl text-income tracking-tight">
            {{ formatCurrency(store.data.monthly_income) }}
          </p>
        </div>
        <div class="bg-white border border-surface-900/8 rounded-2xl p-6">
          <p class="text-xs font-mono uppercase tracking-widest text-surface-400 mb-2">Monthly Expenses</p>
          <p class="font-display text-2xl text-expense tracking-tight">
            {{ formatCurrency(-store.data.monthly_expenses) }}
          </p>
        </div>
        <div class="bg-white border border-surface-900/8 rounded-2xl p-6">
          <p class="text-xs font-mono uppercase tracking-widest text-surface-400 mb-2">Monthly Savings</p>
          <p
            class="font-display text-2xl tracking-tight"
            :class="store.data.monthly_net >= 0 ? 'text-income' : 'text-expense'"
          >
            {{ formatCurrency(store.data.monthly_net) }}
          </p>
        </div>
      </div>

      <!-- Net Worth Chart -->
      <div class="mb-8">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xs font-mono uppercase tracking-widest text-surface-400">
            Net Worth Over Time
          </h2>
          <div class="flex items-center gap-3">
            <div class="flex items-center gap-1.5">
              <div class="w-4 h-0.5 bg-accent rounded"></div>
              <span class="text-[10px] font-mono text-surface-400 uppercase tracking-wider">Historical</span>
            </div>
            <div class="flex items-center gap-1.5">
              <div class="w-4 h-0.5 bg-accent/50 rounded" style="background: repeating-linear-gradient(90deg, #0d9488 0, #0d9488 4px, transparent 4px, transparent 8px)"></div>
              <span class="text-[10px] font-mono text-surface-400 uppercase tracking-wider">Projected</span>
            </div>
          </div>
        </div>
        <div class="bg-white border border-surface-900/8 rounded-2xl p-6">
          <NetWorthChart
            :points="store.data.points"
            :today-index="store.data.today_index"
          />
        </div>
      </div>
    </template>

    <!-- Error -->
    <div v-else-if="store.error" class="text-center py-20">
      <p class="text-sm text-expense">{{ store.error }}</p>
    </div>

    <!-- Empty state -->
    <div v-else class="text-center py-20">
      <p class="text-sm text-surface-400">No financial data available yet. Connect an account to get started.</p>
    </div>
  </div>
</template>

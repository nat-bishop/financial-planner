<script setup lang="ts">
import { onMounted } from 'vue'
import { useProjectionStore } from '../stores/projection'
import ProjectionChart from '../components/ProjectionChart.vue'
import ProjectionConfig from '../components/ProjectionConfig.vue'
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
      <h1 class="font-display text-4xl text-surface-100 tracking-tight mb-1">Projection</h1>
      <p class="text-sm text-surface-400">See how your savings could grow over time with market returns</p>
    </div>

    <!-- Loading -->
    <div v-if="store.loading" class="flex items-center justify-center py-20">
      <div class="w-6 h-6 border-2 border-surface-300 border-t-accent rounded-full animate-spin"></div>
    </div>

    <template v-else-if="store.projection">
      <!-- Summary cards -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div class="bg-surface-0 rounded-2xl p-6 border border-surface-200/50">
          <p class="text-xs font-mono uppercase tracking-widest text-surface-500 mb-2">Monthly Income</p>
          <p class="font-display text-2xl text-income tracking-tight">
            {{ formatCurrency(store.projection.monthly_income) }}
          </p>
          <p v-if="store.projection.income_sources.length > 0" class="text-[10px] text-surface-400 mt-1">
            {{ store.projection.income_sources.length }} source{{ store.projection.income_sources.length > 1 ? 's' : '' }} detected
          </p>
        </div>
        <div class="bg-surface-0 rounded-2xl p-6 border border-surface-200/50">
          <p class="text-xs font-mono uppercase tracking-widest text-surface-500 mb-2">Monthly Expenses</p>
          <p class="font-display text-2xl text-expense tracking-tight">
            {{ formatCurrency(-store.projection.monthly_expenses) }}
          </p>
        </div>
        <div class="bg-surface-0 rounded-2xl p-6 border border-surface-200/50">
          <p class="text-xs font-mono uppercase tracking-widest text-surface-500 mb-2">Monthly Savings</p>
          <p
            class="font-display text-2xl tracking-tight"
            :class="store.projection.monthly_contribution >= 0 ? 'text-income' : 'text-expense'"
          >
            {{ formatCurrency(store.projection.monthly_contribution) }}
          </p>
          <p class="text-[10px] text-surface-400 mt-1">
            {{ store.projection.is_configured ? 'Configured' : 'Auto-calculated' }}
          </p>
        </div>
      </div>

      <!-- Projection Chart -->
      <div class="mb-8">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xs font-mono uppercase tracking-widest text-surface-400">
            Investment Growth Projection
          </h2>
          <span class="text-[10px] font-mono text-surface-300">
            {{ store.projection.time_horizon_years }}-year horizon
          </span>
        </div>
        <div class="bg-white border border-surface-900/8 rounded-2xl p-6">
          <ProjectionChart
            :bands="store.projection.bands"
            :monthly-contribution="store.projection.monthly_contribution"
            :time-horizon-years="store.projection.time_horizon_years"
          />
        </div>
      </div>

      <!-- Configuration -->
      <ProjectionConfig />
    </template>

    <!-- Error -->
    <div v-else-if="store.error" class="text-center py-20">
      <p class="text-sm text-expense">{{ store.error }}</p>
    </div>
  </div>
</template>

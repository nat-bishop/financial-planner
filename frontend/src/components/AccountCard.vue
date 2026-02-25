<script setup lang="ts">
import { computed } from 'vue'
import type { Account } from '../types'
import { formatCurrency, formatRelative } from '../composables/useApi'

const props = defineProps<{
  account: Account
  compact?: boolean
}>()

const isDebt = computed(() => {
  const t = (props.account.account_type || '').toLowerCase()
  return t.includes('loan') || t.includes('credit') || t.includes('mortgage')
})

const typeLabel = computed(() => {
  const t = (props.account.account_type || '').toLowerCase()
  if (t.includes('loan')) return 'Loan'
  if (t.includes('credit')) return 'Credit'
  if (t.includes('mortgage')) return 'Mortgage'
  if (t.includes('checking')) return 'Checking'
  if (t.includes('savings')) return 'Savings'
  if (t.includes('investment')) return 'Investment'
  if (t) return props.account.account_type
  return null
})
</script>

<template>
  <div
    class="group bg-white border border-surface-900/8 rounded-2xl transition-all duration-300 hover:border-surface-900/15 hover:shadow-[0_2px_20px_rgba(0,0,0,0.04)]"
    :class="compact ? 'p-4' : 'p-6'"
  >
    <!-- Header -->
    <div class="flex items-start justify-between mb-4">
      <div class="flex-1 min-w-0">
        <p class="text-sm font-medium text-surface-300 truncate">
          {{ account.org_name || account.name }}
        </p>
        <h3 class="text-sm text-surface-500 mt-0.5 truncate" v-if="account.org_name">
          {{ account.name }}
        </h3>
      </div>
      <span
        v-if="typeLabel"
        class="shrink-0 ml-2 px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider rounded-md"
        :class="isDebt ? 'bg-expense/10 text-expense' : 'bg-accent/10 text-accent'"
      >
        {{ typeLabel }}
      </span>
    </div>

    <!-- Balance -->
    <div :class="compact ? 'mb-2' : 'mb-4'">
      <p class="font-display tracking-tight"
        :class="[
          compact ? 'text-2xl' : 'text-3xl',
          isDebt ? 'text-expense' : 'text-surface-100'
        ]"
      >
        {{ formatCurrency(account.balance_current) }}
      </p>
      <p
        v-if="account.balance_available !== null && account.balance_available !== account.balance_current && !compact"
        class="text-xs text-surface-500 mt-1 font-mono"
      >
        {{ formatCurrency(account.balance_available) }} available
      </p>
    </div>

    <!-- Footer -->
    <div v-if="!compact" class="flex items-center justify-between pt-3 border-t border-surface-900/5">
      <span class="text-[11px] text-surface-500 font-mono">
        {{ account.currency }}
      </span>
      <span class="text-[11px] text-surface-400">
        Synced {{ formatRelative(account.last_synced_at) }}
      </span>
    </div>
  </div>
</template>

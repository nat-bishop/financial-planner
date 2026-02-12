<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useApi, formatCurrency, formatDate } from '../composables/useApi'
import type { RecurringBillsResponse, RecurringBill } from '../types'

const api = useApi()
const data = ref<RecurringBillsResponse | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    data.value = await api.get<RecurringBillsResponse>('/analytics/recurring-bills')
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
})

function timeGroup(bill: RecurringBill): string {
  const now = Date.now() / 1000
  const diff = bill.predicted_next - now
  const days = diff / 86400

  if (days < 0) return 'Overdue'
  if (days <= 7) return 'This Week'
  if (days <= 14) return 'Next Week'
  if (days <= 30) return 'This Month'
  return 'Later'
}

const groupedBills = computed(() => {
  if (!data.value) return []

  const groups: { label: string; bills: RecurringBill[] }[] = []
  const order = ['Overdue', 'This Week', 'Next Week', 'This Month', 'Later']

  const grouped = new Map<string, RecurringBill[]>()
  for (const bill of data.value.bills) {
    const group = timeGroup(bill)
    if (!grouped.has(group)) grouped.set(group, [])
    grouped.get(group)!.push(bill)
  }

  for (const label of order) {
    const bills = grouped.get(label)
    if (bills && bills.length > 0) {
      groups.push({ label, bills })
    }
  }

  return groups
})

function frequencyLabel(freq: string): string {
  const labels: Record<string, string> = {
    weekly: 'Weekly',
    biweekly: 'Bi-weekly',
    monthly: 'Monthly',
    bimonthly: 'Bi-monthly',
    quarterly: 'Quarterly',
    semiannual: 'Semi-annual',
    annual: 'Annual',
  }
  return labels[freq] || freq
}
</script>

<template>
  <div class="w-full">
    <div v-if="loading" class="h-64 flex items-center justify-center">
      <div class="w-5 h-5 border-2 border-surface-300 border-t-accent rounded-full animate-spin"></div>
    </div>

    <div v-else-if="groupedBills.length === 0" class="h-64 flex items-center justify-center">
      <p class="text-sm text-surface-400">No recurring bills detected yet</p>
    </div>

    <div v-else class="space-y-5">
      <div v-for="group in groupedBills" :key="group.label">
        <h3
          class="text-[10px] font-mono uppercase tracking-wider mb-2"
          :class="group.label === 'Overdue' ? 'text-expense' : 'text-surface-400'"
        >
          {{ group.label }}
        </h3>
        <div class="space-y-1.5">
          <div
            v-for="bill in group.bills"
            :key="`${bill.description}-${bill.account_id}`"
            class="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-surface-900/[0.02] transition-colors"
          >
            <!-- Recurring icon -->
            <div class="shrink-0 w-7 h-7 rounded-full bg-expense/8 flex items-center justify-center">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                <path d="M1 6a5 5 0 019-2M11 6a5 5 0 01-9 2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" class="text-expense"/>
                <path d="M10 1v3h-3M2 11V8h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" class="text-expense"/>
              </svg>
            </div>

            <!-- Description + account -->
            <div class="flex-1 min-w-0">
              <p class="text-sm text-surface-200 truncate">{{ bill.raw_description }}</p>
              <p class="text-[10px] text-surface-400 truncate">{{ bill.account_name }}</p>
            </div>

            <!-- Frequency badge -->
            <span class="shrink-0 px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider rounded bg-surface-100 text-surface-500">
              {{ frequencyLabel(bill.frequency) }}
            </span>

            <!-- Amount + date -->
            <div class="shrink-0 text-right">
              <p class="text-sm font-mono tabular-nums text-expense">
                {{ formatCurrency(bill.median_amount) }}
              </p>
              <p class="text-[10px] font-mono text-surface-400">
                {{ formatDate(bill.predicted_next) }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

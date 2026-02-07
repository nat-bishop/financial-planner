<script setup lang="ts">
import { ref } from 'vue'
import type { Transaction, TransactionUpdate } from '../types'
import { formatCurrency, formatDate } from '../composables/useApi'

const props = defineProps<{
  transactions: Transaction[]
  compact?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  update: [id: number, data: TransactionUpdate]
}>()

const editingId = ref<number | null>(null)
const editValue = ref('')

function startEdit(tx: Transaction) {
  editingId.value = tx.id
  editValue.value = tx.category || ''
}

function saveEdit(tx: Transaction) {
  if (editValue.value !== (tx.category || '')) {
    emit('update', tx.id, { category: editValue.value || null })
  }
  editingId.value = null
}

function cancelEdit() {
  editingId.value = null
}
</script>

<template>
  <div class="w-full">
    <!-- Loading skeleton -->
    <div v-if="loading" class="space-y-3">
      <div v-for="i in 5" :key="i" class="flex items-center gap-4 py-3 px-4">
        <div class="h-4 bg-surface-900/5 rounded w-20 animate-pulse"></div>
        <div class="h-4 bg-surface-900/5 rounded flex-1 animate-pulse"></div>
        <div class="h-4 bg-surface-900/5 rounded w-24 animate-pulse"></div>
        <div class="h-4 bg-surface-900/5 rounded w-20 animate-pulse"></div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else-if="transactions.length === 0" class="py-16 text-center">
      <p class="text-surface-400 text-sm">No transactions found</p>
    </div>

    <!-- Table -->
    <div v-else class="w-full">
      <table class="w-full">
        <thead v-if="!compact">
          <tr class="text-left border-b border-surface-900/8">
            <th class="pb-3 text-[11px] font-mono uppercase tracking-wider text-surface-400 font-medium">Date</th>
            <th class="pb-3 text-[11px] font-mono uppercase tracking-wider text-surface-400 font-medium">Description</th>
            <th class="pb-3 text-[11px] font-mono uppercase tracking-wider text-surface-400 font-medium">Category</th>
            <th class="pb-3 text-[11px] font-mono uppercase tracking-wider text-surface-400 font-medium text-right">Amount</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="tx in transactions"
            :key="tx.id"
            class="group border-b border-surface-900/4 last:border-0 transition-colors hover:bg-surface-900/[0.02]"
          >
            <td class="py-3 pr-4" :class="compact ? 'w-16' : 'w-28'">
              <span class="text-xs text-surface-400 font-mono whitespace-nowrap">
                {{ formatDate(tx.posted_at) }}
              </span>
            </td>
            <td class="py-3 pr-4">
              <div class="flex items-center gap-2">
                <span
                  class="text-sm text-surface-200"
                  :class="{ 'opacity-50': tx.is_pending }"
                >
                  {{ tx.description }}
                </span>
                <span
                  v-if="tx.is_pending"
                  class="px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider rounded bg-pending/10 text-pending"
                >
                  Pending
                </span>
              </div>
            </td>
            <td v-if="!compact" class="py-3 pr-4 w-40">
              <!-- Inline edit -->
              <div v-if="editingId === tx.id" class="flex items-center gap-1">
                <input
                  v-model="editValue"
                  @keyup.enter="saveEdit(tx)"
                  @keyup.escape="cancelEdit"
                  @blur="saveEdit(tx)"
                  class="text-xs px-2 py-1 bg-surface-900/5 border border-surface-900/10 rounded-md w-full outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
                  ref="editInput"
                  autofocus
                />
              </div>
              <button
                v-else
                @click="startEdit(tx)"
                class="text-xs rounded-md px-2 py-1 transition-colors text-left w-full truncate"
                :class="tx.category
                  ? 'text-surface-400 hover:bg-surface-900/5'
                  : 'text-surface-300/50 hover:bg-surface-900/5 italic'"
              >
                {{ tx.category || 'Uncategorized' }}
              </button>
            </td>
            <td class="py-3 text-right">
              <span
                class="text-sm font-mono tabular-nums font-medium"
                :class="tx.amount >= 0 ? 'text-income' : 'text-surface-200'"
              >
                {{ formatCurrency(tx.amount) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Transaction, TransactionUpdate } from '../types'
import { formatCurrency, formatDate } from '../composables/useApi'

const props = defineProps<{
  transactions: Transaction[]
  compact?: boolean
  loading?: boolean
  selectable?: boolean
  selectedIds?: Set<number>
}>()

const emit = defineEmits<{
  update: [id: number, data: TransactionUpdate]
  toggleSelect: [id: number]
  toggleSelectAll: []
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

const allSelected = computed(() => {
  if (!props.selectable || !props.selectedIds || props.transactions.length === 0) return false
  return props.transactions.every(tx => props.selectedIds!.has(tx.id))
})

function confidenceLabel(confidence: number | null): string {
  if (confidence === null) return ''
  return `${Math.round(confidence * 100)}%`
}

function confidenceColor(confidence: number | null): string {
  if (confidence === null) return ''
  if (confidence >= 0.8) return 'text-income'
  if (confidence >= 0.5) return 'text-pending'
  return 'text-expense'
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
            <th v-if="selectable" class="pb-3 w-8 pl-1">
              <input
                type="checkbox"
                :checked="allSelected"
                @change="emit('toggleSelectAll')"
                class="w-3.5 h-3.5 rounded border-surface-300 accent-accent cursor-pointer"
              />
            </th>
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
            :class="{ 'bg-accent/[0.03]': selectable && selectedIds?.has(tx.id) }"
          >
            <td v-if="selectable" class="py-3 w-8 pl-1">
              <input
                type="checkbox"
                :checked="selectedIds?.has(tx.id)"
                @change="emit('toggleSelect', tx.id)"
                class="w-3.5 h-3.5 rounded border-surface-300 accent-accent cursor-pointer"
              />
            </td>
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
            <td v-if="!compact" class="py-3 pr-4 w-44">
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
              <div v-else class="flex items-center gap-1.5">
                <button
                  @click="startEdit(tx)"
                  class="text-xs rounded-md px-2 py-1 transition-colors text-left truncate max-w-[130px]"
                  :class="[
                    tx.category === 'Unable to Categorize'
                      ? 'text-pending/70 hover:bg-surface-900/5 italic'
                      : tx.category
                        ? 'text-surface-400 hover:bg-surface-900/5'
                        : 'text-surface-300/50 hover:bg-surface-900/5 italic'
                  ]"
                >
                  {{ tx.category || 'Uncategorized' }}
                </button>
                <span
                  v-if="tx.categorize_confidence !== null && tx.categorize_confidence !== undefined"
                  class="text-[10px] font-mono tabular-nums"
                  :class="confidenceColor(tx.categorize_confidence)"
                  :title="`AI confidence: ${confidenceLabel(tx.categorize_confidence)}`"
                >
                  {{ confidenceLabel(tx.categorize_confidence) }}
                </span>
              </div>
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

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAccountsStore } from '../stores/accounts'
import type { Transaction, TransactionUpdate } from '../types'
import { formatCurrency, formatDate } from '../composables/useApi'

const props = defineProps<{
  transactions: Transaction[]
  compact?: boolean
  loading?: boolean
  selectable?: boolean
  selectedIds?: Set<number>
  selectAllActive?: boolean
  sortBy?: string
  sortOrder?: string
}>()

const emit = defineEmits<{
  update: [id: number, data: TransactionUpdate]
  toggleSelect: [id: number]
  toggleSelectAll: []
  sort: [column: string]
}>()

const accountsStore = useAccountsStore()

const accountMap = computed(() => {
  const map = new Map<string, string>()
  accountsStore.accounts.forEach(a => map.set(a.id, a.name))
  return map
})

const expandedId = ref<number | null>(null)
const editCategory = ref('')
const editSubcategory = ref('')
const editNotes = ref('')

function toggleExpand(tx: Transaction) {
  if (expandedId.value === tx.id) {
    expandedId.value = null
  } else {
    expandedId.value = tx.id
    editCategory.value = tx.category
    editSubcategory.value = tx.subcategory || ''
    editNotes.value = tx.notes || ''
  }
}

function saveEdit(tx: Transaction) {
  const data: TransactionUpdate = {}
  if (editCategory.value !== tx.category) data.category = editCategory.value || null
  if (editSubcategory.value !== (tx.subcategory || '')) data.subcategory = editSubcategory.value || null
  if (editNotes.value !== (tx.notes || '')) data.notes = editNotes.value || null
  if (Object.keys(data).length > 0) {
    emit('update', tx.id, data)
  }
  expandedId.value = null
}

function cancelEdit() {
  expandedId.value = null
}

const allSelected = computed(() => {
  if (props.selectAllActive) return true
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

function sortArrow(column: string): string {
  if (props.sortBy !== column) return ''
  return props.sortOrder === 'asc' ? ' \u2191' : ' \u2193'
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
            <th
              class="pb-3 text-[11px] font-mono uppercase tracking-wider text-surface-400 font-medium cursor-pointer hover:text-surface-200 select-none"
              @click="emit('sort', 'date')"
            >Date{{ sortArrow('date') }}</th>
            <th
              class="pb-3 text-[11px] font-mono uppercase tracking-wider text-surface-400 font-medium cursor-pointer hover:text-surface-200 select-none"
              @click="emit('sort', 'description')"
            >Description{{ sortArrow('description') }}</th>
            <th
              class="pb-3 text-[11px] font-mono uppercase tracking-wider text-surface-400 font-medium cursor-pointer hover:text-surface-200 select-none"
              @click="emit('sort', 'account')"
            >Account{{ sortArrow('account') }}</th>
            <th
              class="pb-3 text-[11px] font-mono uppercase tracking-wider text-surface-400 font-medium cursor-pointer hover:text-surface-200 select-none"
              @click="emit('sort', 'category')"
            >Category{{ sortArrow('category') }}</th>
            <th class="pb-3 text-[11px] font-mono uppercase tracking-wider text-surface-400 font-medium">Subcategory</th>
            <th
              class="pb-3 text-[11px] font-mono uppercase tracking-wider text-surface-400 font-medium text-right cursor-pointer hover:text-surface-200 select-none"
              @click="emit('sort', 'amount')"
            >Amount{{ sortArrow('amount') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="tx in transactions" :key="tx.id">
            <tr
              class="group border-b border-surface-900/4 last:border-0 transition-colors cursor-pointer"
              :class="{
                'bg-accent/[0.03]': selectable && (selectAllActive || selectedIds?.has(tx.id)),
                'hover:bg-surface-900/[0.02]': !selectable || !selectAllActive,
              }"
              @click="toggleExpand(tx)"
            >
              <td v-if="selectable" class="py-3 w-8 pl-1" @click.stop>
                <input
                  type="checkbox"
                  :checked="selectAllActive || selectedIds?.has(tx.id)"
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
              <td v-if="!compact" class="py-3 pr-4 w-32">
                <span class="text-xs text-surface-400 truncate block max-w-[120px]">
                  {{ accountMap.get(tx.account_id) || '--' }}
                </span>
              </td>
              <td v-if="!compact" class="py-3 pr-4 w-40">
                <div class="flex items-center gap-1.5">
                  <span
                    class="text-xs rounded-md px-2 py-1 text-left truncate max-w-[130px]"
                    :class="[
                      tx.category === 'Unable to Categorize'
                        ? 'text-pending/70 italic'
                        : tx.category === 'Uncategorized'
                          ? 'text-surface-300/50 italic'
                          : 'text-surface-400'
                    ]"
                  >
                    {{ tx.category }}
                  </span>
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
              <td v-if="!compact" class="py-3 pr-4 w-28">
                <span class="text-xs text-surface-400 truncate block max-w-[100px]">
                  {{ tx.subcategory || '--' }}
                </span>
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
            <!-- Expanded detail row -->
            <tr v-if="!compact && expandedId === tx.id" class="border-b border-surface-900/4">
              <td :colspan="selectable ? 8 : 7" class="px-4 py-4 bg-surface-900/[0.02]">
                <div class="grid grid-cols-2 gap-4 max-w-xl" @click.stop>
                  <div>
                    <label class="text-[10px] font-mono uppercase tracking-wider text-surface-400 block mb-1">Category</label>
                    <input
                      v-model="editCategory"
                      class="text-xs px-2 py-1.5 bg-white border border-surface-900/10 rounded-md w-full outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
                    />
                  </div>
                  <div>
                    <label class="text-[10px] font-mono uppercase tracking-wider text-surface-400 block mb-1">Subcategory</label>
                    <input
                      v-model="editSubcategory"
                      class="text-xs px-2 py-1.5 bg-white border border-surface-900/10 rounded-md w-full outline-none focus:border-accent focus:ring-1 focus:ring-accent/30"
                    />
                  </div>
                  <div class="col-span-2">
                    <label class="text-[10px] font-mono uppercase tracking-wider text-surface-400 block mb-1">Notes</label>
                    <textarea
                      v-model="editNotes"
                      rows="2"
                      class="text-xs px-2 py-1.5 bg-white border border-surface-900/10 rounded-md w-full outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 resize-none"
                    ></textarea>
                  </div>
                  <div class="col-span-2 flex items-center gap-3">
                    <button
                      @click="saveEdit(tx)"
                      class="px-3 py-1.5 text-xs font-medium bg-accent/10 text-accent hover:bg-accent/20 rounded-lg transition-colors"
                    >Save</button>
                    <button
                      @click="cancelEdit"
                      class="px-3 py-1.5 text-xs font-medium text-surface-400 hover:text-surface-200 transition-colors"
                    >Cancel</button>
                    <span v-if="tx.categorize_confidence !== null" class="ml-auto text-[10px] font-mono text-surface-300">
                      AI confidence: <span :class="confidenceColor(tx.categorize_confidence)">{{ confidenceLabel(tx.categorize_confidence) }}</span>
                    </span>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

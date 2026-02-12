<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch, computed, reactive } from 'vue'
import { useTransactionsStore } from '../stores/transactions'
import { useAccountsStore } from '../stores/accounts'
import { useCategoriesStore } from '../stores/categories'
import { useLLMStore } from '../stores/llm'
import TransactionTable from '../components/TransactionTable.vue'
import { formatCurrency } from '../composables/useApi'

const transactionsStore = useTransactionsStore()
const accountsStore = useAccountsStore()
const categoriesStore = useCategoriesStore()
const llmStore = useLLMStore()

const searchInput = ref('')
const selectedAccount = ref('')
const selectedCategory = ref('')
const dateRange = ref('30d')
const selectedIds = reactive(new Set<number>())
const selectAllActive = ref(false)
let searchTimeout: ReturnType<typeof setTimeout>

// Sorting
const sortBy = ref<'date' | 'description' | 'category' | 'amount' | 'account'>('date')
const sortOrder = ref<'asc' | 'desc'>('desc')

// Categorization result toast
const catToast = ref<{ message: string; type: 'success' | 'error' } | null>(null)
let toastTimeout: ReturnType<typeof setTimeout>

function showToast(message: string, type: 'success' | 'error' = 'success') {
  catToast.value = { message, type }
  clearTimeout(toastTimeout)
  toastTimeout = setTimeout(() => { catToast.value = null }, 5000)
}

onMounted(async () => {
  await Promise.all([
    accountsStore.fetch(),
    categoriesStore.fetch(),
    llmStore.fetchStatus(),
  ])
  await transactionsStore.fetch()
})

onUnmounted(() => {
  clearTimeout(searchTimeout)
  clearTimeout(toastTimeout)
})

// Debounced search
watch(searchInput, (val) => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    transactionsStore.setFilter('search', val || undefined)
    transactionsStore.setFilter('offset', 0)
    clearSelection()
    transactionsStore.fetch()
  }, 300)
})

watch(selectedAccount, (val) => {
  transactionsStore.setFilter('account_id', val || undefined)
  transactionsStore.setFilter('offset', 0)
  clearSelection()
  transactionsStore.fetch()
})

watch(selectedCategory, (val) => {
  transactionsStore.setFilter('category', val || undefined)
  transactionsStore.setFilter('offset', 0)
  clearSelection()
  transactionsStore.fetch()
})

// Date range presets
watch(dateRange, (val) => {
  const now = Math.floor(Date.now() / 1000)
  const rangeMap: Record<string, number | undefined> = {
    '7d': now - 7 * 86400,
    '30d': now - 30 * 86400,
    '90d': now - 90 * 86400,
    '1y': now - 365 * 86400,
    'all': undefined,
  }
  transactionsStore.setFilter('start_date', rangeMap[val])
  transactionsStore.setFilter('offset', 0)
  clearSelection()
  transactionsStore.fetch()
})

function handleUpdate(id: number, data: any) {
  transactionsStore.updateTransaction(id, data)
}

function clearFilters() {
  searchInput.value = ''
  selectedAccount.value = ''
  selectedCategory.value = ''
  dateRange.value = '30d'
  clearSelection()
  transactionsStore.clearFilters()
  transactionsStore.fetch()
}

const hasFilters = computed(() => {
  return searchInput.value || selectedAccount.value || selectedCategory.value || dateRange.value !== '30d'
})

// Selection
function clearSelection() {
  selectedIds.clear()
  selectAllActive.value = false
}

function toggleSelect(id: number) {
  if (selectedIds.has(id)) {
    selectedIds.delete(id)
  } else {
    selectedIds.add(id)
  }
  selectAllActive.value = false
}

function toggleSelectAll() {
  if (selectAllActive.value) {
    clearSelection()
  } else {
    selectAllActive.value = true
    transactionsStore.transactions.forEach(tx => selectedIds.add(tx.id))
  }
}

const selectionCount = computed(() => {
  return selectAllActive.value ? transactionsStore.totalCount : selectedIds.size
})

// Summary
const summaryIncome = computed(() => {
  if (selectAllActive.value) return transactionsStore.totalIncome
  if (selectedIds.size === 0) return transactionsStore.totalIncome
  let sum = 0
  for (const tx of transactionsStore.transactions) {
    if (selectedIds.has(tx.id) && tx.amount > 0) sum += tx.amount
  }
  return sum
})

const summaryExpenses = computed(() => {
  if (selectAllActive.value) return transactionsStore.totalExpenses
  if (selectedIds.size === 0) return transactionsStore.totalExpenses
  let sum = 0
  for (const tx of transactionsStore.transactions) {
    if (selectedIds.has(tx.id) && tx.amount < 0) sum += Math.abs(tx.amount)
  }
  return sum
})

const summaryNet = computed(() => summaryIncome.value - summaryExpenses.value)

// Categorize actions
async function categorizeUncategorized() {
  const result = await llmStore.categorizeUncategorized()
  if (result) {
    showToast(`Categorized ${result.categorized} of ${result.total_processed} transactions`)
    await transactionsStore.fetch()
  } else if (llmStore.error) {
    showToast(llmStore.error, 'error')
  }
}

async function categorizeSelected() {
  let ids: number[]
  if (selectAllActive.value) {
    try {
      ids = await transactionsStore.fetchAllIds()
    } catch {
      showToast('Failed to fetch all transaction IDs', 'error')
      return
    }
  } else {
    ids = Array.from(selectedIds)
  }
  if (ids.length === 0) return

  const result = await llmStore.categorizeSelected(ids)
  if (result) {
    showToast(`Categorized ${result.categorized} of ${result.total_processed} transactions`)
    clearSelection()
    await transactionsStore.fetch()
  } else if (llmStore.error) {
    showToast(llmStore.error, 'error')
  }
}

// Sorting
function handleSort(column: 'date' | 'description' | 'category' | 'amount' | 'account') {
  if (sortBy.value === column) {
    sortOrder.value = sortOrder.value === 'desc' ? 'asc' : 'desc'
  } else {
    sortBy.value = column
    sortOrder.value = 'desc'
  }
  transactionsStore.setFilter('sort_by', sortBy.value)
  transactionsStore.setFilter('sort_order', sortOrder.value)
  transactionsStore.setFilter('offset', 0)
  clearSelection()
  transactionsStore.fetch()
}

// Pagination
const totalPages = computed(() => {
  const limit = transactionsStore.filters.limit || 100
  return Math.max(1, Math.ceil(transactionsStore.totalCount / limit))
})

function nextPage() {
  const offset = (transactionsStore.filters.offset || 0) + (transactionsStore.filters.limit || 100)
  transactionsStore.setFilter('offset', offset)
  clearSelection()
  transactionsStore.fetch()
}

function prevPage() {
  const offset = Math.max(0, (transactionsStore.filters.offset || 0) - (transactionsStore.filters.limit || 100))
  transactionsStore.setFilter('offset', offset)
  clearSelection()
  transactionsStore.fetch()
}

const currentPage = computed(() => {
  const limit = transactionsStore.filters.limit || 100
  return Math.floor((transactionsStore.filters.offset || 0) / limit) + 1
})

const isConfigured = computed(() => llmStore.status?.configured ?? false)
</script>

<template>
  <div class="p-8 max-w-6xl animate-fade-up">
    <!-- Header -->
    <div class="flex items-start justify-between mb-8">
      <div>
        <h1 class="font-display text-4xl text-surface-100 tracking-tight mb-1">Transactions</h1>
        <p class="text-sm text-surface-400">
          {{ transactionsStore.totalCount }} results
          <template v-if="currentPage > 1 || totalPages > 1"> &middot; Page {{ currentPage }} of {{ totalPages }}</template>
          <template v-if="selectionCount > 0"> &middot; {{ selectionCount }} selected</template>
        </p>
      </div>

      <!-- Categorize buttons -->
      <div v-if="isConfigured" class="flex items-center gap-2">
        <button
          v-if="selectionCount > 0"
          @click="categorizeSelected"
          :disabled="llmStore.categorizing"
          class="px-3.5 py-2 text-xs font-medium rounded-lg transition-all"
          :class="llmStore.categorizing
            ? 'bg-surface-200 text-surface-400 cursor-wait'
            : 'bg-accent/10 text-accent hover:bg-accent/20'"
        >
          <span v-if="llmStore.categorizing" class="flex items-center gap-1.5">
            <svg class="animate-spin w-3 h-3" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="2" opacity="0.3"/>
              <path d="M14 8a6 6 0 00-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            Categorizing...
          </span>
          <span v-else>Categorize Selected ({{ selectionCount }})</span>
        </button>
        <button
          @click="categorizeUncategorized"
          :disabled="llmStore.categorizing"
          class="px-3.5 py-2 text-xs font-medium rounded-lg transition-all"
          :class="llmStore.categorizing
            ? 'bg-surface-200 text-surface-400 cursor-wait'
            : 'bg-surface-900/8 text-surface-200 hover:bg-surface-900/12'"
        >
          <span v-if="llmStore.categorizing && selectionCount === 0" class="flex items-center gap-1.5">
            <svg class="animate-spin w-3 h-3" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="2" opacity="0.3"/>
              <path d="M14 8a6 6 0 00-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            Categorizing...
          </span>
          <span v-else>Categorize Uncategorized</span>
        </button>
      </div>
    </div>

    <!-- Categorize toast -->
    <Transition
      enter-active-class="transition-all duration-300"
      enter-from-class="opacity-0 -translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition-all duration-200"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="catToast"
        class="mb-4 px-4 py-2.5 rounded-lg text-xs font-medium"
        :class="catToast.type === 'error'
          ? 'bg-expense/10 text-expense'
          : 'bg-income/10 text-income'"
      >
        {{ catToast.message }}
      </div>
    </Transition>

    <!-- Filters -->
    <div class="flex flex-nowrap items-center gap-3 mb-6 overflow-x-auto">
      <!-- Search -->
      <div class="relative flex-1 min-w-0 max-w-sm">
        <svg class="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" width="16" height="16" viewBox="0 0 16 16" fill="none">
          <circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5"/>
          <path d="M11 11l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        <input
          v-model="searchInput"
          type="text"
          placeholder="Search transactions..."
          class="w-full pl-9 pr-4 py-2.5 text-sm bg-white border border-surface-900/8 rounded-xl outline-none focus:border-surface-900/20 focus:ring-2 focus:ring-surface-900/5 transition-all placeholder:text-surface-400"
        />
      </div>

      <!-- Date range -->
      <select
        v-model="dateRange"
        class="px-3 py-2.5 text-sm bg-white border border-surface-900/8 rounded-xl outline-none focus:border-surface-900/20 appearance-none pr-8 cursor-pointer shrink-0"
        style="background-image: url('data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 12 12%22><path d=%22M3 5l3 3 3-3%22 fill=%22none%22 stroke=%22%23999%22 stroke-width=%221.5%22 stroke-linecap=%22round%22/></svg>'); background-repeat: no-repeat; background-position: right 8px center;"
      >
        <option value="7d">Last 7 days</option>
        <option value="30d">Last 30 days</option>
        <option value="90d">Last 90 days</option>
        <option value="1y">Last year</option>
        <option value="all">All time</option>
      </select>

      <!-- Account filter -->
      <select
        v-model="selectedAccount"
        class="px-3 py-2.5 text-sm bg-white border border-surface-900/8 rounded-xl outline-none focus:border-surface-900/20 appearance-none pr-8 cursor-pointer shrink-0"
        style="background-image: url('data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 12 12%22><path d=%22M3 5l3 3 3-3%22 fill=%22none%22 stroke=%22%23999%22 stroke-width=%221.5%22 stroke-linecap=%22round%22/></svg>'); background-repeat: no-repeat; background-position: right 8px center;"
      >
        <option value="">All accounts</option>
        <option v-for="acc in accountsStore.accounts" :key="acc.id" :value="acc.id">
          {{ acc.name }}
        </option>
      </select>

      <!-- Category filter -->
      <select
        v-model="selectedCategory"
        class="px-3 py-2.5 text-sm bg-white border border-surface-900/8 rounded-xl outline-none focus:border-surface-900/20 appearance-none pr-8 cursor-pointer shrink-0"
        style="background-image: url('data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 12 12%22><path d=%22M3 5l3 3 3-3%22 fill=%22none%22 stroke=%22%23999%22 stroke-width=%221.5%22 stroke-linecap=%22round%22/></svg>'); background-repeat: no-repeat; background-position: right 8px center;"
      >
        <option value="">All categories</option>
        <option value="Uncategorized">Uncategorized</option>
        <option value="Unable to Categorize">Unable to Categorize</option>
        <option v-for="cat in categoriesStore.categories" :key="cat.id" :value="cat.name">
          {{ cat.name }}
        </option>
      </select>

      <!-- Clear filters -->
      <button
        v-if="hasFilters"
        @click="clearFilters"
        class="px-3 py-2.5 text-xs font-medium text-surface-400 hover:text-surface-200 transition-colors whitespace-nowrap shrink-0"
      >
        Clear filters
      </button>
    </div>

    <!-- Summary -->
    <div class="flex items-center gap-6 mb-6 px-1">
      <div class="flex items-center gap-1.5">
        <span class="text-[11px] font-mono uppercase tracking-wider text-surface-400">Income</span>
        <span class="text-sm font-mono tabular-nums text-income font-medium">{{ formatCurrency(summaryIncome) }}</span>
      </div>
      <div class="flex items-center gap-1.5">
        <span class="text-[11px] font-mono uppercase tracking-wider text-surface-400">Expenses</span>
        <span class="text-sm font-mono tabular-nums text-surface-200 font-medium">{{ formatCurrency(summaryExpenses) }}</span>
      </div>
      <div class="flex items-center gap-1.5">
        <span class="text-[11px] font-mono uppercase tracking-wider text-surface-400">Net</span>
        <span
          class="text-sm font-mono tabular-nums font-medium"
          :class="summaryNet >= 0 ? 'text-income' : 'text-expense'"
        >{{ formatCurrency(summaryNet) }}</span>
      </div>
    </div>

    <!-- Table -->
    <div class="bg-white border border-surface-900/8 rounded-2xl p-6">
      <TransactionTable
        :transactions="transactionsStore.transactions"
        :loading="transactionsStore.loading"
        :selectable="true"
        :selectedIds="selectedIds"
        :selectAllActive="selectAllActive"
        :sortBy="sortBy"
        :sortOrder="sortOrder"
        @update="handleUpdate"
        @toggle-select="toggleSelect"
        @toggle-select-all="toggleSelectAll"
        @sort="handleSort"
      />
    </div>

    <!-- Pagination -->
    <div class="flex items-center justify-between mt-4">
      <button
        @click="prevPage"
        :disabled="currentPage <= 1"
        class="px-4 py-2 text-sm rounded-lg transition-colors"
        :class="currentPage <= 1
          ? 'text-surface-300 cursor-not-allowed'
          : 'text-surface-400 hover:text-surface-200 hover:bg-surface-900/5'"
      >
        &larr; Previous
      </button>
      <span class="text-xs font-mono text-surface-400">Page {{ currentPage }} of {{ totalPages }}</span>
      <button
        @click="nextPage"
        :disabled="currentPage >= totalPages"
        class="px-4 py-2 text-sm rounded-lg transition-colors"
        :class="currentPage >= totalPages
          ? 'text-surface-300 cursor-not-allowed'
          : 'text-surface-400 hover:text-surface-200 hover:bg-surface-900/5'"
      >
        Next &rarr;
      </button>
    </div>
  </div>
</template>

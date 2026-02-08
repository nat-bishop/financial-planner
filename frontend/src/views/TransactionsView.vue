<script setup lang="ts">
import { onMounted, ref, watch, computed, reactive } from 'vue'
import { useTransactionsStore } from '../stores/transactions'
import { useAccountsStore } from '../stores/accounts'
import { useCategoriesStore } from '../stores/categories'
import { useLLMStore } from '../stores/llm'
import TransactionTable from '../components/TransactionTable.vue'

const transactionsStore = useTransactionsStore()
const accountsStore = useAccountsStore()
const categoriesStore = useCategoriesStore()
const llmStore = useLLMStore()

const searchInput = ref('')
const selectedAccount = ref('')
const selectedCategory = ref('')
const selectedIds = reactive(new Set<number>())
let searchTimeout: ReturnType<typeof setTimeout>

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

// Debounced search
watch(searchInput, (val) => {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    transactionsStore.setFilter('search', val || undefined)
    transactionsStore.setFilter('offset', 0)
    transactionsStore.fetch()
  }, 300)
})

watch(selectedAccount, (val) => {
  transactionsStore.setFilter('account_id', val || undefined)
  transactionsStore.setFilter('offset', 0)
  transactionsStore.fetch()
})

watch(selectedCategory, (val) => {
  // Special handling for "uncategorized" filter
  if (val === '__uncategorized__') {
    transactionsStore.setFilter('category', undefined)
    transactionsStore.setFilter('uncategorized', true)
  } else {
    transactionsStore.setFilter('uncategorized', undefined)
    transactionsStore.setFilter('category', val || undefined)
  }
  transactionsStore.setFilter('offset', 0)
  transactionsStore.fetch()
})

// Category list for dropdown: DB categories + special entries
const categoryOptions = computed(() => {
  return categoriesStore.categories.map(c => c.name)
})

function handleUpdate(id: number, data: any) {
  transactionsStore.updateTransaction(id, data)
}

function clearFilters() {
  searchInput.value = ''
  selectedAccount.value = ''
  selectedCategory.value = ''
  selectedIds.clear()
  transactionsStore.clearFilters()
  transactionsStore.fetch()
}

const hasFilters = computed(() => {
  return searchInput.value || selectedAccount.value || selectedCategory.value
})

// Selection
function toggleSelect(id: number) {
  if (selectedIds.has(id)) {
    selectedIds.delete(id)
  } else {
    selectedIds.add(id)
  }
}

function toggleSelectAll() {
  const allSelected = transactionsStore.transactions.every(tx => selectedIds.has(tx.id))
  if (allSelected) {
    transactionsStore.transactions.forEach(tx => selectedIds.delete(tx.id))
  } else {
    transactionsStore.transactions.forEach(tx => selectedIds.add(tx.id))
  }
}

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
  const ids = Array.from(selectedIds)
  if (ids.length === 0) return

  const result = await llmStore.categorizeSelected(ids)
  if (result) {
    showToast(`Categorized ${result.categorized} of ${result.total_processed} transactions`)
    selectedIds.clear()
    await transactionsStore.fetch()
  } else if (llmStore.error) {
    showToast(llmStore.error, 'error')
  }
}

// Pagination
function nextPage() {
  const offset = (transactionsStore.filters.offset || 0) + (transactionsStore.filters.limit || 100)
  transactionsStore.setFilter('offset', offset)
  transactionsStore.fetch()
}

function prevPage() {
  const offset = Math.max(0, (transactionsStore.filters.offset || 0) - (transactionsStore.filters.limit || 100))
  transactionsStore.setFilter('offset', offset)
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
          {{ transactionsStore.transactions.length }} results
          <template v-if="currentPage > 1"> &middot; Page {{ currentPage }}</template>
          <template v-if="selectedIds.size > 0"> &middot; {{ selectedIds.size }} selected</template>
        </p>
      </div>

      <!-- Categorize buttons -->
      <div v-if="isConfigured" class="flex items-center gap-2">
        <button
          v-if="selectedIds.size > 0"
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
          <span v-else>Categorize Selected ({{ selectedIds.size }})</span>
        </button>
        <button
          @click="categorizeUncategorized"
          :disabled="llmStore.categorizing"
          class="px-3.5 py-2 text-xs font-medium rounded-lg transition-all"
          :class="llmStore.categorizing
            ? 'bg-surface-200 text-surface-400 cursor-wait'
            : 'bg-surface-100 text-surface-400 hover:text-surface-200 hover:bg-surface-200'"
        >
          <span v-if="llmStore.categorizing && selectedIds.size === 0" class="flex items-center gap-1.5">
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
    <div class="flex flex-wrap items-center gap-3 mb-6">
      <!-- Search -->
      <div class="relative flex-1 min-w-[200px] max-w-sm">
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

      <!-- Account filter -->
      <select
        v-model="selectedAccount"
        class="px-3 py-2.5 text-sm bg-white border border-surface-900/8 rounded-xl outline-none focus:border-surface-900/20 appearance-none pr-8 cursor-pointer"
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
        class="px-3 py-2.5 text-sm bg-white border border-surface-900/8 rounded-xl outline-none focus:border-surface-900/20 appearance-none pr-8 cursor-pointer"
        style="background-image: url('data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 12 12%22><path d=%22M3 5l3 3 3-3%22 fill=%22none%22 stroke=%22%23999%22 stroke-width=%221.5%22 stroke-linecap=%22round%22/></svg>'); background-repeat: no-repeat; background-position: right 8px center;"
      >
        <option value="">All categories</option>
        <option value="__uncategorized__">Uncategorized</option>
        <option value="Unable to Categorize">Unable to Categorize</option>
        <option v-for="cat in categoryOptions" :key="cat" :value="cat">
          {{ cat }}
        </option>
      </select>

      <!-- Clear filters -->
      <button
        v-if="hasFilters"
        @click="clearFilters"
        class="px-3 py-2.5 text-xs font-medium text-surface-400 hover:text-surface-200 transition-colors"
      >
        Clear filters
      </button>
    </div>

    <!-- Table -->
    <div class="bg-white border border-surface-900/8 rounded-2xl p-6">
      <TransactionTable
        :transactions="transactionsStore.transactions"
        :loading="transactionsStore.loading"
        :selectable="true"
        :selectedIds="selectedIds"
        @update="handleUpdate"
        @toggle-select="toggleSelect"
        @toggle-select-all="toggleSelectAll"
      />
    </div>

    <!-- Pagination -->
    <div class="flex items-center justify-between mt-4">
      <button
        @click="prevPage"
        :disabled="(transactionsStore.filters.offset || 0) === 0"
        class="px-4 py-2 text-sm rounded-lg transition-colors"
        :class="(transactionsStore.filters.offset || 0) === 0
          ? 'text-surface-300 cursor-not-allowed'
          : 'text-surface-400 hover:text-surface-200 hover:bg-surface-900/5'"
      >
        &larr; Previous
      </button>
      <span class="text-xs font-mono text-surface-400">Page {{ currentPage }}</span>
      <button
        @click="nextPage"
        :disabled="transactionsStore.transactions.length < (transactionsStore.filters.limit || 100)"
        class="px-4 py-2 text-sm rounded-lg transition-colors"
        :class="transactionsStore.transactions.length < (transactionsStore.filters.limit || 100)
          ? 'text-surface-300 cursor-not-allowed'
          : 'text-surface-400 hover:text-surface-200 hover:bg-surface-900/5'"
      >
        Next &rarr;
      </button>
    </div>
  </div>
</template>

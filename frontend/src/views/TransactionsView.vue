<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { useTransactionsStore } from '../stores/transactions'
import { useAccountsStore } from '../stores/accounts'
import TransactionTable from '../components/TransactionTable.vue'

const transactionsStore = useTransactionsStore()
const accountsStore = useAccountsStore()

const searchInput = ref('')
const selectedAccount = ref('')
const selectedCategory = ref('')
let searchTimeout: ReturnType<typeof setTimeout>

onMounted(async () => {
  await accountsStore.fetch()
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
  transactionsStore.setFilter('category', val || undefined)
  transactionsStore.setFilter('offset', 0)
  transactionsStore.fetch()
})

// Unique categories from current transactions
const categories = computed(() => {
  const cats = new Set<string>()
  transactionsStore.transactions.forEach(tx => {
    if (tx.category) cats.add(tx.category)
  })
  return Array.from(cats).sort()
})

function handleUpdate(id: number, data: any) {
  transactionsStore.updateTransaction(id, data)
}

function clearFilters() {
  searchInput.value = ''
  selectedAccount.value = ''
  selectedCategory.value = ''
  transactionsStore.clearFilters()
  transactionsStore.fetch()
}

const hasFilters = computed(() => {
  return searchInput.value || selectedAccount.value || selectedCategory.value
})

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
        </p>
      </div>
    </div>

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
        <option v-for="cat in categories" :key="cat" :value="cat">
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
        @update="handleUpdate"
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

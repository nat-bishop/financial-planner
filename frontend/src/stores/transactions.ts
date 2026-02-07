import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { useApi } from '../composables/useApi'
import type { Transaction, TransactionFilters, TransactionUpdate } from '../types'

export const useTransactionsStore = defineStore('transactions', () => {
  const transactions = ref<Transaction[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const filters = reactive<TransactionFilters>({
    limit: 100,
    offset: 0,
  })

  async function fetch(overrides?: Partial<TransactionFilters>) {
    const api = useApi()
    loading.value = true
    error.value = null

    const params = { ...filters, ...overrides }

    try {
      transactions.value = await api.get<Transaction[]>('/transactions/', params)
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function updateTransaction(id: number, data: TransactionUpdate): Promise<Transaction | null> {
    const api = useApi()
    try {
      const updated = await api.patch<Transaction>(`/transactions/${id}`, data)
      const idx = transactions.value.findIndex(t => t.id === id)
      if (idx !== -1) {
        transactions.value[idx] = updated
      }
      return updated
    } catch (e: any) {
      error.value = e.message
      return null
    }
  }

  function setFilter(key: keyof TransactionFilters, value: any) {
    ;(filters as any)[key] = value
  }

  function clearFilters() {
    filters.account_id = undefined
    filters.category = undefined
    filters.search = undefined
    filters.start_date = undefined
    filters.end_date = undefined
    filters.offset = 0
  }

  return { transactions, loading, error, filters, fetch, updateTransaction, setFilter, clearFilters }
})

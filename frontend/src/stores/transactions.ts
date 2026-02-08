import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { useApi } from '../composables/useApi'
import type { Transaction, TransactionFilters, TransactionUpdate, TransactionListResponse, TransactionIdsResponse } from '../types'

function thirtyDaysAgo(): number {
  return Math.floor(Date.now() / 1000) - 30 * 86400
}

export const useTransactionsStore = defineStore('transactions', () => {
  const transactions = ref<Transaction[]>([])
  const totalCount = ref(0)
  const totalIncome = ref(0)
  const totalExpenses = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const filters = reactive<TransactionFilters>({
    limit: 100,
    offset: 0,
    sort_by: 'date',
    sort_order: 'desc',
    start_date: thirtyDaysAgo(),
  })

  async function fetch(overrides?: Partial<TransactionFilters>) {
    const api = useApi()
    loading.value = true
    error.value = null

    const params = { ...filters, ...overrides }

    try {
      const response = await api.get<TransactionListResponse>('/transactions/', params)
      transactions.value = response.transactions
      totalCount.value = response.total_count
      totalIncome.value = response.total_income
      totalExpenses.value = response.total_expenses
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function fetchRecent(limit: number) {
    const api = useApi()
    loading.value = true
    error.value = null

    try {
      const response = await api.get<TransactionListResponse>('/transactions/', {
        limit,
        offset: 0,
        sort_by: 'date',
        sort_order: 'desc',
        start_date: thirtyDaysAgo(),
      })
      transactions.value = response.transactions
      totalCount.value = response.total_count
      totalIncome.value = response.total_income
      totalExpenses.value = response.total_expenses
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function fetchAllIds(): Promise<number[]> {
    const api = useApi()
    const params: Record<string, any> = {}
    if (filters.account_id) params.account_id = filters.account_id
    if (filters.category) params.category = filters.category
    if (filters.search) params.search = filters.search
    if (filters.start_date !== undefined) params.start_date = filters.start_date
    if (filters.end_date !== undefined) params.end_date = filters.end_date

    const response = await api.get<TransactionIdsResponse>('/transactions/ids', params)
    return response.ids
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
    filters.start_date = thirtyDaysAgo()
    filters.end_date = undefined
    filters.sort_by = 'date'
    filters.sort_order = 'desc'
    filters.offset = 0
  }

  return {
    transactions, totalCount, totalIncome, totalExpenses,
    loading, error, filters,
    fetch, fetchRecent, fetchAllIds, updateTransaction, setFilter, clearFilters,
  }
})

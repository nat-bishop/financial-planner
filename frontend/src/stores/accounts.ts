import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '../composables/useApi'
import type { Account } from '../types'

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref<Account[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetch() {
    const api = useApi()
    loading.value = true
    error.value = null
    try {
      accounts.value = await api.get<Account[]>('/accounts/', { limit: 100 })
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  const totalBalance = () => {
    return accounts.value.reduce((sum, acc) => sum + (acc.balance_current ?? 0), 0)
  }

  return { accounts, loading, error, fetch, totalBalance }
})

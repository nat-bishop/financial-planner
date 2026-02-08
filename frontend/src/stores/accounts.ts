import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '../composables/useApi'
import type { Account } from '../types'

export const useAccountsStore = defineStore('accounts', () => {
  const accounts = ref<Account[]>([])
  const allAccounts = ref<Account[]>([])
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

  async function fetchAll() {
    const api = useApi()
    loading.value = true
    error.value = null
    try {
      allAccounts.value = await api.get<Account[]>('/accounts/', {
        limit: 100,
        include_disabled: true,
      })
      accounts.value = allAccounts.value.filter(a => !a.is_disabled)
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function toggleDisabled(accountId: string, isDisabled: boolean) {
    const api = useApi()
    try {
      const updated = await api.patch<Account>(`/accounts/${accountId}`, {
        is_disabled: isDisabled,
      })
      const idx = allAccounts.value.findIndex(a => a.id === accountId)
      if (idx !== -1) allAccounts.value[idx] = updated
      accounts.value = allAccounts.value.filter(a => !a.is_disabled)
      return updated
    } catch (e: any) {
      error.value = e.message
      return null
    }
  }

  const totalBalance = () => {
    return accounts.value.reduce((sum, acc) => sum + (acc.balance_current ?? 0), 0)
  }

  return { accounts, allAccounts, loading, error, fetch, fetchAll, toggleDisabled, totalBalance }
})

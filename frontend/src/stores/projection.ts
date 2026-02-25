import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '../composables/useApi'
import type { NetWorthHistoryResponse } from '../types'

export const useProjectionStore = defineStore('projection', () => {
  const data = ref<NetWorthHistoryResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetch() {
    const api = useApi()
    loading.value = true
    error.value = null
    try {
      data.value = await api.get<NetWorthHistoryResponse>('/analytics/net-worth-history')
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, fetch }
})

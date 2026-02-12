import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '../composables/useApi'
import type { IncomeProjectionResponse } from '../types'

export const useProjectionStore = defineStore('projection', () => {
  const projection = ref<IncomeProjectionResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetch(years?: number) {
    const api = useApi()
    loading.value = true
    error.value = null
    try {
      const params: Record<string, any> = {}
      if (years) params.time_horizon_years = years
      projection.value = await api.get<IncomeProjectionResponse>('/analytics/income-projection', params)
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function saveIncomeSources(sources: { name: string; monthly_amount: number }[]) {
    const api = useApi()
    try {
      await api.put('/settings/projection_income_sources', { value: sources })
      await fetch()
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function saveContribution(amount: number) {
    const api = useApi()
    try {
      await api.put('/settings/projection_monthly_contribution', { value: amount })
      await fetch()
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function saveReturnRates(rates: { low: number; average: number; high: number }) {
    const api = useApi()
    try {
      await api.put('/settings/projection_return_rates', { value: rates })
      await fetch()
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function clearConfig() {
    const api = useApi()
    try {
      await api.del('/settings/projection_income_sources').catch(() => {})
      await api.del('/settings/projection_monthly_contribution').catch(() => {})
      await api.del('/settings/projection_return_rates').catch(() => {})
      await fetch()
    } catch (e: any) {
      error.value = e.message
    }
  }

  return { projection, loading, error, fetch, saveIncomeSources, saveContribution, saveReturnRates, clearConfig }
})

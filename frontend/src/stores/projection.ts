import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '../composables/useApi'
import type { IncomeProjectionResponse } from '../types'

const SETTING_KEYS = [
  'projection_income_sources',
  'projection_monthly_contribution',
  'projection_return_rates',
] as const

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

  async function saveSetting(key: string, value: unknown) {
    const api = useApi()
    try {
      await api.put(`/settings/${key}`, { value })
      await fetch()
    } catch (e: any) {
      error.value = e.message
    }
  }

  const saveIncomeSources = (sources: { name: string; monthly_amount: number }[]) =>
    saveSetting('projection_income_sources', sources)

  const saveContribution = (amount: number) =>
    saveSetting('projection_monthly_contribution', amount)

  const saveReturnRates = (rates: { low: number; average: number; high: number }) =>
    saveSetting('projection_return_rates', rates)

  async function clearConfig() {
    const api = useApi()
    try {
      await Promise.all(SETTING_KEYS.map(k => api.del(`/settings/${k}`).catch(() => {})))
      await fetch()
    } catch (e: any) {
      error.value = e.message
    }
  }

  return { projection, loading, error, fetch, saveIncomeSources, saveContribution, saveReturnRates, clearConfig }
})

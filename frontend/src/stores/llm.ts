import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '../composables/useApi'
import type { LLMStatus, CategorizeResponse } from '../types'

export const useLLMStore = defineStore('llm', () => {
  const status = ref<LLMStatus | null>(null)
  const categorizing = ref(false)
  const lastResult = ref<CategorizeResponse | null>(null)
  const error = ref<string | null>(null)

  async function fetchStatus() {
    const api = useApi()
    try {
      status.value = await api.get<LLMStatus>('/llm/status')
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function categorizeUncategorized(): Promise<CategorizeResponse | null> {
    const api = useApi()
    categorizing.value = true
    error.value = null
    try {
      const result = await api.post<CategorizeResponse>('/llm/categorize')
      lastResult.value = result
      return result
    } catch (e: any) {
      error.value = e.message
      return null
    } finally {
      categorizing.value = false
    }
  }

  async function categorizeSelected(transactionIds: number[]): Promise<CategorizeResponse | null> {
    const api = useApi()
    categorizing.value = true
    error.value = null
    try {
      const result = await api.post<CategorizeResponse>('/llm/categorize', {
        transaction_ids: transactionIds,
      })
      lastResult.value = result
      return result
    } catch (e: any) {
      error.value = e.message
      return null
    } finally {
      categorizing.value = false
    }
  }

  return { status, categorizing, lastResult, error, fetchStatus, categorizeUncategorized, categorizeSelected }
})

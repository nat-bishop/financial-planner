import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '../composables/useApi'
import type { SyncLog, HealthResponse } from '../types'

export const useSyncStore = defineStore('sync', () => {
  const syncing = ref(false)
  const lastSync = ref<SyncLog | null>(null)
  const health = ref<HealthResponse | null>(null)
  const error = ref<string | null>(null)

  async function triggerSync(): Promise<SyncLog | null> {
    const api = useApi()
    syncing.value = true
    error.value = null
    try {
      const result = await api.post<SyncLog>('/sync/')
      lastSync.value = result
      return result
    } catch (e: any) {
      error.value = e.message
      return null
    } finally {
      syncing.value = false
    }
  }

  async function createSandboxToken(): Promise<boolean> {
    const api = useApi()
    error.value = null
    try {
      await api.post('/sync/sandbox-token')
      return true
    } catch (e: any) {
      error.value = e.message
      return false
    }
  }

  async function fetchHealth() {
    const api = useApi()
    try {
      health.value = await api.get<HealthResponse>('/health')
    } catch (e: any) {
      error.value = e.message
    }
  }

  return { syncing, lastSync, health, error, triggerSync, createSandboxToken, fetchHealth }
})

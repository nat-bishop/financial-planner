import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '../composables/useApi'
import type { SyncLog, HealthResponse } from '../types'

export const useSyncStore = defineStore('sync', () => {
  const syncing = ref(false)
  const lastSync = ref<SyncLog | null>(null)
  const health = ref<HealthResponse | null>(null)
  const error = ref<string | null>(null)
  const claiming = ref(false)
  const connected = ref(false)

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

  async function claimSetupToken(setupToken: string): Promise<boolean> {
    const api = useApi()
    claiming.value = true
    error.value = null
    try {
      await api.post('/sync/credentials', { setup_token: setupToken })
      connected.value = true
      await triggerSync()
      return true
    } catch (e: any) {
      error.value = e.message
      return false
    } finally {
      claiming.value = false
    }
  }

  async function deleteCredentials(): Promise<boolean> {
    const api = useApi()
    error.value = null
    try {
      await api.del('/sync/credentials')
      connected.value = false
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
      connected.value = health.value.has_credentials
      console.log('fetchHealth:', {
        lastSyncAt: health.value.last_sync_at,
        connected: connected.value,
        accountCount: health.value.account_count
      })
    } catch (e: any) {
      error.value = e.message
    }
  }

  return {
    syncing, lastSync, health, error, claiming, connected,
    triggerSync, claimSetupToken, deleteCredentials, fetchHealth,
  }
})

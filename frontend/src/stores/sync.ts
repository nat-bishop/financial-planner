import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '../composables/useApi'
import type {
  HealthResponse,
  ProviderStatus,
  SyncStatusResponse,
  SyncTriggerResponse,
} from '../types'

export const useSyncStore = defineStore('sync', () => {
  const syncing = ref(false)
  const health = ref<HealthResponse | null>(null)
  const error = ref<string | null>(null)
  const claiming = ref(false)
  const providers = ref<ProviderStatus[]>([])
  const syncStatus = ref<SyncStatusResponse | null>(null)

  let pollTimer: ReturnType<typeof setInterval> | null = null

  function isConnected(providerName: string): boolean {
    return providers.value.some(p => p.provider === providerName && p.connected)
  }

  function hasAnyConnection(): boolean {
    return providers.value.some(p => p.connected)
  }

  async function fetchProviders(): Promise<void> {
    const api = useApi()
    try {
      providers.value = await api.get<ProviderStatus[]>('/providers/')
    } catch (e: any) {
      error.value = e.message
    }
  }

  async function connectProvider(name: string, data: Record<string, string>): Promise<boolean> {
    const api = useApi()
    claiming.value = true
    error.value = null
    try {
      await api.post(`/providers/${name}/credentials`, data)
      await fetchProviders()
      await triggerSync()
      return true
    } catch (e: any) {
      error.value = e.message
      return false
    } finally {
      claiming.value = false
    }
  }

  async function disconnectProvider(name: string): Promise<boolean> {
    const api = useApi()
    error.value = null
    try {
      await api.del(`/providers/${name}/credentials`)
      await fetchProviders()
      return true
    } catch (e: any) {
      error.value = e.message
      return false
    }
  }

  async function triggerSync(): Promise<SyncTriggerResponse | null> {
    const api = useApi()
    syncing.value = true
    error.value = null
    try {
      const result = await api.post<SyncTriggerResponse>('/sync/')
      startPolling()
      return result
    } catch (e: any) {
      error.value = e.message
      syncing.value = false
      return null
    }
  }

  async function triggerProviderSync(name: string): Promise<SyncTriggerResponse | null> {
    const api = useApi()
    syncing.value = true
    error.value = null
    try {
      const result = await api.post<SyncTriggerResponse>(`/sync/${name}`)
      startPolling()
      return result
    } catch (e: any) {
      error.value = e.message
      syncing.value = false
      return null
    }
  }

  async function pollSyncStatus(): Promise<void> {
    const api = useApi()
    try {
      syncStatus.value = await api.get<SyncStatusResponse>('/sync/status')
      if (!syncStatus.value.any_running) {
        stopPolling()
        syncing.value = false
        await fetchHealth()
        await fetchProviders()
      }
    } catch {
      // Don't update error for poll failures
    }
  }

  function startPolling(): void {
    stopPolling()
    pollTimer = setInterval(pollSyncStatus, 2000)
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function fetchHealth() {
    const api = useApi()
    try {
      health.value = await api.get<HealthResponse>('/health')
      providers.value = health.value.providers
    } catch (e: any) {
      error.value = e.message
    }
  }

  return {
    syncing, health, error, claiming, providers, syncStatus,
    isConnected, hasAnyConnection,
    fetchProviders, connectProvider, disconnectProvider,
    triggerSync, triggerProviderSync, pollSyncStatus,
    fetchHealth,
  }
})

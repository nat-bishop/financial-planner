<script setup lang="ts">
import { ref } from 'vue'
import { useSyncStore } from '../stores/sync'
import { formatRelative } from '../composables/useApi'

const syncStore = useSyncStore()
const setupToken = ref('')
const disconnecting = ref(false)

async function connect() {
  if (!setupToken.value.trim()) return
  const ok = await syncStore.connectProvider('simplefin', {
    setup_token: setupToken.value.trim(),
  })
  if (ok) setupToken.value = ''
}

async function disconnect() {
  disconnecting.value = true
  await syncStore.disconnectProvider('simplefin')
  disconnecting.value = false
}

const connected = () => syncStore.isConnected('simplefin')
const providerInfo = () => syncStore.providers.find(p => p.provider === 'simplefin')
</script>

<template>
  <div class="bg-surface-0 rounded-2xl p-6 border border-surface-200/50">
    <div class="flex items-center gap-3 mb-4">
      <div class="w-8 h-8 bg-surface-100 rounded-lg flex items-center justify-center">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <rect x="1" y="4" width="14" height="10" rx="2" stroke="currentColor" stroke-width="1.5" class="text-surface-500"/>
          <path d="M1 7h14" stroke="currentColor" stroke-width="1.5" class="text-surface-500"/>
          <circle cx="11" cy="10" r="1.5" fill="currentColor" class="text-accent"/>
        </svg>
      </div>
      <div>
        <h2 class="text-sm font-medium text-surface-900">SimpleFIN Bridge</h2>
        <p class="text-xs text-surface-500">Bank account sync via SimpleFIN</p>
      </div>
    </div>

    <!-- Connected state -->
    <div v-if="connected()" class="space-y-4">
      <div class="flex items-center gap-2 px-3 py-2 bg-income/10 rounded-lg">
        <div class="w-2 h-2 rounded-full bg-income"></div>
        <span class="text-sm text-income font-medium">Connected</span>
        <span v-if="providerInfo()?.last_sync_at" class="text-xs text-surface-500 ml-1">
          &middot; Last sync {{ formatRelative(providerInfo()?.last_sync_at) }}
        </span>
      </div>
      <div class="flex items-center justify-between pt-2 border-t border-surface-100">
        <p class="text-xs text-surface-400">
          Removing the connection will delete stored credentials. Your synced data will be kept.
        </p>
        <button
          @click="disconnect"
          :disabled="disconnecting"
          class="shrink-0 ml-4 px-4 py-2 text-sm font-medium text-expense bg-expense/10 rounded-xl transition-all duration-200 hover:bg-expense/20 active:scale-[0.98]"
          :class="{ 'opacity-60 cursor-wait': disconnecting }"
        >
          {{ disconnecting ? 'Removing...' : 'Disconnect' }}
        </button>
      </div>
    </div>

    <!-- Disconnected state -->
    <div v-else class="space-y-3">
      <div class="flex items-end gap-3">
        <div class="flex-1">
          <label class="block text-xs font-mono uppercase tracking-widest text-surface-500 mb-2">
            Setup Token
          </label>
          <input
            v-model="setupToken"
            type="text"
            placeholder="Paste setup token from bridge.simplefin.org"
            class="w-full px-4 py-2 bg-surface-50 border border-surface-200 rounded-xl text-sm text-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent font-mono"
            @keyup.enter="connect"
          />
        </div>
        <button
          @click="connect"
          :disabled="syncStore.claiming || !setupToken.trim()"
          class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-accent text-surface-0 rounded-xl transition-all duration-200 hover:brightness-110 active:scale-[0.98]"
          :class="{ 'opacity-60 cursor-wait': syncStore.claiming, 'opacity-40 cursor-not-allowed': !setupToken.trim() }"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <span v-if="syncStore.claiming">Connecting...</span>
          <span v-else>Connect</span>
        </button>
      </div>
      <p class="text-xs text-surface-400">
        Get a setup token from
        <a href="https://bridge.simplefin.org" target="_blank" rel="noopener" class="text-accent-dim underline hover:text-accent transition-colors">bridge.simplefin.org</a>
        ($1.50/mo)
      </p>
    </div>

    <p v-if="syncStore.error" class="mt-3 text-xs text-expense font-mono">{{ syncStore.error }}</p>
  </div>
</template>

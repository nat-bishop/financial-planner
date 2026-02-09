<script setup lang="ts">
import { ref } from 'vue'
import { useSyncStore } from '../stores/sync'
import { formatRelative } from '../composables/useApi'

const syncStore = useSyncStore()
const username = ref('')
const password = ref('')
const disconnecting = ref(false)

async function connect() {
  if (!username.value.trim() || !password.value) return
  const ok = await syncStore.connectProvider('nelnet', {
    username: username.value.trim(),
    password: password.value,
  })
  if (ok) {
    username.value = ''
    password.value = ''
  }
}

async function disconnect() {
  disconnecting.value = true
  await syncStore.disconnectProvider('nelnet')
  disconnecting.value = false
}

const connected = () => syncStore.isConnected('nelnet')
const providerInfo = () => syncStore.providers.find(p => p.provider === 'nelnet')
</script>

<template>
  <div class="bg-surface-0 rounded-2xl p-6 border border-surface-200/50">
    <div class="flex items-center gap-3 mb-4">
      <div class="w-8 h-8 bg-surface-100 rounded-lg flex items-center justify-center">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M2 12V4a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2z" stroke="currentColor" stroke-width="1.5" class="text-surface-500"/>
          <path d="M5 7l2 2 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="text-accent"/>
        </svg>
      </div>
      <div>
        <h2 class="text-sm font-medium text-surface-900">Nelnet Student Loans</h2>
        <p class="text-xs text-surface-500">Browser-based sync for student loan data</p>
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
          Removing the connection will delete stored credentials and session data.
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
      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-mono uppercase tracking-widest text-surface-500 mb-2">
            Username
          </label>
          <input
            v-model="username"
            type="text"
            placeholder="Nelnet username"
            autocomplete="username"
            class="w-full px-4 py-2 bg-surface-50 border border-surface-200 rounded-xl text-sm text-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent"
          />
        </div>
        <div>
          <label class="block text-xs font-mono uppercase tracking-widest text-surface-500 mb-2">
            Password
          </label>
          <input
            v-model="password"
            type="password"
            placeholder="Nelnet password"
            autocomplete="current-password"
            class="w-full px-4 py-2 bg-surface-50 border border-surface-200 rounded-xl text-sm text-surface-900 placeholder:text-surface-400 focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent"
            @keyup.enter="connect"
          />
        </div>
      </div>
      <div class="flex items-center justify-between">
        <p class="text-xs text-surface-400">
          Credentials are encrypted and stored locally. First sync may require 2FA in the browser.
        </p>
        <button
          @click="connect"
          :disabled="syncStore.claiming || !username.trim() || !password"
          class="shrink-0 ml-4 inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-accent text-surface-0 rounded-xl transition-all duration-200 hover:brightness-110 active:scale-[0.98]"
          :class="{ 'opacity-60 cursor-wait': syncStore.claiming, 'opacity-40 cursor-not-allowed': !username.trim() || !password }"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <span v-if="syncStore.claiming">Connecting...</span>
          <span v-else>Connect</span>
        </button>
      </div>
    </div>

    <p v-if="syncStore.error" class="mt-3 text-xs text-expense font-mono">{{ syncStore.error }}</p>
  </div>
</template>

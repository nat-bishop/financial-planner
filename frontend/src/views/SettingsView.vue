<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useSyncStore } from '../stores/sync'
import { useAccountsStore } from '../stores/accounts'
import { formatRelative } from '../composables/useApi'

const syncStore = useSyncStore()
const accountsStore = useAccountsStore()
const setupToken = ref('')
const disconnecting = ref(false)

onMounted(async () => {
  await syncStore.fetchHealth()
  await accountsStore.fetchAll()
})

async function connectBank() {
  if (!setupToken.value.trim()) return
  const ok = await syncStore.claimSetupToken(setupToken.value.trim())
  if (ok) {
    setupToken.value = ''
    await accountsStore.fetch()
    await syncStore.fetchHealth()
  }
}

async function disconnect() {
  disconnecting.value = true
  const ok = await syncStore.deleteCredentials()
  if (ok) {
    await syncStore.fetchHealth()
    await accountsStore.fetch()
  }
  disconnecting.value = false
}
</script>

<template>
  <div class="p-8 max-w-6xl animate-fade-up">
    <!-- Header -->
    <div class="mb-10">
      <h1 class="font-display text-4xl text-surface-100 tracking-tight mb-1">Settings</h1>
      <p class="text-sm text-surface-400">Manage your connections and preferences</p>
    </div>

    <!-- SimpleFIN Connection -->
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
      <div v-if="syncStore.connected" class="space-y-4">
        <div class="flex items-center gap-2 px-3 py-2 bg-income/10 rounded-lg">
          <div class="w-2 h-2 rounded-full bg-income"></div>
          <span class="text-sm text-income font-medium">Connected</span>
          <span v-if="syncStore.health?.account_count" class="text-xs text-surface-500 ml-1">
            &middot; {{ syncStore.health.account_count }} account{{ syncStore.health.account_count === 1 ? '' : 's' }}
          </span>
          <span v-if="syncStore.health?.last_sync_at" class="text-xs text-surface-500 ml-1">
            &middot; Last sync {{ formatRelative(syncStore.health.last_sync_at) }}
          </span>
        </div>
        <div class="flex items-center justify-between pt-2 border-t border-surface-100">
          <p class="text-xs text-surface-400">
            Removing the connection will delete stored credentials. Your synced data (accounts, transactions) will be kept.
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
              @keyup.enter="connectBank"
            />
          </div>
          <button
            @click="connectBank"
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

    <!-- Account Visibility -->
    <div
      v-if="accountsStore.allAccounts.length > 0"
      class="bg-surface-0 rounded-2xl p-6 border border-surface-200/50 mt-6"
    >
      <div class="flex items-center gap-3 mb-4">
        <div class="w-8 h-8 bg-surface-100 rounded-lg flex items-center justify-center">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M1 8s3-5 7-5 7 5 7 5-3 5-7 5-7-5-7-5z" stroke="currentColor" stroke-width="1.5" class="text-surface-500"/>
            <circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.5" class="text-accent"/>
          </svg>
        </div>
        <div>
          <h2 class="text-sm font-medium text-surface-900">Account Visibility</h2>
          <p class="text-xs text-surface-500">Hidden accounts still sync but won't appear in dashboard, transactions, or analytics</p>
        </div>
      </div>

      <div class="space-y-2">
        <div
          v-for="account in accountsStore.allAccounts"
          :key="account.id"
          class="flex items-center justify-between px-4 py-3 rounded-xl border border-surface-200/50"
          :class="account.is_disabled ? 'opacity-50' : ''"
        >
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-surface-300 truncate">
              {{ account.org_name || account.name }}
            </p>
            <p v-if="account.org_name" class="text-xs text-surface-500 truncate">
              {{ account.name }}
            </p>
          </div>
          <button
            @click="accountsStore.toggleDisabled(account.id, !account.is_disabled)"
            class="shrink-0 ml-4 relative w-10 h-6 rounded-full transition-colors duration-200 cursor-pointer"
            :class="account.is_disabled ? 'bg-surface-200' : 'bg-accent'"
          >
            <span
              class="absolute top-1 left-1 w-4 h-4 bg-white rounded-full shadow transition-transform duration-200"
              :class="account.is_disabled ? '' : 'translate-x-4'"
            ></span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

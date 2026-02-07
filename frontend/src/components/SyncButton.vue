<script setup lang="ts">
import { useSyncStore } from '../stores/sync'
import { useAccountsStore } from '../stores/accounts'
import { formatRelative } from '../composables/useApi'

const syncStore = useSyncStore()
const accountsStore = useAccountsStore()

async function handleSync() {
  const result = await syncStore.triggerSync()
  if (result) {
    await accountsStore.fetch()
  }
}
</script>

<template>
  <button
    @click="handleSync"
    :disabled="syncStore.syncing"
    class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl transition-all duration-200"
    :class="syncStore.syncing
      ? 'bg-surface-100 text-surface-400 cursor-wait'
      : 'bg-surface-0 text-surface-900 hover:bg-surface-100 active:scale-[0.98]'"
  >
    <svg
      width="16" height="16" viewBox="0 0 16 16" fill="none"
      :class="{ 'animate-spin': syncStore.syncing }"
    >
      <path d="M14 8A6 6 0 1 1 8 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M8 2V5L10.5 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    <span v-if="syncStore.syncing">Syncing...</span>
    <span v-else>Sync Now</span>
  </button>

  <!-- Result toast -->
  <Transition name="toast">
    <div
      v-if="syncStore.lastSync && !syncStore.syncing"
      class="mt-2 text-xs font-mono"
      :class="syncStore.lastSync.status === 'success' ? 'text-income' : 'text-expense'"
    >
      <span v-if="syncStore.lastSync.status === 'success'">
        +{{ syncStore.lastSync.transactions_added }} added,
        {{ syncStore.lastSync.accounts_synced }} accounts
      </span>
      <span v-else>
        {{ syncStore.lastSync.error_message || 'Sync failed' }}
      </span>
    </div>
  </Transition>

  <div v-if="syncStore.error && !syncStore.syncing" class="mt-2 text-xs text-expense font-mono">
    {{ syncStore.error }}
  </div>
</template>

<style scoped>
.toast-enter-active { transition: all 0.3s ease-out; }
.toast-leave-active { transition: all 0.2s ease-in; }
.toast-enter-from { opacity: 0; transform: translateY(-4px); }
.toast-leave-to { opacity: 0; }
</style>

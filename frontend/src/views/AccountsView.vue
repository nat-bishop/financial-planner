<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useAccountsStore } from '../stores/accounts'
import { useSyncStore } from '../stores/sync'
import AccountCard from '../components/AccountCard.vue'
import SyncButton from '../components/SyncButton.vue'
import { formatCurrency } from '../composables/useApi'

const accountsStore = useAccountsStore()
const syncStore = useSyncStore()
const connecting = ref(false)

onMounted(async () => {
  await accountsStore.fetch()
})

async function connectTestBank() {
  connecting.value = true
  const ok = await syncStore.createSandboxToken()
  if (ok) {
    // Auto-sync after connecting
    await syncStore.triggerSync()
    await accountsStore.fetch()
  }
  connecting.value = false
}
</script>

<template>
  <div class="p-8 max-w-6xl animate-fade-up">
    <!-- Header -->
    <div class="flex items-start justify-between mb-10">
      <div>
        <h1 class="font-display text-4xl text-surface-100 tracking-tight mb-1">Accounts</h1>
        <p class="text-sm text-surface-400">
          {{ accountsStore.accounts.length }} connected accounts
        </p>
      </div>
      <div class="flex items-center gap-3">
        <SyncButton />
        <button
          @click="connectTestBank"
          :disabled="connecting"
          class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-accent text-surface-0 rounded-xl transition-all duration-200 hover:brightness-110 active:scale-[0.98]"
          :class="{ 'opacity-60 cursor-wait': connecting }"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <span v-if="connecting">Connecting...</span>
          <span v-else>Connect Test Bank</span>
        </button>
      </div>
    </div>

    <!-- Net worth summary -->
    <div
      v-if="accountsStore.accounts.length > 0"
      class="bg-surface-0 rounded-2xl p-8 mb-8 border border-surface-200/50"
    >
      <div class="grid grid-cols-3 gap-8">
        <div>
          <p class="text-xs font-mono uppercase tracking-widest text-surface-500 mb-2">Total Balance</p>
          <p class="font-display text-3xl text-surface-900 tracking-tight">
            {{ formatCurrency(accountsStore.totalBalance()) }}
          </p>
        </div>
        <div>
          <p class="text-xs font-mono uppercase tracking-widest text-surface-500 mb-2">Accounts</p>
          <p class="font-display text-3xl text-surface-900 tracking-tight">
            {{ accountsStore.accounts.length }}
          </p>
        </div>
        <div>
          <p class="text-xs font-mono uppercase tracking-widest text-surface-500 mb-2">Providers</p>
          <p class="font-display text-3xl text-surface-900 tracking-tight">
            {{ new Set(accountsStore.accounts.map(a => a.provider)).size }}
          </p>
        </div>
      </div>
    </div>

    <!-- Account cards -->
    <div v-if="accountsStore.accounts.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 stagger-children">
      <AccountCard
        v-for="account in accountsStore.accounts"
        :key="account.id"
        :account="account"
      />
    </div>

    <!-- Empty state -->
    <div
      v-if="!accountsStore.loading && accountsStore.accounts.length === 0"
      class="text-center py-20"
    >
      <div class="w-20 h-20 mx-auto mb-6 bg-surface-0 rounded-2xl flex items-center justify-center border border-surface-200/50">
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
          <rect x="4" y="8" width="24" height="18" rx="3" stroke="#555" stroke-width="1.5"/>
          <path d="M4 13h24" stroke="#555" stroke-width="1.5"/>
          <circle cx="22" cy="20" r="2" fill="#c8ff00"/>
        </svg>
      </div>
      <h2 class="font-display text-2xl text-surface-200 mb-2">No accounts yet</h2>
      <p class="text-sm text-surface-400 mb-8 max-w-md mx-auto">
        Connect a test bank to start exploring. This uses Plaid's sandbox environment with sample data.
      </p>
      <button
        @click="connectTestBank"
        :disabled="connecting"
        class="inline-flex items-center gap-2 px-6 py-3 bg-accent text-surface-0 text-sm font-medium rounded-xl transition-all hover:brightness-110 active:scale-[0.98]"
        :class="{ 'opacity-60 cursor-wait': connecting }"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        {{ connecting ? 'Connecting...' : 'Connect Test Bank' }}
      </button>
      <p v-if="syncStore.error" class="mt-4 text-xs text-expense font-mono">{{ syncStore.error }}</p>
    </div>

    <!-- Loading -->
    <div v-if="accountsStore.loading" class="flex items-center justify-center py-20">
      <div class="w-6 h-6 border-2 border-surface-300 border-t-accent rounded-full animate-spin"></div>
    </div>
  </div>
</template>

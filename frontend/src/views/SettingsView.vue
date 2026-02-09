<script setup lang="ts">
import { onMounted } from 'vue'
import { useSyncStore } from '../stores/sync'
import { useAccountsStore } from '../stores/accounts'
import SimpleFINConnect from '../components/SimpleFINConnect.vue'
import NelnetConnect from '../components/NelnetConnect.vue'

const syncStore = useSyncStore()
const accountsStore = useAccountsStore()

onMounted(async () => {
  await syncStore.fetchHealth()
  await accountsStore.fetchAll()
})
</script>

<template>
  <div class="p-8 max-w-6xl animate-fade-up">
    <!-- Header -->
    <div class="mb-10">
      <h1 class="font-display text-4xl text-surface-100 tracking-tight mb-1">Settings</h1>
      <p class="text-sm text-surface-400">Manage your connections and preferences</p>
    </div>

    <!-- Provider Connections -->
    <div class="space-y-6">
      <SimpleFINConnect />
      <NelnetConnect />
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

<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useAccountsStore } from '../stores/accounts'
import { useSyncStore } from '../stores/sync'
import AccountCard from '../components/AccountCard.vue'
import MonthlyTrendChart from '../components/MonthlyTrendChart.vue'
import SpendingChart from '../components/SpendingChart.vue'
import BillCalendar from '../components/BillCalendar.vue'
import SyncButton from '../components/SyncButton.vue'
import { formatCurrency, formatRelative } from '../composables/useApi'

const accountsStore = useAccountsStore()
const syncStore = useSyncStore()

const totalAssets = computed(() =>
  accountsStore.accounts
    .filter(a => (a.balance_current ?? 0) > 0)
    .reduce((sum, a) => sum + (a.balance_current ?? 0), 0)
)

const totalLiabilities = computed(() =>
  accountsStore.accounts
    .filter(a => (a.balance_current ?? 0) < 0)
    .reduce((sum, a) => sum + Math.abs(a.balance_current ?? 0), 0)
)

onMounted(async () => {
  await Promise.all([
    accountsStore.fetch(),
    syncStore.fetchHealth(),
  ])
})
</script>

<template>
  <div class="p-8 max-w-6xl animate-fade-up">
    <!-- Page header -->
    <div class="flex items-start justify-between mb-10">
      <div>
        <h1 class="font-display text-4xl text-surface-100 tracking-tight mb-1">Overview</h1>
        <p class="text-sm text-surface-400">
          <template v-if="syncStore.health">
            {{ syncStore.health.account_count }} accounts
            <span class="text-surface-300 mx-1.5">&middot;</span>
            Last synced {{ formatRelative(syncStore.health.last_sync_at) }}
          </template>
          <template v-else>Loading...</template>
        </p>
      </div>
      <SyncButton />
    </div>

    <!-- Net worth banner -->
    <div
      v-if="accountsStore.accounts.length > 0"
      class="bg-surface-0 rounded-2xl p-8 mb-8 border border-surface-200/50"
    >
      <p class="text-xs font-mono uppercase tracking-widest text-surface-500 mb-3">Total Balance</p>
      <p class="font-display text-5xl text-surface-900 tracking-tight leading-none mb-3">
        {{ formatCurrency(accountsStore.totalBalance()) }}
      </p>
      <div v-if="totalAssets > 0 || totalLiabilities > 0" class="flex items-center gap-4 text-xs font-mono">
        <span class="text-surface-400">Assets: <span class="text-income">{{ formatCurrency(totalAssets) }}</span></span>
        <span v-if="totalLiabilities > 0" class="text-surface-400">Liabilities: <span class="text-expense">{{ formatCurrency(-totalLiabilities) }}</span></span>
      </div>
    </div>

    <!-- Accounts row -->
    <div v-if="accountsStore.accounts.length > 0" class="mb-10">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-xs font-mono uppercase tracking-widest text-surface-400">Accounts</h2>
        <router-link to="/accounts" class="text-xs text-surface-400 hover:text-surface-200 transition-colors">
          View all &rarr;
        </router-link>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 stagger-children">
        <AccountCard
          v-for="account in accountsStore.accounts.slice(0, 3)"
          :key="account.id"
          :account="account"
          compact
        />
      </div>
    </div>

    <!-- Monthly Trend (full width) -->
    <div v-if="accountsStore.accounts.length > 0" class="mb-10">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-xs font-mono uppercase tracking-widest text-surface-400">
          Monthly Income &amp; Expenses
        </h2>
        <span class="text-[10px] font-mono text-surface-300">Last 12 months</span>
      </div>
      <div class="bg-white border border-surface-900/8 rounded-2xl p-6">
        <MonthlyTrendChart />
      </div>
    </div>

    <!-- Two column: Spending Chart + Upcoming Bills -->
    <div v-if="accountsStore.accounts.length > 0" class="grid grid-cols-1 lg:grid-cols-2 gap-8">
      <div>
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xs font-mono uppercase tracking-widest text-surface-400">
            Spending by Category
          </h2>
          <span class="text-[10px] font-mono text-surface-300">Last 30 days</span>
        </div>
        <div class="bg-white border border-surface-900/8 rounded-2xl p-6">
          <SpendingChart />
        </div>
      </div>

      <div>
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-xs font-mono uppercase tracking-widest text-surface-400">
            Upcoming Bills
          </h2>
        </div>
        <div class="bg-white border border-surface-900/8 rounded-2xl p-6">
          <BillCalendar />
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-if="!accountsStore.loading && accountsStore.accounts.length === 0"
      class="text-center py-20"
    >
      <div class="w-16 h-16 mx-auto mb-6 bg-surface-0 rounded-2xl flex items-center justify-center">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
          <path d="M14 7v14M7 14h14" stroke="#0d9488" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </div>
      <h2 class="font-display text-2xl text-surface-200 mb-2">No accounts connected</h2>
      <p class="text-sm text-surface-400 mb-6 max-w-md mx-auto">
        Connect your bank accounts to start tracking your finances.
      </p>
      <router-link
        to="/settings"
        class="inline-flex items-center gap-2 px-5 py-2.5 bg-surface-0 text-surface-900 text-sm font-medium rounded-xl hover:bg-surface-100 transition-colors"
      >
        Connect Accounts &rarr;
      </router-link>
    </div>
  </div>
</template>

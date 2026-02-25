<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useSyncStore } from '../stores/sync'
import { useAccountsStore } from '../stores/accounts'
import { useCategoriesStore } from '../stores/categories'
import SimpleFINConnect from '../components/SimpleFINConnect.vue'
import NelnetConnect from '../components/NelnetConnect.vue'
import CollapsibleSection from '../components/CollapsibleSection.vue'

const syncStore = useSyncStore()
const accountsStore = useAccountsStore()
const categoriesStore = useCategoriesStore()

const newCategoryName = ref('')
const newCategoryDesc = ref('')
const creatingCategory = ref(false)

// Auto-categorization rules
const memoryRules = ref<any[]>([])
const loadingRules = ref(false)

onMounted(async () => {
  await Promise.all([
    syncStore.fetchHealth(),
    accountsStore.fetchAll(),
    categoriesStore.fetch(),
    fetchMemoryRules(),
  ])
})

async function toggleExclude(id: number, current: boolean) {
  await categoriesStore.update(id, { exclude_from_totals: !current })
}

async function createCategory() {
  if (!newCategoryName.value.trim()) return
  creatingCategory.value = true
  const result = await categoriesStore.create(newCategoryName.value.trim(), newCategoryDesc.value.trim() || undefined)
  if (result) {
    newCategoryName.value = ''
    newCategoryDesc.value = ''
  }
  creatingCategory.value = false
}

async function deleteCategory(id: number, name: string) {
  if (!confirm(`Delete category "${name}"? Transactions with this category will be reset to Uncategorized.`)) return
  await categoriesStore.remove(id)
}

async function fetchMemoryRules() {
  loadingRules.value = true
  try {
    const resp = await fetch('/api/categories/memory')
    if (resp.ok) memoryRules.value = await resp.json()
  } catch {
    // ignore
  } finally {
    loadingRules.value = false
  }
}

async function deleteMemoryRule(id: number) {
  try {
    const resp = await fetch(`/api/categories/memory/${id}`, { method: 'DELETE' })
    if (resp.ok) {
      memoryRules.value = memoryRules.value.filter(r => r.id !== id)
    }
  } catch {
    // ignore
  }
}
</script>

<template>
  <div class="p-8 max-w-6xl animate-fade-up">
    <!-- Header -->
    <div class="mb-10">
      <h1 class="font-display text-4xl text-surface-100 tracking-tight mb-1">Settings</h1>
      <p class="text-sm text-surface-400">Manage your connections and preferences</p>
    </div>

    <div class="space-y-4">
      <!-- Provider Connections (default open) -->
      <CollapsibleSection title="Provider Connections" :default-open="true">
        <template #icon>
          <div class="w-8 h-8 bg-surface-100 rounded-lg flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M8 1v6M8 9v6M1 8h6M9 8h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" class="text-surface-500"/>
            </svg>
          </div>
        </template>
        <template #description>
          <p class="text-xs text-surface-500">Connect financial data providers</p>
        </template>
        <div class="space-y-6">
          <SimpleFINConnect />
          <NelnetConnect />
        </div>
      </CollapsibleSection>

      <!-- Account Visibility -->
      <CollapsibleSection
        v-if="accountsStore.allAccounts.length > 0"
        title="Account Visibility"
      >
        <template #icon>
          <div class="w-8 h-8 bg-surface-100 rounded-lg flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M1 8s3-5 7-5 7 5 7 5-3 5-7 5-7-5-7-5z" stroke="currentColor" stroke-width="1.5" class="text-surface-500"/>
              <circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.5" class="text-accent"/>
            </svg>
          </div>
        </template>
        <template #description>
          <p class="text-xs text-surface-500">Hidden accounts still sync but won't appear in dashboard, transactions, or analytics</p>
        </template>

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
      </CollapsibleSection>

      <!-- Categories -->
      <CollapsibleSection title="Categories">
        <template #icon>
          <div class="w-8 h-8 bg-surface-100 rounded-lg flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 4h4v4H2zM10 4h4v4h-4zM2 10h4v4H2zM10 10h4v4h-4z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" class="text-surface-500"/>
            </svg>
          </div>
        </template>
        <template #description>
          <p class="text-xs text-surface-500">Manage spending categories and control which appear in analytics totals</p>
        </template>

        <!-- Category list -->
        <div v-if="categoriesStore.categories.length > 0" class="space-y-2 mb-4">
          <div class="flex items-center gap-4 px-4 py-1.5">
            <span class="flex-1 text-[10px] font-mono uppercase tracking-wider text-surface-400">Category</span>
            <span class="w-24 text-[10px] font-mono uppercase tracking-wider text-surface-400 text-center">In Totals</span>
            <span class="w-8"></span>
          </div>
          <div
            v-for="cat in categoriesStore.categories"
            :key="cat.id"
            class="flex items-center gap-4 px-4 py-3 rounded-xl border border-surface-200/50"
          >
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium text-surface-300 truncate">{{ cat.name }}</p>
              <p v-if="cat.description" class="text-xs text-surface-500 truncate">{{ cat.description }}</p>
            </div>
            <div class="w-24 flex justify-center">
              <button
                @click="toggleExclude(cat.id, cat.exclude_from_totals)"
                class="relative w-10 h-6 rounded-full transition-colors duration-200 cursor-pointer"
                :class="cat.exclude_from_totals ? 'bg-surface-200' : 'bg-accent'"
              >
                <span
                  class="absolute top-1 left-1 w-4 h-4 bg-white rounded-full shadow transition-transform duration-200"
                  :class="cat.exclude_from_totals ? '' : 'translate-x-4'"
                ></span>
              </button>
            </div>
            <div class="w-8 flex justify-center">
              <button
                v-if="!cat.is_default"
                @click="deleteCategory(cat.id, cat.name)"
                class="text-surface-400 hover:text-expense transition-colors p-1"
                title="Delete category"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 3.5l8 8M11 3.5l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <!-- Add category form -->
        <div class="flex items-end gap-3 pt-3 border-t border-surface-200/50">
          <div class="flex-1">
            <label class="text-[10px] font-mono uppercase tracking-wider text-surface-400 block mb-1">Name</label>
            <input
              v-model="newCategoryName"
              placeholder="New category..."
              class="w-full text-sm px-3 py-2 bg-white border border-surface-200/50 rounded-lg outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 text-surface-900 placeholder:text-surface-400"
              @keydown.enter="createCategory"
            />
          </div>
          <div class="flex-1">
            <label class="text-[10px] font-mono uppercase tracking-wider text-surface-400 block mb-1">Description</label>
            <input
              v-model="newCategoryDesc"
              placeholder="Optional description..."
              class="w-full text-sm px-3 py-2 bg-white border border-surface-200/50 rounded-lg outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 text-surface-900 placeholder:text-surface-400"
              @keydown.enter="createCategory"
            />
          </div>
          <button
            @click="createCategory"
            :disabled="!newCategoryName.trim() || creatingCategory"
            class="shrink-0 px-4 py-2 text-sm font-medium bg-accent/10 text-accent rounded-lg hover:bg-accent/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Add
          </button>
        </div>
      </CollapsibleSection>

      <!-- Auto-Categorization Rules -->
      <CollapsibleSection title="Auto-Categorization Rules">
        <template #icon>
          <div class="w-8 h-8 bg-surface-100 rounded-lg flex items-center justify-center shrink-0">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 3h12M2 8h8M2 13h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" class="text-surface-500"/>
            </svg>
          </div>
        </template>
        <template #description>
          <p class="text-xs text-surface-500">Rules created when you manually change a transaction's category. Matching transactions in future syncs will be auto-categorized.</p>
        </template>

        <div v-if="loadingRules" class="flex items-center justify-center py-8">
          <div class="w-5 h-5 border-2 border-surface-300 border-t-accent rounded-full animate-spin"></div>
        </div>

        <div v-else-if="memoryRules.length === 0" class="py-8 text-center">
          <p class="text-sm text-surface-400">No rules yet. Edit a transaction's category to create one.</p>
        </div>

        <div v-else class="max-h-96 overflow-y-auto space-y-2">
          <div class="flex items-center gap-4 px-4 py-1.5 sticky top-0 bg-surface-0">
            <span class="flex-1 text-[10px] font-mono uppercase tracking-wider text-surface-400">Pattern</span>
            <span class="w-32 text-[10px] font-mono uppercase tracking-wider text-surface-400">Account</span>
            <span class="w-32 text-[10px] font-mono uppercase tracking-wider text-surface-400">Category</span>
            <span class="w-8"></span>
          </div>
          <div
            v-for="rule in memoryRules"
            :key="rule.id"
            class="flex items-center gap-4 px-4 py-2.5 rounded-xl border border-surface-200/50"
          >
            <div class="flex-1 min-w-0">
              <p class="text-xs text-surface-300 font-mono truncate">{{ rule.normalized_pattern }}</p>
            </div>
            <div class="w-32">
              <p class="text-xs text-surface-400 truncate">{{ rule.account_name || '--' }}</p>
            </div>
            <div class="w-32">
              <p class="text-xs text-surface-300 truncate">{{ rule.category }}</p>
            </div>
            <div class="w-8 flex justify-center">
              <button
                @click="deleteMemoryRule(rule.id)"
                class="text-surface-400 hover:text-expense transition-colors p-1"
                title="Delete rule"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M3 3.5l8 8M11 3.5l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
                </svg>
              </button>
            </div>
          </div>
        </div>
      </CollapsibleSection>
    </div>
  </div>
</template>

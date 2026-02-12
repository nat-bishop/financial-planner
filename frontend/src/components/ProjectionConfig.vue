<script setup lang="ts">
import { ref, watch } from 'vue'
import { useProjectionStore } from '../stores/projection'

const store = useProjectionStore()

const incomeSources = ref<{ name: string; amount: string }[]>([])
const contributionOverride = ref('')
const saving = ref(false)

// Sync from store when projection loads
watch(() => store.projection, (p) => {
  if (!p) return
  if (p.income_sources.length > 0) {
    incomeSources.value = p.income_sources.map(s => ({
      name: s.name,
      amount: (s.monthly_amount / 100).toFixed(2),
    }))
  } else if (incomeSources.value.length === 0) {
    incomeSources.value = [{ name: '', amount: '' }]
  }
}, { immediate: true })

function addSource() {
  incomeSources.value.push({ name: '', amount: '' })
}

function removeSource(i: number) {
  incomeSources.value.splice(i, 1)
  if (incomeSources.value.length === 0) {
    incomeSources.value.push({ name: '', amount: '' })
  }
}

async function save() {
  saving.value = true

  // Save income sources (filter out empty ones)
  const sources = incomeSources.value
    .filter(s => s.name.trim() && s.amount.trim())
    .map(s => ({
      name: s.name.trim(),
      monthly_amount: Math.round(parseFloat(s.amount) * 100),
    }))
  if (sources.length > 0) {
    await store.saveIncomeSources(sources)
  }

  // Save contribution override if set
  if (contributionOverride.value.trim()) {
    const amount = Math.round(parseFloat(contributionOverride.value) * 100)
    await store.saveContribution(amount)
  }

  saving.value = false
}

async function reset() {
  saving.value = true
  await store.clearConfig()
  incomeSources.value = [{ name: '', amount: '' }]
  contributionOverride.value = ''
  saving.value = false
}
</script>

<template>
  <div class="bg-surface-0 rounded-2xl p-6 border border-surface-200/50">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h3 class="text-sm font-medium text-surface-900">Configuration</h3>
        <p class="text-xs text-surface-500">
          {{ store.projection?.is_configured ? 'Using your configured values' : 'Auto-calculated from your transaction history' }}
        </p>
      </div>
      <button
        v-if="store.projection?.is_configured"
        @click="reset"
        :disabled="saving"
        class="text-xs text-surface-400 hover:text-surface-200 transition-colors"
      >
        Reset to auto
      </button>
    </div>

    <!-- Income Sources -->
    <div class="mb-4">
      <label class="text-[10px] font-mono uppercase tracking-wider text-surface-400 block mb-2">Income Sources</label>
      <div class="space-y-2">
        <div v-for="(source, i) in incomeSources" :key="i" class="flex items-center gap-2">
          <input
            v-model="source.name"
            placeholder="Source name..."
            class="flex-1 text-sm px-3 py-2 bg-white border border-surface-200/50 rounded-lg outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 text-surface-900 placeholder:text-surface-400"
          />
          <div class="relative">
            <span class="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-surface-400">$</span>
            <input
              v-model="source.amount"
              type="number"
              placeholder="0.00"
              step="0.01"
              class="w-32 text-sm pl-7 pr-3 py-2 bg-white border border-surface-200/50 rounded-lg outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 text-surface-900 placeholder:text-surface-400 font-mono"
            />
          </div>
          <span class="text-[10px] text-surface-400 font-mono">/mo</span>
          <button
            @click="removeSource(i)"
            class="text-surface-400 hover:text-expense transition-colors p-1"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M3 3.5l8 8M11 3.5l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
      </div>
      <button
        @click="addSource"
        class="mt-2 text-xs text-accent hover:text-accent/80 transition-colors"
      >
        + Add income source
      </button>
    </div>

    <!-- Monthly Contribution Override -->
    <div class="mb-4">
      <label class="text-[10px] font-mono uppercase tracking-wider text-surface-400 block mb-1">
        Monthly Investment (optional override)
      </label>
      <div class="relative w-48">
        <span class="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-surface-400">$</span>
        <input
          v-model="contributionOverride"
          type="number"
          :placeholder="store.projection ? (store.projection.monthly_contribution / 100).toFixed(2) : '0.00'"
          step="0.01"
          class="w-full text-sm pl-7 pr-3 py-2 bg-white border border-surface-200/50 rounded-lg outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 text-surface-900 placeholder:text-surface-400 font-mono"
        />
      </div>
      <p class="text-[10px] text-surface-400 mt-1">Leave empty to auto-calculate (income - expenses)</p>
    </div>

    <!-- Save -->
    <div class="flex items-center gap-3 pt-3 border-t border-surface-200/50">
      <button
        @click="save"
        :disabled="saving"
        class="px-4 py-2 text-sm font-medium bg-accent/10 text-accent rounded-lg hover:bg-accent/20 transition-colors disabled:opacity-40"
      >
        {{ saving ? 'Saving...' : 'Save Configuration' }}
      </button>
    </div>
  </div>
</template>

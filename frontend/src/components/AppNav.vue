<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()

const links = [
  { to: '/', label: 'Overview', icon: 'grid' },
  { to: '/transactions', label: 'Transactions', icon: 'list' },
  { to: '/accounts', label: 'Accounts', icon: 'wallet' },
  { to: '/projection', label: 'Projection', icon: 'trending' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
]

const isActive = (path: string) => {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}

const currentTime = new Date().toLocaleDateString('en-US', {
  weekday: 'long',
  month: 'long',
  day: 'numeric',
})
</script>

<template>
  <nav class="fixed left-0 top-0 bottom-0 w-64 bg-surface-0 border-r border-surface-200/50 flex flex-col z-50">
    <!-- Brand -->
    <div class="px-6 pt-8 pb-6">
      <div class="flex items-center gap-3 mb-1">
        <div class="w-8 h-8 bg-accent rounded-lg flex items-center justify-center">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M2 4h12M2 8h8M2 12h10" stroke="#0a0a0a" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </div>
        <span class="font-display text-xl text-surface-900 tracking-tight">Finance</span>
      </div>
      <p class="text-xs text-surface-500 mt-3 font-mono">{{ currentTime }}</p>
    </div>

    <!-- Links -->
    <div class="flex-1 px-3 space-y-1">
      <router-link
        v-for="link in links"
        :key="link.to"
        :to="link.to"
        class="group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-200"
        :class="[
          isActive(link.to)
            ? 'bg-surface-100 text-surface-900'
            : 'text-surface-500 hover:text-surface-700 hover:bg-surface-50'
        ]"
      >
        <!-- Icons -->
        <svg v-if="link.icon === 'grid'" width="18" height="18" viewBox="0 0 18 18" fill="none"
          :class="isActive(link.to) ? 'text-accent' : 'text-surface-400 group-hover:text-surface-500'"
        >
          <rect x="1" y="1" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.5"/>
          <rect x="10" y="1" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.5"/>
          <rect x="1" y="10" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.5"/>
          <rect x="10" y="10" width="7" height="7" rx="2" stroke="currentColor" stroke-width="1.5"/>
        </svg>
        <svg v-else-if="link.icon === 'list'" width="18" height="18" viewBox="0 0 18 18" fill="none"
          :class="isActive(link.to) ? 'text-accent' : 'text-surface-400 group-hover:text-surface-500'"
        >
          <path d="M5 4h10M5 9h10M5 14h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          <circle cx="2" cy="4" r="1" fill="currentColor"/>
          <circle cx="2" cy="9" r="1" fill="currentColor"/>
          <circle cx="2" cy="14" r="1" fill="currentColor"/>
        </svg>
        <svg v-else-if="link.icon === 'wallet'" width="18" height="18" viewBox="0 0 18 18" fill="none"
          :class="isActive(link.to) ? 'text-accent' : 'text-surface-400 group-hover:text-surface-500'"
        >
          <rect x="1" y="4" width="16" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
          <path d="M1 7h16" stroke="currentColor" stroke-width="1.5"/>
          <circle cx="13" cy="11" r="1.5" fill="currentColor"/>
        </svg>
        <svg v-else-if="link.icon === 'trending'" width="18" height="18" viewBox="0 0 18 18" fill="none"
          :class="isActive(link.to) ? 'text-accent' : 'text-surface-400 group-hover:text-surface-500'"
        >
          <path d="M2 14l4-5 3 3 7-8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M12 4h4v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <svg v-else-if="link.icon === 'settings'" width="18" height="18" viewBox="0 0 18 18" fill="none"
          :class="isActive(link.to) ? 'text-accent' : 'text-surface-400 group-hover:text-surface-500'"
        >
          <circle cx="9" cy="9" r="3" stroke="currentColor" stroke-width="1.5"/>
          <path d="M9 1v2M9 15v2M1 9h2M15 9h2M3.34 3.34l1.42 1.42M13.24 13.24l1.42 1.42M3.34 14.66l1.42-1.42M13.24 4.76l1.42-1.42" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>

        <span class="font-medium">{{ link.label }}</span>

        <div
          v-if="isActive(link.to)"
          class="ml-auto w-1.5 h-1.5 rounded-full bg-accent"
        ></div>
      </router-link>
    </div>

    <!-- Footer -->
    <div class="px-6 py-6 border-t border-surface-100">
      <p class="text-[10px] text-surface-400 font-mono uppercase tracking-widest">Finance Planner v0.1</p>
    </div>
  </nav>
</template>

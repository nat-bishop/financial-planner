<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  title: string
  defaultOpen?: boolean
}>(), {
  defaultOpen: false,
})

const isOpen = ref(props.defaultOpen)

function toggle() {
  isOpen.value = !isOpen.value
}
</script>

<template>
  <div class="bg-surface-0 rounded-2xl border border-surface-200/50">
    <!-- Header (clickable) -->
    <button
      @click="toggle"
      class="w-full flex items-center gap-3 p-6 text-left cursor-pointer select-none"
    >
      <slot name="icon" />
      <div class="flex-1 min-w-0">
        <h2 class="text-sm font-medium text-surface-900">{{ title }}</h2>
        <slot name="description" />
      </div>
      <svg
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        class="shrink-0 text-surface-400 transition-transform duration-200"
        :class="isOpen ? 'rotate-180' : ''"
      >
        <path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </button>

    <!-- Content -->
    <div
      class="grid transition-all duration-200"
      :class="isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'"
    >
      <div class="overflow-hidden">
        <div class="px-6 pb-6">
          <slot />
        </div>
      </div>
    </div>
  </div>
</template>

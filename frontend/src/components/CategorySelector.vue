<script setup lang="ts">
import { useCategoriesStore } from '../stores/categories'

const categoriesStore = useCategoriesStore()

const model = defineModel<string>({ required: true })
</script>

<template>
  <select
    v-model="model"
    class="text-xs px-2 py-1.5 bg-white border border-surface-900/10 rounded-md w-full outline-none focus:border-accent focus:ring-1 focus:ring-accent/30 appearance-none cursor-pointer"
    style="background-image: url('data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 12 12%22><path d=%22M3 5l3 3 3-3%22 fill=%22none%22 stroke=%22%23999%22 stroke-width=%221.5%22 stroke-linecap=%22round%22/></svg>'); background-repeat: no-repeat; background-position: right 8px center; padding-right: 28px;"
  >
    <option value="Uncategorized">Uncategorized</option>
    <option v-for="cat in categoriesStore.categories" :key="cat.id" :value="cat.name">
      {{ cat.name }}
    </option>
  </select>
</template>

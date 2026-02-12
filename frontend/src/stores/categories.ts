import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApi } from '../composables/useApi'
import type { Category } from '../types'

export const useCategoriesStore = defineStore('categories', () => {
  const categories = ref<Category[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetch() {
    const api = useApi()
    loading.value = true
    error.value = null
    try {
      categories.value = await api.get<Category[]>('/categories/')
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function create(name: string, description?: string): Promise<Category | null> {
    const api = useApi()
    try {
      const cat = await api.post<Category>('/categories/', { name, description })
      categories.value.push(cat)
      categories.value.sort((a, b) => a.name.localeCompare(b.name))
      return cat
    } catch (e: any) {
      error.value = e.message
      return null
    }
  }

  async function update(id: number, data: { exclude_from_totals?: boolean; description?: string }): Promise<boolean> {
    const api = useApi()
    try {
      const updated = await api.patch<Category>(`/categories/${id}`, data)
      const idx = categories.value.findIndex(c => c.id === id)
      if (idx !== -1) categories.value[idx] = updated
      return true
    } catch (e: any) {
      error.value = e.message
      return false
    }
  }

  async function remove(id: number): Promise<boolean> {
    const api = useApi()
    try {
      await api.del(`/categories/${id}`)
      categories.value = categories.value.filter(c => c.id !== id)
      return true
    } catch (e: any) {
      error.value = e.message
      return false
    }
  }

  return { categories, loading, error, fetch, create, update, remove }
})

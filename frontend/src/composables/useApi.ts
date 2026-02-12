import { ref } from 'vue'

const BASE = '/api'

function parseDetail(detail: unknown, status: number): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg || JSON.stringify(d)).join('; ')
  return `HTTP ${status}`
}

export function useApi() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function _request<T>(url: string, init?: RequestInit): Promise<T> {
    loading.value = true
    error.value = null
    try {
      const res = await fetch(url, init)
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(parseDetail(body.detail, res.status))
      }
      return await res.json() as T
    } catch (e: any) {
      error.value = e.message
      throw e
    } finally {
      loading.value = false
    }
  }

  function _jsonInit(method: string, body?: any): RequestInit {
    return {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }
  }

  function get<T>(path: string, params?: Record<string, any>): Promise<T> {
    const url = new URL(BASE + path, window.location.origin)
    if (params) {
      for (const [key, val] of Object.entries(params)) {
        if (val !== undefined && val !== null && val !== '') {
          url.searchParams.set(key, String(val))
        }
      }
    }
    return _request<T>(url.toString())
  }

  const post = <T>(path: string, body?: any) => _request<T>(BASE + path, _jsonInit('POST', body))
  const put = <T>(path: string, body: any) => _request<T>(BASE + path, _jsonInit('PUT', body))
  const patch = <T>(path: string, body: any) => _request<T>(BASE + path, _jsonInit('PATCH', body))
  const del = <T>(path: string) => _request<T>(BASE + path, { method: 'DELETE' })

  return { loading, error, get, post, put, patch, del }
}

/** Format cents as currency string */
export function formatCurrency(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '--'
  const dollars = Math.abs(cents) / 100
  const formatted = dollars.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return cents < 0 ? `-$${formatted}` : `$${formatted}`
}

/** Format unix timestamp as readable date */
export function formatDate(timestamp: number | null | undefined): string {
  if (!timestamp) return '--'
  return new Date(timestamp * 1000).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/** Format unix timestamp as relative time */
export function formatRelative(timestamp: number | null | undefined): string {
  if (!timestamp) return 'Never'
  const seconds = Math.floor(Date.now() / 1000) - timestamp
  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

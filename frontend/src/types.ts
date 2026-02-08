export interface Account {
  id: string
  provider: string
  org_name: string | null
  name: string
  account_type: string | null
  currency: string
  balance_current: number | null
  balance_available: number | null
  balance_date: number | null
  last_synced_at: number | null
  created_at: number
}

export interface Transaction {
  id: number
  account_id: string
  external_id: string
  posted_at: number
  amount: number
  description: string
  is_pending: boolean
  category: string | null
  subcategory: string | null
  tags: string | null
  notes: string | null
  created_at: number
  updated_at: number | null
}

export interface TransactionUpdate {
  category?: string | null
  subcategory?: string | null
  tags?: string | null
  notes?: string | null
}

export interface SyncLog {
  id: number
  started_at: number
  completed_at: number | null
  status: string
  accounts_synced: number
  transactions_added: number
  transactions_updated: number
  error_message: string | null
}

export interface SpendingCategory {
  category: string | null
  total: number
  count: number
}

export interface SpendingByCategoryResponse {
  start_date: number
  end_date: number
  categories: SpendingCategory[]
}

export interface HealthResponse {
  status: string
  has_credentials: boolean
  last_sync_at: number | null
  last_sync_status: string | null
  account_count: number
  recent_errors: { at: number; message: string | null }[]
}

export interface TransactionFilters {
  account_id?: string
  category?: string
  search?: string
  start_date?: number
  end_date?: number
  limit?: number
  offset?: number
}

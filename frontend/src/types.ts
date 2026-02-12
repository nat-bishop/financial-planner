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
  is_disabled: boolean
}

export interface Transaction {
  id: number
  account_id: string
  external_id: string
  posted_at: number
  transacted_at: number | null
  amount: number
  description: string
  is_pending: boolean
  category: string
  categorize_confidence: number | null
  tags: string | null
  notes: string | null
  raw_data: string | null
  created_at: number
  updated_at: number | null
}

export interface TransactionUpdate {
  category?: string | null
  tags?: string | null
  notes?: string | null
}

export interface TransactionListResponse {
  transactions: Transaction[]
  total_count: number
  total_income: number
  total_expenses: number
}

export interface TransactionIdsResponse {
  ids: number[]
}

export interface SyncLog {
  id: number
  provider: string
  started_at: number
  completed_at: number | null
  status: string
  accounts_synced: number
  transactions_added: number
  transactions_updated: number
  error_message: string | null
  two_fa_status: string | null
  two_fa_method: string | null
}

export interface SyncTriggerResponse {
  sync_ids: number[]
  message: string
}

export interface ProviderSyncStatus {
  provider: string
  display_name: string
  status: string
  started_at: number | null
  completed_at: number | null
  error_message: string | null
  two_fa_sync_id: number | null
  two_fa_method: string | null
  two_fa_prompt: string | null
}

export interface TwoFASubmitResponse {
  status: string
  attempts: number
}

export interface SyncStatusResponse {
  providers: ProviderSyncStatus[]
  any_running: boolean
}

export interface ProviderStatus {
  provider: string
  display_name: string
  connected: boolean
  last_sync_at: number | null
  last_sync_status: string | null
}

export interface IncomeSource {
  name: string
  monthly_amount: number
}

export interface ProjectionPoint {
  year: number
  balance: number
  contributions: number
}

export interface ProjectionBand {
  label: string
  annual_return: number
  points: ProjectionPoint[]
}

export interface IncomeProjectionResponse {
  monthly_income: number
  monthly_expenses: number
  monthly_contribution: number
  income_sources: IncomeSource[]
  bands: ProjectionBand[]
  time_horizon_years: number
  is_configured: boolean
}

export interface RecurringBill {
  description: string
  raw_description: string
  account_id: string
  account_name: string
  frequency: string
  median_amount: number
  last_occurrence: number
  predicted_next: number
  occurrence_count: number
  confidence: number
}

export interface RecurringBillsResponse {
  bills: RecurringBill[]
  lookback_months: number
}

export interface MonthlyBucket {
  month: string
  month_start: number
  income: number
  expenses: number
  net: number
  transaction_count: number
}

export interface MonthlyTrendResponse {
  months: MonthlyBucket[]
}

export interface SpendingCategory {
  category: string | null
  total: number
  count: number
  exclude_from_totals: boolean
}

export interface SpendingByCategoryResponse {
  start_date: number
  end_date: number
  categories: SpendingCategory[]
}

export interface HealthResponse {
  status: string
  has_credentials: boolean
  providers: ProviderStatus[]
  last_sync_at: number | null
  last_sync_status: string | null
  account_count: number
  recent_errors: { at: number; message: string | null }[]
  warnings: string[]
}

export interface TransactionFilters {
  account_id?: string
  category?: string
  search?: string
  start_date?: number
  end_date?: number
  sort_by?: 'date' | 'description' | 'category' | 'amount' | 'account'
  sort_order?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

export interface Category {
  id: number
  name: string
  description: string | null
  is_default: boolean
  exclude_from_totals: boolean
  created_at: number
}

export interface LLMStatus {
  configured: boolean
  model: string
}

export interface CategorizeResult {
  transaction_id: number
  description: string
  category: string
  suggested_category: string
  confidence: number
  reasoning: string
  applied: boolean
}

export interface CategorizeResponse {
  total_processed: number
  categorized: number
  unable_to_categorize: number
  memory_matched: number
  results: CategorizeResult[]
  error: string | null
}

// Mirrors the Pydantic response schemas in app/db/schemas.py.
// Money arrives as strings ("33.34") so no precision is lost in transit.

export type OrderStatus = "active" | "completed" | "cancelled"
export type InstallmentStatus = "pending" | "paid" | "overdue" | "cancelled"
export type RiskLevel = "LOW" | "MEDIUM" | "HIGH"
export type Recommendation = "APPROVE" | "REVIEW" | "DENY"

export interface User {
  user_id: string
  email: string
  full_name: string
  created_at: string
}

export interface Merchant {
  merchant_id: string
  name: string
  category: string
  commission_rate: string
}

export interface Installment {
  installment_id: string
  order_id: string
  due_date: string
  amount: string
  status: InstallmentStatus
  paid_at: string | null
}

export interface OrderListItem {
  order_id: string
  user_id: string
  merchant_id: string
  total_amount: string
  num_installments: number
  status: OrderStatus
  created_at: string
  installments: Installment[]
  user: User
  merchant: Merchant
}

export interface OrderPage {
  items: OrderListItem[]
  total: number
  limit: number
  offset: number
}

export interface RevenueTotals {
  orders: number
  gmv: string
  revenue: string
  collected: string
}

export interface RevenueMonth extends RevenueTotals {
  month: string
}

export interface RevenueReport {
  start: string
  end: string
  totals: RevenueTotals
  by_month: RevenueMonth[]
}

export interface DashboardSummary {
  as_of: string
  active_orders: number
  total_revenue: string
  overdue_installments: number
  on_time_payment_rate: number | null
}

export interface RiskFeatures {
  total_orders: number
  on_time_payments: number
  late_payments: number
  active_installments: number
  requested_amount: string
  avg_order_amount: string
}

export interface RiskAssessment {
  order_id: string
  score: number
  risk_level: RiskLevel
  recommendation: Recommendation
  reasoning: string
  source: "llm" | "rules"
  llm_model: string | null
  features: RiskFeatures
}

import type {
  DashboardSummary,
  OrderPage,
  OrderStatus,
  RevenueReport,
  RiskAssessment,
} from "@/lib/types"

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1"

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type ValidationIssue = { loc: (string | number)[]; msg: string }

// FastAPI sends two error shapes: our domain errors ({"detail": "text"})
// and Pydantic validation errors ({"detail": [{loc, msg, ...}]}).
function errorMessage(body: unknown): string | null {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[])
      .map((issue) => `${issue.loc.slice(1).join(".")}: ${issue.msg}`)
      .join("; ")
  }
  return null
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, init)
  } catch {
    throw new ApiError(0, `Can't reach the API at ${API_URL}. Is the backend running?`)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(response.status, errorMessage(body) ?? `Request failed (${response.status})`)
  }
  return (await response.json()) as T
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ""
}

export const api = {
  summary: () => request<DashboardSummary>("/analytics/summary"),

  revenue: (start?: string, end?: string) =>
    request<RevenueReport>(`/analytics/revenue${query({ start, end })}`),

  orders: (params: { status?: OrderStatus; limit: number; offset: number }) =>
    request<OrderPage>(`/orders/${query(params)}`),

  assessRisk: (orderId: string) =>
    request<RiskAssessment>(`/orders/${encodeURIComponent(orderId)}/risk`, { method: "POST" }),
}

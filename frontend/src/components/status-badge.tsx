import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type {
  InstallmentStatus,
  OrderStatus,
  Recommendation,
  RiskLevel,
} from "@/lib/types"

// Status colors: pending=yellow, paid=green, overdue=red, active=blue
const TONES = {
  yellow:
    "border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-300",
  green:
    "border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  red: "border-red-500/30 bg-red-500/15 text-red-700 dark:text-red-300",
  blue: "border-sky-500/30 bg-sky-500/15 text-sky-700 dark:text-sky-300",
  gray: "border-border bg-muted text-muted-foreground",
} as const

type Tone = keyof typeof TONES

const STATUS_TONE: Record<OrderStatus | InstallmentStatus, Tone> = {
  pending: "yellow",
  paid: "green",
  overdue: "red",
  active: "blue",
  completed: "green",
  cancelled: "gray",
}

const RISK_TONE: Record<RiskLevel | Recommendation, Tone> = {
  LOW: "green",
  MEDIUM: "yellow",
  HIGH: "red",
  APPROVE: "green",
  REVIEW: "yellow",
  DENY: "red",
}

function ToneBadge({
  tone,
  children,
}: {
  tone: Tone
  children: React.ReactNode
}) {
  return (
    <Badge variant="outline" className={cn("capitalize", TONES[tone])}>
      {children}
    </Badge>
  )
}

export function StatusBadge({
  status,
}: {
  status: OrderStatus | InstallmentStatus
}) {
  return <ToneBadge tone={STATUS_TONE[status]}>{status}</ToneBadge>
}

export function RiskBadge({ value }: { value: RiskLevel | Recommendation }) {
  return <ToneBadge tone={RISK_TONE[value]}>{value.toLowerCase()}</ToneBadge>
}

// Risk score colors: green < 40, yellow 40–70, red > 70
export function scoreTone(score: number): string {
  if (score < 40) return "text-emerald-600 dark:text-emerald-400"
  if (score <= 70) return "text-amber-600 dark:text-amber-400"
  return "text-red-600 dark:text-red-400"
}

export function scoreBarColor(score: number): string {
  if (score < 40) return "bg-emerald-500"
  if (score <= 70) return "bg-amber-500"
  return "bg-red-500"
}

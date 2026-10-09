import { useMutation } from "@tanstack/react-query"
import { Bot, Loader2, ScrollText } from "lucide-react"
import { useState } from "react"
import { useSearchParams } from "react-router"

import { ErrorAlert, PageHeader } from "@/components/query-state"
import { RiskBadge, scoreBarColor, scoreTone } from "@/components/status-badge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { api } from "@/lib/api"
import { formatMoney } from "@/lib/format"
import type { RiskAssessment } from "@/lib/types"
import { cn } from "@/lib/utils"

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function RiskResult({ result }: { result: RiskAssessment }) {
  const f = result.features
  const features: [string, string][] = [
    ["Previous orders", String(f.total_orders)],
    ["Paid on time", String(f.on_time_payments)],
    ["Late or overdue", String(f.late_payments)],
    ["Active installments", String(f.active_installments)],
    ["Requested amount", formatMoney(f.requested_amount)],
    ["Average order", formatMoney(f.avg_order_amount)],
  ]

  return (
    <Card>
      <CardHeader>
        <CardDescription className="font-mono text-xs">
          Order {result.order_id}
        </CardDescription>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p
              className={cn(
                "text-6xl font-semibold tabular-nums",
                scoreTone(result.score)
              )}
            >
              {result.score}
            </p>
            <p className="text-sm text-muted-foreground">
              risk score · 0 = lowest, 100 = highest
            </p>
          </div>
          <div className="flex gap-2">
            <RiskBadge value={result.risk_level} />
            <RiskBadge value={result.recommendation} />
          </div>
        </div>
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-muted"
          role="presentation"
        >
          <div
            className={cn("h-full rounded-full", scoreBarColor(result.score))}
            style={{ width: `${result.score}%` }}
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium">
            {result.source === "llm" ? (
              <Bot className="size-4" />
            ) : (
              <ScrollText className="size-4" />
            )}
            Reasoning
            <Badge variant="secondary">
              {result.source === "llm"
                ? `AI · ${result.llm_model}`
                : "Rules fallback (AI unavailable)"}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">{result.reasoning}</p>
        </div>
        <Separator />
        <div>
          <p className="mb-2 text-sm font-medium">What the score is based on</p>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
            {features.map(([label, value]) => (
              <div key={label}>
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="font-mono tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-xs text-muted-foreground">
            Only these aggregated numbers are sent to the model — never names or
            emails. Level and recommendation come from fixed thresholds in code,
            and late payments always require a review.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}

export function RiskPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [orderId, setOrderId] = useState(searchParams.get("order") ?? "")
  const assess = useMutation({ mutationFn: api.assessRisk })
  const trimmed = orderId.trim()
  const looksValid = UUID_PATTERN.test(trimmed)

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!looksValid) return
    setSearchParams({ order: trimmed }, { replace: true })
    assess.mutate(trimmed)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Risk Check"
        description="Score the chance that a customer misses payments, using an LLM with a rule-based fallback."
      />

      <Card>
        <CardHeader>
          <CardTitle>Analyze an order</CardTitle>
          <CardDescription>
            Paste an order ID, or use the Check button on the Orders page.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
            <div className="min-w-0 flex-1 space-y-2">
              <Label htmlFor="order-id">Order ID</Label>
              <Input
                id="order-id"
                value={orderId}
                onChange={(e) => setOrderId(e.target.value)}
                placeholder="e.g. d0b8fd7f-cfc2-4165-8e20-0e30b297e148"
                className="font-mono"
                aria-invalid={trimmed !== "" && !looksValid}
                autoComplete="off"
              />
            </div>
            <Button type="submit" disabled={!looksValid || assess.isPending}>
              {assess.isPending && <Loader2 className="animate-spin" />}
              Analyze
            </Button>
          </form>
          {trimmed !== "" && !looksValid && (
            <p className="mt-2 text-xs text-destructive">
              That doesn't look like an order ID (a UUID).
            </p>
          )}
        </CardContent>
      </Card>

      {assess.isError && (
        <ErrorAlert error={assess.error} title="Couldn't score this order" />
      )}
      {assess.data && <RiskResult result={assess.data} />}
    </div>
  )
}

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"

import {
  type ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import { formatMoney, formatMonth } from "@/lib/format"
import type { RevenueMonth } from "@/lib/types"

export type RevenueMetric = "revenue" | "gmv" | "collected"

export const METRICS: Record<RevenueMetric, { label: string; color: string }> = {
  revenue: { label: "Revenue (commissions)", color: "oklch(0.696 0.17 162.48)" },
  gmv: { label: "GMV (sales volume)", color: "oklch(0.623 0.214 259.815)" },
  collected: { label: "Collected (payments)", color: "oklch(0.606 0.25 292.717)" },
}

export function RevenueChart({
  data,
  metric = "revenue",
  className,
}: {
  data: RevenueMonth[]
  metric?: RevenueMetric
  className?: string
}) {
  const config = { [metric]: METRICS[metric] } satisfies ChartConfig
  // Recharts needs numbers; values are only plotted, never added up here
  const points = data.map((m) => ({ month: m.month, [metric]: Number(m[metric]) }))

  return (
    <ChartContainer config={config} className={className}>
      <BarChart data={points} margin={{ left: 8, right: 8 }}>
        <CartesianGrid vertical={false} />
        <XAxis
          dataKey="month"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          tickFormatter={(month: string) => formatMonth(month).split(" ")[0]}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={64}
          tickFormatter={(value: number) => formatMoney(value).replace(/\.00$/, "")}
        />
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              labelFormatter={(_, payload) => formatMonth(String(payload?.[0]?.payload?.month ?? ""))}
              formatter={(value) => (
                <div className="flex w-full items-center justify-between gap-4">
                  <span className="text-muted-foreground">{METRICS[metric].label}</span>
                  <span className="font-mono font-medium tabular-nums">{formatMoney(Number(value))}</span>
                </div>
              )}
            />
          }
        />
        <Bar dataKey={metric} fill={`var(--color-${metric})`} radius={4} />
      </BarChart>
    </ChartContainer>
  )
}

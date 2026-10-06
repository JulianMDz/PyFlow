import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorAlert, PageHeader } from "@/components/query-state"
import { METRICS, RevenueChart, type RevenueMetric } from "@/components/revenue-chart"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { formatMoney } from "@/lib/format"

export function AnalyticsPage() {
  // Empty strings mean "let the API choose" (last 12 months, ending today in UTC)
  const [range, setRange] = useState({ start: "", end: "" })
  const [metric, setMetric] = useState<RevenueMetric>("revenue")
  const invalidRange = !!range.start && !!range.end && range.start > range.end

  const report = useQuery({
    queryKey: ["revenue", range.start, range.end],
    queryFn: () => api.revenue(range.start || undefined, range.end || undefined),
    enabled: !invalidRange,
    placeholderData: keepPreviousData,
  })
  const data = report.data

  // Editing one date keeps the other one the API is currently showing
  const updateRange = (field: "start" | "end", value: string) =>
    setRange({ start: range.start || data?.start || "", end: range.end || data?.end || "", [field]: value })

  return (
    <div className="space-y-6">
      <PageHeader title="Analytics" description="GMV, commission revenue and collected payments by month (UTC)" />

      <Card>
        <CardContent className="flex flex-wrap items-end gap-4">
          <div className="space-y-2">
            <Label htmlFor="start">From</Label>
            <Input
              id="start"
              type="date"
              value={range.start || data?.start || ""}
              onChange={(e) => updateRange("start", e.target.value)}
              className="w-44"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="end">To</Label>
            <Input
              id="end"
              type="date"
              value={range.end || data?.end || ""}
              onChange={(e) => updateRange("end", e.target.value)}
              className="w-44"
            />
          </div>
          <div className="space-y-2">
            <Label>Chart metric</Label>
            <Select value={metric} onValueChange={(value) => setMetric(value as RevenueMetric)}>
              <SelectTrigger className="w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(METRICS) as RevenueMetric[]).map((key) => (
                  <SelectItem key={key} value={key}>
                    {METRICS[key].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {invalidRange && <ErrorAlert error={new Error("'From' must be on or before 'To'.")} title="Invalid range" />}
      {report.isError && <ErrorAlert error={report.error} title="Couldn't load the report" />}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {(
          [
            ["Orders", data?.totals.orders.toString()],
            ["GMV", data && formatMoney(data.totals.gmv)],
            ["Revenue", data && formatMoney(data.totals.revenue)],
            ["Collected", data && formatMoney(data.totals.collected)],
          ] as const
        ).map(([title, value]) => (
          <Card key={title}>
            <CardHeader>
              <CardDescription>{title}</CardDescription>
              <CardTitle className="text-2xl tabular-nums">{value ?? <Skeleton className="h-8 w-24" />}</CardTitle>
            </CardHeader>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{METRICS[metric].label} by month</CardTitle>
          <CardDescription>
            Orders count in the month they were created; payments in the month they were processed.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {data ? (
            <RevenueChart data={data.by_month} metric={metric} className="h-80 w-full" />
          ) : (
            <Skeleton className="h-80 w-full" />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

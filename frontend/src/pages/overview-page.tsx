import { useQuery } from "@tanstack/react-query"
import {
  CircleDollarSign,
  Clock,
  ShoppingBag,
  TriangleAlert,
} from "lucide-react"

import { ErrorAlert, PageHeader } from "@/components/query-state"
import { RevenueChart } from "@/components/revenue-chart"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import { formatDate, formatMoney, formatPercent } from "@/lib/format"
import { cn } from "@/lib/utils"

function MetricCard({
  title,
  value,
  hint,
  icon: Icon,
  alert = false,
}: {
  title: string
  value: string | undefined
  hint: string
  icon: React.ComponentType<{ className?: string }>
  alert?: boolean
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardDescription>{title}</CardDescription>
        <Icon
          className={cn(
            "size-4 text-muted-foreground",
            alert && "text-red-500"
          )}
        />
      </CardHeader>
      <CardContent className="space-y-1">
        {value === undefined ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <p
            className={cn(
              "text-3xl font-semibold tabular-nums",
              alert && "text-red-600 dark:text-red-400"
            )}
          >
            {value}
          </p>
        )}
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  )
}

export function OverviewPage() {
  const summary = useQuery({ queryKey: ["summary"], queryFn: api.summary })
  const revenue = useQuery({
    queryKey: ["revenue", "", ""],
    queryFn: () => api.revenue(),
  })
  const s = summary.data

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description={
          s
            ? `Platform health as of ${formatDate(s.as_of)} (UTC)`
            : "Platform health at a glance"
        }
      />

      {summary.isError && (
        <ErrorAlert error={summary.error} title="Couldn't load the summary" />
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          title="Active orders"
          value={s?.active_orders.toString()}
          hint="Orders still being paid"
          icon={ShoppingBag}
        />
        <MetricCard
          title="Total revenue"
          value={s && formatMoney(s.total_revenue)}
          hint="Merchant commissions, all time"
          icon={CircleDollarSign}
        />
        <MetricCard
          title="Overdue installments"
          value={s?.overdue_installments.toString()}
          hint="Unpaid and past their due date"
          icon={TriangleAlert}
          alert={!!s && s.overdue_installments > 0}
        />
        <MetricCard
          title="On-time payment rate"
          value={s && formatPercent(s.on_time_payment_rate)}
          hint="Paid on time ÷ installments already due"
          icon={Clock}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Revenue, last 12 months</CardTitle>
          <CardDescription>
            Merchant commissions on non-cancelled orders, by month created
          </CardDescription>
        </CardHeader>
        <CardContent>
          {revenue.isError ? (
            <ErrorAlert error={revenue.error} title="Couldn't load revenue" />
          ) : revenue.data ? (
            <RevenueChart
              data={revenue.data.by_month}
              className="h-72 w-full"
            />
          ) : (
            <Skeleton className="h-72 w-full" />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

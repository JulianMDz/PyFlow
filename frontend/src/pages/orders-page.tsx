import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { ChevronDown, ChevronRight, ShieldCheck } from "lucide-react"
import { Fragment, useState } from "react"
import { useNavigate } from "react-router"

import { ErrorAlert, PageHeader } from "@/components/query-state"
import { StatusBadge } from "@/components/status-badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api } from "@/lib/api"
import { formatDate, formatDateTime, formatMoney, shortId } from "@/lib/format"
import type { OrderListItem, OrderStatus } from "@/lib/types"

const PAGE_SIZE = 20
const ALL = "all"

function InstallmentsDetail({ order }: { order: OrderListItem }) {
  return (
    <div className="space-y-2 px-4 py-3">
      <p className="text-xs text-muted-foreground">
        {order.merchant.name} · {order.user.full_name} ({order.user.email}) ·
        order {order.order_id}
      </p>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>#</TableHead>
            <TableHead>Due date</TableHead>
            <TableHead className="text-right">Amount</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Paid at</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {order.installments.map((inst, index) => (
            <TableRow key={inst.installment_id}>
              <TableCell className="text-muted-foreground">
                {index + 1}
              </TableCell>
              <TableCell>{formatDate(inst.due_date)}</TableCell>
              <TableCell className="text-right font-mono tabular-nums">
                {formatMoney(inst.amount)}
              </TableCell>
              <TableCell>
                <StatusBadge status={inst.status} />
              </TableCell>
              <TableCell className="text-muted-foreground">
                {inst.paid_at ? formatDateTime(inst.paid_at) : "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

export function OrdersPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<OrderStatus | typeof ALL>(ALL)
  const [offset, setOffset] = useState(0)
  const [expanded, setExpanded] = useState<string | null>(null)

  const orders = useQuery({
    queryKey: ["orders", status, offset],
    queryFn: () =>
      api.orders({
        status: status === ALL ? undefined : status,
        limit: PAGE_SIZE,
        offset,
      }),
    placeholderData: keepPreviousData,
  })
  const page = orders.data
  const toggle = (orderId: string) =>
    setExpanded((current) => (current === orderId ? null : orderId))

  return (
    <div className="space-y-6">
      <PageHeader
        title="Orders"
        description="Every purchase split into installments. Click a row to see its schedule."
      />

      <div className="flex flex-wrap items-center justify-between gap-4">
        <Select
          value={status}
          onValueChange={(value) => {
            setStatus(value as OrderStatus | typeof ALL)
            setOffset(0)
            setExpanded(null)
          }}
        >
          <SelectTrigger className="w-44" aria-label="Filter by status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
          </SelectContent>
        </Select>
        {page && (
          <p className="text-sm text-muted-foreground">
            {page.total === 0
              ? "No orders"
              : `Showing ${offset + 1}–${offset + page.items.length} of ${page.total}`}
          </p>
        )}
      </div>

      {orders.isError && (
        <ErrorAlert error={orders.error} title="Couldn't load orders" />
      )}

      <Card className="py-0">
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8" />
                <TableHead>Order</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead>Merchant</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead>Paid</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Risk</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {!page &&
                !orders.isError &&
                Array.from({ length: 5 }, (_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={9}>
                      <Skeleton className="h-6 w-full" />
                    </TableCell>
                  </TableRow>
                ))}
              {page?.items.map((order) => {
                const paid = order.installments.filter(
                  (i) => i.status === "paid"
                ).length
                const isOpen = expanded === order.order_id
                return (
                  <Fragment key={order.order_id}>
                    <TableRow
                      className="cursor-pointer"
                      onClick={() => toggle(order.order_id)}
                    >
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          aria-expanded={isOpen}
                          aria-label={
                            isOpen ? "Hide installments" : "Show installments"
                          }
                          onClick={(e) => {
                            e.stopPropagation()
                            toggle(order.order_id)
                          }}
                        >
                          {isOpen ? <ChevronDown /> : <ChevronRight />}
                        </Button>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {shortId(order.order_id)}
                      </TableCell>
                      <TableCell className="max-w-56 truncate">
                        {order.user.email}
                      </TableCell>
                      <TableCell>{order.merchant.name}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">
                        {formatMoney(order.total_amount)}
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {paid}/{order.installments.length}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={order.status} />
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDate(order.created_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="outline"
                          size="xs"
                          onClick={(e) => {
                            e.stopPropagation()
                            navigate(`/risk?order=${order.order_id}`)
                          }}
                        >
                          <ShieldCheck /> Check
                        </Button>
                      </TableCell>
                    </TableRow>
                    {isOpen && (
                      <TableRow className="bg-muted/40 hover:bg-muted/40">
                        <TableCell colSpan={9} className="p-0">
                          <InstallmentsDetail order={order} />
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                )
              })}
              {page?.items.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={9}
                    className="py-10 text-center text-muted-foreground"
                  >
                    No orders match this filter.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          disabled={offset === 0 || orders.isFetching}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          disabled={
            !page || offset + PAGE_SIZE >= page.total || orders.isFetching
          }
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          Next
        </Button>
      </div>
    </div>
  )
}

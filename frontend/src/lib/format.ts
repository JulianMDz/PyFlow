const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" })

// Display only: the API sends exact decimal strings, and any arithmetic on
// money happens on the server. Number() here is just for formatting.
export function formatMoney(value: string | number): string {
  return usd.format(Number(value))
}

export function formatPercent(rate: number | null): string {
  return rate === null ? "—" : `${(rate * 100).toFixed(1)}%`
}

// "2026-10-08" is a calendar date in UTC. Parsing it with the local time zone
// would show Oct 7 for anyone west of UTC, so format it in UTC too.
export function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-US", {
    timeZone: "UTC",
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

export function formatDateTime(isoDateTime: string): string {
  return new Date(isoDateTime).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

// "2026-10" → "Oct 2026"
export function formatMonth(month: string): string {
  return new Date(`${month}-01`).toLocaleDateString("en-US", {
    timeZone: "UTC",
    month: "short",
    year: "numeric",
  })
}

export function shortId(id: string): string {
  return id.slice(0, 8)
}

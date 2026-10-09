import {
  BarChart3,
  LayoutDashboard,
  Moon,
  ReceiptText,
  ShieldCheck,
  Sun,
} from "lucide-react"
import { NavLink, Route, Routes } from "react-router"

import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { AnalyticsPage } from "@/pages/analytics-page"
import { OrdersPage } from "@/pages/orders-page"
import { OverviewPage } from "@/pages/overview-page"
import { RiskPage } from "@/pages/risk-page"

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/orders", label: "Orders", icon: ReceiptText },
  { to: "/risk", label: "Risk Check", icon: ShieldCheck },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
]

function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const isDark = theme !== "light"
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {isDark ? <Sun /> : <Moon />}
    </Button>
  )
}

function NotFound() {
  return <p className="text-muted-foreground">Page not found.</p>
}

export function App() {
  return (
    <div className="min-h-svh">
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
          <span className="font-semibold tracking-tight">
            Pay<span className="text-emerald-500">Flow</span>
          </span>
          <nav className="flex flex-1 items-center gap-1 overflow-x-auto">
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                aria-label={label}
                title={label}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm whitespace-nowrap text-muted-foreground transition-colors hover:text-foreground",
                    isActive && "bg-muted text-foreground"
                  )
                }
              >
                <Icon className="size-4" />
                {/* Icons only on phones, so all four sections fit without hidden scrolling */}
                <span className="hidden sm:inline">{label}</span>
              </NavLink>
            ))}
          </nav>
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/orders" element={<OrdersPage />} />
          <Route path="/risk" element={<RiskPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}

export default App

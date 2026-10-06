# PayFlow Dashboard

React dashboard for the PayFlow BNPL API: platform metrics, orders with their installment schedules, AI risk scoring and revenue analytics.

| | |
| --- | --- |
| Framework | React 19 + TypeScript + Vite |
| UI | [shadcn/ui](https://ui.shadcn.com) (Radix + Tailwind CSS v4, "Nova" preset), dark mode by default |
| Charts | Recharts, through shadcn's `chart` component |
| Data | TanStack Query + native `fetch` |
| Routing | React Router |

## Run it

The API must be running first (from the repository root):

```bash
docker compose up -d          # API on http://localhost:8000
```

Then the dashboard:

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

The API URL defaults to `http://localhost:8000/api/v1`. To point somewhere else, copy `.env.example` to `.env` and change `VITE_API_URL`. Anything prefixed with `VITE_` is bundled into the JavaScript the browser downloads, so it must never contain secrets.

The API only accepts browser requests from the origins in its `CORS_ORIGINS` setting (`http://localhost:5173` and `http://127.0.0.1:5173` by default).

## Views

| Route | View | API |
| --- | --- | --- |
| `/` | Overview: 4 metric cards + revenue for the last 12 months | `GET /analytics/summary`, `GET /analytics/revenue` |
| `/orders` | Paginated orders, status filter, expandable installment schedule | `GET /orders/` |
| `/risk` | Risk score, level, recommendation, reasoning and the features behind it | `POST /orders/{id}/risk` |
| `/analytics` | GMV, revenue and collected payments by month, with a date range | `GET /analytics/revenue` |

## Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Dev server with hot reload |
| `npm run build` | Type-check and build to `dist/` |
| `npm run lint` | ESLint |
| `npm run format` | Prettier |

## Structure

```text
src/
├── main.tsx              providers: TanStack Query, router, theme
├── App.tsx               layout, navigation and routes
├── pages/                one file per view
├── components/           shared pieces (status badges, revenue chart, error alert, theme provider)
│   └── ui/               shadcn/ui components (generated, editable)
└── lib/
    ├── api.ts            typed fetch client; turns both FastAPI error shapes into readable messages
    ├── types.ts          mirrors the API's response schemas
    ├── format.ts         money, dates (in UTC) and IDs
    └── utils.ts          cn() helper for merging Tailwind classes (from shadcn)
```

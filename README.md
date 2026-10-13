# ProfitLeak AI

Financial analytics for small businesses in Taraz. React, FastAPI, and PostgreSQL
are the implemented stack. The backend currently provides database models and migrations,
a health endpoint, business profiles, CSV/XLSX import, a repeatable 90 day demo,
and financial analytics. The Russian React interface includes a dashboard, revenue
and expense charts, product profitability, file import, and business profiles.

## Local setup

Requires Python 3.11+ and Docker Desktop with Linux containers running. From the
repository root in PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up -d db
python -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -e './backend[dev]'
backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --reload
```

Open `http://localhost:8000/docs` for the API and `http://localhost:8000/api/v1/health`
for the database health check. The health endpoint returns HTTP 503 if PostgreSQL
is unavailable. Startup never creates database tables; run migrations explicitly.
Local database credentials in `.env.example` are for development.

In a second terminal, start the frontend (Node.js 22.18+ required):

```powershell
cd frontend
npm.cmd ci --offline=false
npm.cmd run dev
```

Open **http://127.0.0.1:5173**. Create a business under **Мой бизнес**, or click
**Открыть демо-бизнес** to load the Taraz cafe. An existing business is restored
from the browser's last selection. Dashboard and product pages support date filters;
the default covers 90 days ending at the latest confirmed data. CSV templates are
available on the import page. Preview and confirmation use the backend API.

Vite proxies `/api` to `http://127.0.0.1:8000`, so both servers must be running.
For a production static build, configure the hosting server to proxy `/api` to
FastAPI and return `index.html` for React routes. `vite preview` alone does not
provide this production API setup.

## Data models

| Model | Purpose |
| --- | --- |
| Business | Business profile, KZT currency, Asia/Almaty timezone |
| Product | Business scoped external product ID and product metadata |
| ImportBatch | File digest, import type/status, row count and confirmation timestamp |
| Sale | Product, business date, quantity, price/cost, import and source row |
| Expense | Category, description, amount, business date, import and source row |
| Insight | Rule type, severity, confidence, period, JSON evidence and scenario savings |

IDs are UUIDs; timestamps include timezone information. Money uses `NUMERIC(18,2)`
and Python `Decimal`; quantities use `NUMERIC(18,3)`. Missing unit cost remains null
so analytics can report insufficient data. Composite foreign keys prevent a sale
or expense from referencing another business's product or import.

File digest and normalized content uniqueness prevent the same data from being
imported again for the same business and type. Normalization ignores row order,
surrounding whitespace and decimal trailing zeroes, while retaining repeated rows.
Source row uniqueness prevents inserting an import row twice. Different rows with
identical expense values remain available to the future possible duplicate detector.
Partially overlapping files with different contents are separate imports.

Sales and expenses store positive magnitudes. `record_type=return` reverses a sale;
`record_type=refund` reverses an expense in the analytics service. Standard
CSV templates default to `sale` and `expense`. Discounts should be included in the
effective unit price for this schema. Returns use the price and cost from the
original transaction. Expense imports represent operating expenses; product costs
already represented by `unit_cost` belong in sales data.

## Import API

This local MVP accepts synthetic demonstration data. It has no authentication yet;
use it locally until account access controls are implemented.

1. Create a business with `POST /api/v1/businesses` and JSON
   `{"name":"Кафе Тараз","industry":"cafe"}`. Save the returned `id`.
2. Send `POST /api/v1/imports/preview` as multipart form data with `business_id`,
   `kind` (`sales`, `expenses`, or `products`), and `file`.
3. Preview returns the first 20 valid rows, row/column errors, `can_confirm`, and
   a token that expires after 15 minutes. Preview creates no database records.
4. If `can_confirm` is true, send the same form and file to
   `POST /api/v1/imports/confirm`, adding `preview_token`. All rows and product
   creation are committed in one transaction. Changed files, changed business/type,
   invalid signatures, and expired tokens are rejected.
5. Repeating confirmation with a valid token returns the existing import with
   `already_imported=true`. Preview of existing content returns `existing_import_id`
   without offering confirmation. `GET /api/v1/imports?business_id=<id>` lists history.

The interactive API at `/docs` supports this flow. Example CSV templates are in
`demo_data/`. CSV uses UTF-8 (BOM accepted), comma separators, and ISO `YYYY-MM-DD`
dates. XLSX must have one worksheet with the same headers; date cells are supported.
Formulas are rejected, including cells that have cached formula results.

Sales require `date,product_id,product_name,quantity,unit_price,unit_cost`; cost can
be blank. Expenses require `date,category,description,amount`; description can be
blank. Products require `product_id,name` and optionally `category`. Sales and
expenses accept the optional `record_type` column described above. Unknown or
duplicate headers are rejected. Products are created automatically from sales;
product imports update name/category for existing external IDs.

Limits: 10 MB per file, 20,000 rows, 32 columns, 50 MB expanded XLSX content, and
100 reported errors. `errors_truncated` indicates additional errors. Decimal values
are validated before storage; excessive precision, nonfinite and negative values
are rejected. Response amounts are decimal strings.

Set `IMPORT_SIGNING_KEY` to a random server secret before deployment and use the
same key across workers. The example key is for local demos. Preview tokens are
stateless and bound to file bytes, business, and type; confirmation reuploads the
file, so the server does not keep preview files.

## API contract

The current implemented contract is tracked in `shared/openapi.json`. After changing
endpoint schemas, regenerate it from FastAPI:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/export_openapi.py
backend/.venv/Scripts/python.exe backend/scripts/export_openapi.py --check
```

The contract covers business, import, demo, dashboard and analytics endpoints. It
will expand with insight endpoints next. The React client uses generated types in
`frontend/src/types/api.ts`. Regenerate those types after changing the contract:

```powershell
cd frontend
npm.cmd run generate:api
```

## Demo and analytics

Send `POST /api/v1/demo/load` with no request body. It creates a synthetic Taraz
cafe with 90 days of data from **2026-07-04 through 2026-10-01**, three products,
270 sales rows and 274 expense rows. The response includes its `business.id`.
Repeated loads use the same business and imports, report `already_loaded=true`,
and preserve row counts. All three imports and business creation are atomic.

Use that business ID with these GET endpoints:

| Endpoint | Result |
| --- | --- |
| `/api/v1/dashboard/summary` | Revenue, COGS, gross profit, gross margin, operating expenses/profit |
| `/api/v1/analytics/revenue` | Daily revenue points with sales row counts |
| `/api/v1/analytics/expenses` | Net expenses by category, including refunds |
| `/api/v1/analytics/products` | Product profitability, sorted by gross profit, with pagination |

Every analytics endpoint requires `business_id` and accepts inclusive `date_from`
and `date_to` filters. The maximum range is 366 days. Without dates, the range ends
on the latest confirmed sales/expense date and covers 90 days; an empty business
uses its local current date. If only `date_from` is provided, the range starts
there and covers 90 days; if only `date_to` is provided, it ends there and covers
90 days. Product results accept `limit` (1–100, default 50) and `offset`.

All calculations use confirmed imports. PostgreSQL stores exact `NUMERIC` values;
Python streams the records and calculates financial amounts with `Decimal`.
Each sale line's revenue and cost is rounded to two decimals
using half away from zero, then summed. Returns reverse those line amounts;
refunds reduce operating expenses. Gross margin is gross profit divided by net
revenue, rounded to two decimal places. No tax is inferred.

KPI fields use `{value, status, reason}`; values are decimal strings or null.
`status` is `available`, `insufficient_data`, or `not_applicable`. Missing unit
cost makes COGS, gross profit/margin and operating profit unavailable. No expense
records in the selected period makes operating expenses/profit unavailable. Zero
net revenue makes margin not applicable. Revenue points include every requested
day; days without records have null values. This does not establish complete
accounting coverage for days or categories omitted from uploaded files.

The demo seeds a packaging expense spike, coffee margin decline and possible
duplicate packaging payment for the upcoming detector. Expected results and
scenario calculations are in [demo data notes](demo_data/README.md).
Export the generated files for manual import:

```powershell
backend/.venv/Scripts/python.exe backend/scripts/generate_demo.py
```

## Verification

Frontend type checks, production bundle, and financial display precision checks:

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

The UI preserves exact decimal strings in cards, tables and tooltips. Numeric
conversion is limited to plotting. Days without records stay missing, and margin
or profit with incomplete costs remains unavailable. Desktop and 390px mobile
layouts, date filtering, daily revenue tables and navigation were checked in Chrome.
Automated browser file selection requires the Chrome extension's local file access;
that setting was disabled during verification, so upload UI automation was not
completed. The backend import flow is covered by the integration tests below.

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://profitleak:profitleak_local@127.0.0.1:55432/profitleak'
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
backend/.venv/Scripts/python.exe -m ruff check backend
backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini check
```

PostgreSQL integration tests create a unique schema inside a transaction and roll
back all test DDL and data; they do not alter the application's tables. Without
`TEST_DATABASE_URL`, those tests are skipped. Tests cover exact monetary values,
tenant references, invalid values, import duplication, savings labels, migration
consistency, migration reversal, hand calculated KPIs, returns/refunds, missing
data, date filters, pagination, and repeatable demo loading.

See [the development plan](DEVELOPMENT_PLAN.md) for the remaining implementation stages.

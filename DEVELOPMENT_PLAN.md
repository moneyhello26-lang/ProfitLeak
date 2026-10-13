# ProfitLeak AI development plan

## Starting point and objective

At the initial review, the repository contained only `README.md` and `ProfitLeak_AI_Requirements.docx`, with no application code, API contract, test suite, or deployment setup. Build a working Russian language MVP for a synthetic Taraz cafe: load 90 days of sales and expenses, display server calculated KPIs, and explain at least three detectable issues. Use React, FastAPI, and PostgreSQL. This plan replaces the requirements document's SQLite choice with PostgreSQL; the other MVP priorities remain.

## MVP scope

**P0:** CSV/XLSX preview and confirmed import; schema and value validation; duplicate import protection; date filtering; revenue, cost of goods, gross profit, gross margin, and operating profit; revenue and expense charts; product profitability; explainable expense spike, margin drop, low profit product, sales drop, and possible duplicate signals; evidence and recommendations; deterministic demo load; usable loading, empty, and error states. Recommendations must work without an LLM.

**Later:** advisor chat, PDF export, Kazakh localization, period comparison, and forecasting. Accounts and roles are required before real customer data is accepted or a public multi tenant deployment is offered. Until then, deployment is demo only with synthetic data.

## Implementation progress

The backend database foundation and CSV/XLSX import stage are implemented: six
SQLAlchemy models, Alembic migrations, PostgreSQL Compose configuration, health and
business endpoints, preview/confirm endpoints, row validation, transaction rollback,
and raw/normalized file deduplication. Deterministic 90 day cafe data and financial
analytics are implemented, including date filters, revenue trends, expense categories,
product profitability and explicit missing data states. The current implemented API
contract is exported to `shared/openapi.json`. All 89 tests passed against PostgreSQL;
financial results match independent fixtures and repeat demo loading preserves row
counts. See README for setup and verification.
The React interface is now implemented with a light teal workspace, Russian
navigation, backend KPI cards, revenue chart/table, expense chart, product
profitability and pagination, date filters, business creation, repeatable demo
loading, and CSV/XLSX preview/confirmation/history. API types are generated from
OpenAPI. Loading, empty, request error and missing-data states are included.
Desktop and 390px mobile layouts and date/table/navigation interactions were
checked in Chrome. Browser upload automation was blocked by the extension's local
file access setting; the backend import integration tests remain the verification
for that path. Next work is the rule based leak detector, insight screens and
evidence-based recommendations. The current UI does not claim to detect leaks yet.

## Architecture and repository

```text
frontend/                 React + TypeScript + Vite, custom CSS, React Router, Recharts
  src/App.tsx             Workspace, routes and current MVP screens
  src/styles.css          Responsive layout, components and typography
  src/{lib,types}/         API client, exact decimal display, generated contract
  public/templates/       Downloadable CSV examples
  tests/                  Financial display precision checks
backend/                  FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL
  app/{api,models,schemas,services,db,core}/
  tests/
shared/openapi.json       Versioned contract, generated from FastAPI and reviewed
demo_data/                Reproducible cafe generator and expected signal fixtures
docker-compose.yml        Local PostgreSQL and application services
.env.example              Nonsecret configuration
README.md                 Setup, commands, demo flow
```

Keep business calculations and detection in backend services. Store money as PostgreSQL `NUMERIC` and calculate with Python `Decimal`; serialize amounts as decimal strings in the API so the browser does not silently round them. Use UTC timestamps for records and business local dates for analysis. Every query and import is scoped to a business ID, even in the single demo business.

## Contract and data design first

1. Define request and response schemas and freeze `shared/openapi.json` before the frontend and backend branches diverge. Cover health, demo load, import preview/confirm, dashboard summary, revenue, expenses, products, analysis run, insight list/detail, and a reserved advisor endpoint. Specify date range semantics, pagination, error shape, and `insufficient_data` or `null` values.
2. Design `businesses`, `products`, `sales`, `expenses`, `imports`, and `insights`. Add an import row identity or file digest plus business/type uniqueness, and transactionally associate inserted rows with an import. Include source row number and source file where useful for evidence. Index business/date and business/product/date queries.
3. Use Alembic migrations from the first schema. Provide a local PostgreSQL container, connection settings, and a migration command. No schema creation as a production startup side effect.
4. Define explicit CSV/XLSX templates, including returns and adjustments. Reject negative values unless their row type permits them. Preview reports column, row, and value errors without writing records; confirm accepts a short lived preview token or file digest and prevents repeated inserts.

## Implementation sequence

| Stage | Backend owner | Frontend owner | Exit check |
| --- | --- | --- | --- |
| 0. Foundation, hours 0–6 | FastAPI skeleton, PostgreSQL Compose, migration, Pydantic schemas, OpenAPI | React skeleton, routes, shared client types, layout | Both apps boot; contract and sample payloads reviewed together |
| 1. Import and demo, hours 6–18 | CSV/XLSX parser, preview/confirm, duplicate guard, deterministic 90 day demo generator | Import page, preview table, error report, demo load action | Demo loads once; repeat load/import does not duplicate rows |
| 2. Analytics, hours 18–30 | Decimal KPI queries, product and trend endpoints, rule based detector with evidence | Dashboard KPI cards/charts, date filter, insight list/detail | UI shows backend values; three seeded issues are found |
| 3. Recommendations, hours 30–38 | Template recommendations; optional LLM explanation behind a feature flag and safe fallback | Show evidence, scenario savings label, recommendation states | With LLM disabled, complete demo still works |
| 4. Integration and delivery, hours 38–48 | Endpoint and calculation tests, migration check, seed verification | Responsive and accessibility pass, loading/error states, end to end demo | Fresh checkout follows README and acceptance script succeeds |

The two owners work in `feature/backend-ai` and `feature/frontend`, merging through reviewed pull requests. Freeze API examples before parallel work, and update OpenAPI, frontend types, and backend tests together when an endpoint changes. Run the full import → analysis → dashboard → insight path at least daily.

## Calculation and detection rules

- Revenue is `sum(quantity × unit_price)` after explicitly represented discounts and returns. Cost of goods is `sum(quantity × unit_cost)`. Gross profit is revenue minus cost of goods; operating profit subtracts operating expenses. Gross margin is unavailable when revenue is zero.
- Compare equal length periods and document minimum sample thresholds. For sparse data, return `insufficient_data` instead of a forced signal. Start with transparent rules; consider IsolationForest only after enough observations exist and keep its score separate from any claimed loss probability.
- Each signal includes type, severity, current value, comparable baseline, deviation when defined, evidence references, recommendation, and a scenario savings estimate or `null`. A duplicate is a candidate for human review; an anomaly is never presented as proven loss.
- Seed the cafe with known packaging cost growth, a product margin decline, and one possible duplicate expense. Record expected figures and signal IDs in fixtures for independent tests.

## Quality, security, and release gates

- Unit tests compare KPI results against hand calculated fixtures and cover zero revenue, missing unit cost, returns, invalid dates/numbers, and small samples. Import integration tests verify idempotency and transaction rollback. API tests verify date filters and evidence payloads.
- Limit uploads to 10 MB; validate extension, MIME/content, UTF-8 CSV and XLSX structure; read spreadsheet values without executing formulas. Set parser row limits and clear error messages. Keep secrets in server environment variables and `.env` out of Git.
- Send only aggregate, confirmed facts to an optional LLM. The model may explain or phrase recommendations; it must not calculate or invent financial amounts. Never send personal or banking data without consent. Set timeouts and return template text when the provider fails.
- For a demo deployment, use synthetic data only. Before onboarding real businesses, add authentication, authorization on every business scoped endpoint, tenant isolation tests, backup/restore, retention rules, and operational monitoring.

## MVP acceptance demonstration

From a clean checkout, start PostgreSQL and both apps, run migrations, and open the Russian UI. Load the Taraz cafe demo data twice and confirm the second attempt changes no row counts. Show 90 days of revenue, expenses, and profit; run analysis; inspect the packaging spike, margin decline, and possible duplicate with their source evidence. Upload one malformed file and show row level validation. Disable the LLM setting and repeat the insight flow. Confirm scenario savings is marked as an estimate and KPI values match the independent fixture calculations.

## Decisions to settle during stage 0

- Define return/discount columns and whether expenses can contain tax; the supplied file examples do not define these semantics.
- Choose exact thresholds and baseline windows for each detector, then encode them in fixtures.
- Choose demo hosting only after the local path works; the current requirements do not specify a deployment target.

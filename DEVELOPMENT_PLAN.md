# ProfitLeak AI development plan

## Starting point and objective

The repository currently contains only `README.md` and `ProfitLeak_AI_Requirements.docx`; there is no application code, API contract, test suite, or deployment setup. Build a working Russian language MVP for a synthetic Taraz cafe: load 90 days of sales and expenses, display server calculated KPIs, and explain at least three detectable issues. Use React, FastAPI, and PostgreSQL. This plan replaces the requirements document's SQLite choice with PostgreSQL; the other MVP priorities remain.

## MVP scope

**P0:** CSV/XLSX preview and confirmed import; schema and value validation; duplicate import protection; date filtering; revenue, cost of goods, gross profit, gross margin, and operating profit; revenue and expense charts; product profitability; explainable expense spike, margin drop, low profit product, sales drop, and possible duplicate signals; evidence and recommendations; deterministic demo load; usable loading, empty, and error states. Recommendations must work without an LLM.

**Later:** advisor chat, PDF export, Kazakh localization, period comparison, and forecasting. Accounts and roles are required before real customer data is accepted or a public multi tenant deployment is offered. Until then, deployment is demo only with synthetic data.

## Implementation progress

The backend database foundation is implemented: six SQLAlchemy models, an Alembic
migration, PostgreSQL Compose configuration, and a FastAPI database health endpoint.
The initial migration has been applied locally and checked for schema drift. Nineteen
tests passed against PostgreSQL, including decimal arithmetic, import uniqueness,
references across businesses, invalid values, and migration reversal. See README for
setup and verification. The next work is API request/response contracts, frontend
scaffolding, and the CSV/XLSX import flow.

## Architecture and repository

```text
frontend/                 React + TypeScript + Vite, Tailwind, React Router, Recharts
  src/{components,pages,services,types}/
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

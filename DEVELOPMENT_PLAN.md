# ProfitLeak AI development plan

> Current release plan (2026-10-16): see
> [release and handoff for October 17](docs/RELEASE_PLAN_2026-10-17.md).
> The historical stages below predate the implemented accounts, Kazakh
> localization, period comparison and forecasts; they are not outstanding features.

## Starting point and objective

At the initial review, the repository contained only `README.md` and `ProfitLeak_AI_Requirements.docx`, with no application code, API contract, test suite, or deployment setup. Build a working Russian language MVP for a synthetic Taraz cafe: load 90 days of sales and expenses, display server calculated KPIs, and explain at least three detectable issues. React and FastAPI are implemented. The initial database choice was PostgreSQL; on 2026-10-13 the user requested operation without Docker, so SQLite became the default, matching the source requirements. PostgreSQL remains optional.

## MVP scope

**P0:** CSV/XLSX preview and confirmed import; schema and value validation; duplicate import protection; date filtering; revenue, cost of goods, gross profit, gross margin, and operating profit; revenue and expense charts; product profitability; explainable expense spike, margin drop, low profit product, sales drop, and possible duplicate signals; evidence and recommendations; deterministic demo load; usable loading, empty, and error states. Recommendations must work without an LLM.

**Implemented continuation:** advisor chat and PDF export. **Later:** Kazakh localization, period comparison, and forecasting. Accounts and roles are required before real customer data is accepted or a public multi tenant deployment is offered. Until then, deployment is demo only with synthetic data.

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
for that path. The next stage now implements five detectors, persisted analysis and evidence,
template recommendations, insight filters/details and recent dashboard findings.
SQLite migrations and isolated database tests run without Docker. `start.ps1`
applies migrations and starts both servers.

## Current continuation

Implemented FR-05, FR-07 and the offline recommendation path of FR-08 as one complete
stage: five Decimal rules, persisted analysis status and insights, source evidence,
`POST /analysis/run`, `GET /insights`, `GET /insights/{id}`, a detector page with
severity/type filters and details, and recent signals on the dashboard. Sync OpenAPI
and TypeScript types, then validate the three independent demo scenarios, sparse
data, missing costs, returns/refunds, repeat analysis, tenant scoping and stale data.
Use SQLite by default and keep the existing visual style. The following stage implements
the LLM provider, advisor chat and PDF; remaining P1/P2 features stay separate,
as requested by section 16 of the DOCX.

## Architecture and repository

### Advisor and PDF continuation, 2026-10-14

FR-08 provider integration, FR-11 and FR-12 are implemented. OpenAI Responses API
uses strict structured output, verified backend fact placeholders, a bounded
stateless history, explicit external-send consent and template fallback on API or
validation failures. No raw source rows are sent; no model-derived amounts are
accepted. Read transactions end before external API waits so chat does not hold
a SQLite write lock. Insight details can request a focused explanation.
Local ReportLab PDF export includes exact KPIs, products, expenses, evidence,
recommendations and explicit missing/stale analysis state; the Cyrillic font is
bundled with its license. OpenAPI/types and the setup guide are synchronized.
Real provider verification requires the user's API key. Remaining stages are
Kazakh localization, general period comparison, forecasts and accounts/roles.

### Quota economy, 2026-10-15

Gemini 3.5 Flash-Lite is selected for free-tier operation; OpenAI nano remains
a manually configured alternative. Keys are separated by provider and outbound
consent is tied to the selected provider. Response budget is 600 tokens, history
defaults to four messages capped at 1200 characters each, and context includes
up to three insights. Validated responses are cached in memory for ten minutes,
with scope/facts/history/provider/model/key in the cache identity. Rate and billing
429 failures pause further provider calls while retaining local fallback and
valid cache hits. There are no automatic retries or paid-provider failovers.
The Google key is not configured yet. Existing OpenAI credentials are preserved.

```text
frontend/                 React + TypeScript + Vite, custom CSS, React Router, Recharts
  src/App.tsx             Workspace, routes and current MVP screens
  src/styles.css          Responsive layout, components and typography
  src/{lib,types}/         API client, exact decimal display, generated contract
  public/templates/       Downloadable CSV examples
  tests/                  Financial display precision checks
backend/                  FastAPI, Pydantic, SQLAlchemy, Alembic, SQLite
  app/{api,models,schemas,services,db,core}/
  tests/
shared/openapi.json       Versioned contract, generated from FastAPI and reviewed
demo_data/                Reproducible cafe generator and expected signal fixtures
start.ps1                 SQLite migrations and both local servers
docker-compose.yml        Optional PostgreSQL only
.env.example              Nonsecret configuration
README.md                 Setup, commands, demo flow
```

Keep business calculations and detection in backend services. Store money as integer cents and quantities as integer thousandths on SQLite (NUMERIC on optional PostgreSQL); calculate with Python `Decimal`; serialize amounts as decimal strings in the API so the browser does not silently round them. Use UTC timestamps for records and business local dates for analysis. Every query and import is scoped to a business ID, even in the single demo business.

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

From a clean checkout, install dependencies, run `start.ps1`, and open the Russian UI. Load the Taraz cafe demo data twice and confirm the second attempt changes no row counts. Show 90 days of revenue, expenses, and profit; run analysis; inspect the packaging spike, margin decline, and possible duplicate with their source evidence. Upload one malformed file and show row level validation. Disable the LLM setting and repeat the insight flow. Confirm scenario savings is marked as an estimate and KPI values match the independent fixture calculations.

## Decisions to settle during stage 0

- Define return/discount columns and whether expenses can contain tax; the supplied file examples do not define these semantics.
- Choose exact thresholds and baseline windows for each detector, then encode them in fixtures.
- Choose demo hosting only after the local path works; the current requirements do not specify a deployment target.

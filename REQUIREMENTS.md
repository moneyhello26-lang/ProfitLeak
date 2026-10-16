# ProfitLeak AI implementation status

Source of product requirements: `ProfitLeak_AI_Requirements.docx`, MVP 1.0.
This file maps those requirements to implementation; it does not replace the source.

| Requirement | Implementation |
| --- | --- |
| FR-01 Dashboard | Backend KPIs, revenue and expense charts, product table, recent insights |
| FR-02 CSV/XLSX import | Preview, confirmation, source rows and import history |
| FR-03 Validation | Columns, dates, Decimal values, limits, formula rejection, duplicate import protection |
| FR-04 Financial calculations | Exact Decimal revenue, COGS, gross/operating profit and margin; returns/refunds |
| FR-05 Expense anomalies | Rule based category comparison with explicit minimum samples |
| FR-06 Product profitability | Revenue, COGS, profit/margin, pagination and product rules |
| FR-07 Evidence cards | Detector, priority/type filters, detail route, periods, formulas and source rows |
| FR-08 Recommendations | Russian templates plus Gemini/OpenAI explanations with verified fact substitution, provider-specific consent, bounded history, cache and quota pause |
| FR-09 Dates | Inclusive 1–366 day filters on analytics and analysis |
| FR-10 Demo | Repeatable 90 day Taraz cafe; three independently checked detector scenarios |
| FR-11 Advisor chat | Business/date scoped chat, bounded transient history, source labels and backend facts; offline fallback |
| FR-12 PDF | Local PDF with KPIs, expenses, products, evidence, recommendations and stale/missing analysis notices |
| FR-13 Kazakh language | RU/KK selector with persistence; all pages, locale dates, import errors, evidence, advisor/templates/LLM and PDF; request-local backend locale and Kazakh font glyphs |
| FR-14 Period comparison | Separate dashboard: previous/custom non-overlapping periods, six KPIs, absolute/relative/daily changes, margin points, aligned revenue chart, paginated products and expense categories |
| FR-15 Forecasts | Local weekday-average forecast, 1–90 day API horizon, sales/expense scenarios, independent 7-day holdout, explicit data coverage and assumptions; no LLM dependency |
| FR-16 Accounts and roles | Registration/login/logout/password change, hashed passwords and revocable HttpOnly sessions; owner/analyst/viewer per business; server authorization, membership management, atomic adoption of existing data and personal demo |

SQLite is the default database, matching the source document and the user's
request to run without Docker. Money is stored as integer cents, quantities as
integer thousandths; Python receives Decimal values with no float conversion.
PostgreSQL remains an optional driver and is not required for setup or tests.
The existing custom CSS is preserved instead of Tailwind/shadcn.
ML and LLM are not prerequisites for deterministic detection.
Comparison and forecasts use confirmed imports and Decimal calculations, scoped
to the selected business. See [planning guide](docs/PLANNING_GUIDE.md) for formulas,
data requirements, API parameters, and a hand-checkable demo.
See [accounts and language guide](docs/ACCOUNTS_AND_LANGUAGE_GUIDE.md) for the
first-account transition, permissions, sessions and bilingual usage.

## Analysis contract

- `POST /api/v1/analysis/run`: JSON `business_id`, optional `date_from`, `date_to`.
  Returns selected period, comparison periods, timestamp, rules version, count,
  and per-rule `evaluated` / `insufficient_data` checks.
- `GET /api/v1/insights`: same business/date query; optional `severity`, `type`,
  `limit` (1–100), `offset`. Returns the saved analysis and paginated signals.
- `GET /api/v1/insights/{id}`: requires `business_id`; returns evidence and a
  recommendation. Signals from another business return 404.

Date defaults match analytics. Each business and selected period has one saved
analysis; repeating it replaces that period's signals atomically with stable IDs.
Results for other periods/businesses remain available. Newly confirmed imports
mark previous analyses stale. An analysis with no signals is persisted too, so an
unrun analysis is distinguishable from one with insufficient data or no findings.

## Rules v1

Comparison uses the final `min(30, floor(selected_days / 2))` days and the preceding
window of the same length, both entirely inside the selection. Fewer than 14
selected days disables comparative rules. Low margin and duplicate rules can
still run independently. Missing days are never inferred to contain zero sales.

| Rule | Trigger and minimum data |
| --- | --- |
| EXPENSE_SPIKE | Category net expenses rise ≥25%; positive baseline, at least 7 observed category days per window |
| MARGIN_DROP | Product gross margin falls ≥10 percentage points; 7 observed days and 10 net units per window, positive revenue, complete unit costs |
| LOW_PROFIT_PRODUCT | Gross margin ≤20%; 5 rows, 3 observed days, 10 net units, positive revenue and complete costs |
| SALES_DROP | Business net revenue drops ≥20%; positive baseline, nonnegative current revenue, records on every day of both windows |
| POSSIBLE_DUPLICATE | Same date, category, amount and nonblank description after whitespace/case normalization; positive expense rows only |

Sales line revenue/cost uses the same half-away-from-zero cent rounding as KPIs.
Returns reverse revenue/cost/quantity; refunds reverse expenses. Thresholds are
evaluated with unrounded Decimal ratios. Comparison confidence is a qualitative
data assessment, not a probability of financial loss.

Signals explain the formula, coverage, source filenames/row numbers and limitations.
Up to 20 source rows are shown, sampling both compared windows. Possible duplicates
have low confidence because input files do not include bank payment identifiers.
No records are removed automatically.

Scenario savings for expense growth assumes a return to baseline spending with the
same purchasing volume. Margin scenarios assume restored baseline margin at current
revenue. Other rules return null savings. These estimates can overlap and are not
summed or presented as proven losses or guaranteed savings.

## Acceptance demonstration

1. Run `start.ps1`: it applies SQLite migrations and starts FastAPI and Vite.
2. Open the Taraz demo twice; check that row counts and KPI values are unchanged.
3. Open **Детектор проблем** and run analysis for the default 90 days.
4. Check packaging: 30,000 → 46,500 KZT, +55%, scenario 16,500 KZT.
5. Check coffee margin: 62.50% → 25.00%, −37.50 p.p., scenario 337,500 KZT.
6. Check the two packaging expenses on 2026-10-01, amount 1,500 KZT, with distinct
   source rows. Duplicate savings remain null until a person verifies the payment.
7. Open each detail, verify calculation and recommendation, then rerun analysis.
   Counts and IDs stay unchanged; dashboard displays the saved findings.
8. Import new data: saved analysis becomes stale until rerun. Check malformed import
   errors and short date selections. The entire flow works without any LLM key.

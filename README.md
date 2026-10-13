# ProfitLeak AI

Financial analytics for small businesses in Taraz. React, FastAPI, and PostgreSQL
are the planned stack. The first implementation stage provides the backend database
models, migrations, and a database health endpoint.

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

File digest uniqueness prevents the same file from being imported again for the
same business and type. Source row uniqueness prevents inserting an import row
twice. Different rows with identical expense values remain available to the
possible duplicate detector. The future import service will handle transactions,
file normalization and repeated files with changed contents.

Sales and expenses store positive magnitudes. `record_type=return` reverses a sale;
`record_type=refund` reverses an expense in the future analytics service. Standard
CSV templates default to `sale` and `expense`. Discounts should be included in the
effective unit price for this schema. Returns use the price and cost from the
original transaction. Import parsing and financial calculations are the next stage.

## Verification

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
consistency, and migration reversal.

See [the development plan](DEVELOPMENT_PLAN.md) for the remaining implementation stages.

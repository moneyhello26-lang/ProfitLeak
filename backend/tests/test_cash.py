from datetime import date
from decimal import Decimal
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.main import app
from app.models import BusinessMembership, CashEntry, User
from app.services import auth
from app.services.cash import next_due


@pytest.fixture
def client(db):
    auth._attempts.clear()
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        auth._attempts.clear()


def register(client, email):
    response = client.post("/api/v1/auth/register", json={
        "email": email, "password": "Correct horse battery 2026", "full_name": "Cash tester"})
    assert response.status_code == 201, response.text


@pytest.fixture
def business(client):
    register(client, "cash-owner@example.test")
    response = client.post("/api/v1/businesses", json={"name": "Cash shop", "industry": "retail"})
    assert response.status_code == 201
    return response.json()["id"]


def post(client, business, path, payload, status=201):
    response = client.post(f"/api/v1/cash/{path}", params={"business_id": business}, json=payload)
    assert response.status_code == status, response.text
    return response.json()


def account(client, business, balance="100.00", opening="2026-10-01"):
    return post(client, business, "accounts", {
        "name": "Bank", "opening_date": opening, "opening_balance": balance})["id"]


def entry(client, business, account_id, **changes):
    payload = {"account_id": account_id, "date": "2026-10-10", "kind": "expense",
               "amount": "0.10", "category": "rent"}
    payload.update(changes)
    return post(client, business, "entries", payload)


def report(client, business, start="2026-10-01", end="2026-10-31"):
    response = client.get("/api/v1/cash/report", params={
        "business_id": business, "date_from": start, "date_to": end})
    assert response.status_code == 200, response.text
    return response.json()


def test_exact_balances_transfers_and_reconciliation(client, business):
    source = account(client, business, "90071992547409.93")
    target = account(client, business, "0.00")
    entry(client, business, source, kind="income", amount="0.20")
    entry(client, business, source)
    entry(client, business, source, kind="transfer", destination_id=target, amount="10.01")
    data = report(client, business)
    assert data["closing_balance"] == "90071992547410.03"
    assert data["income"] == "0.20" and data["expense"] == "0.10"
    assert data["net_flow"] == "0.10"
    assert data["opening_balance"] == "90071992547409.93"
    assert data["introduced_balance"] == "0.00"
    assert sum(Decimal(a["balance"]) for a in data["accounts"]) == Decimal(data["closing_balance"])
    assert data["projection"][-1]["balance"] == data["closing_balance"]
    assert data["categories"] == [{"category": "rent", "amount": "0.10"}]


def test_opening_balance_introduced_during_period_and_prior_transactions(client, business):
    old = account(client, business)
    account(client, business, "20.00", "2026-10-15")
    entry(client, business, old, date="2026-10-02", amount="10.00")
    data = report(client, business, "2026-10-10")
    assert data["opening_balance"] == "90.00"
    assert data["introduced_balance"] == "20.00"
    assert data["closing_balance"] == "110.00"
    assert data["projection"][-1]["balance"] == "110.00"


def test_budget_actual_covers_whole_month_and_upserts(client, business):
    source = account(client, business)
    entry(client, business, source, amount="10.00", date="2026-10-03")
    entry(client, business, source, amount="25.00", date="2026-10-20")
    payload = {"month": "2026-10-01", "category": "rent", "amount": "30.00"}
    before = post(client, business, "budgets", payload, 200)
    after = post(client, business, "budgets", {**payload, "amount": "40.00"}, 200)
    assert before["id"] == after["id"]
    budgets = report(client, business, "2026-10-10", "2026-10-15")["budgets"]
    assert len(budgets) == 1 and budgets[0]["actual"] == "35.00"
    assert budgets[0]["remaining"] == "5.00"


def test_payment_posts_once_recurrence_and_cancellation(client, business):
    source = account(client, business, "100.00", "2026-01-01")
    planned = post(client, business, "payments", {
        "account_id": source, "due_date": "2026-01-31", "kind": "expense",
        "amount": "10.00", "category": "rent", "recurrence": "monthly"})
    url = f"/api/v1/cash/payments/{planned['id']}?business_id={business}"
    assert client.patch(url, json={"action": "pay", "paid_date": "2026-01-31"}).status_code == 200
    assert client.patch(url, json={"action": "pay"}).status_code == 409
    data = report(client, business, "2026-02-01", "2026-03-31")
    assert data["closing_balance"] == "90.00"
    next_payment = data["payments"][0]
    assert next_payment["due_date"] == "2026-02-28"
    next_url = f"/api/v1/cash/payments/{next_payment['id']}?business_id={business}"
    paid = client.patch(next_url, json={"action": "pay", "paid_date": "2026-02-28"})
    assert paid.status_code == 200
    data = report(client, business, "2026-03-01", "2026-03-31")
    assert data["payments"][0]["due_date"] == "2026-03-31"
    last_url = f"/api/v1/cash/payments/{data['payments'][0]['id']}?business_id={business}"
    assert client.patch(last_url, json={"action": "cancel"}).status_code == 200
    assert report(client, business)["closing_balance"] == "80.00"


def test_projection_detects_account_gap_and_overdue_without_hiding_in_total(client, business):
    source = account(client, business, "10.00")
    account(client, business, "1000.00")
    post(client, business, "payments", {"account_id": source, "due_date": "2026-10-03",
         "kind": "expense", "amount": "20.00", "category": "rent"})
    data = report(client, business, "2026-10-10")
    assert data["projection"][0]["balance"] == "990.00"
    assert data["projection"][0]["gap_accounts"] == [source]
    assert data["closing_balance"] == "1010.00"


def upload(client, business, source, content, filename="statement.csv", token=None):
    data = {"business_id": business, "account_id": source}
    if token:
        data["preview_token"] = token
    return client.post(f"/api/v1/cash/statements/{'confirm' if token else 'preview'}",
                       data=data, files={"file": (filename, content)})


CSV = (b"date,kind,amount,category,description,reference\n"
       b"2026-10-17,income,100.20,sales,Sale,TX1\n"
       b"2026-10-17,expense,10.10,rent,Rent,TX2\n")


def test_statement_preview_confirmation_exact_sums_and_duplicates(client, business, db):
    source = account(client, business, "0.00")
    preview = upload(client, business, source, CSV).json()
    assert preview["can_confirm"] and preview["row_count"] == 2
    assert db.scalar(select(func.count()).select_from(CashEntry)) == 0
    confirmed = upload(client, business, source, CSV, token=preview["preview_token"])
    assert confirmed.status_code == 200 and confirmed.json()["imported"] == 2
    assert report(client, business)["closing_balance"] == "90.10"
    assert not upload(client, business, source, CSV).json()["can_confirm"]
    reordered = CSV.splitlines()[0] + b"\n" + b"\n".join(reversed(CSV.splitlines()[1:])) + b"\n"
    assert not upload(client, business, source, reordered).json()["can_confirm"]
    assert upload(client, business, source, CSV, token=preview["preview_token"]).status_code == 409


def test_statement_token_bound_to_business_account_and_file(client, business):
    source = account(client, business)
    other = account(client, business)
    token = upload(client, business, source, CSV).json()["preview_token"]
    assert upload(client, business, other, CSV, token=token).status_code == 409
    assert upload(client, business, source, CSV.replace(b"100.20", b"200.20"),
                  token=token).status_code == 409
    assert report(client, business)["closing_balance"] == "200.00"


@pytest.mark.parametrize("row", [
    b"2026-10-17,expense,-1,rent,Test,A", b"2026-10-17,expense,0,rent,Test,A",
    b"2026-10-17,expense,1.001,rent,Test,A", b"2026-10-17,transfer,1,rent,Test,A",
    b"2026-09-01,expense,1,rent,Test,A", b"2026-10-17,expense,1,rent,Test,",
])
def test_invalid_statement_is_not_confirmable(client, business, db, row):
    source = account(client, business)
    data = upload(client, business, source, CSV.splitlines()[0] + b"\n" + row + b"\n").json()
    assert not data["can_confirm"] and data["errors"]
    assert db.scalar(select(func.count()).select_from(CashEntry)) == 0


def test_xlsx_values_accepted_formulas_rejected(client, business):
    source = account(client, business)
    book = Workbook()
    sheet = book.active
    sheet.append(CSV.decode().splitlines()[0].split(','))
    sheet.append(["2026-10-17", "income", 100.25, "sales", None, "X1"])
    data = BytesIO()
    book.save(data)
    preview = upload(client, business, source, data.getvalue(), "statement.xlsx").json()
    assert preview["can_confirm"]
    assert upload(client, business, source, data.getvalue(), "statement.xlsx",
                  preview["preview_token"]).status_code == 200
    sheet["C2"] = "=100+1"
    data = BytesIO()
    book.save(data)
    invalid = upload(client, business, source, data.getvalue(), "statement.xlsx").json()
    assert not invalid["can_confirm"]


def test_roles_and_cross_business_references(client, business, db):
    source = account(client, business)
    register(client, "cash-outsider@example.test")
    params = {"business_id": business, "date_from": "2026-10-01", "date_to": "2026-10-31"}
    assert client.get("/api/v1/cash/report", params=params).status_code == 404
    assert upload(client, business, source, CSV).status_code == 404
    user = db.scalar(select(User).where(User.email == "cash-outsider@example.test"))
    member = BusinessMembership(business_id=UUID(business), user_id=user.id, role="viewer")
    db.add(member)
    db.commit()
    assert client.get("/api/v1/cash/report", params=params).status_code == 200
    assert upload(client, business, source, CSV).status_code == 403
    assert client.post("/api/v1/cash/budgets", params=params, json={
        "month": "2026-10-01", "category": "rent", "amount": "1"}).status_code == 403
    member.role = "analyst"
    db.commit()
    created = client.post("/api/v1/businesses", json={"name": "Other", "industry": "retail"})
    another = created.json()["id"]
    other_account = account(client, another)
    assert client.post(f"/api/v1/cash/entries?business_id={business}", json={
        "account_id": source, "destination_id": other_account, "date": "2026-10-17",
        "kind": "transfer", "amount": "1", "category": "transfer"}).status_code == 404
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(CashEntry(business_id=UUID(business), account_id=UUID(other_account),
                        date=date(2026, 10, 17), kind="expense", amount=Decimal("1"),
                        category="rent", description=""))
        db.flush()
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/cash/report", params=params).status_code == 401


def test_invalid_period_transfer_and_duplicate_reference(client, business):
    source = account(client, business)
    for payload in (
        {"kind": "transfer"}, {"kind": "transfer", "destination_id": source},
        {"kind": "expense", "destination_id": source}, {"date": "2026-09-30"},
        {"account_id": str(uuid4())}, {"amount": "NaN"},
    ):
        response = client.post(f"/api/v1/cash/entries?business_id={business}", json={
            "account_id": source, "kind": "expense", "date": "2026-10-17",
            "amount": "1", "category": "rent", **payload})
        assert response.status_code in (400, 404, 422), response.text
    entry(client, business, source, reference="R1")
    response = client.post(f"/api/v1/cash/entries?business_id={business}", json={
        "account_id": source, "kind": "expense", "date": "2026-10-17",
        "amount": "1", "category": "rent", "reference": "R1"})
    assert response.status_code == 409
    assert client.get("/api/v1/cash/report", params={"business_id": business,
        "date_from": "2026-10-17", "date_to": "2026-10-01"}).status_code == 400


def test_monthly_recurrence_retains_anchor():
    assert next_due(date(2026, 1, 31), "monthly", 31) == date(2026, 2, 28)
    assert next_due(date(2026, 2, 28), "monthly", 31) == date(2026, 3, 31)
    assert next_due(date(2026, 12, 31), "weekly") == date(2027, 1, 7)

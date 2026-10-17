import calendar
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.cash import CashAccount, CashBudget, CashEntry, PlannedPayment
from app.schemas.cash import EntryCreate
from app.services.import_parser import FileProblem

ZERO = Decimal("0.00")


def problem(message, status=400):
    raise FileProblem("cash_validation", message, status)


def account(db, business_id, account_id):
    row = db.scalar(select(CashAccount).where(
        CashAccount.business_id == business_id, CashAccount.id == account_id))
    if row is None:
        problem("Счёт не найден.", 404)
    return row


def add_entry(db, business_id, payload):
    source = account(db, business_id, payload.account_id)
    if payload.date < source.opening_date:
        problem("Операция раньше даты начального остатка.")
    if payload.kind == "transfer":
        if payload.destination_id is None or payload.destination_id == payload.account_id:
            problem("Выберите другой счёт для перевода.")
        target = account(db, business_id, payload.destination_id)
        if payload.date < target.opening_date:
            problem("Операция раньше даты начального остатка.")
    elif payload.destination_id is not None:
        problem("Счёт получателя нужен только для перевода.")
    row = CashEntry(business_id=business_id, **payload.model_dump())
    db.add(row)
    return row


def commit(db):
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise FileProblem(
            "cash_duplicate", "Операция с таким номером уже существует.", 409
        ) from error


def next_due(value, recurrence, anchor_day=None):
    if recurrence == "weekly":
        return value + timedelta(days=7)
    month = value.month % 12 + 1
    year = value.year + (value.month == 12)
    return date(year, month, min(anchor_day or value.day, calendar.monthrange(year, month)[1]))


def apply_payment(db, business_id, payment, action, paid_date):
    if payment.status != "pending":
        problem("Платёж уже оплачен или отменён.", 409)
    due = None
    if action == "pay":
        source = account(db, business_id, payment.account_id)
        if paid_date < source.opening_date:
            problem("Операция раньше даты начального остатка.")
        if payment.recurrence != "none":
            try:
                due = next_due(payment.due_date, payment.recurrence, payment.recurrence_day)
            except (ValueError, OverflowError):
                problem("Следующий платёж выходит за допустимые даты.")
    # The caller locks the business on PostgreSQL. The guarded UPDATE also
    # prevents two SQLite requests from posting the same payment.
    from sqlalchemy import update

    changed = db.execute(update(PlannedPayment).where(
        PlannedPayment.id == payment.id, PlannedPayment.status == "pending"
    ).values(status="paid" if action == "pay" else "cancelled"))
    if changed.rowcount != 1:
        problem("Платёж уже оплачен или отменён.", 409)
    if action == "pay":
        add_entry(db, business_id, EntryCreate(
            account_id=payment.account_id, date=paid_date, kind=payment.kind,
            amount=payment.amount, category=payment.category,
            description=payment.description, reference=f"payment:{payment.id}",
        ))
        if due is not None:
            db.add(PlannedPayment(
                business_id=business_id, account_id=payment.account_id,
                due_date=due, kind=payment.kind, amount=payment.amount,
                category=payment.category, description=payment.description,
                recurrence=payment.recurrence,
                recurrence_day=payment.recurrence_day,
            ))
    commit(db)


def report(db, business_id, start, end):
    accounts = list(db.scalars(select(CashAccount).where(
        CashAccount.business_id == business_id).order_by(CashAccount.created_at, CashAccount.id)))
    entries = list(db.scalars(select(CashEntry).where(
        CashEntry.business_id == business_id, CashEntry.date <= end
    ).order_by(CashEntry.date, CashEntry.created_at, CashEntry.id)))
    payments = list(db.scalars(select(PlannedPayment).where(
        PlannedPayment.business_id == business_id,
        PlannedPayment.due_date <= end,
        (PlannedPayment.due_date >= start) | (PlannedPayment.status == "pending"),
    ).order_by(PlannedPayment.due_date, PlannedPayment.id)))
    opening = {a.id: a.opening_balance if a.opening_date <= start else ZERO for a in accounts}
    closing = {a.id: a.opening_balance if a.opening_date <= end else ZERO for a in accounts}
    income, expense = ZERO, ZERO
    categories = {}
    for row in entries:
        signed = row.amount if row.kind == "income" else -row.amount
        closing[row.account_id] += signed
        if row.destination_id:
            closing[row.destination_id] += row.amount
        if row.date < start:
            opening[row.account_id] += signed
            if row.destination_id:
                opening[row.destination_id] += row.amount
        elif row.kind == "income":
            income += row.amount
        elif row.kind == "expense":
            expense += row.amount
            categories[row.category] = categories.get(row.category, ZERO) + row.amount
    # Project by account, since a positive business total can hide a cash gap
    # on the particular account from which a payment must be made.
    projected = dict(opening)
    points = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        for a in accounts:
            if a.opening_date == day and day > start:
                projected[a.id] += a.opening_balance
        for row in entries:
            if row.date == day:
                projected[row.account_id] += row.amount if row.kind == "income" else -row.amount
                if row.destination_id:
                    projected[row.destination_id] += row.amount
        for p in payments:
            if p.status == "pending" and max(start, p.due_date) == day:
                projected[p.account_id] += p.amount if p.kind == "income" else -p.amount
        points.append({"date": day, "balance": sum(projected.values(), ZERO),
                       "gap_accounts": [str(key) for key, value in projected.items() if value < 0]})
    budgets = list(db.scalars(select(CashBudget).where(
        CashBudget.business_id == business_id,
        CashBudget.month == start.replace(day=1)).order_by(CashBudget.category)))
    month_end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
    # Budget actuals always cover the whole month, independently of the selected range.
    spent = {}
    for row in db.scalars(select(CashEntry).where(
        CashEntry.business_id == business_id, CashEntry.kind == "expense",
        CashEntry.date >= start.replace(day=1), CashEntry.date <= month_end,
    )):
        spent[row.category] = spent.get(row.category, ZERO) + row.amount
    return {
        "date_from": start, "date_to": end,
        "accounts": [{"id": a.id, "name": a.name, "opening_date": a.opening_date,
                      "opening_balance": a.opening_balance, "balance": closing[a.id]}
                     for a in accounts],
        "opening_balance": sum(opening.values(), ZERO),
        "closing_balance": sum(closing.values(), ZERO), "income": income, "expense": expense,
        "net_flow": income - expense,
        "introduced_balance": sum((a.opening_balance for a in accounts
                                   if start < a.opening_date <= end), ZERO),
        "categories": [{"category": k, "amount": v} for k, v in sorted(categories.items())],
        "projection": points,
        "payments": [{"id": p.id, "account_id": p.account_id, "due_date": p.due_date,
                      "kind": p.kind, "amount": p.amount, "category": p.category,
                      "description": p.description, "recurrence": p.recurrence, "status": p.status}
                     for p in payments],
        "budgets": [{"id": b.id, "month": b.month, "category": b.category, "amount": b.amount,
                     "actual": spent.get(b.category, ZERO),
                     "remaining": b.amount - spent.get(b.category, ZERO)} for b in budgets],
    }

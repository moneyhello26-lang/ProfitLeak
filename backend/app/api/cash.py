from datetime import date, datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, File, Form, Query, UploadFile
from sqlalchemy import select

from app.api.dependencies import Database, require_business
from app.models.cash import CashAccount, CashBudget, CashEntry, PlannedPayment
from app.schemas.cash import (
    AccountCreate,
    AccountRead,
    BudgetCreate,
    BudgetRead,
    CashReport,
    EntryCreate,
    EntryRead,
    PaymentAction,
    PaymentCreate,
    PaymentRead,
    StatementConfirmed,
    StatementPreview,
    StatementPreviewRow,
    StatementRow,
)
from app.services import cash
from app.services.import_parser import MAX_UPLOAD_BYTES, parse_file
from app.services.import_tokens import issue_token, verify_token

router = APIRouter(prefix="/api/v1/cash", tags=["Cash management"])
EDIT = ("owner", "analyst")


@router.post("/accounts", response_model=AccountRead, status_code=201)
def create_account(payload: AccountCreate, business_id: UUID, db: Database):
    require_business(db, business_id, EDIT, lock=True)
    row = CashAccount(business_id=business_id, **payload.model_dump())
    db.add(row)
    cash.commit(db)
    return row


@router.post("/entries", response_model=EntryRead, status_code=201)
def create_entry(payload: EntryCreate, business_id: UUID, db: Database):
    require_business(db, business_id, EDIT, lock=True)
    row = cash.add_entry(db, business_id, payload)
    cash.commit(db)
    return row


@router.get("/entries", response_model=list[EntryRead])
def entries(business_id: UUID, db: Database, date_from: date, date_to: date,
            limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    require_business(db, business_id)
    check_period(date_from, date_to)
    return db.scalars(select(CashEntry).where(
        CashEntry.business_id == business_id, CashEntry.date >= date_from,
        CashEntry.date <= date_to,
    ).order_by(CashEntry.date.desc(), CashEntry.created_at.desc(), CashEntry.id)
        .limit(limit).offset(offset)).all()


def check_period(start, end):
    if not 0 <= (end - start).days < 366:
        cash.problem("Выберите период от 1 до 366 дней.")


@router.get("/report", response_model=CashReport)
def report(business_id: UUID, db: Database, date_from: date, date_to: date):
    require_business(db, business_id)
    check_period(date_from, date_to)
    return cash.report(db, business_id, date_from, date_to)


@router.post("/payments", response_model=PaymentRead, status_code=201)
def create_payment(payload: PaymentCreate, business_id: UUID, db: Database):
    require_business(db, business_id, EDIT, lock=True)
    source = cash.account(db, business_id, payload.account_id)
    if payload.due_date < source.opening_date:
        cash.problem("Операция раньше даты начального остатка.")
    row = PlannedPayment(business_id=business_id, recurrence_day=payload.due_date.day,
                         **payload.model_dump())
    db.add(row)
    cash.commit(db)
    return row


@router.patch("/payments/{payment_id}", response_model=PaymentRead)
def payment_action(payment_id: UUID, payload: PaymentAction, business_id: UUID, db: Database):
    business = require_business(db, business_id, EDIT, lock=True)
    row = db.scalar(select(PlannedPayment).where(
        PlannedPayment.business_id == business_id, PlannedPayment.id == payment_id))
    if row is None:
        cash.problem("Платёж не найден.", 404)
    paid_date = payload.paid_date or datetime.now(ZoneInfo(business.timezone)).date()
    cash.apply_payment(db, business_id, row, payload.action, paid_date)
    return row


@router.post("/budgets", response_model=BudgetRead)
def save_budget(payload: BudgetCreate, business_id: UUID, db: Database):
    require_business(db, business_id, EDIT, lock=True)
    row = db.scalar(select(CashBudget).where(
        CashBudget.business_id == business_id, CashBudget.month == payload.month,
        CashBudget.category == payload.category))
    if row:
        row.amount = payload.amount
    else:
        row = CashBudget(business_id=business_id, **payload.model_dump())
        db.add(row)
    cash.commit(db)
    return row


def read_statement(db, business_id, account_id, file):
    source = cash.account(db, business_id, account_id)
    try:
        parsed = parse_file(file.filename or "", file.file.read(MAX_UPLOAD_BYTES + 1),
                            "cash", model=StatementRow, row_type=StatementPreviewRow)
    finally:
        file.file.close()
    seen = set()
    existing = set(db.scalars(select(CashEntry.reference).where(
        CashEntry.business_id == business_id, CashEntry.account_id == account_id,
        CashEntry.reference.is_not(None))))
    for row in parsed.rows:
        if row.data.reference in seen or row.data.reference in existing:
            parsed.error(row.source_row, "reference", "Операция с таким номером уже существует.")
        if row.data.date < source.opening_date:
            parsed.error(row.source_row, "date", "Операция раньше даты начального остатка.")
        seen.add(row.data.reference)
    return parsed


@router.post("/statements/preview", response_model=StatementPreview)
def preview_statement(db: Database, business_id: Annotated[UUID, Form()],
                      account_id: Annotated[UUID, Form()], file: Annotated[UploadFile, File()]):
    require_business(db, business_id, EDIT)
    parsed = read_statement(db, business_id, account_id, file)
    token = None
    if not parsed.error_count and parsed.rows:
        token, _ = issue_token(business_id, f"cash:{account_id}", parsed.file_sha256)
    return {"row_count": parsed.row_count, "preview": parsed.rows[:20],
            "errors": parsed.errors, "can_confirm": token is not None, "preview_token": token}


@router.post("/statements/confirm", response_model=StatementConfirmed)
def confirm_statement(db: Database, business_id: Annotated[UUID, Form()],
                      account_id: Annotated[UUID, Form()], file: Annotated[UploadFile, File()],
                      preview_token: Annotated[str, Form(max_length=2000)]):
    require_business(db, business_id, EDIT, lock=True)
    parsed = read_statement(db, business_id, account_id, file)
    verify_token(preview_token, business_id, f"cash:{account_id}", parsed.file_sha256)
    if parsed.error_count or not parsed.rows:
        cash.problem("Исправьте ошибки и проверьте файл снова.", 409)
    for row in parsed.rows:
        cash.add_entry(db, business_id, EntryCreate(account_id=account_id, **row.data.model_dump()))
    cash.commit(db)
    return {"imported": len(parsed.rows)}

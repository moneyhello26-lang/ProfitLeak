import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Money = Annotated[Decimal, Field(max_digits=18, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]
Label = Annotated[str, Field(min_length=1, max_length=100)]


class CashInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("date", "opening_date", "due_date", "paid_date", "month",
                     mode="before", check_fields=False)
    @classmethod
    def calendar_date(cls, value):
        if value is None or isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime) and value.time().isoformat() == "00:00:00":
            return value.date()
        if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return value
        raise ValueError("Expected YYYY-MM-DD without a time")


class AccountCreate(CashInput):
    name: str = Field(min_length=1, max_length=120)
    opening_date: date
    opening_balance: Money = Decimal(0)


class EntryCreate(CashInput):
    account_id: UUID
    destination_id: UUID | None = None
    date: date
    kind: Literal["income", "expense", "transfer"]
    amount: PositiveMoney
    category: Label
    description: str = Field(default="", max_length=500)
    reference: str | None = Field(default=None, min_length=1, max_length=160)


class PaymentCreate(CashInput):
    account_id: UUID
    due_date: date
    kind: Literal["income", "expense"]
    amount: PositiveMoney
    category: Label
    description: str = Field(default="", max_length=500)
    recurrence: Literal["none", "weekly", "monthly"] = "none"


class PaymentAction(CashInput):
    action: Literal["pay", "cancel"]
    paid_date: date | None = None


class BudgetCreate(CashInput):
    month: date
    category: Label
    amount: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]

    @field_validator("month")
    @classmethod
    def first_day(cls, value):
        if value.day != 1:
            raise ValueError("month must be the first day of the month")
        return value


class StatementRow(CashInput):
    date: date
    kind: Literal["income", "expense"]
    amount: PositiveMoney
    category: Label
    description: str = Field(default="", max_length=500)
    reference: str = Field(min_length=1, max_length=160)

    @field_validator("description", mode="before")
    @classmethod
    def empty_description(cls, value):
        return "" if value is None else value


class AccountRead(AccountCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class EntryRead(EntryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class PaymentRead(PaymentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: Literal["pending", "paid", "cancelled"]


class BudgetRead(BudgetCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class AccountBalance(AccountRead):
    balance: Decimal


class ProjectionPoint(BaseModel):
    date: date
    balance: Decimal
    gap_accounts: list[str]


class BudgetActual(BudgetRead):
    actual: Decimal
    remaining: Decimal


class CategoryFlow(BaseModel):
    category: str
    amount: Decimal


class CashReport(BaseModel):
    date_from: date
    date_to: date
    accounts: list[AccountBalance]
    opening_balance: Decimal
    introduced_balance: Decimal
    closing_balance: Decimal
    income: Decimal
    expense: Decimal
    net_flow: Decimal
    categories: list[CategoryFlow]
    projection: list[ProjectionPoint]
    payments: list[PaymentRead]
    budgets: list[BudgetActual]


class StatementPreviewRow(BaseModel):
    source_row: int
    data: StatementRow


class StatementError(BaseModel):
    row: int
    field: str
    message: str


class StatementPreview(BaseModel):
    row_count: int
    preview: list[StatementPreviewRow]
    errors: list[StatementError]
    can_confirm: bool
    preview_token: str | None


class StatementConfirmed(BaseModel):
    imported: int

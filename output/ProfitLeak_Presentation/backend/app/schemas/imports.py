import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ImportKind = Literal["sales", "expenses", "products"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2, allow_inf_nan=False)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=3, allow_inf_nan=False)]


class BusinessCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    industry: Code
    currency: Literal["KZT"] = "KZT"
    timezone: Literal["Asia/Almaty"] = "Asia/Almaty"


class BusinessRead(BusinessCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    is_demo: bool


class RowBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class DatedRow(RowBase):
    date: date

    @field_validator("date", mode="before")
    @classmethod
    def exact_date(cls, value):
        if isinstance(value, datetime):
            if value.time().isoformat() != "00:00:00":
                raise ValueError("Expected a date without a time")
            return value.date()
        if isinstance(value, str):
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value.strip()):
                raise ValueError("Expected YYYY-MM-DD")
            return date.fromisoformat(value.strip())
        if not isinstance(value, date):
            raise ValueError("Expected YYYY-MM-DD")
        return value


class SalesRow(DatedRow):
    product_id: Code
    product_name: Name
    quantity: Quantity
    unit_price: Money
    unit_cost: Money | None
    record_type: Literal["sale", "return"] = "sale"

    @field_validator("unit_cost", mode="before")
    @classmethod
    def missing_cost(cls, value):
        return None if value is None or (isinstance(value, str) and not value.strip()) else value


class ExpensesRow(DatedRow):
    category: Code
    description: Annotated[str, StringConstraints(max_length=5000)]
    amount: Money
    record_type: Literal["expense", "refund"] = "expense"

    @field_validator("description", mode="before")
    @classmethod
    def blank_description(cls, value):
        return "" if value is None else value


class ProductsRow(RowBase):
    product_id: Code
    name: Name
    category: Annotated[str | None, StringConstraints(max_length=100)] = None

    @field_validator("category", mode="before")
    @classmethod
    def blank_category(cls, value):
        return None if value is None or (isinstance(value, str) and not value.strip()) else value


class RowError(BaseModel):
    row: int
    field: str
    message: str


class PreviewRow(BaseModel):
    source_row: int
    data: SalesRow | ExpensesRow | ProductsRow


class ImportPreview(BaseModel):
    business_id: UUID
    kind: ImportKind
    filename: str
    row_count: int
    valid_row_count: int
    preview: list[PreviewRow]
    errors: list[RowError]
    errors_truncated: bool
    can_confirm: bool
    existing_import_id: UUID | None = None
    preview_token: str | None = None
    expires_at: datetime | None = None


class ImportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    business_id: UUID
    filename: str
    kind: ImportKind
    status: Literal["processing", "confirmed", "failed"]
    row_count: int
    created_at: datetime
    confirmed_at: datetime | None


class ImportConfirmation(BaseModel):
    imported: ImportRead
    already_imported: bool


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class RequestValidationDetail(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class RequestValidationResponse(BaseModel):
    detail: list[RequestValidationDetail]

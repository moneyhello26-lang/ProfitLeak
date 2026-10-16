from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile
from sqlalchemy import select

from app.api.dependencies import Database, require_business
from app.models import Business, BusinessMembership, ImportBatch
from app.schemas.imports import (
    BusinessCreate,
    BusinessRead,
    ErrorResponse,
    ImportConfirmation,
    ImportKind,
    ImportPreview,
    ImportRead,
    RequestValidationResponse,
)
from app.services.import_parser import MAX_UPLOAD_BYTES, parse_file
from app.services.import_store import confirm_import, find_existing
from app.services.import_tokens import issue_token, verify_token

router = APIRouter(prefix="/api/v1", tags=["Data import"])
ERRORS = {status: {"model": ErrorResponse} for status in (400, 404, 409, 413, 415)}
ERRORS[422] = {"model": ErrorResponse | RequestValidationResponse}


def read_upload(file: UploadFile, kind: ImportKind):
    try:
        data = file.file.read(MAX_UPLOAD_BYTES + 1)
        return parse_file(file.filename or "", data, kind)
    finally:
        file.file.close()


@router.post("/businesses", response_model=BusinessRead, status_code=201)
def create_business(payload: BusinessCreate, db: Database):
    business = Business(**payload.model_dump())
    db.add(business)
    db.flush()
    db.add(
        BusinessMembership(
            business_id=business.id, user_id=db.info["current_user"].id, role="owner"
        )
    )
    db.commit()
    db.refresh(business)
    return business


@router.get("/businesses", response_model=list[BusinessRead])
def list_businesses(
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return db.scalars(
        select(Business)
        .join(BusinessMembership)
        .where(BusinessMembership.user_id == db.info["current_user"].id)
        .order_by(Business.created_at, Business.id)
        .offset(offset)
        .limit(limit)
    ).all()


@router.post("/imports/preview", response_model=ImportPreview, responses=ERRORS)
def preview_import(
    db: Database,
    business_id: Annotated[UUID, Form()],
    kind: Annotated[ImportKind, Form()],
    file: Annotated[UploadFile, File()],
):
    require_business(db, business_id, ("owner", "analyst"))
    parsed = read_upload(file, kind)
    existing = None
    token = None
    expiry = None
    if not parsed.error_count and parsed.rows:
        existing = find_existing(db, business_id, kind, parsed)
        if existing is None:
            token, expires = issue_token(business_id, kind, parsed.file_sha256)
            expiry = datetime.fromtimestamp(expires, UTC)
    return ImportPreview(
        business_id=business_id,
        kind=kind,
        filename=parsed.filename,
        row_count=parsed.row_count,
        valid_row_count=len(parsed.rows),
        preview=parsed.rows[:20],
        errors=parsed.errors,
        errors_truncated=parsed.error_count > len(parsed.errors),
        can_confirm=token is not None,
        existing_import_id=existing.id if existing else None,
        preview_token=token,
        expires_at=expiry,
    )


@router.post("/imports/confirm", response_model=ImportConfirmation, responses=ERRORS)
def confirm(
    db: Database,
    business_id: Annotated[UUID, Form()],
    kind: Annotated[ImportKind, Form()],
    file: Annotated[UploadFile, File()],
    preview_token: Annotated[str, Form(max_length=2048)],
):
    require_business(db, business_id, ("owner", "analyst"))
    parsed = read_upload(file, kind)
    verify_token(preview_token, business_id, kind, parsed.file_sha256)
    batch, already_imported = confirm_import(db, business_id, kind, parsed)
    db.commit()
    db.refresh(batch)
    return ImportConfirmation(
        imported=ImportRead.model_validate(batch), already_imported=already_imported
    )


@router.get("/imports", response_model=list[ImportRead], responses={404: {"model": ErrorResponse}})
def list_imports(
    db: Database,
    business_id: UUID,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    require_business(db, business_id)
    return db.scalars(
        select(ImportBatch)
        .where(ImportBatch.business_id == business_id)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id)
        .offset(offset)
        .limit(limit)
    ).all()

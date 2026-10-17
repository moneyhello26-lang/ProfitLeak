from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Business, BusinessMembership, User
from app.services.auth import COOKIE_NAME, session_user
from app.services.import_parser import FileProblem

RawDatabase = Annotated[Session, Depends(get_db)]


def current_user(request: Request, db: RawDatabase) -> User:
    return session_user(db, request.cookies.get(COOKIE_NAME))


CurrentUser = Annotated[User, Depends(current_user)]


def authenticated_database(db: RawDatabase, user: CurrentUser) -> Session:
    db.info["current_user"] = user
    return db


Database = Annotated[Session, Depends(authenticated_database)]


def require_business(
    db: Session, business_id: UUID, roles: tuple[str, ...] | None = None, *, lock: bool = False
) -> Business:
    user = db.info.get("current_user")
    if user is None:
        raise FileProblem("authentication_required", "Войдите в аккаунт.", 401)
    statement = (
        select(Business)
        .join(BusinessMembership)
        .where(Business.id == business_id, BusinessMembership.user_id == user.id)
    )
    if lock:
        statement = statement.with_for_update(of=Business)
    business = db.scalar(statement)
    if business is None:
        raise FileProblem("business_not_found", "Бизнес не найден.", 404)
    if roles is not None:
        role = db.scalar(
            select(BusinessMembership.role).where(
                BusinessMembership.business_id == business_id,
                BusinessMembership.user_id == user.id,
            )
        )
        if role not in roles:
            raise FileProblem("role_forbidden", "Недостаточно прав для этого действия.", 403)
    return business

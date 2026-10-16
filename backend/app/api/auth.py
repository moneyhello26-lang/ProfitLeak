from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import delete, select

from app.api.dependencies import CurrentUser, Database, RawDatabase, require_business
from app.core.config import get_settings
from app.models import BusinessMembership, User, UserSession
from app.schemas.auth import (
    AddMemberRequest,
    AuthRead,
    ChangeRoleRequest,
    LoginRequest,
    MemberRead,
    PasswordRequest,
    RegisterRequest,
)
from app.schemas.imports import ErrorResponse
from app.services import auth
from app.services.import_parser import FileProblem

router = APIRouter(prefix="/api/v1", tags=["Accounts and roles"])
ERRORS = {code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 429)}


def set_cookie(response: Response, token: str):
    settings = get_settings()
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path=auth.COOKIE_PATH,
    )
    response.headers["Cache-Control"] = "no-store"


def remove_cookie(response: Response):
    response.delete_cookie(
        auth.COOKIE_NAME,
        path=auth.COOKIE_PATH,
        secure=get_settings().session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


def check_attempts(request: Request, email: str, action: str):
    auth.check_attempts(request.client.host if request.client else "unknown", email, action)


@router.post("/auth/register", response_model=AuthRead, status_code=201, responses=ERRORS)
def register(payload: RegisterRequest, request: Request, response: Response, db: RawDatabase):
    check_attempts(request, payload.email, "register")
    user = auth.register(db, payload)
    token = auth.new_session(db, user, get_settings())
    db.commit()
    set_cookie(response, token)
    return auth.account(db, user)


@router.post("/auth/login", response_model=AuthRead, responses=ERRORS)
def login(payload: LoginRequest, request: Request, response: Response, db: RawDatabase):
    check_attempts(request, payload.email, "login")
    user = db.scalar(select(User).where(User.email == payload.email))
    if not auth.verify_password(payload.password, user.password_hash if user else None):
        raise FileProblem("invalid_credentials", "Неверный email или пароль.", 401)
    # Rotate the current browser's previous session instead of retaining its token.
    old_token = request.cookies.get(auth.COOKIE_NAME)
    if old_token and old_token.isascii() and len(old_token) <= 128:
        db.execute(
            delete(UserSession).where(UserSession.token_hash == auth.token_digest(old_token))
        )
    token = auth.new_session(db, user, get_settings())
    db.commit()
    set_cookie(response, token)
    return auth.account(db, user)


@router.get("/auth/me", response_model=AuthRead, responses=ERRORS)
def me(db: Database, user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return auth.account(db, user)


@router.post("/auth/logout", status_code=204, responses=ERRORS)
def logout(db: Database, request: Request, response: Response):
    token = request.cookies.get(auth.COOKIE_NAME)
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == auth.token_digest(token)))
    db.commit()
    remove_cookie(response)


@router.post("/auth/password", status_code=204, responses=ERRORS)
def change_password(
    payload: PasswordRequest, db: Database, user: CurrentUser, request: Request, response: Response
):
    check_attempts(request, user.email, "password")
    if not auth.verify_password(payload.current_password, user.password_hash):
        raise FileProblem("invalid_password", "Текущий пароль неверен.", 400)
    user.password_hash = auth.hash_password(payload.new_password)
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    db.commit()
    remove_cookie(response)


@router.get("/businesses/{business_id}/members", response_model=list[MemberRead], responses=ERRORS)
def list_members(business_id: UUID, db: Database):
    require_business(db, business_id, ("owner",))
    return auth.members(db, business_id)


@router.post(
    "/businesses/{business_id}/members",
    response_model=MemberRead,
    status_code=201,
    responses=ERRORS,
)
def add_member(business_id: UUID, payload: AddMemberRequest, db: Database):
    require_business(db, business_id, ("owner",), lock=True)
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        raise FileProblem("user_not_found", "Сначала участнику нужно зарегистрироваться.", 404)
    if (
        db.scalar(
            select(BusinessMembership.id).where(
                BusinessMembership.business_id == business_id, BusinessMembership.user_id == user.id
            )
        )
        is not None
    ):
        raise FileProblem("member_exists", "Этот пользователь уже участник бизнеса.", 409)
    db.add(BusinessMembership(business_id=business_id, user_id=user.id, role=payload.role))
    db.commit()
    return MemberRead(
        user_id=user.id, email=user.email, full_name=user.full_name, role=payload.role
    )


@router.patch(
    "/businesses/{business_id}/members/{user_id}", response_model=MemberRead, responses=ERRORS
)
def change_role(business_id: UUID, user_id: UUID, payload: ChangeRoleRequest, db: Database):
    require_business(db, business_id, ("owner",), lock=True)
    membership = auth.member(db, business_id, user_id)
    auth.protect_last_owner(db, membership, payload.role)
    membership.role = payload.role
    db.commit()
    return next(item for item in auth.members(db, business_id) if item.user_id == user_id)


@router.delete("/businesses/{business_id}/members/{user_id}", status_code=204, responses=ERRORS)
def remove_member(business_id: UUID, user_id: UUID, db: Database):
    require_business(db, business_id, ("owner",), lock=True)
    membership = auth.member(db, business_id, user_id)
    auth.protect_last_owner(db, membership, None)
    db.delete(membership)
    db.commit()

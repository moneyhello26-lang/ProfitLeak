"""Password verification, opaque sessions and membership administration."""

import hashlib
import hmac
import secrets
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic
from uuid import UUID

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AccountBootstrap, Business, BusinessMembership, User, UserSession
from app.schemas.auth import AuthRead, MemberRead, MembershipRead, RegisterRequest, UserRead
from app.services.import_parser import FileProblem

COOKIE_NAME = "profitleak_session"
COOKIE_PATH = "/api/v1"
SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1
_attempts: OrderedDict[str, tuple[int, float]] = OrderedDict()
_attempt_lock = Lock()


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt),
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=256 * 1024 * 1024,
        dklen=32,
    ).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password: str, encoded: str | None) -> bool:
    # Unknown users execute the same expensive operation, with no account-specific error.
    if encoded is None:
        hash_password(password, "00" * 16)
        return False
    try:
        algorithm, salt, _ = encoded.split("$")
        if algorithm != "scrypt":
            return False
        return hmac.compare_digest(hash_password(password, salt), encoded)
    except (ValueError, TypeError):
        return False


def check_attempts(client_ip: str, email: str, action: str) -> None:
    """Bounded per-worker limits, suitable for the app's single-worker local launch."""
    now = monotonic()
    limits = [(f"ip:{action}:{client_ip}", 30, 600), (f"email:{action}:{email}", 10, 600)]
    with _attempt_lock:
        for key, limit, window in limits:
            count, started = _attempts.get(key, (0, now))
            if now - started >= window:
                count, started = 0, now
            if count >= limit:
                raise FileProblem(
                    "auth_rate_limited", "Слишком много попыток. Повторите через 10 минут.", 429
                )
        for key, _, window in limits:
            count, started = _attempts.get(key, (0, now))
            if now - started >= window:
                count, started = 0, now
            _attempts[key] = (count + 1, started)
            _attempts.move_to_end(key)
        while len(_attempts) > 10000:
            _attempts.popitem(last=False)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_session(db: Session, user: User, settings: Settings) -> str:
    now = datetime.now(UTC)
    db.execute(delete(UserSession).where(UserSession.expires_at <= now))
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=token_digest(token),
            expires_at=now + timedelta(hours=settings.session_ttl_hours),
        )
    )
    return token


def session_user(db: Session, token: str | None) -> User:
    if token is not None and 20 <= len(token) <= 128 and token.isascii():
        user = db.scalar(
            select(User)
            .join(UserSession, UserSession.user_id == User.id)
            .where(
                UserSession.token_hash == token_digest(token),
                UserSession.expires_at > datetime.now(UTC),
            )
        )
        if user is not None:
            return user
    raise FileProblem("authentication_required", "Войдите в аккаунт.", 401)


def register(db: Session, payload: RegisterRequest) -> User:
    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise FileProblem("email_registered", "Этот email уже зарегистрирован.", 409)
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
            # Conditional UPDATE locks the singleton on PostgreSQL; SQLite mutations use
            # BEGIN IMMEDIATE. Exactly one registration can adopt pre-account businesses.
            claimed = db.execute(
                update(AccountBootstrap)
                .where(AccountBootstrap.id == 1, AccountBootstrap.claimed_by.is_(None))
                .values(claimed_by=user.id)
            ).rowcount
            if claimed:
                unowned = db.scalars(
                    select(Business.id).where(
                        ~exists().where(BusinessMembership.business_id == Business.id)
                    )
                )
                db.add_all(
                    BusinessMembership(business_id=id_, user_id=user.id, role="owner")
                    for id_ in unowned
                )
            db.flush()
    except IntegrityError as error:
        raise FileProblem("email_registered", "Этот email уже зарегистрирован.", 409) from error
    return user


def account(db: Session, user: User) -> AuthRead:
    memberships = db.scalars(
        select(BusinessMembership)
        .where(BusinessMembership.user_id == user.id)
        .order_by(BusinessMembership.created_at, BusinessMembership.business_id)
    ).all()
    return AuthRead(
        user=UserRead.model_validate(user),
        memberships=[MembershipRead.model_validate(membership) for membership in memberships],
    )


def members(db: Session, business_id: UUID) -> list[MemberRead]:
    rows = db.execute(
        select(User, BusinessMembership.role)
        .join(BusinessMembership, BusinessMembership.user_id == User.id)
        .where(BusinessMembership.business_id == business_id)
        .order_by(User.email)
    )
    return [
        MemberRead(user_id=user.id, email=user.email, full_name=user.full_name, role=role)
        for user, role in rows
    ]


def member(db: Session, business_id: UUID, user_id: UUID) -> BusinessMembership:
    membership = db.scalar(
        select(BusinessMembership).where(
            BusinessMembership.business_id == business_id, BusinessMembership.user_id == user_id
        )
    )
    if membership is None:
        raise FileProblem("member_not_found", "Участник не найден.", 404)
    return membership


def protect_last_owner(db: Session, membership: BusinessMembership, new_role: str | None) -> None:
    if membership.role == "owner" and new_role != "owner":
        count = db.scalar(
            select(func.count())
            .select_from(BusinessMembership)
            .where(
                BusinessMembership.business_id == membership.business_id,
                BusinessMembership.role == "owner",
            )
        )
        if count <= 1:
            raise FileProblem(
                "last_owner", "Нельзя удалить или понизить последнего владельца бизнеса.", 409
            )

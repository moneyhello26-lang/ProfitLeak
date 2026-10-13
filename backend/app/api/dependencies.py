from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Business
from app.services.import_parser import FileProblem

Database = Annotated[Session, Depends(get_db)]


def require_business(db: Session, business_id: UUID) -> Business:
    business = db.get(Business, business_id)
    if business is None:
        raise FileProblem("business_not_found", "Бизнес не найден.", 404)
    return business

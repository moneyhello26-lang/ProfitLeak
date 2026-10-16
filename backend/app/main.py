from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.api.advisor import router as advisor_router
from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.imports import router as imports_router
from app.api.insights import router as insights_router
from app.api.planning import router as planning_router
from app.api.reports import router as reports_router
from app.core.config import get_settings
from app.core.csrf import OriginMiddleware
from app.core.i18n import LanguageMiddleware
from app.core.upload_limit import UploadLimitMiddleware
from app.db.session import get_db
from app.services.import_parser import FileProblem

app = FastAPI(title="ProfitLeak AI", version="0.1.0")
app.add_middleware(UploadLimitMiddleware)
app.add_middleware(OriginMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Accept-Language"],
)
app.add_middleware(LanguageMiddleware)
app.include_router(auth_router)
app.include_router(imports_router)
app.include_router(analytics_router)
app.include_router(planning_router)
app.include_router(insights_router)
app.include_router(advisor_router)
app.include_router(reports_router)


@app.exception_handler(FileProblem)
async def import_problem(request: Request, error: FileProblem):
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": {"code": error.code, "message": str(error)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_problem(request: Request, error: RequestValidationError):
    if not request.url.path.startswith("/api/v1/auth/"):
        return await request_validation_exception_handler(request, error)
    issues = []
    for issue in error.errors():
        # Pydantic's default `input` can contain the entire submitted password.
        # Keep only fixed validation bounds in ctx for translated field guidance.
        safe = {key: value for key, value in issue.items() if key not in {"input", "ctx"}}
        bounds = {
            key: value
            for key, value in issue.get("ctx", {}).items()
            if key in {"min_length", "max_length", "ge", "le", "gt", "lt"}
            and isinstance(value, (int, float))
        }
        if bounds:
            safe["ctx"] = bounds
        issues.append(safe)
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(issues)})


class HealthResponse(BaseModel):
    status: str
    database: str


@app.get("/api/v1/health", response_model=HealthResponse)
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="Database unavailable") from error
    return HealthResponse(status="ok", database="ok")

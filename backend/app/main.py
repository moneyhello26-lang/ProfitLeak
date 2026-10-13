from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.api.analytics import router as analytics_router
from app.api.imports import router as imports_router
from app.api.insights import router as insights_router
from app.core.config import get_settings
from app.core.upload_limit import UploadLimitMiddleware
from app.db.session import get_db
from app.services.import_parser import FileProblem

app = FastAPI(title="ProfitLeak AI", version="0.1.0")
app.add_middleware(UploadLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(imports_router)
app.include_router(analytics_router)
app.include_router(insights_router)


@app.exception_handler(FileProblem)
async def import_problem(request: Request, error: FileProblem):
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": {"code": error.code, "message": str(error)}},
    )


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

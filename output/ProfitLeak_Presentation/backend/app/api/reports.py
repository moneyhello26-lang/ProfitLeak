from uuid import UUID

from fastapi import APIRouter, Response

from app.api.analytics import SelectedPeriod
from app.api.dependencies import Database, require_business
from app.schemas.imports import ErrorResponse
from app.services.reports import export_pdf

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


@router.get(
    "/pdf",
    response_class=Response,
    responses={
        200: {
            "description": "Financial PDF report",
            "content": {
                "application/pdf": {
                    "schema": {
                        "type": "string",
                        "format": "binary",
                    }
                }
            },
        },
        **{code: {"model": ErrorResponse} for code in (400, 404)},
    },
)
def report(db: Database, business_id: UUID, period: SelectedPeriod):
    business = require_business(db, business_id)
    content = export_pdf(db, business, period)
    filename = f"profitleak_{period.date_from:%Y%m%d}_{period.date_to:%Y%m%d}.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )

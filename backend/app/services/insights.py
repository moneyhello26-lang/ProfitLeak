from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.models import AnalysisRun, Business, Expense, ImportBatch, Insight, Product, Sale
from app.schemas.analytics import Period
from app.schemas.insights import AnalysisRead, InsightRead, InsightsRead, Severity, SourceRow
from app.services.analytics import bounds, rounded
from app.services.detector import RULES_VERSION, ExpenseRecord, SaleRecord, detect
from app.services.import_parser import FileProblem


def source_imports(db: Session, business_id: UUID) -> list[str]:
    return sorted(
        str(value)
        for value in db.scalars(
            select(ImportBatch.id).where(
                ImportBatch.business_id == business_id, ImportBatch.status == "confirmed"
            )
        )
    )


def records(db: Session, business_id: UUID, period: Period):
    sales = []
    for sale, product, batch in db.execute(
        select(Sale, Product, ImportBatch)
        .join(Product, Sale.product_id == Product.id)
        .join(ImportBatch, Sale.import_id == ImportBatch.id)
        .where(*bounds(Sale, business_id, period))
    ):
        sales.append(
            SaleRecord(
                source=SourceRow(
                    record_id=sale.id,
                    import_id=batch.id,
                    filename=batch.filename,
                    source_row=sale.source_row,
                    date=sale.date,
                    record_type=sale.record_type,
                    amount=rounded(sale.quantity * sale.unit_price),
                ),
                product_id=product.id,
                name=product.name,
                quantity=sale.quantity,
                unit_price=sale.unit_price,
                unit_cost=sale.unit_cost,
            )
        )
    expenses = []
    for row, batch in db.execute(
        select(Expense, ImportBatch)
        .join(ImportBatch, Expense.import_id == ImportBatch.id)
        .where(*bounds(Expense, business_id, period))
    ):
        expenses.append(
            ExpenseRecord(
                source=SourceRow(
                    record_id=row.id,
                    import_id=batch.id,
                    filename=batch.filename,
                    source_row=row.source_row,
                    date=row.date,
                    record_type=row.record_type,
                    amount=row.amount,
                ),
                category=row.category,
                description=row.description,
            )
        )
    return sales, expenses


def read_analysis(db: Session, run: AnalysisRun) -> AnalysisRead:
    result = {key: value for key, value in run.result_json.items() if key != "source_imports"}
    return AnalysisRead(
        id=run.id,
        business_id=run.business_id,
        period=Period(date_from=run.period_start, date_to=run.period_end),
        analyzed_at=run.analyzed_at,
        stale=run.result_json["source_imports"] != source_imports(db, run.business_id),
        **result,
    )


def run_analysis(db: Session, business_id: UUID, period: Period) -> AnalysisRead:
    # PostgreSQL locks the business row; SQLite HTTP writes use BEGIN IMMEDIATE.
    db.scalar(select(Business).where(Business.id == business_id).with_for_update())
    sales, expenses = records(db, business_id, period)
    result = detect(period, sales, expenses)
    imports = source_imports(db, business_id)
    now = datetime.now(timezone.utc)
    run = db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.business_id == business_id,
            AnalysisRun.period_start == period.date_from,
            AnalysisRun.period_end == period.date_to,
        )
    )
    if run is None:
        run = AnalysisRun(
            business_id=business_id, period_start=period.date_from, period_end=period.date_to
        )
        db.add(run)
    run.analyzed_at = now
    run.result_json = {
        "current_period": result.current.model_dump(mode="json") if result.current else None,
        "baseline_period": result.baseline.model_dump(mode="json") if result.baseline else None,
        "rules_version": RULES_VERSION,
        "insight_count": len(result.signals),
        "checks": [check.model_dump(mode="json") for check in result.checks],
        "source_imports": imports,
    }
    db.execute(
        delete(Insight).where(
            Insight.business_id == business_id,
            Insight.period_start == period.date_from,
            Insight.period_end == period.date_to,
        )
    )
    for signal in result.signals:
        identity = f"profitleak/{business_id}/{period.date_from}/{period.date_to}/"
        identity += signal.type + "/" + signal.key
        # NUMERIC(18,2) limits a stored scenario. No estimate is better than overflow/rounding.
        savings = signal.savings
        if savings is not None and savings >= 10**16:
            savings = None
        db.add(
            Insight(
                id=uuid5(NAMESPACE_URL, identity),
                business_id=business_id,
                type=signal.type,
                severity=signal.severity,
                confidence=signal.confidence,
                period_start=period.date_from,
                period_end=period.date_to,
                evidence_json=signal.evidence.model_dump(mode="json"),
                estimated_savings=savings,
                estimate_type="scenario" if savings is not None else None,
                recommendation=signal.recommendation,
                created_at=now,
            )
        )
    db.flush()
    return read_analysis(db, run)


def read_insight(insight: Insight) -> InsightRead:
    return InsightRead(
        id=insight.id,
        business_id=insight.business_id,
        type=insight.type,
        severity=insight.severity,
        confidence=insight.confidence,
        period=Period(date_from=insight.period_start, date_to=insight.period_end),
        evidence=insight.evidence_json,
        potential_savings_kzt=insight.estimated_savings,
        estimate_type=insight.estimate_type,
        recommendation=insight.recommendation,
        created_at=insight.created_at,
    )


def list_insights(
    db: Session,
    business_id: UUID,
    period: Period,
    severity: Severity | None,
    insight_type: str | None,
    limit: int,
    offset: int,
) -> InsightsRead:
    run = db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.business_id == business_id,
            AnalysisRun.period_start == period.date_from,
            AnalysisRun.period_end == period.date_to,
        )
    )
    filters = [
        Insight.business_id == business_id,
        Insight.period_start == period.date_from,
        Insight.period_end == period.date_to,
    ]
    if severity:
        filters.append(Insight.severity == severity)
    if insight_type:
        filters.append(Insight.type == insight_type)
    total = db.scalar(select(func.count()).select_from(Insight).where(*filters))
    priority = case((Insight.severity == "high", 0), (Insight.severity == "medium", 1), else_=2)
    items = db.scalars(
        select(Insight)
        .where(*filters)
        .order_by(priority, Insight.type, Insight.id)
        .limit(limit)
        .offset(offset)
    )
    return InsightsRead(
        business_id=business_id,
        period=period,
        analysis=read_analysis(db, run) if run else None,
        items=[read_insight(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


def insight_detail(db: Session, business_id: UUID, insight_id: UUID) -> InsightRead:
    item = db.scalar(
        select(Insight).where(
            Insight.id == insight_id,
            Insight.business_id == business_id,
        )
    )
    if item is None:
        raise FileProblem("insight_not_found", "Сигнал не найден для выбранного бизнеса.", 404)
    return read_insight(item)

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.statements import insert
from app.models import Expense, ImportBatch, Product, Sale
from app.schemas.imports import ImportKind
from app.services.import_parser import FileProblem, ParsedFile


def find_existing(db: Session, business_id: UUID, kind: ImportKind, parsed: ParsedFile):
    return db.scalar(
        select(ImportBatch).where(
            ImportBatch.business_id == business_id,
            ImportBatch.kind == kind,
            or_(
                ImportBatch.file_sha256 == parsed.file_sha256,
                ImportBatch.content_sha256 == parsed.content_sha256,
            ),
        )
    )


def confirm_import(db: Session, business_id: UUID, kind: ImportKind, parsed: ParsedFile):
    if parsed.error_count or not parsed.rows:
        raise FileProblem("invalid_rows", "Исправьте ошибки и проверьте файл снова.", 422)
    with db.begin_nested():
        # The uniqueness constraints also guard simultaneous confirmations across workers.
        batch_id = db.scalar(
            insert(db, ImportBatch)
            .values(
                business_id=business_id,
                kind=kind,
                filename=parsed.filename,
                file_sha256=parsed.file_sha256,
                content_sha256=parsed.content_sha256,
                status="processing",
                row_count=len(parsed.rows),
            )
            .on_conflict_do_nothing()
            .returning(ImportBatch.id)
        )
        if batch_id is None:
            existing = find_existing(db, business_id, kind, parsed)
            if existing is None or existing.status != "confirmed":
                raise FileProblem(
                    "import_conflict", "Импорт уже выполняется или требует проверки.", 409
                )
            return existing, True
        batch = db.get(ImportBatch, batch_id)
        product_values = {}
        if kind in ("sales", "products"):
            for row in parsed.rows:
                record = row.data
                value = {
                    "business_id": business_id,
                    "external_id": record.product_id,
                    "name": record.product_name if kind == "sales" else record.name,
                }
                if kind == "products":
                    value["category"] = record.category
                product_values[record.product_id] = value
            values = list(product_values.values())
            for start in range(0, len(values), 500):
                statement = insert(db, Product).values(values[start : start + 500])
                if kind == "products":
                    statement = statement.on_conflict_do_update(
                        index_elements=[Product.business_id, Product.external_id],
                        set_={
                            "name": statement.excluded.name,
                            "category": statement.excluded.category,
                        },
                    )
                else:
                    statement = statement.on_conflict_do_nothing(
                        index_elements=[Product.business_id, Product.external_id]
                    )
                db.execute(statement)
        if kind == "sales":
            products = dict(
                db.execute(
                    select(Product.external_id, Product.id).where(
                        Product.business_id == business_id,
                        Product.external_id.in_(list(product_values)),
                    )
                ).all()
            )
            values = []
            for row in parsed.rows:
                record = row.data.model_dump(exclude={"product_id", "product_name"})
                record.update(
                    business_id=business_id,
                    import_id=batch_id,
                    source_row=row.source_row,
                    product_id=products[row.data.product_id],
                )
                values.append(record)
            db.execute(insert(db, Sale), values)
        elif kind == "expenses":
            values = [
                dict(
                    row.data.model_dump(),
                    business_id=business_id,
                    import_id=batch_id,
                    source_row=row.source_row,
                )
                for row in parsed.rows
            ]
            db.execute(insert(db, Expense), values)
        batch.status = "confirmed"
        batch.confirmed_at = datetime.now(UTC)
        db.flush()
        return batch, False
